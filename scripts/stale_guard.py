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
from datetime import date, datetime
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Staleness guard (tier D4).")
    parser.add_argument("--today", default=None, help="Override today's date (YYYY-MM-DD), for testing.")
    parser.add_argument("--window-days", type=int, default=None, help="Override the staleness window.")
    parser.add_argument("--fail-on-stale", action="store_true", help="Exit non-zero when anything is stale.")
    args = parser.parse_args()

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
