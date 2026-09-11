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
10. human-only containment — a `docs.github.com` source may be registered under
                           `human_only_sources` only, never under `sources`, so
                           no automated run fetches it and no GitHub Docs page
                           content reaches the model tier. This is the condition
                           on which ALLOWED_SOURCE_HOSTS admits the host at all,
                           and it was published to contributors as a guarantee
                           while nothing enforced it.
11. date corroboration   — a last-verified date may not advance unless something
                           that can actually corroborate it did. Every other
                           check here asks whether a *label* is justified; this
                           one asks whether the *date* is, which was the one
                           claim a run could set freely. See
                           `check_date_corroboration`.

Exit code 0 = all checks pass. Non-zero = at least one violation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from datetime import date, timedelta
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


def load_sibling_script(name: str):
    """Import a sibling script by file location rather than through `sys.path`.

    `scripts/` is not a package. A plain `import stale_guard` works only when
    this file is executed directly, because then `sys.path[0]` happens to be
    `scripts/`; the tests load this module with
    `importlib.util.spec_from_file_location`, where the same import raises. So
    the one place this file depends on another script resolves the path itself.

    Deliberately not registered in `sys.modules`. The tests load `stale_guard`
    under that name too, and a break test is only meaningful if reverting the
    real file is what the code under test sees -- a cached module object from
    another test file would make a reverted parser keep passing.
    """
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The only "Last verified" parser in this repository, imported rather than
# reimplemented. The cost of the alternative is on record: this file and
# stale_guard.py once disagreed about whether a blank line ends a markdown
# table, one saw a single cross-walk row while the other saw four, and three
# valid registry entries were reported as claiming rows that "do not exist".
# See `crosswalk_row_names` below, which carries the full account.
stale_guard = load_sibling_script("stale_guard")
LAST_VERIFIED_COLUMN = "Last verified"

# The column of the cross-walk's framework-versions table that states which
# edition a row cites. Named once so the reader and the rule cannot drift.
EDITION_COLUMN = "Version / edition cited"

# An edition year stated in that cell, e.g. "2026 edition". Only one of the four
# framework rows spells its edition this way; the others pin a dist version, a
# publication month or a semantic version, and for those the rule must report
# *not applicable* rather than staying silent.
EDITION_YEAR = re.compile(r"(20[0-9]{2}) edition")

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

# Named once so the citation allowlist and the containment gate cannot drift
# apart: the second is the condition on which the first admits this host.
GITHUB_DOCS_HOST = re.compile(r"^https://docs\.github\.com/", re.IGNORECASE)

ALLOWED_SOURCE_HOSTS = [
    re.compile(r"^https://learn\.microsoft\.com/", re.IGNORECASE),
    re.compile(r"^https://(www\.)?microsoft\.com/[^ )]*microsoft-365/roadmap", re.IGNORECASE),
    # GitHub Docs is the first-party documentation site for a Microsoft-owned
    # product, so it is the same *class* of source as Microsoft Learn — not a
    # relaxation toward blogs. It is admitted on one condition, and that
    # condition is now a gate rather than a convention: a docs.github.com source
    # is registered under `human_only_sources`, never under `sources`, so the
    # watcher never fetches it and no GitHub *Docs* page content reaches the
    # adjudicator. Not "no GitHub content": four watched entries fetch Markdown
    # from raw.githubusercontent.com, which is the MicrosoftDocs source for
    # pages Learn renders. `check_human_only_containment` enforces this. See
    # docs/agent-cadence.md.
    GITHUB_DOCS_HOST,
]

URL_PATTERN = re.compile(r"https?://[^\s)\]<>\"']+")

CONFIDENTIALITY_PATTERNS = [
    ("GUID", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)),
    ("email address", re.compile(r"\b[\w.+-]+@(?!example\.)[\w-]+\.[A-Za-z]{2,}\b")),
    # Octets constrained to 0-255, so a four-part number that cannot be an
    # address is not reported as one.
    ("IPv4 address", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b")),
    ("onmicrosoft.com tenant", re.compile(r"\b[\w-]+\.onmicrosoft\.com\b", re.IGNORECASE)),
]

# Suffixes `check_confidentiality` reads. `.ps1` and `.yml` were added when
# `.claude/**` entered the workflow's path filters: the tracked PowerShell hooks
# and the workflow definitions are executable influence surfaces, and a
# hooks-only pull request otherwise produced a green `Validate matrix` that had
# read nothing at all — a present-but-vacuous check, which reads as validation
# exactly the way an absent one reads as green. The patterns below are
# content-agnostic, so widening the set costs nothing but coverage.
SCANNED_SUFFIXES = {".md", ".json", ".ps1", ".yml"}

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


# The content an automated run is allowed to touch, as plain paths. Kept beside
# PATH_ALLOWLIST, which is the same set as regexes; this form is what git takes
# as a pathspec.
GOVERNED_PATHS = [
    "matrix",
    "crosswalk",
    "checklists",
    "CHANGELOG.md",
    ".github/watch-state",
]


def uncommitted_governed_changes() -> str | None:
    """Uncommitted edits to content an automated change may modify.

    Used to tell "the automated run correctly wrote nothing" apart from "the
    automated run wrote something and never committed it". Only the second is a
    failure, and only the second is invisible to a diff against the base ref.

    **Scoped to `GOVERNED_PATHS`, and the scoping is the whole point.** An
    unscoped `git status --porcelain` reports untracked files too, and both bot
    workflows leave an untracked `evidence/` directory inside the checkout --
    `--evidence-out evidence/evidence.json` in the monthly refresh, and the
    downloaded artifact in the source watch -- neither of which is gitignored.
    So the unscoped form was dirty on every single run, which would have failed
    exactly the correct-outcome path this check exists to keep green: an
    adjudicator that files an issue and commits nothing.

    Tri-state, because "clean" and "could not look" must not be the same
    answer. `git status` failing -- a dubious-ownership refusal, a broken index,
    git absent from PATH -- is precisely the case where uncommitted edits would
    be invisible to the diff AND to this probe, so answering "clean" there would
    assert a state nobody observed. That is the pattern this file rejects
    everywhere else.

    Returns the porcelain output when something is pending, `""` when the probe
    ran and found nothing, and None when the probe could not run.
    """
    try:
        output = subprocess.run(
            ["git", "status", "--porcelain", "--"] + GOVERNED_PATHS,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return None
    return output.strip()


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
            # An empty diff under --bot has two very different causes, and
            # treating them alike is wrong in both directions.
            #
            # Writing nothing is often the CORRECT automated outcome: the
            # adjudicator's own permission table requires an issue and never a
            # pull request for a move out of "Requires further validation", and
            # a detected source change that turns out not to be status-relevant
            # is also written up rather than committed. Failing those would
            # manufacture a red daily run on the path operators most need to
            # trust.
            #
            # The dangerous case is narrower: edits sitting in the working tree
            # that were never committed. The bot workflows diff
            # `origin/<ref>...HEAD`, which sees committed work only, while
            # `check_escalation_direction` reads the working tree for its
            # "after" state -- so uncommitted edits would be judged by the label
            # gate and skipped entirely by the allowlist.
            pending = uncommitted_governed_changes()
            if pending is None:
                findings.error(
                    "path allowlist",
                    "the diff against the base ref is empty and the working tree could not "
                    "be inspected (`git status` failed), so it is unknown whether an "
                    "automated change was left uncommitted. This is not a clean result.",
                )
            elif pending:
                listed = ", ".join(sorted(line[3:] for line in pending.splitlines()))
                findings.error(
                    "path allowlist",
                    "the diff against the base ref is empty but these governed files have "
                    f"uncommitted changes, so the allowlist did not run over them: {listed}. "
                    "An automated change must be committed before it is validated.",
                )
            else:
                findings.note(
                    "path allowlist: no automated change was committed and no governed file "
                    "has uncommitted changes — nothing for the allowlist to check"
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
    # Deliberately no early return here. A missing header disables only the
    # checks keyed on *that* header; the others still run. Returning would mask
    # them, so a header rename plus a genuinely missing ISO date would surface
    # as one error, be repaired, and only then reveal the second -- the same
    # masking that `orphan_claims` is reported above its own early return to
    # avoid. Nothing is at risk of reading as a pass: each missing header is
    # already an error, and each note below additionally requires that its
    # column resolved and that every row was examined.

    label_failures = 0
    date_failures = 0
    domain_failures = 0
    label_checked = 0
    date_checked = 0
    domain_checked = 0

    for row in rows:
        identifier = row[0] if row else "?"

        if status_index is not None and len(row) > status_index:
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

        if verified_index is not None and len(row) > verified_index:
            date_checked += 1
            if not re.search(r"\b20\d{2}-\d{2}-\d{2}\b", row[verified_index]):
                findings.error("last-verified date", f"row {identifier}: no ISO date in 'Last verified'")
                date_failures += 1

        if source_index is not None and len(row) > source_index:
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
    for name, index, checked in (
        ("Status", status_index, label_checked),
        ("Last verified", verified_index, date_checked),
        ("Primary source", source_index, domain_checked),
    ):
        # An unresolved column is already reported above; saying "0 of 13 rows
        # have a cell to check" as well would be a second error for one fault.
        if index is not None and checked != len(rows):
            findings.error(
                "matrix",
                f"only {checked} of {len(rows)} capability row(s) have a '{name}' cell to "
                "check; the rest are too short to reach that column.",
            )

    if not label_failures and status_index is not None and label_checked == len(rows):
        findings.note(f"status labels: all {label_checked} row(s) use legend labels only")
    if not date_failures and verified_index is not None and date_checked == len(rows):
        findings.note(f"last-verified dates: all {date_checked} row(s) carry an ISO date")
    if not domain_failures and source_index is not None and domain_checked == len(rows):
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
    two scripts name a cross-walk row the same way.

    Blank lines inside the table are skipped rather than treated as its end,
    which is what `stale_guard.parse_table_dates` already does. The two parsers
    diverging there was not harmless: a blank line after the first data row left
    this one seeing a single name while stale_guard still saw four, so three
    perfectly good registry entries would have been reported as claiming
    cross-walk rows that "do not exist" -- blaming the registry for a stray line
    in a markdown file.

    Markdown emphasis is deliberately not normalised: an emphasised name would
    also silently change stale_guard's identifier, so a red build is the right
    outcome rather than a divergence hidden by two strippers.

    An empty return is a parse failure, not "nothing to check", and the caller
    must treat it as an error -- the same rule matrix_row_ids follows.
    """
    return {
        row[0] + CROSSWALK_ROW_SUFFIX
        for row in framework_versions_rows(text)
        if row and row[0]
    }


def framework_versions_rows(text: str) -> list[list[str]]:
    """Cells of each data row of the cross-walk's "Framework versions cited" table.

    Split out of `crosswalk_row_names` when `check_date_corroboration` needed a
    second column of the same table. Reading it with a second locator would have
    recreated exactly the divergence that docstring warns about, one table
    further in: the row-name check and the edition check could then disagree
    about which rows exist.
    """
    lines = text.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and "Framework" in stripped and LAST_VERIFIED_COLUMN in stripped:
            header_index = index
            break
    if header_index is None:
        return []
    width = len([c for c in lines[header_index].strip().strip("|").split("|")])
    rows: list[list[str]] = []
    for line in lines[header_index + 2 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if stripped == "":
                continue
            break
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        # Same width as the header, and not a separator row. Skipping blank
        # lines is what lets a *second* table under the same heading be read as
        # part of this one -- markdown requires a blank line between adjacent
        # tables -- and its `|---|---|` separator would otherwise contribute the
        # name "--- framework-versions row". A row of the wrong table would then
        # be a valid `crosswalk_rows` value that `stale_guard` never tracks:
        # coverage asserted and never watched, which is the state this check
        # exists to prevent.
        if len(cells) != width:
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(cells)
    return rows


def framework_versions_header(text: str) -> list[str]:
    """The header cells of that table, so a column can be resolved by name.

    Separate from `framework_versions_rows` because an unresolvable column must
    be a loud error rather than an index that silently reads the wrong cell --
    the fail-open `ColumnContractTests` pins for the matrix, reached here
    through the cross-walk.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and "Framework" in stripped and LAST_VERIFIED_COLUMN in stripped:
            return [c.strip() for c in stripped.strip("|").split("|")]
    return []


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
    watched = registry.get("sources", [])
    human_only = registry.get("human_only_sources", [])
    watched_rows = claimed_rows(watched)
    human_rows = claimed_rows(human_only)
    row_set = set(rows)

    # The matrix-row half runs first and unconditionally. It is this function's
    # reason for existing -- rows 12 and 13 sat unclaimed through a full release
    # -- and it needs nothing from the cross-walk, so a cross-walk parse failure
    # must not take it down with it. Reading the cross-walk earlier and
    # returning on failure meant exactly that.
    uncovered = [row for row in rows if row not in watched_rows | human_rows]
    for row in uncovered:
        findings.error(
            "source coverage",
            f"matrix row {row} is claimed by no entry in {REGISTRY.name}. Add the row to "
            "'matrix_rows' on the source that backs it, or to a 'human_only_sources' entry "
            "if no automation may fetch it.",
        )

    crosswalk_names: set[str] = set()
    crosswalk_readable = True
    if not CROSSWALK.exists():
        findings.error("source coverage", f"{CROSSWALK} not found")
        crosswalk_readable = False
    else:
        crosswalk_names = crosswalk_row_names(CROSSWALK.read_text(encoding="utf-8"))
        if not crosswalk_names:
            findings.error(
                "source coverage",
                "could not read any framework row from the 'Framework versions cited' table in "
                f"{CROSSWALK.name}, so cross-walk claims cannot be checked against it",
            )
            crosswalk_readable = False

    # Reported *above* the early return, deliberately. The single most likely
    # edit that creates an orphan — renumbering a row — creates both faults at
    # once, so if this sat below the return, masking would be the common case
    # and the maintainer would close the gap and leave the stale claim behind.
    #
    # Skipped entirely when the cross-walk could not be read: with no
    # authoritative name list every registered cross-walk claim would be
    # reported as an orphan, blaming the registry for a defect in the document.
    orphans: list[str] = []
    if crosswalk_readable:
        orphans = orphan_claims(watched, "sources", row_set, crosswalk_names)
        orphans += orphan_claims(human_only, "human_only_sources", row_set, crosswalk_names)
    for problem in orphans:
        findings.error("source coverage", problem)

    if uncovered or orphans or not crosswalk_readable:
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


def check_human_only_containment(findings: Findings, registry: dict | None = None) -> None:
    """A GitHub Docs source may be registered human-only, never watched.

    This rule was published as a guarantee on two reader-facing surfaces -- the
    README and the new-row-proposal template both tell a contributor that such a
    source "is registered under `human_only_sources`, never under `sources`" --
    while nothing enforced it. `ALLOWED_SOURCE_HOSTS` admits `docs.github.com`
    for citation, and the registry note records the containment as the condition
    of that admission, but a maintainer could move the entry into `sources` and
    every gate would stay green.

    It is worth a gate rather than a convention because of what it contains.
    Per the registry's own reason, the page is "perfectly fetchable, and that is
    exactly why the rule matters": admitting `docs.github.com` to the citation
    allowlist widened what this repository may *cite*, and keeping those entries
    out of `sources` is what stops that from also widening what an automated run
    may *fetch and adjudicate*.

    Scoped to GitHub Docs, not to "non-Learn content", because the watched array
    is not Learn-only: four entries fetch from `raw.githubusercontent.com` (the
    MicrosoftDocs repositories Learn renders), one from the OWASP GenAI site and
    one from the public Microsoft 365 Roadmap. A promise that only holds while
    everyone remembers it is the class of control this repository does not
    accept anywhere else -- and so is one stated more broadly than it holds.
    """
    if registry is None:
        registry = load_registry(findings)
    if registry is None:
        return
    offenders = []
    for entry in registry.get("sources", []):
        for key in ("url", "cite_url"):
            value = entry.get(key) or ""
            if GITHUB_DOCS_HOST.match(value):
                offenders.append(f"{entry.get('id', '<no id>')} ({key}: {value})")
    for offender in offenders:
        findings.error(
            "human-only containment",
            f"{offender} is a docs.github.com source in the watched 'sources' array. "
            "GitHub Docs is admitted as a citable host only on the condition that it is "
            "registered under 'human_only_sources', so no automated run fetches it and no "
            "GitHub Docs page content reaches the model tier. Move the entry.",
        )
    if not offenders:
        findings.note(
            "human-only containment: no docs.github.com source is in the watched array"
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


# Adjacency, not a window. The first version of this allowed 12 free characters
# after a bare `\bv`, which suppressed a genuine address after any v-initial
# word: "VPN gateway 10.0.0.1", "the connector VM at 10.0.0.5" and "traffic via
# 10.1.2.3" were all silently dropped from a confidentiality gate. A version
# marker has to sit immediately before the number, separated only by the
# punctuation a version assignment uses.
VERSION_CONTEXT = re.compile(r"(?i)(?:(?:version|\bver)[\s=:'\"()-]{0,4}|\bv)$")


def looks_like_a_version(text: str, start: int) -> bool:
    """Is this four-part number a version string rather than an address?

    The guard this replaces was dead code: it re-tested the match against the
    same shape that produced it, so the `continue` was unreachable and the
    comment described a filter that could not exclude anything. That went
    unnoticed while only `.md` and `.json` were scanned; four-part versions are
    idiomatic in exactly the two file types since added -- `ModuleVersion =
    '1.0.0.0'` in PowerShell, four-part image tags in a workflow -- so a
    dead filter would have turned ordinary content into a red confidentiality
    gate.

    Decided on the preceding text rather than the digits: `1.0.0.0` is a
    perfectly valid address, so nothing about the number itself distinguishes
    the two.

    **The residual hole, stated exactly rather than reassuringly.** An address
    is missed only when a version marker sits immediately before it -- after
    `version`/`ver` with at most four characters of assignment punctuation
    between, or after a bare `v` with nothing between. So `version 10.0.0.1`,
    `ver=10.0.0.1` and `v10.0.0.1` are not reported. Everything else is,
    including the cases an earlier and much wider form of this filter dropped:
    `VPN gateway 10.0.0.1`, `the connector VM at 10.0.0.5`, `traffic via
    10.1.2.3`. Those are pinned as negative tests, because a filter in a
    confidentiality gate that quietly widens is worse than no filter at all.
    """
    return bool(VERSION_CONTEXT.search(text[max(0, start - 24) : start]))


def check_confidentiality(files: list[str], findings: Findings) -> None:
    """Scan the changed files this check can read, and report the scan's scope.

    The note this emits used to be an unscoped absence claim: it skips any file
    that is not in `SCANNED_SUFFIXES`, so a pull request touching only `scripts/` or
    `tests/` or `.github/workflows/` scanned nothing and still reported "no
    tenant-shaped identifiers or out-of-scope content found". That is the
    standard this repository applies to its own published absence claims, so it
    applies here: the note names how many files were read, and says plainly
    when the answer is none.
    """
    # The no-diff fallback carries the two watch-state files deliberately. When
    # the diff is empty -- a workflow_dispatch run, or a push whose base ref
    # resolves to the pushed commit -- this list is the entire scan, and
    # `fingerprints.json` is the file most worth scanning: it is machine-written
    # and holds text taken verbatim from upstream pages, so it is the one place
    # third-party content enters the repository without a human reading it.
    targets = [REPO_ROOT / f for f in files] if files else [
        REPO_ROOT / "matrix" / "capability-status-matrix.md",
        REPO_ROOT / "crosswalk" / "framework-crosswalk.md",
        REPO_ROOT / "checklists" / "capability-status-verification.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / ".github" / "watch-state" / "sources.json",
        REPO_ROOT / ".github" / "watch-state" / "fingerprints.json",
    ]
    hits = 0
    scanned: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []
    for path in targets:
        # POSIX spelling on every platform, so the note reads the same locally as
        # in CI and matches the git-derived paths above.
        relative = (
            path.relative_to(REPO_ROOT).as_posix()
            if path.is_relative_to(REPO_ROOT)
            else path.as_posix()
        )
        if path.suffix not in SCANNED_SUFFIXES:
            skipped.append(relative)
            continue
        if not path.exists():
            # A changed file that no longer exists -- a deletion, or the old side
            # of a rename. Counted rather than dropped: the note is a scoped
            # absence claim, so every changed file must land in exactly one
            # bucket or `scanned + skipped` silently understates the diff.
            missing.append(relative)
            continue
        scanned.append(relative)
        text = path.read_text(encoding="utf-8")
        for name, pattern in CONFIDENTIALITY_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(0)
                if name == "IPv4 address" and looks_like_a_version(text, match.start()):
                    continue
                findings.error("confidentiality", f"{relative}: possible {name} '{value}'")
                hits += 1
        for name, pattern in OUT_OF_SCOPE_PATTERNS:
            if pattern.search(text):
                findings.error("scope", f"{relative}: contains {name}, which is out of scope")
                hits += 1
    if not hits:
        unread = ""
        if skipped:
            unread += (
                f"; {len(skipped)} changed file(s) are outside this check: "
                f"{', '.join(sorted(skipped))}"
            )
        if missing:
            unread += (
                f"; {len(missing)} changed scannable file(s) no longer exist and were "
                f"not read: {', '.join(sorted(missing))}"
            )
        if not scanned:
            findings.note(
                "confidentiality and scope: no changed file this check can read" + unread
            )
        else:
            findings.note(
                "confidentiality and scope: no tenant-shaped identifiers or out-of-scope "
                f"content found across {len(scanned)} file(s) ({', '.join(sorted(scanned))})"
                + unread
            )


def check_escalation_direction(
    base_ref: str | None,
    findings: Findings,
    bot: bool,
    before_text: str | None = None,
    after_text: str | None = None,
) -> None:
    """A row may never be moved *out* of 'Requires further validation' automatically.

    A human who has completed the in-tenant verification may make exactly this
    change, so outside --bot mode the transition is reported for reviewer
    attention rather than blocked.

    `before_text`/`after_text` are injection seams for the tests, matching the
    ones on `check_matrix` and `check_source_coverage`. The states this must
    catch are states the committed tree must never be in, so they cannot be
    exercised through the git path.
    """
    if before_text is None:
        if not base_ref:
            findings.note("escalation direction: skipped (no base ref supplied)")
            return
        try:
            before_text = subprocess.run(
                ["git", "show", f"{base_ref}:matrix/capability-status-matrix.md"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (subprocess.CalledProcessError, OSError):
            findings.note("escalation direction: skipped (matrix not present at base ref)")
            return
    before = before_text

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
    new = labels_by_row(
        MATRIX.read_text(encoding="utf-8") if after_text is None else after_text,
        "working-tree",
    )
    if old is None or new is None:
        return
    violations = 0

    def report(message: str) -> None:
        """Hard failure for an automated run, reviewer attention for a human.

        Either way it counts as a violation, so the reassuring note below cannot
        print beside it.
        """
        nonlocal violations
        violations += 1
        if bot:
            findings.error(
                "escalation direction",
                message + " An automated run may never make this change.",
            )
        else:
            findings.note(
                "escalation direction: " + message
                + " Reviewer must confirm the in-tenant verification was actually performed."
            )

    for row_id, old_labels in old.items():
        if "Requires further validation" not in old_labels:
            continue

        # Both of these used to be silent passes. `new.get(row_id, [])` returned
        # an empty list and `if new_labels and ...` short-circuited, so a row
        # that carried the label at the base and could not be found or read in
        # the working tree left `violations` at 0 and printed "no row moved out
        # of 'Requires further validation'". That is the same fail-open the
        # column-resolution guard above closes, reached through the other door:
        # renaming the identifier is enough, and `matrix_row_ids` strips
        # non-digits, so `5` -> `5a` keeps `check_source_coverage` clean too.
        if row_id not in new:
            report(
                f"row {row_id} carried 'Requires further validation' at the base ref and no "
                "row with that identifier exists in the working-tree matrix, so its "
                "transition could not be checked. Renaming or removing a row's identifier "
                "must not be a way to leave that state unobserved."
            )
            continue

        new_labels = new[row_id]
        if not new_labels:
            report(
                f"row {row_id} carried 'Requires further validation' at the base ref and its "
                "Status cell in the working-tree matrix yields no legend label, so its "
                "transition could not be checked."
            )
            continue

        if "Requires further validation" not in new_labels:
            report(
                f"row {row_id} was moved out of 'Requires further validation' to {new_labels}. "
                "Leaving that state requires in-tenant confirmation by a human "
                "(docs/how-to-read-status.md)."
            )

    if not violations:
        findings.note("escalation direction: no row moved out of 'Requires further validation'")


CORROBORATED = "corroborated"
CONTRADICTED = "contradicted"
NOT_APPLICABLE = "not applicable"

# Governed content files this check compares across the diff, keyed by the name
# used in findings. The checklist footer is deliberately absent: it carries a
# date but is not a row, no registry entry claims it, and there is nothing that
# could corroborate it other than the human who re-ran the checklist.
CORROBORATED_TARGETS = {
    "matrix row": "matrix/capability-status-matrix.md",
    "cross-walk row": "crosswalk/framework-crosswalk.md",
}


def claim_keys(entry: dict) -> list[tuple[str, str]]:
    """The dated items a registry entry claims, as (kind, identifier) pairs.

    Read from `.github/watch-state/sources.json` and never from
    `fingerprints.json`: the fingerprint file is evidence of what a run
    fetched, not a registry of what a source backs, and its `mode: "version"`
    entries carry an empty `matrix_rows` and no `crosswalk_rows` key at all.
    Deriving coverage from it would silently conclude that the two framework
    sources back nothing.
    """
    keys: list[tuple[str, str]] = []
    for row in entry.get("matrix_rows") or []:
        if isinstance(row, int):
            keys.append(("matrix row", str(row)))
    for row in entry.get("crosswalk_rows") or []:
        if isinstance(row, str) and row.endswith(CROSSWALK_ROW_SUFFIX):
            keys.append(("cross-walk row", row[: -len(CROSSWALK_ROW_SUFFIX)]))
    return keys


def parse_iso_day(value: str | None) -> date | None:
    """A calendar date from an ISO date or timestamp, or None if it is neither.

    None is never read as agreement anywhere below. A timestamp this cannot
    parse is an unreadable input, and an unreadable input is the one thing that
    must not be allowed to look like corroboration.
    """
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def check_date_corroboration(
    base_ref: str | None,
    findings: Findings,
    bot: bool,
    evidence_path: Path | None = None,
    before_texts: dict[str, str] | None = None,
    after_texts: dict[str, str] | None = None,
    registry: dict | None = None,
    fingerprints: dict | None = None,
    evidence: dict | None = None,
) -> None:
    """A last-verified date may not advance unless something could corroborate it.

    Every other check in this file asks whether a *label* is justified. This one
    asks whether the *date* is, which until now was the single claim a run could
    set freely: the matrix says a date set by a monthly automated refresh means
    the row's pinned source was fetched successfully on that date, and nothing
    checked that a fetch had happened at all.

    Three rules, each reporting one of three outcomes for every row whose date
    moved forward. Three, not two, because "this rule does not apply here" and
    "this rule found agreement" are different findings and collapsing them is
    how a check comes to report a pass over work it never did:

      R-a  Something watched could corroborate this row at all. A row claimed
           only by `human_only_sources` can never be advanced by an agent run,
           by construction -- nothing fetches it.
      R-b  A claiming watched source was actually fetched for this stamp: an
           entry with `ok: true` whose `checked_at` falls on the stamped day or
           the day before.
      R-c  For a cross-walk row backed by a `mode: "version"` source, the
           edition year the row cites appears in that source's captured
           `signals.versions`. Only one of the four framework rows states its
           edition as a year; the rest pin a dist version, a publication month
           or a semantic version, and for those this reports *not applicable:
           no edition year stated* rather than nothing.

    **Why {D, D-1} is a correct tolerance rather than a guess.** It is only
    correct because the adjudicator is required to stamp an advanced row with
    the claiming fetch's UTC `checked_at` date -- which is what the matrix's
    "How rows are verified" already says a refresh-set date means, now written
    into `.claude/agents/status-adjudicator.md` as a rule rather than left as a
    description. With the stamp anchored that way the length of the refresh
    window stops mattering: a four-day window would otherwise need a four-day
    tolerance, and a tolerance that wide corroborates almost anything. D-1
    remains because the fetch and the commit can legitimately fall either side
    of a UTC midnight.

    **Both the evidence bundle and the committed fingerprints are consulted, in
    that order.** The documented local procedure runs the watcher *without*
    `--update-baseline`, so a locally-produced refresh pull request carries a
    `checked_at` in `fingerprints.json` that is stale by construction -- it is
    the previous baseline's. Without reading the bundle this check would flag
    every row of its own first refresh. The committed skew is worth looking at
    directly: at the time this was written every `checked_at` in
    `fingerprints.json` read 2026-09-10, a day *after* the rows it is supposed
    to back were stamped 2026-09-09, because the re-baseline was a separate
    commit from the refresh. A later fetch is not corroboration for an earlier
    stamp -- it is a different run than the one the date claims -- which is why
    the tolerance is one-sided.

    Bot = error, human = note, the same asymmetry the path allowlist and the
    escalation-direction check already use: a human re-reading a human-only
    source is exactly how rows 12 and 13 legitimately advance, and failing that
    would block the maintenance this repository depends on. A *structural*
    failure -- an unreadable registry, an unparseable table -- is an error in
    both modes, because a check that could not run must never report clean.

    Note that nothing here reads the clock. The comparison is stamp against
    fetch, never either against today, so validating a refresh three days after
    it was produced gives the same answer as validating it the same hour.
    """
    if before_texts is None:
        if not base_ref:
            findings.note("date corroboration: skipped (no base ref supplied)")
            return
        before_texts = {}
        for kind, path in CORROBORATED_TARGETS.items():
            try:
                before_texts[kind] = subprocess.run(
                    ["git", "show", f"{base_ref}:{path}"],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            except (subprocess.CalledProcessError, OSError):
                findings.note(
                    f"date corroboration: skipped ({path} not present at base ref)"
                )
                return

    if after_texts is None:
        after_texts = {
            kind: (REPO_ROOT / path).read_text(encoding="utf-8")
            for kind, path in CORROBORATED_TARGETS.items()
        }

    advanced: list[tuple[str, str, date]] = []
    for kind in CORROBORATED_TARGETS:
        before = dict(stale_guard.parse_table_dates(before_texts[kind], LAST_VERIFIED_COLUMN))
        after = dict(stale_guard.parse_table_dates(after_texts[kind], LAST_VERIFIED_COLUMN))
        if not after:
            findings.error(
                "date corroboration",
                f"no '{LAST_VERIFIED_COLUMN}' date could be read from "
                f"{CORROBORATED_TARGETS[kind]} in the working tree, so no date was "
                "compared. This check cannot be reported as clean.",
            )
            return
        for identifier, iso in sorted(after.items()):
            new_day = parse_iso_day(iso)
            if new_day is None:
                findings.error(
                    "date corroboration",
                    f"{kind} {identifier} carries '{iso}', which is not a calendar date, "
                    "so it could not be compared against the base ref.",
                )
                continue
            old_day = parse_iso_day(before.get(identifier))
            if old_day is not None and new_day <= old_day:
                continue
            if identifier in before and old_day is None:
                findings.error(
                    "date corroboration",
                    f"{kind} {identifier} carries an unreadable date at the base ref, so "
                    "whether its stamp advanced is unknown. This is not a clean result.",
                )
                continue
            # A row absent at the base ref -- newly added, or with a date cell
            # the parser could not read at all -- is treated as advanced. The
            # conservative direction: it is asserting a verification from a
            # state nothing could be compared against.
            advanced.append((kind, identifier, new_day))

    if not advanced:
        findings.note(
            "date corroboration: no last-verified date advanced in this change — "
            "nothing to corroborate"
        )
        return

    if registry is None:
        registry_path = REPO_ROOT / ".github" / "watch-state" / "sources.json"
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.error(
                "date corroboration",
                f"{len(advanced)} date(s) advanced and the source registry could not be "
                f"read ({exc}), so none of them could be corroborated.",
            )
            return

    if fingerprints is None:
        fingerprints_path = REPO_ROOT / ".github" / "watch-state" / "fingerprints.json"
        try:
            fingerprints = json.loads(fingerprints_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.error(
                "date corroboration",
                f"{len(advanced)} date(s) advanced and the committed fingerprints could "
                f"not be read ({exc}), so none of them could be corroborated.",
            )
            return

    if evidence is None and evidence_path is not None and evidence_path.exists():
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.error(
                "date corroboration",
                f"evidence bundle {evidence_path.name} could not be read ({exc}), so this "
                "check fell back to the committed fingerprints alone. Stating it rather "
                "than corroborating against a file that was not read.",
            )
            evidence = None

    watched = {entry["id"]: entry for entry in registry.get("sources", []) if entry.get("id")}
    human_only = {
        entry["id"]: entry for entry in registry.get("human_only_sources", []) if entry.get("id")
    }
    watched_by_item: dict[tuple[str, str], list[str]] = {}
    human_by_item: dict[tuple[str, str], list[str]] = {}
    for source_id, entry in watched.items():
        for key in claim_keys(entry):
            watched_by_item.setdefault(key, []).append(source_id)
    for source_id, entry in human_only.items():
        for key in claim_keys(entry):
            human_by_item.setdefault(key, []).append(source_id)

    committed_fetches = fingerprints.get("sources") or {}
    bundle_fetches = (evidence or {}).get("sources") or {}

    def fetch_record(source_id: str) -> tuple[dict | None, str]:
        """The freshest record for a source, and where it came from.

        The bundle wins because it is this run; the committed fingerprints are
        the previous baseline whenever the local procedure was followed.
        """
        if source_id in bundle_fetches:
            return bundle_fetches[source_id], "evidence bundle"
        if source_id in committed_fetches:
            return committed_fetches[source_id], "committed fingerprints"
        return None, "nowhere"

    def report(message: str) -> None:
        if bot:
            findings.error("date corroboration", message)
        else:
            findings.note("date corroboration: " + message)

    edition_header = framework_versions_header(after_texts["cross-walk row"])
    edition_index = (
        edition_header.index(EDITION_COLUMN) if EDITION_COLUMN in edition_header else None
    )
    edition_cells: dict[str, str] = {}
    if edition_index is not None:
        for cells in framework_versions_rows(after_texts["cross-walk row"]):
            if len(cells) > edition_index and cells[0]:
                edition_cells[cells[0]] = cells[edition_index]

    contradictions = 0
    for kind, identifier, day in advanced:
        key = (kind, identifier)
        watching = sorted(watched_by_item.get(key, []))
        humans = sorted(human_by_item.get(key, []))
        outcomes: list[tuple[str, str, str]] = []

        # R-a --------------------------------------------------------------
        if watching:
            outcomes.append(("R-a", CORROBORATED, f"watched by {', '.join(watching)}"))
        elif humans:
            outcomes.append(
                (
                    "R-a",
                    CONTRADICTED,
                    f"claimed only by human-only source(s) {', '.join(humans)}, which no "
                    "automated run fetches, so this date can only have been set by a "
                    "human re-read",
                )
            )
        else:
            outcomes.append(
                (
                    "R-a",
                    CONTRADICTED,
                    "no registry entry claims this row, so nothing can corroborate its date",
                )
            )

        # R-b --------------------------------------------------------------
        if not watching:
            outcomes.append(("R-b", NOT_APPLICABLE, "no watched source claims this row (see R-a)"))
        else:
            accepted = sorted({day, day - timedelta(days=1)})
            agreeing: list[str] = []
            unreadable: list[str] = []
            disagreeing: list[str] = []
            for source_id in watching:
                record, origin = fetch_record(source_id)
                if record is None:
                    unreadable.append(f"{source_id} (no fetch record in {origin})")
                    continue
                fetched = parse_iso_day(record.get("checked_at"))
                if fetched is None:
                    unreadable.append(
                        f"{source_id} (unreadable checked_at {record.get('checked_at')!r} "
                        f"in the {origin})"
                    )
                    continue
                if record.get("ok") is not True:
                    disagreeing.append(f"{source_id} (ok={record.get('ok')!r}, {origin})")
                    continue
                if fetched in accepted:
                    agreeing.append(f"{source_id} fetched ok {fetched.isoformat()} ({origin})")
                else:
                    disagreeing.append(f"{source_id} last fetched {fetched.isoformat()} ({origin})")
            if agreeing:
                outcomes.append(("R-b", CORROBORATED, "; ".join(agreeing)))
            else:
                detail = "; ".join(disagreeing + unreadable) or "no record examined"
                outcomes.append(
                    (
                        "R-b",
                        CONTRADICTED,
                        f"no watched claimant was fetched successfully on "
                        f"{accepted[1].isoformat()} or {accepted[0].isoformat()} — {detail}",
                    )
                )

        # R-c --------------------------------------------------------------
        version_claimants = [s for s in watching if watched[s].get("mode") == "version"]
        if kind != "cross-walk row" or not version_claimants:
            outcomes.append(
                ("R-c", NOT_APPLICABLE, "not a cross-walk row backed by a version-mode source")
            )
        elif edition_index is None:
            outcomes.append(
                (
                    "R-c",
                    CONTRADICTED,
                    f"the cross-walk has no '{EDITION_COLUMN}' column, so the cited edition "
                    "could not be read. This is not a clean result.",
                )
            )
        elif identifier not in edition_cells:
            outcomes.append(
                (
                    "R-c",
                    CONTRADICTED,
                    f"no '{EDITION_COLUMN}' cell could be read for this row",
                )
            )
        else:
            years = EDITION_YEAR.findall(edition_cells[identifier])
            if not years:
                outcomes.append(
                    ("R-c", NOT_APPLICABLE, f"no edition year stated in '{EDITION_COLUMN}'")
                )
            else:
                captured: list[str] = []
                for source_id in version_claimants:
                    record, origin = fetch_record(source_id)
                    tokens = ((record or {}).get("signals") or {}).get("versions")
                    if not isinstance(tokens, list):
                        captured.append(f"!{source_id}:{origin}")
                        continue
                    captured.extend(str(token) for token in tokens)
                unreadable = [c for c in captured if c.startswith("!")]
                tokens = [c for c in captured if not c.startswith("!")]
                missing = sorted(
                    {year for year in years if not any(year in token for token in tokens)}
                )
                if unreadable:
                    outcomes.append(
                        (
                            "R-c",
                            CONTRADICTED,
                            "no readable `signals.versions` for "
                            + ", ".join(u[1:] for u in unreadable),
                        )
                    )
                elif missing:
                    outcomes.append(
                        (
                            "R-c",
                            CONTRADICTED,
                            f"the cited edition year(s) {', '.join(missing)} appear in no "
                            f"token captured by {', '.join(version_claimants)} "
                            f"({', '.join(tokens) or 'none'})",
                        )
                    )
                else:
                    outcomes.append(
                        (
                            "R-c",
                            CORROBORATED,
                            f"cited edition {', '.join(years)} present in the tokens captured "
                            f"by {', '.join(version_claimants)}",
                        )
                    )

        line = f"{kind} {identifier} → {day.isoformat()} — " + "; ".join(
            f"{rule} {verdict} ({reason})" for rule, verdict, reason in outcomes
        )
        if any(verdict == CONTRADICTED for _, verdict, _ in outcomes):
            contradictions += 1
            report(line)
        else:
            findings.note("date corroboration: " + line)

    if not contradictions:
        findings.note(
            f"date corroboration: all {len(advanced)} advanced date(s) corroborated"
        )


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
    check_human_only_containment(findings)
    check_doc_counts(findings)
    check_citation_containment(args.evidence, findings)
    check_confidentiality(files, findings)
    check_escalation_direction(args.base_ref, findings, args.bot)
    check_date_corroboration(args.base_ref, findings, args.bot, args.evidence)

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
