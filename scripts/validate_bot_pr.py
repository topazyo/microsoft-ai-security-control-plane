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
8. source coverage       — every matrix row is claimed by at least one registry
                           entry, watched or human-only. Without this a new row
                           can ship with no source of any kind, and the staleness
                           output cannot be read correctly: which rows no agent
                           run can ever advance stops being derivable.
9. documented counts     — the sizes docs/agent-cadence.md asserts in prose are
                           re-derived from the registry and the matrix. The doc
                           already carried an instruction to re-derive its own
                           count rather than trust the sentence; the instruction
                           worked and the number drifted anyway, twice. A count
                           in prose is a claim, and claims here are checked.

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
REGISTRY = REPO_ROOT / ".github" / "watch-state" / "sources.json"
CADENCE_DOC = REPO_ROOT / "docs" / "agent-cadence.md"
CROSSWALK = REPO_ROOT / "crosswalk" / "framework-crosswalk.md"

# A source that backs a cross-walk row names it as the framework's own name in
# the "Framework versions cited" table plus this suffix. That was a convention
# held in four registry entries and written down nowhere, so there was nothing
# for a claim to be wrong against. It is written once, here, and enforced.
CROSSWALK_ROW_SUFFIX = " framework-versions row"

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
        if bot:
            # In --bot mode the allowlist IS the gate, so an empty diff is not
            # "nothing to check" — it means the gate did not run. The bot
            # workflows diff `origin/<ref>...HEAD`, which sees committed work
            # only, so an adjudicator whose edits are still uncommitted would
            # otherwise clear the one check that confines it to its allowed
            # paths.
            findings.error(
                "path allowlist",
                "no changed file could be determined, so the allowlist did not run. An "
                "automated change must be committed before it is validated.",
            )
            return
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


def check_matrix(findings: Findings, text: str | None = None) -> None:
    """`text` is an injection seam for the tests.

    The fail-open this guards against is a matrix state the committed tree must
    never be in, so it cannot be exercised through the on-disk path — and
    writing a fixture file into the repository to test a validator is worse
    than passing the text in.
    """
    if text is None:
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

    # A renamed header cell used to disable three checks *and* print three
    # positive notes over zero rows examined. `matrix_table_rows` locates the
    # table by substring while `column_indexes` keys on the exact cell text, so
    # renaming "Last verified" to "Last verified (UTC)" still found all 13 data
    # rows and resolved no index — every check body was guarded out, every
    # failure counter stayed 0, and the run reported "all 13 row(s)" for each.
    # A check that could not run is an error; it is never a pass.
    missing = [
        name
        for name, index in (
            ("Status", status_index),
            ("Last verified", verified_index),
            ("Primary source", source_index),
        )
        if index is None
    ]
    for name in missing:
        findings.error(
            "matrix",
            f"header column '{name}' not found in the capability table, so the checks keyed "
            f"on it did not run. Header cells read {sorted(indexes)}; the keys are matched "
            "exactly, so a reworded column must be renamed here too.",
        )
    if missing:
        return

    label_failures = 0
    date_failures = 0
    domain_failures = 0
    label_checked = 0
    date_checked = 0
    domain_checked = 0

    for row in rows:
        identifier = row[0] if row else "?"

        if len(row) > status_index:
            label_checked += 1
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

        if len(row) > verified_index:
            date_checked += 1
            if not re.search(r"\b20\d{2}-\d{2}-\d{2}\b", row[verified_index]):
                findings.error("last-verified date", f"row {identifier}: no ISO date in 'Last verified'")
                date_failures += 1

        if len(row) > source_index:
            domain_checked += 1
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

    # Each note names the number of rows the check actually examined, not the
    # number of rows found. A row too short to reach a keyed column is a
    # malformed table row, and reporting it as an error rather than skipping it
    # is what stops "all N row(s)" from ever standing over an unexamined row.
    for name, checked in (
        ("Status", label_checked),
        ("Last verified", date_checked),
        ("Primary source", domain_checked),
    ):
        if checked != len(rows):
            findings.error(
                "matrix",
                f"only {checked} of {len(rows)} capability row(s) have a '{name}' cell to "
                "check; the rest are too short to reach that column.",
            )

    if not label_failures and label_checked == len(rows):
        findings.note(f"status labels: all {label_checked} row(s) use legend labels only")
    if not date_failures and date_checked == len(rows):
        findings.note(f"last-verified dates: all {date_checked} row(s) carry an ISO date")
    if not domain_failures and domain_checked == len(rows):
        findings.note(
            f"source domains: all {domain_checked} row(s) cite Learn, the public Roadmap or GitHub Docs"
        )


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


def matrix_row_ids(text: str) -> list[int]:
    """Numeric row identifiers from the capability table's first column."""
    ids: list[int] = []
    for row in matrix_table_rows(text):
        cell = re.sub(r"[^0-9]", "", row[0]) if row else ""
        if cell:
            ids.append(int(cell))
    return ids


def load_registry(findings: Findings) -> dict | None:
    if not REGISTRY.exists():
        findings.error("source coverage", f"{REGISTRY.name} not found")
        return None
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        findings.error("source coverage", f"{REGISTRY.name} is not valid JSON: {exc}")
        return None


def claimed_rows(entries: list[dict]) -> set[int]:
    return {row for entry in entries for row in entry.get("matrix_rows", []) if isinstance(row, int)}


def claimed_crosswalk_rows(entries: list[dict]) -> set[str]:
    return {row for entry in entries for row in entry.get("crosswalk_rows", []) if isinstance(row, str)}


def crosswalk_row_names(text: str) -> set[str]:
    """Valid `crosswalk_rows` values, derived from the cross-walk itself.

    The authoritative list is the first column of the "Framework versions
    cited" table -- the same column scripts/stale_guard.py reads as that
    table's row identifier, extracted with the same cell expression, so the
    two scripts name a cross-walk row the same way for every table this
    repository actually commits. They are not the same parser: stale_guard
    matches the header case-insensitively and skips blank lines inside the
    table (stale_guard.py:79-84), this one matches "Framework" and
    "Last verified" case-sensitively and stops at the first blank line. A
    lower-cased header, or a blank line inserted mid-table, would make them
    disagree -- which reds this gate rather than passing silently, and that is
    the intended direction.

    Markdown emphasis is deliberately not normalised: an emphasised name would
    also silently change stale_guard's identifier, so a red build is the right
    outcome rather than a divergence hidden by two strippers.

    An empty return is a parse failure, not "nothing to check", and the caller
    must treat it as an error -- the same rule matrix_row_ids follows.
    """
    lines = text.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and "Framework" in stripped and "Last verified" in stripped:
            header_index = index
            break
    if header_index is None:
        return set()
    names: set[str] = set()
    for line in lines[header_index + 2 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells and cells[0]:
            names.add(cells[0] + CROSSWALK_ROW_SUFFIX)
    return names


def orphan_claims(
    entries: list[dict], array: str, rows: set[int], crosswalk_names: set[str]
) -> list[str]:
    """Registry claims that point at nothing -- the converse of `uncovered`.

    `check_source_coverage` asked only "is every matrix row claimed?". The
    other direction was unasked, so `"matrix_rows": [99]` on a thirteen-row
    matrix passed every gate and exited 0. That is not cosmetic: an orphan
    claim inflates the claimed set, so a row that is later renumbered or
    removed leaves behind a claim that still reads as coverage -- the exact
    failure this check exists to prevent, in the direction it did not look.

    The strongest case is the quietest one: a typo of an *existing*
    `human_only_sources` cross-walk name keeps the residue set's cardinality,
    so the derived "N of the dated items" count stays 4 and check_doc_counts
    stays green while the registry names a row that does not exist.

    An orphan is an ERROR, not a note. There is no input on which a claim on a
    non-existent row is legitimate, so the check has no false-positive case to
    be lenient about, and the repair is one deleted number. A note prints on
    every run and never changes the exit code, i.e. it is prose in a different
    font -- and coverage asserted in prose is precisely how rows 12 and 13 sat
    unwatched through a full release.

    Member *types* are not rechecked here: `registry_problems` in
    scripts/watch_sources.py owns them, and this function must not read the
    matrix into that layer.
    """
    problems: list[str] = []
    present = sorted(rows)
    for entry in entries:
        identifier = entry.get("id", "<entry with no id>")
        for row in sorted(claimed_rows([entry])):
            if row not in rows:
                problems.append(
                    f"{REGISTRY.name} entry '{identifier}' ({array}) claims matrix row {row}, "
                    f"which {MATRIX.name} does not contain (rows present: {present}). Remove "
                    "the claim, or add the row. An orphan claim inflates the claimed set, so a "
                    "renumbered or deleted row keeps looking backed by a source."
                )
        for name in sorted(claimed_crosswalk_rows([entry])):
            if name not in crosswalk_names:
                problems.append(
                    f"{REGISTRY.name} entry '{identifier}' ({array}) claims cross-walk row "
                    f"'{name}', which is not a row of the 'Framework versions cited' table in "
                    f"{CROSSWALK.name}. Valid values are {sorted(crosswalk_names)}. Unlike a "
                    "matrix claim this one is not filtered anywhere downstream: it also "
                    "inflates the human-only residue reported below and the "
                    "'N of the dated items' count check_doc_counts re-derives."
                )
    return problems


def check_source_coverage(findings: Findings, registry: dict | None = None) -> None:
    """Every matrix row must be claimed by some registry entry.

    `registry_problems` in scripts/watch_sources.py checks that each entry
    declares what it backs; this checks the converse, which needs the matrix and
    so cannot live there. The converse is the half that matters operationally: a
    row nothing claims is a row the cadence silently does not cover, and rows 12
    and 13 sat in exactly that state through a full release because coverage was
    asserted in prose ("covering every matrix row") instead of tested.

    The human-only residue is reported as a note on every run, not just when it
    breaks. That set is the invariant needed to read `stale_guard.py` output
    correctly — those rows can never be advanced by any agent run, so their
    staleness means "a human is overdue", not "the automation is failing".

    Both directions are now checked. A row nothing claims is a row the cadence
    silently does not cover; a claim on a row that does not exist is a silent
    false assertion that it does. Both are errors, and both are reported in
    the same run — see the ordering note below.
    """
    if registry is None:
        registry = load_registry(findings)
    if registry is None:
        return
    if not MATRIX.exists():
        findings.error("source coverage", f"{MATRIX} not found")
        return
    rows = matrix_row_ids(MATRIX.read_text(encoding="utf-8"))
    if not rows:
        findings.error("source coverage", "could not read any row identifier from the capability table")
        return
    if not CROSSWALK.exists():
        findings.error("source coverage", f"{CROSSWALK} not found")
        return
    crosswalk_names = crosswalk_row_names(CROSSWALK.read_text(encoding="utf-8"))
    if not crosswalk_names:
        findings.error(
            "source coverage",
            "could not read any framework row from the 'Framework versions cited' table in "
            f"{CROSSWALK.name}, so cross-walk claims cannot be checked against it",
        )
        return

    watched = registry.get("sources", [])
    human_only = registry.get("human_only_sources", [])
    watched_rows = claimed_rows(watched)
    human_rows = claimed_rows(human_only)
    row_set = set(rows)

    uncovered = [row for row in rows if row not in watched_rows | human_rows]
    for row in uncovered:
        findings.error(
            "source coverage",
            f"matrix row {row} is claimed by no entry in {REGISTRY.name}. Add the row to "
            "'matrix_rows' on the source that backs it, or to a 'human_only_sources' entry "
            "if no automation may fetch it.",
        )

    # Reported *above* the early return, deliberately. The single most likely
    # edit that creates an orphan — renumbering a row — creates both faults at
    # once, so if this sat below the return, masking would be the common case
    # and the maintainer would close the gap and leave the stale claim behind.
    orphans = orphan_claims(watched, "sources", row_set, crosswalk_names)
    orphans += orphan_claims(human_only, "human_only_sources", row_set, crosswalk_names)
    for problem in orphans:
        findings.error("source coverage", problem)

    if uncovered or orphans:
        return

    human_exclusive = sorted(row for row in rows if row in human_rows and row not in watched_rows)
    crosswalk_exclusive = sorted(
        claimed_crosswalk_rows(human_only) - claimed_crosswalk_rows(watched)
    )
    findings.note(
        f"source coverage: all {len(rows)} matrix row(s) claimed by a registry entry"
    )
    findings.note(
        "source coverage: "
        f"{len(human_exclusive) + len(crosswalk_exclusive)} dated item(s) are backed ONLY by "
        f"human-only sources and can never be advanced by an agent run — matrix row(s) "
        f"{human_exclusive or 'none'}, cross-walk row(s) {crosswalk_exclusive or 'none'}"
    )


# Counts docs/agent-cadence.md states in prose, each with the way to re-derive
# it. Written as digits inside bold markers so the claim is machine-locatable:
# the previous form spelled them in words ("fifteen pinned sources") and drifted
# to a figure 7 short while carrying its own instruction to re-derive it.
DOC_COUNT_CLAIMS = [
    ("watched sources", re.compile(r"\*\*(\d+) watched sources\*\*")),
    ("human-only sources", re.compile(r"\*\*(\d+) human-only sources\*\*")),
    ("matrix rows", re.compile(r"\*\*(\d+) matrix rows\*\*")),
    ("human-only-backed dated items", re.compile(r"\*\*(\d+) of the dated items\*\*")),
]


def check_doc_counts(findings: Findings) -> None:
    """Re-derive every count docs/agent-cadence.md asserts.

    A missing claim is a failure, not a pass. Deleting the sentence would
    otherwise disable the check silently, which is the same trap the workflow
    path filters carry: an absent check reads as a green one.
    """
    registry = load_registry(findings)
    if registry is None or not CADENCE_DOC.exists():
        if registry is not None:
            findings.error("documented counts", f"{CADENCE_DOC} not found")
        return
    if not MATRIX.exists():
        findings.error("documented counts", f"{MATRIX} not found")
        return

    watched = registry.get("sources", [])
    human_only = registry.get("human_only_sources", [])
    rows = matrix_row_ids(MATRIX.read_text(encoding="utf-8"))
    human_exclusive = [r for r in rows if r in claimed_rows(human_only) and r not in claimed_rows(watched)]
    crosswalk_exclusive = claimed_crosswalk_rows(human_only) - claimed_crosswalk_rows(watched)

    actual = {
        "watched sources": len(watched),
        "human-only sources": len(human_only),
        "matrix rows": len(rows),
        "human-only-backed dated items": len(human_exclusive) + len(crosswalk_exclusive),
    }

    doc = CADENCE_DOC.read_text(encoding="utf-8")
    failures = 0
    for name, pattern in DOC_COUNT_CLAIMS:
        found = pattern.findall(doc)
        if not found:
            findings.error(
                "documented counts",
                f"docs/agent-cadence.md states no '{name}' count in the checked form "
                f"({pattern.pattern}). The count is derived in CI, so the sentence may be "
                "reworded but not removed.",
            )
            failures += 1
            continue
        for stated in found:
            if int(stated) != actual[name]:
                findings.error(
                    "documented counts",
                    f"docs/agent-cadence.md says {stated} {name}; re-derived from the "
                    f"repository it is {actual[name]}.",
                )
                failures += 1
    if not failures:
        findings.note(
            "documented counts: docs/agent-cadence.md matches the repository — "
            + ", ".join(f"{value} {name}" for name, value in actual.items())
        )


def check_confidentiality(files: list[str], findings: Findings) -> None:
    """Scan changed `.md`/`.json` files, and report the scope of the scan.

    The note this emits used to be an unscoped absence claim: it skips any file
    that is not `.md`/`.json`, so a pull request touching only `scripts/` or
    `tests/` or `.github/workflows/` scanned nothing and still reported "no
    tenant-shaped identifiers or out-of-scope content found". That is the
    standard this repository applies to its own published absence claims, so it
    applies here: the note names how many files were read, and says plainly
    when the answer is none.
    """
    targets = [REPO_ROOT / f for f in files] if files else [
        REPO_ROOT / "matrix" / "capability-status-matrix.md",
        REPO_ROOT / "crosswalk" / "framework-crosswalk.md",
        REPO_ROOT / "checklists" / "capability-status-verification.md",
        REPO_ROOT / "CHANGELOG.md",
    ]
    hits = 0
    scanned: list[str] = []
    skipped: list[str] = []
    for path in targets:
        if not path.exists() or path.suffix not in {".md", ".json"}:
            if path.suffix not in {".md", ".json"}:
                # POSIX spelling on every platform, so the note reads the same
                # locally as in CI and matches the git-derived paths above.
                skipped.append(
                    path.relative_to(REPO_ROOT).as_posix()
                    if path.is_relative_to(REPO_ROOT)
                    else path.as_posix()
                )
            continue
        scanned.append(path.relative_to(REPO_ROOT).as_posix())
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
        if not scanned:
            findings.note(
                "confidentiality and scope: no changed .md/.json file to scan"
                + (f" ({len(skipped)} changed file(s) are outside this check: {', '.join(sorted(skipped))})" if skipped else "")
            )
        else:
            findings.note(
                f"confidentiality and scope: no tenant-shaped identifiers or out-of-scope "
                f"content found across {len(scanned)} file(s) ({', '.join(sorted(scanned))})"
                + (f"; {len(skipped)} changed file(s) are outside this check: {', '.join(sorted(skipped))}" if skipped else "")
            )


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

    def labels_by_row(text: str, side: str) -> dict[str, list[str]] | None:
        """None means the Status column could not be resolved on this side.

        Returning an empty dict instead made this check fail *open*: with no
        Status index the loop below finds no violations and the run reports
        "no row moved out of 'Requires further validation'". That is the
        repository's hardest safety control asserting a clean result over a
        comparison it never performed, and a single reworded header cell was
        enough to do it.
        """
        indexes = column_indexes(text)
        status_index = indexes.get("Status")
        if status_index is None:
            findings.error(
                "escalation direction",
                f"could not resolve the 'Status' column in the {side} matrix, so no label "
                "comparison was made. This check cannot be reported as clean.",
            )
            return None
        result: dict[str, list[str]] = {}
        for row in matrix_table_rows(text):
            if len(row) > status_index:
                result[row[0]] = normalise_label(row[status_index])
        return result

    old = labels_by_row(before, f"base ({base_ref})")
    new = labels_by_row(MATRIX.read_text(encoding="utf-8"), "working-tree")
    if old is None or new is None:
        return
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


def use_utf8_streams() -> None:
    """Print repository text without depending on the console's code page.

    Findings quote cell text and URLs straight out of the tracked files, and
    the report itself uses an em dash. cp1252 happens to carry the em dash but
    not an arrow (U+2192), so this failed only for some content -- which is
    worse than failing always. CI runs UTF-8 and never saw it. See
    scripts/changelog_entry.py, where a published command was found crashing.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main() -> int:
    use_utf8_streams()
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
    check_source_coverage(findings)
    check_doc_counts(findings)
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
