#!/usr/bin/env python3
"""Tier D4 — deterministic staleness guard.

Implements the rule the README already commits to: "Any row older than the
monthly window is treated as stale." Before this script existed the rule was
stated but never enforced, which is how the cross-walk and the checklist came to
sit 35 days unrefreshed with nothing to flag them.

Reads the last-verified dates recorded in the content files and reports every
one older than the staleness window. Writes no content file and makes no
judgement about status.

Forbidden actions:
  - Never edits matrix/, crosswalk/, checklists/, docs/ or CHANGELOG.md.
  - Never fetches a source (that is tier D1's job).
  - Never assigns or changes a status label.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = REPO_ROOT / ".github" / "watch-state" / "sources.json"

ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")

# Where structured last-verified dates live. Each entry names the file and how
# to pull the dates out of it.
TARGETS = [
    {
        "path": "matrix/capability-status-matrix.md",
        "label": "matrix row",
        "kind": "table",
        "column": "Last verified",
    },
    {
        "path": "crosswalk/framework-crosswalk.md",
        "label": "cross-walk framework row",
        "kind": "table",
        "column": "Last verified",
    },
    {
        "path": "checklists/capability-status-verification.md",
        "label": "checklist footer stamp",
        "kind": "footer",
        "pattern": r"Last validated:\s*(20\d{2}-\d{2}-\d{2})",
    },
]


def parse_table_dates(text: str, column: str) -> list[tuple[str, str]]:
    """Return (row_identifier, iso_date) for each markdown table row carrying the column."""
    rows: list[tuple[str, str]] = []
    lines = text.splitlines()
    header_index = None
    column_index = None

    for index, line in enumerate(lines):
        if line.strip().startswith("|") and column.lower() in line.lower():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            for position, cell in enumerate(cells):
                if cell.lower().replace("*", "") == column.lower():
                    header_index = index
                    column_index = position
                    break
        if header_index is not None:
            break

    if header_index is None or column_index is None:
        return rows

    for line in lines[header_index + 2 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if stripped == "":
                continue
            break
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) <= column_index:
            continue
        match = ISO_DATE.search(cells[column_index])
        if match:
            identifier = cells[0] if cells[0] else "?"
            rows.append((identifier, match.group(1)))
    return rows


def parse_footer_date(text: str, pattern: str) -> list[tuple[str, str]]:
    match = re.search(pattern, text)
    return [("footer", match.group(1))] if match else []


def watched_matrix_rows(registry: dict) -> set[int]:
    """Matrix rows claimed by at least one entry a workflow may fetch.

    The same derivation as `claimed_rows(registry["sources"])` in
    scripts/validate_bot_pr.py, which tests/test_stale_guard.py pins. Human-only
    rows are excluded on purpose: a human re-read of row 12 or 13 says nothing
    about whether the month's consolidation ran.
    """
    return {
        row
        for entry in registry.get("sources", [])
        for row in entry.get("matrix_rows", [])
        if isinstance(row, int)
    }


def consolidation_status(matrix_text: str, registry: dict, today: date) -> tuple[bool, list[str]]:
    """Has this calendar month's consolidation (tier D3) already been recorded?

    Yes only when every matrix row backed by a watched source carries a
    last-verified date in `today`'s calendar month. That is what a consolidation
    leaves behind: it re-stamps every row whose sources it fetched. The monthly
    run used to ask a human for the consolidation even when that month's refresh
    had already merged (issue #55), because its only gate was a missing API key.

    Every doubt resolves to "not consolidated", because the cost of a wrong
    "not consolidated" is one issue a human closes, and the cost of a wrong
    "consolidated" is a month's obligation silently skipped:

      - no watched rows at all (a registry that claims nothing would otherwise
        pass vacuously);
      - an unreadable matrix table;
      - a row identifier that is not an integer;
      - a watched row missing from the matrix;
      - any watched row dated in another month, including a row whose source
        could not be fetched and so legitimately kept its old date.

    Returns (consolidated, reasons). `reasons` names every row that blocks the
    answer, and is empty only when the answer is yes.
    """
    month = today.strftime("%Y-%m")
    watched = watched_matrix_rows(registry)
    if not watched:
        return False, ["the registry claims no matrix row through a watched source"]

    entries = parse_table_dates(matrix_text, "Last verified")
    if not entries:
        return False, ["no last-verified date could be read from the matrix table"]

    dated: dict[int, str] = {}
    reasons: list[str] = []
    for identifier, iso in entries:
        if not identifier.isdigit():
            reasons.append(f"matrix row identifier {identifier!r} is not an integer")
            continue
        dated[int(identifier)] = iso

    for row in sorted(watched):
        iso = dated.get(row)
        if iso is None:
            reasons.append(f"matrix row {row}: claimed by a watched source but has no readable date")
        elif not iso.startswith(month):
            reasons.append(f"matrix row {row}: last verified {iso}, not in {month}")
    return not reasons, reasons


def emit_github_output(**values) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            if "\n" in str(value):
                handle.write(f"{key}<<__EOF__\n{value}\n__EOF__\n")
            else:
                handle.write(f"{key}={value}\n")


def use_utf8_streams() -> None:
    """Print repository text without depending on the console's code page.

    A Windows console defaults to a legacy code page, and the identifiers this
    guard echoes come verbatim from tracked files. An em dash survives cp1252;
    an arrow (U+2192) does not. CI runs UTF-8, so this failure mode is invisible
    there and hits only the local runs -- which is where tiers D2 and D3 are
    currently operated. See scripts/changelog_entry.py, where it was found.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def run_consolidation_check(today_arg: str | None) -> int:
    """`--consolidation-check`: emit `consolidated=true|false` and a report.

    Today is the UTC date, matching the `date -u` month the monthly workflow
    writes into its issue title. An unreadable registry or matrix exits 1 and
    so turns the run red. Neither input can legitimately be unreadable, and a
    red run is the loud signal that makes someone look. The `consolidated`
    output is still written as `false` first, so a caller that does read it
    leans towards filing the issue.
    """
    today = (
        datetime.strptime(today_arg, "%Y-%m-%d").date()
        if today_arg
        else datetime.now(timezone.utc).date()
    )
    month = today.strftime("%Y-%m")
    matrix_path = REPO_ROOT / "matrix" / "capability-status-matrix.md"
    try:
        registry = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        matrix_text = matrix_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        report = f"Cannot decide whether the {month} consolidation is recorded: {exc}"
        print(report)
        emit_github_output(consolidated="false", report=report)
        return 1

    consolidated, reasons = consolidation_status(matrix_text, registry, today)
    watched = sorted(watched_matrix_rows(registry))
    if consolidated:
        report = (
            f"The {month} consolidation is recorded: all {len(watched)} matrix row(s) backed by a "
            f"watched source carry a last-verified date in {month} (rows {', '.join(map(str, watched))})."
        )
    else:
        lines = [f"The {month} consolidation is NOT recorded yet:", ""]
        lines.extend(f"- {reason}" for reason in reasons)
        report = "\n".join(lines)
    print(report)
    emit_github_output(consolidated=str(consolidated).lower(), report=report)
    return 0


def main() -> int:
    use_utf8_streams()
    parser = argparse.ArgumentParser(description="Staleness guard (tier D4).")
    parser.add_argument("--today", default=None, help="Override today's date (YYYY-MM-DD), for testing.")
    parser.add_argument("--window-days", type=int, default=None, help="Override the staleness window.")
    parser.add_argument("--fail-on-stale", action="store_true", help="Exit non-zero when anything is stale.")
    parser.add_argument(
        "--consolidation-check",
        action="store_true",
        help="Report whether this calendar month's consolidation is already recorded, instead of staleness.",
    )
    args = parser.parse_args()

    if args.consolidation_check:
        return run_consolidation_check(args.today)

    window = args.window_days
    if window is None:
        try:
            window = json.loads(SOURCES_FILE.read_text(encoding="utf-8")).get("staleness_window_days", 30)
        except (OSError, json.JSONDecodeError):
            window = 30

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()

    stale: list[dict] = []
    fresh_count = 0
    unparsed: list[str] = []

    for target in TARGETS:
        path = REPO_ROOT / target["path"]
        if not path.exists():
            unparsed.append(f"{target['path']} (missing)")
            continue
        text = path.read_text(encoding="utf-8")
        if target["kind"] == "table":
            entries = parse_table_dates(text, target["column"])
        else:
            entries = parse_footer_date(text, target["pattern"])

        if not entries:
            # Do not silently pass: an unparseable file is itself a finding.
            unparsed.append(target["path"])
            continue

        for identifier, iso in entries:
            age = (today - datetime.strptime(iso, "%Y-%m-%d").date()).days
            if age > window:
                stale.append(
                    {
                        "file": target["path"],
                        "label": target["label"],
                        "id": identifier,
                        "last_verified": iso,
                        "age_days": age,
                    }
                )
            else:
                fresh_count += 1

    lines: list[str] = []
    if stale:
        lines.append(f"{len(stale)} item(s) exceed the {window}-day staleness window (as of {today.isoformat()}):")
        lines.append("")
        for item in sorted(stale, key=lambda i: -i["age_days"]):
            lines.append(
                f"- `{item['file']}` - {item['label']} {item['id']}: "
                f"last verified {item['last_verified']} ({item['age_days']} days ago)"
            )
    else:
        lines.append(f"All {fresh_count} dated item(s) are within the {window}-day window (as of {today.isoformat()}).")

    if unparsed:
        lines.append("")
        lines.append("Could not read a last-verified date from:")
        for item in unparsed:
            lines.append(f"- `{item}`")

    report = "\n".join(lines)
    print(report)
    emit_github_output(stale=str(bool(stale or unparsed)).lower(), report=report, stale_count=str(len(stale)))

    if args.fail_on_stale and (stale or unparsed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
