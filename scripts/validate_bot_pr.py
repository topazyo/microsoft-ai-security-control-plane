#!/usr/bin/env python3
"""Deterministic validators for automated matrix changes.

Every rule this repository states in prose is enforced here as a mechanical
check. Prompt instructions are advisory; a set-membership test in CI is not.

Checks
------
1. path allowlist        — an automated change may only touch permitted files,
                           which mechanically prevents drift into the README's
                           out-of-scope list (KQL/detections, DevSecOps, vendor
                           comparisons).
2. status labels         — every matrix Status cell uses one of the four legend
                           labels, exactly.
3. source domains        — every primary-source URL is Microsoft Learn, the
                           public Microsoft 365 Roadmap, or GitHub Docs. This is
                           the "never a launch blog" rule, executed.
4. last-verified dates   — every matrix row carries an ISO last-verified date.
5. citation containment  — when an evidence bundle is supplied, every URL cited
                           by the adjudicator is one the watcher actually
                           fetched, or one registered as a human-only source.
                           This is the anti-fabrication control.
6. confidentiality       — no GUIDs, emails, IPs or tenant-shaped identifiers.
7. escalation direction  — a row may never be moved *out* of "Requires further
                           validation" by automation; that transition requires
                           in-tenant confirmation by a human.

Exit code 0 = all checks pass. Non-zero = at least one violation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MATRIX = REPO_ROOT / "matrix" / "capability-status-matrix.md"

LEGEND_LABELS = {
    "GA",
    "Public Preview",
    "Roadmap",
    "Requires further validation",
}

# Paths an automated run is permitted to modify.
PATH_ALLOWLIST = [
    re.compile(r"^matrix/.*\.md$"),
    re.compile(r"^crosswalk/.*\.md$"),
    re.compile(r"^checklists/.*\.md$"),
    re.compile(r"^CHANGELOG\.md$"),
    re.compile(r"^\.github/watch-state/.*\.json$"),
]

ALLOWED_SOURCE_HOSTS = [
    re.compile(r"^https://learn\.microsoft\.com/", re.IGNORECASE),
    re.compile(r"^https://(www\.)?microsoft\.com/[^ )]*microsoft-365/roadmap", re.IGNORECASE),
    # GitHub Docs is the first-party documentation site for a Microsoft-owned
    # product, so it is the same *class* of source as Microsoft Learn — not a
    # relaxation toward blogs. It is admitted on one condition, enforced by
    # convention in sources.json rather than here: a docs.github.com source is
    # registered under `human_only_sources`, never under `sources`, so the
    # watcher never fetches it and no GitHub page content ever reaches the
    # adjudicator. See docs/agent-cadence.md.
    re.compile(r"^https://docs\.github\.com/", re.IGNORECASE),
]

URL_PATTERN = re.compile(r"https?://[^\s)\]<>\"']+")

CONFIDENTIALITY_PATTERNS = [
    ("GUID", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)),
    ("email address", re.compile(r"\b[\w.+-]+@(?!example\.)[\w-]+\.[A-Za-z]{2,}\b")),
    ("IPv4 address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("onmicrosoft.com tenant", re.compile(r"\b[\w-]+\.onmicrosoft\.com\b", re.IGNORECASE)),
]

# Out-of-scope content markers per the README's out-of-scope list.
OUT_OF_SCOPE_PATTERNS = [
    ("KQL/detection content", re.compile(r"```\s*(kql|kusto)\b", re.IGNORECASE)),
    ("KQL/detection content", re.compile(r"^\s*(SecurityAlert|CloudAppEvents|OfficeActivity)\s*\|", re.MULTILINE)),
]


class Findings:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.notes: list[str] = []

    def error(self, check: str, message: str) -> None:
        self.errors.append(f"[FAIL] {check}: {message}")

    def note(self, message: str) -> None:
        self.notes.append(f"[ok]   {message}")


def changed_files(base_ref: str | None) -> list[str]:
    if not base_ref:
        return []
    try:
        output = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError) as exc:
        raise SystemExit(f"could not compute changed files against {base_ref}: {exc}")
    return [line.strip() for line in output.splitlines() if line.strip()]


def matrix_table_rows(text: str) -> list[list[str]]:
    """Return the cells of each data row of the main capability table."""
    rows: list[list[str]] = []
    lines = text.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        if line.strip().startswith("|") and "Capability" in line and "Status" in line and "Last verified" in line:
            header_index = index
            break
    if header_index is None:
        return rows
    for line in lines[header_index + 2 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        rows.append([c.strip() for c in stripped.strip("|").split("|")])
    return rows


def column_indexes(text: str) -> dict[str, int]:
    for line in text.splitlines():
        if line.strip().startswith("|") and "Capability" in line and "Status" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            return {name: position for position, name in enumerate(cells)}
    return {}


def normalise_label(cell: str) -> list[str]:
    """Extract the legend labels asserted in a Status cell.

    Status cells may legitimately carry qualifying prose, e.g.
    "**GA** (Roadmap 548671 status "Launched")". Only bolded label tokens are
    treated as asserted labels.
    """
    return [re.sub(r"\s+", " ", m).strip() for m in re.findall(r"\*\*([^*]+)\*\*", cell)]


def check_paths(files: list[str], findings: Findings, bot: bool) -> None:
    """The path allowlist constrains *automated* changes only.

    A human maintainer may legitimately touch workflows, scripts or docs; an
    automated run may not. Applying this rule to human pull requests would block
    ordinary maintenance, so outside --bot mode it is reported, not enforced.
    """
    if not files:
        findings.note("path allowlist: no changed files to check")
        return
    outside = [p for p in files if not any(pattern.match(p) for pattern in PATH_ALLOWLIST)]
    if not outside:
        findings.note(f"path allowlist: all {len(files)} changed file(s) within the automated-change allowlist")
        return
    for path in outside:
        if bot:
            findings.error("path allowlist", f"'{path}' is outside the paths an automated change may modify")
        else:
            findings.note(f"path allowlist: '{path}' is outside the automated-change allowlist (human change - not enforced)")


def check_matrix(findings: Findings) -> None:
    if not MATRIX.exists():
        findings.error("matrix", f"{MATRIX} not found")
        return
    text = MATRIX.read_text(encoding="utf-8")
    indexes = column_indexes(text)
    rows = matrix_table_rows(text)
    if not rows:
        findings.error("matrix", "could not locate the capability table")
        return

    status_index = indexes.get("Status")
    verified_index = indexes.get("Last verified")
    source_index = indexes.get("Primary source")

    label_failures = 0
    date_failures = 0
    domain_failures = 0

    for row in rows:
        identifier = row[0] if row else "?"

        if status_index is not None and len(row) > status_index:
            labels = normalise_label(row[status_index])
            asserted = [l for l in labels if l in LEGEND_LABELS]
            unknown = [l for l in labels if l not in LEGEND_LABELS and not l.startswith('"')]
            if not asserted:
                findings.error("status label", f"row {identifier}: no legend label found in Status cell")
                label_failures += 1
            for label in unknown:
                if re.match(r"^[A-Z]", label) and label not in {"Launched", "Preview", "Not GA"}:
                    findings.error(
                        "status label",
                        f"row {identifier}: '{label}' is bolded in the Status cell but is not one of the four legend labels",
                    )
                    label_failures += 1

        if verified_index is not None and len(row) > verified_index:
            if not re.search(r"\b20\d{2}-\d{2}-\d{2}\b", row[verified_index]):
                findings.error("last-verified date", f"row {identifier}: no ISO date in 'Last verified'")
                date_failures += 1

        if source_index is not None and len(row) > source_index:
            urls = URL_PATTERN.findall(row[source_index])
            if not urls:
                findings.error("primary source", f"row {identifier}: no primary-source URL")
                domain_failures += 1
            for url in urls:
                if not any(pattern.match(url) for pattern in ALLOWED_SOURCE_HOSTS):
                    findings.error(
                        "source domain",
                        f"row {identifier}: '{url}' is not Microsoft Learn, the public "
                        "Microsoft 365 Roadmap, or GitHub Docs",
                    )
                    domain_failures += 1

    if not label_failures:
        findings.note(f"status labels: all {len(rows)} row(s) use legend labels only")
    if not date_failures:
        findings.note(f"last-verified dates: all {len(rows)} row(s) carry an ISO date")
    if not domain_failures:
        findings.note(f"source domains: all {len(rows)} row(s) cite Learn, the public Roadmap or GitHub Docs")


def citable_urls(entries: list[dict]) -> set[str]:
    """Citable URL for each registry entry that declares one.

    `entry.get("cite_url") or entry["url"]`, never `entry.get("cite_url",
    entry["url"])`: Python evaluates a `dict.get` default *eagerly*, so the
    second form raises KeyError on an entry that has `cite_url` but no `url` —
    which is exactly the shape of a human-only source, since a source that is
    never fetched has no fetch URL. That crashes the validator with a traceback
    instead of failing a check.
    """
    return {
        entry.get("cite_url") or entry["url"]
        for entry in entries
        if entry.get("cite_url") or entry.get("url")
    }


def check_citation_containment(evidence_path: Path | None, findings: Findings) -> None:
    """Every primary-source URL in the matrix must be one the watcher fetches.

    With an evidence bundle, the constraint is what was fetched in *this run*.
    Without one, it falls back to the pinned source registry, so the check still
    runs on human pull requests: a citation nothing watches is a citation that
    will silently go stale.

    Human-only sources are the deliberate exception, and the two sets are kept
    apart on purpose. A human-only source is never fetched, so it can never
    appear in `allowed_citation_urls` — the set the adjudicator is told is the
    complete list of URLs it may cite. Merging the two would let an automated run
    cite a page no watcher ever read, which is precisely what this check exists
    to prevent. So the bundle carries them under a separate key, and only this
    validator unions them: containment recognises a human-maintained citation,
    while the adjudicator's citable set stays strictly fetch-backed.
    """
    if evidence_path is not None and evidence_path.exists():
        bundle = json.loads(evidence_path.read_text(encoding="utf-8"))
        allowed = set(bundle.get("allowed_citation_urls") or [])
        allowed |= set(bundle.get("human_only_citation_urls") or [])
        origin = f"evidence bundle {evidence_path.name}"
    elif evidence_path is not None:
        findings.error("citation containment", f"evidence bundle {evidence_path} not found")
        return
    else:
        registry_path = REPO_ROOT / ".github" / "watch-state" / "sources.json"
        if not registry_path.exists():
            findings.error("citation containment", "no evidence bundle and no source registry to check against")
            return
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        allowed = citable_urls(registry.get("sources", []))
        allowed |= citable_urls(registry.get("human_only_sources", []))
        origin = "pinned source registry"

    if not allowed:
        findings.error("citation containment", f"{origin} lists no allowed citation URLs")
        return

    text = MATRIX.read_text(encoding="utf-8")
    cited = {u.rstrip(".,;") for u in URL_PATTERN.findall(text)}
    # Only primary-source citations are constrained; internal anchors and
    # framework links elsewhere in the document are not primary sources.
    primary = {u for u in cited if any(p.match(u) for p in ALLOWED_SOURCE_HOSTS)}
    unbacked = {u for u in primary if u not in allowed}
    if unbacked:
        for url in sorted(unbacked):
            findings.error(
                "citation containment",
                f"'{url}' is cited in the matrix but was not fetched by the watcher — "
                "the adjudicator may only cite sources present in the evidence bundle",
            )
    else:
        findings.note(
            f"citation containment: all {len(primary)} primary-source citation(s) backed by the {origin}"
        )


def check_confidentiality(files: list[str], findings: Findings) -> None:
    targets = [REPO_ROOT / f for f in files] if files else [
        REPO_ROOT / "matrix" / "capability-status-matrix.md",
        REPO_ROOT / "crosswalk" / "framework-crosswalk.md",
        REPO_ROOT / "checklists" / "capability-status-verification.md",
        REPO_ROOT / "CHANGELOG.md",
    ]
    hits = 0
    for path in targets:
        if not path.exists() or path.suffix not in {".md", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        for name, pattern in CONFIDENTIALITY_PATTERNS:
            for match in pattern.findall(text):
                value = match if isinstance(match, str) else match[0]
                # Version strings such as 1.1.0 are not IPv4 addresses.
                if name == "IPv4 address" and not re.match(r"^(\d{1,3}\.){3}\d{1,3}$", value):
                    continue
                findings.error("confidentiality", f"{path.relative_to(REPO_ROOT)}: possible {name} '{value}'")
                hits += 1
        for name, pattern in OUT_OF_SCOPE_PATTERNS:
            if pattern.search(text):
                findings.error("scope", f"{path.relative_to(REPO_ROOT)}: contains {name}, which is out of scope")
                hits += 1
    if not hits:
        findings.note("confidentiality and scope: no tenant-shaped identifiers or out-of-scope content found")


def check_escalation_direction(base_ref: str | None, findings: Findings, bot: bool) -> None:
    """A row may never be moved *out* of 'Requires further validation' automatically.

    A human who has completed the in-tenant verification may make exactly this
    change, so outside --bot mode the transition is reported for reviewer
    attention rather than blocked.
    """
    if not base_ref:
        findings.note("escalation direction: skipped (no base ref supplied)")
        return
    try:
        before = subprocess.run(
            ["git", "show", f"{base_ref}:matrix/capability-status-matrix.md"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        findings.note("escalation direction: skipped (matrix not present at base ref)")
        return

    def labels_by_row(text: str) -> dict[str, list[str]]:
        indexes = column_indexes(text)
        status_index = indexes.get("Status")
        result: dict[str, list[str]] = {}
        if status_index is None:
            return result
        for row in matrix_table_rows(text):
            if len(row) > status_index:
                result[row[0]] = normalise_label(row[status_index])
        return result

    old = labels_by_row(before)
    new = labels_by_row(MATRIX.read_text(encoding="utf-8"))
    violations = 0
    for row_id, old_labels in old.items():
        if "Requires further validation" in old_labels:
            new_labels = new.get(row_id, [])
            if new_labels and "Requires further validation" not in new_labels:
                message = (
                    f"row {row_id} was moved out of 'Requires further validation' to {new_labels}. "
                    "Leaving that state requires in-tenant confirmation by a human "
                    "(docs/how-to-read-status.md)."
                )
                if bot:
                    findings.error("escalation direction", message + " An automated run may never make this change.")
                else:
                    findings.note(
                        "escalation direction: " + message
                        + " Reviewer must confirm the in-tenant verification was actually performed."
                    )
                violations += 1
    if not violations:
        findings.note("escalation direction: no row moved out of 'Requires further validation'")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic validators for automated matrix changes.")
    parser.add_argument("--base-ref", default=None, help="Base git ref to diff against (e.g. origin/main).")
    parser.add_argument("--evidence", type=Path, default=None, help="Path to the watcher's evidence bundle.")
    parser.add_argument(
        "--bot",
        action="store_true",
        help="Treat the change as automated: enforce the path allowlist and the "
        "'never leave Requires further validation' rule as hard failures.",
    )
    args = parser.parse_args()

    findings = Findings()
    files = changed_files(args.base_ref)

    check_paths(files, findings, args.bot)
    check_matrix(findings)
    check_citation_containment(args.evidence, findings)
    check_confidentiality(files, findings)
    check_escalation_direction(args.base_ref, findings, args.bot)

    for note in findings.notes:
        print(note)
    for error in findings.errors:
        print(error)

    if findings.errors:
        print(f"\n{len(findings.errors)} validation failure(s).")
        return 1
    print("\nAll validations passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
