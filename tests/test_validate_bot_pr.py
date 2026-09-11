#!/usr/bin/env python3
"""Tests for the deterministic gates in scripts/validate_bot_pr.py, and for the
published instructions that must match them.

Standard library only. Run with `python3 -m unittest discover -s tests`.

The two registry-coverage checks came first, and they answer questions the
watcher's own validation cannot, because they need the matrix as well as the
registry: does every row have a source at all, and do the counts
`docs/agent-cadence.md` asserts in prose still hold? Both failed silently before
— rows 12 and 13 were unwatched through a full release while the doc claimed
coverage of "every matrix row", and three of the doc's figures had drifted, one
of them by seven.

The rest of the file grew from the same principle applied to the other gates and
to the prose describing them: the exact-key column contract, the confidentiality
scan's scope, the `--bot` path allowlist, the escalation-direction gate, GitHub
Docs containment, the workflow path filters, the published suite size, and the
contributor-facing command lists. Several of those are not registry checks at
all; what they share is that each was a place where something could report a
pass over work it had not done, or a document could describe a rule the code no
longer had.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


validate = load_script("validate_bot_pr")


class MatrixRowIdTests(unittest.TestCase):
    def test_row_ids_are_read_from_the_committed_matrix(self):
        rows = validate.matrix_row_ids(validate.MATRIX.read_text(encoding="utf-8"))
        self.assertEqual(rows, list(range(1, len(rows) + 1)))
        self.assertGreaterEqual(len(rows), 13)

    def test_a_table_that_cannot_be_parsed_yields_no_rows(self):
        """An unparseable table must yield nothing, so the check fails loudly.

        Returning [] here is what turns a broken table into a reported error in
        check_source_coverage rather than a vacuous pass over zero rows.
        """
        self.assertEqual(validate.matrix_row_ids("# not a matrix\n\nsome prose\n"), [])


class ClaimedRowTests(unittest.TestCase):
    def test_only_integers_are_read_as_matrix_rows(self):
        entries = [{"matrix_rows": [1, 2]}, {"matrix_rows": ["3"]}, {}]
        self.assertEqual(validate.claimed_rows(entries), {1, 2})

    def test_only_strings_are_read_as_crosswalk_rows(self):
        entries = [{"crosswalk_rows": ["NIST row"]}, {"crosswalk_rows": [7]}, {}]
        self.assertEqual(validate.claimed_crosswalk_rows(entries), {"NIST row"})


class ColumnContractTests(unittest.TestCase):
    """`matrix_table_rows` locates the table; `column_indexes` keys it exactly.

    The two use different rules on purpose, and that mismatch was a silent
    fail-open: renaming a header cell to "Last verified (UTC)" still finds
    every data row while resolving no index, so each check body was guarded
    out, every failure counter stayed 0, and the run printed "all 13 row(s)"
    for three checks that examined none. A check that could not run is an
    error, never a pass.
    """

    HEADER = "| # | Capability | Status | Primary source | Last verified |"
    DIVIDER = "|---|---|---|---|---|"
    ROW = "| 1 | Something | **GA** | https://learn.microsoft.com/x | 2026-09-01 |"

    def matrix(self, header: str) -> str:
        return "\n".join([header, self.DIVIDER, self.ROW, ""])

    def check_matrix_against(self, text: str) -> "validate.Findings":
        findings = validate.Findings()
        validate.check_matrix(findings, text=text)
        return findings

    def test_indexes_are_keyed_on_the_exact_header_text(self):
        indexes = validate.column_indexes(self.matrix(self.HEADER))
        self.assertEqual(indexes["Status"], 2)
        self.assertEqual(indexes["Last verified"], 4)

    def test_a_reworded_header_resolves_no_index(self):
        """The precondition for the fail-open, pinned so the fix has a reason."""
        reworded = self.HEADER.replace("Last verified", "Last verified (UTC)")
        indexes = validate.column_indexes(reworded)
        self.assertIsNone(indexes.get("Last verified"))

    def test_the_table_is_still_located_when_a_header_is_reworded(self):
        """Both halves of the mismatch, so neither can be 'fixed' in isolation."""
        reworded = self.HEADER.replace("Last verified", "Last verified (UTC)")
        self.assertEqual(len(validate.matrix_table_rows(self.matrix(reworded))), 1)

    def test_a_clean_matrix_passes_and_notes_what_it_checked(self):
        findings = self.check_matrix_against(self.matrix(self.HEADER))
        self.assertEqual(findings.errors, [])
        self.assertTrue(
            any("status labels: all 1 row(s)" in n for n in findings.notes), findings.notes
        )

    def test_a_reworded_column_is_an_error_not_a_silent_pass(self):
        reworded = self.HEADER.replace("Last verified", "Last verified (UTC)")
        findings = self.check_matrix_against(self.matrix(reworded))
        self.assertTrue(
            any("header column 'Last verified' not found" in e for e in findings.errors),
            findings.errors,
        )

    def test_a_reworded_column_emits_no_reassuring_note(self):
        """The defect was the note, not only the missing error."""
        reworded = self.HEADER.replace("Status", "Status (label)")
        findings = self.check_matrix_against(self.matrix(reworded))
        self.assertEqual([n for n in findings.notes if "status labels" in n], [])

    def test_a_missing_header_does_not_mask_the_other_checks(self):
        """One fault must not hide another.

        An early return here would mean a header rename plus a genuinely
        missing ISO date surface as a single error: the maintainer repairs the
        header, re-runs, and only then learns about the date. That is the same
        masking `orphan_claims` is reported above its own early return to avoid.
        """
        reworded = self.HEADER.replace("Status", "Status (label)")
        undated = self.ROW.replace("2026-09-01", "sometime")
        findings = self.check_matrix_against(
            "\n".join([reworded, self.DIVIDER, undated, ""])
        )
        self.assertTrue(
            any("header column 'Status' not found" in e for e in findings.errors),
            findings.errors,
        )
        self.assertTrue(
            any("no ISO date in 'Last verified'" in e for e in findings.errors),
            findings.errors,
        )

    def test_an_unresolved_column_is_reported_once_not_twice(self):
        """A missing header is one fault, not a header error plus a count error."""
        reworded = self.HEADER.replace("Status", "Status (label)")
        findings = self.check_matrix_against(self.matrix(reworded))
        self.assertEqual(
            [e for e in findings.errors if "have a 'Status' cell to check" in e], []
        )

    def test_the_checks_that_did_run_still_report(self):
        """A disabled check must not silence the ones that worked."""
        reworded = self.HEADER.replace("Status", "Status (label)")
        findings = self.check_matrix_against(self.matrix(reworded))
        self.assertTrue(
            any("last-verified dates: all 1 row(s)" in n for n in findings.notes),
            findings.notes,
        )

    def test_a_row_too_short_to_carry_a_column_is_reported(self):
        text = "\n".join([self.HEADER, self.DIVIDER, self.ROW, "| 2 | Short |", ""])
        findings = self.check_matrix_against(text)
        self.assertTrue(
            any("of 2 capability row(s) have a" in e for e in findings.errors), findings.errors
        )


class ConfidentialityScopeTests(unittest.TestCase):
    """The scan's own note must be scoped to what it read.

    check_confidentiality skips every file that is not `.md`/`.json`, so a
    pull request touching only `scripts/`, `tests/` or `.github/workflows/`
    scanned nothing and still reported "no tenant-shaped identifiers or
    out-of-scope content found" — an unscoped absence claim, which is the one
    thing this repository does not permit itself elsewhere.
    """

    def scan(self, files: list[str]) -> "validate.Findings":
        findings = validate.Findings()
        validate.check_confidentiality(files, findings)
        return findings

    def test_a_python_only_change_does_not_claim_a_clean_scan(self):
        findings = self.scan(["scripts/validate_bot_pr.py"])
        note = " ".join(findings.notes)
        self.assertIn("no changed file this check can read", note)
        self.assertNotIn("no tenant-shaped identifiers or out-of-scope content found", note)

    def test_the_tracked_agent_configuration_is_scanned(self):
        """`.claude/**` is in the workflow's path filters, so it must be read.

        A hooks-only pull request otherwise produced a green `Validate matrix`
        that had read nothing — a present-but-vacuous check, which reads as
        validation the same way an absent one reads as green.
        """
        findings = self.scan(
            [".claude/hooks/instructions-loaded-log.ps1", ".claude/agents/status-adjudicator.md"]
        )
        note = " ".join(findings.notes)
        self.assertIn("across 2 file(s)", note)
        self.assertIn(".claude/hooks/instructions-loaded-log.ps1", note)

    def test_a_workflow_change_is_scanned(self):
        findings = self.scan([".github/workflows/stale-guard.yml"])
        self.assertIn("across 1 file(s)", " ".join(findings.notes))

    def test_a_deleted_file_is_counted_rather_than_dropped(self):
        """Every changed file lands in exactly one bucket.

        A path that is scannable but no longer exists — a deletion, or the old
        side of a rename — used to fall through with no bookkeeping, so
        `scanned + skipped` silently understated the diff and the note could
        claim there was nothing to scan.
        """
        findings = self.scan(["docs/a-file-that-was-deleted.md"])
        note = " ".join(findings.notes)
        self.assertIn("no longer exist and were not read", note)
        self.assertIn("docs/a-file-that-was-deleted.md", note)

    def ipv4_hits(self, text: str) -> list[str]:
        pattern = dict(validate.CONFIDENTIALITY_PATTERNS)["IPv4 address"]
        return [
            m.group(0)
            for m in pattern.finditer(text)
            if not validate.looks_like_a_version(text, m.start())
        ]

    def test_a_real_address_is_still_reported(self):
        """Pin the positive case first: a filter that excludes everything is worse."""
        self.assertEqual(self.ipv4_hits("host at 192.168.0.1 today"), ["192.168.0.1"])

    def test_a_four_part_version_is_not_an_address(self):
        """Idiomatic in the two file types the scan was just widened to cover.

        The guard this replaces was dead code -- it re-tested the match against
        the shape that produced it -- so `ModuleVersion = '1.0.0.0'` in a
        tracked PowerShell hook would have been a hard confidentiality failure.
        """
        self.assertEqual(self.ipv4_hits("ModuleVersion = '1.0.0.0'"), [])
        self.assertEqual(self.ipv4_hits("ver 1.0.0.0"), [])

    def test_an_impossible_octet_is_not_an_address(self):
        self.assertEqual(self.ipv4_hits("build 999.1.2.3"), [])

    def test_a_v_initial_word_does_not_suppress_a_real_address(self):
        """The hole an earlier, wider form of this filter opened.

        It allowed 12 free characters after a bare `\\bv`, so any v-initial
        word within that window disabled the confidentiality check for the
        address after it -- and "VPN", "VM" and "via" are all idiomatic in this
        domain. A filter in a confidentiality gate that quietly widens is worse
        than no filter at all, so each of these is pinned.
        """
        for text, expected in (
            ("VPN gateway 10.0.0.1", "10.0.0.1"),
            ("the connector VM at 10.0.0.5", "10.0.0.5"),
            ("traffic via 10.1.2.3", "10.1.2.3"),
            ("value 10.2.3.4", "10.2.3.4"),
            ("vendor: 10.9.8.7", "10.9.8.7"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.ipv4_hits(text), [expected])

    def test_only_an_adjacent_version_marker_suppresses(self):
        for text in ("version 1.0.0.0", "ver=1.0.0.0", "v1.0.0.0", "ModuleVersion = '1.0.0.0'"):
            with self.subTest(text=text):
                self.assertEqual(self.ipv4_hits(text), [])

    def test_the_committed_hooks_and_workflows_are_clean_under_the_widened_scan(self):
        """The widening must not redden the tree it was added for."""
        findings = self.scan(
            [
                ".claude/hooks/instructions-loaded-log.ps1",
                ".claude/hooks/postcompact-wrap-up.ps1",
                ".github/workflows/source-watch.yml",
                ".github/workflows/monthly-refresh.yml",
                ".github/workflows/stale-guard.yml",
                ".github/workflows/validate-matrix.yml",
            ]
        )
        self.assertEqual(findings.errors, [])

    def test_the_no_diff_fallback_reads_the_machine_written_state(self):
        """With no diff this list is the whole scan.

        `fingerprints.json` is machine-written and holds text taken verbatim
        from upstream pages, so it is the file most worth scanning — and on a
        push whose base ref resolves to the pushed commit, the fallback is all
        that runs.
        """
        findings = self.scan([])
        note = " ".join(findings.notes)
        self.assertIn(".github/watch-state/fingerprints.json", note)
        self.assertIn(".github/watch-state/sources.json", note)

    def test_a_markdown_change_names_the_files_it_read(self):
        findings = self.scan(["docs/agent-cadence.md"])
        note = " ".join(findings.notes)
        self.assertIn("across 1 file(s)", note)
        self.assertIn("docs/agent-cadence.md", note)

    def test_skipped_changed_files_are_named_rather_than_ignored(self):
        findings = self.scan(["docs/agent-cadence.md", "scripts/stale_guard.py"])
        note = " ".join(findings.notes)
        self.assertIn("outside this check", note)
        self.assertIn("scripts/stale_guard.py", note)


class PathAllowlistTests(unittest.TestCase):
    """In --bot mode the allowlist is the gate, so an empty diff is a failure.

    The bot workflows diff `origin/<ref>...HEAD`, which sees committed work
    only, so an adjudicator whose edits were still uncommitted cleared the one
    check that confines it to its allowed paths.
    """

    def check(self, files: list[str], bot: bool) -> "validate.Findings":
        findings = validate.Findings()
        validate.check_paths(files, findings, bot=bot)
        return findings

    def test_an_empty_diff_with_uncommitted_work_is_an_error_in_bot_mode(self):
        """The dangerous case: edits the diff cannot see.

        `check_escalation_direction` reads the working tree for its "after"
        state while the allowlist reads the committed diff, so uncommitted
        edits are judged by the label gate and skipped by the allowlist.
        """
        original = validate.uncommitted_governed_changes
        validate.uncommitted_governed_changes = lambda: " M matrix/capability-status-matrix.md"
        try:
            findings = self.check([], bot=True)
        finally:
            validate.uncommitted_governed_changes = original
        self.assertTrue(
            any("the allowlist did not run over them" in e for e in findings.errors),
            findings.errors,
        )
        self.assertTrue(
            any("matrix/capability-status-matrix.md" in e for e in findings.errors),
            findings.errors,
        )

    def test_an_empty_diff_with_no_governed_changes_is_not_an_error_in_bot_mode(self):
        """Writing nothing is often the correct automated outcome.

        The adjudicator's permission table requires an issue and never a pull
        request for a move out of "Requires further validation", so failing an
        empty diff would manufacture a red daily run on exactly the path
        operators most need to trust.
        """
        original = validate.uncommitted_governed_changes
        validate.uncommitted_governed_changes = lambda: ""
        try:
            findings = self.check([], bot=True)
        finally:
            validate.uncommitted_governed_changes = original
        self.assertEqual(findings.errors, [])
        self.assertTrue(
            any("no automated change was committed" in n for n in findings.notes),
            findings.notes,
        )

    def test_an_uninspectable_tree_is_not_reported_as_clean(self):
        """"Clean" and "could not look" must not be the same answer.

        A failing `git status` is exactly the case where uncommitted edits are
        invisible to both the diff and this probe -- the situation the check
        exists to catch -- so answering with a reassuring note would assert a
        state nobody observed.
        """
        original = validate.uncommitted_governed_changes
        validate.uncommitted_governed_changes = lambda: None
        try:
            findings = self.check([], bot=True)
        finally:
            validate.uncommitted_governed_changes = original
        self.assertTrue(
            any("could not be inspected" in e for e in findings.errors), findings.errors
        )
        self.assertEqual(findings.notes, [])

    def test_the_dirtiness_probe_is_scoped_to_governed_paths(self):
        """Unscoped, it was dirty on every single automated run.

        `git status --porcelain` reports untracked files, and both bot
        workflows leave an untracked `evidence/` directory inside the checkout.
        An unscoped probe therefore failed the exact correct-outcome path the
        check exists to keep green. This asserts the pathspec is really passed,
        against the real subprocess call rather than a stand-in.
        """
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command

            class Result:
                stdout = ""

            return Result()

        original = validate.subprocess.run
        validate.subprocess.run = fake_run
        try:
            validate.uncommitted_governed_changes()
        finally:
            validate.subprocess.run = original
        self.assertIn("--", seen["command"])
        for governed in validate.GOVERNED_PATHS:
            with self.subTest(path=governed):
                self.assertIn(governed, seen["command"])

    def test_the_governed_paths_match_the_allowlist(self):
        """The pathspec and PATH_ALLOWLIST must describe the same content.

        If they drift, the probe either misses an edit the allowlist governs or
        trips on one it does not.
        """
        # The allowlist is extension-specific -- `.github/watch-state` admits
        # `.json` only, the content directories `.md` -- so the probe uses the
        # extension each path actually carries.
        suffixes = {".github/watch-state": ".json"}
        for governed in validate.GOVERNED_PATHS:
            if governed.endswith(".md"):
                probe = governed
            else:
                probe = f"{governed}/x{suffixes.get(governed, '.md')}"
            with self.subTest(path=probe):
                self.assertTrue(
                    any(p.match(probe) for p in validate.PATH_ALLOWLIST),
                    f"{probe} is in GOVERNED_PATHS but not PATH_ALLOWLIST",
                )

    def test_the_evidence_bundle_is_ignored_rather_than_merely_unscoped(self):
        """Belt and braces: the artifact must not be committable either.

        Scoping the probe stops it failing the run; gitignoring the bundle
        stops an adjudicator's `git add -A` committing upstream page text to a
        path outside the allowlist.
        """
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("evidence/", ignored)

    def test_an_empty_diff_is_only_a_note_for_a_human(self):
        findings = self.check([], bot=False)
        self.assertEqual(findings.errors, [])
        self.assertTrue(
            any("no changed files to check" in n for n in findings.notes), findings.notes
        )

    def test_a_path_outside_the_allowlist_is_an_error_in_bot_mode(self):
        findings = self.check(["scripts/watch_sources.py"], bot=True)
        self.assertTrue(
            any("outside the paths an automated change may modify" in e for e in findings.errors),
            findings.errors,
        )

    def test_a_path_outside_the_allowlist_is_reported_not_enforced_for_a_human(self):
        findings = self.check(["scripts/watch_sources.py"], bot=False)
        self.assertEqual(findings.errors, [])
        self.assertTrue(
            any("human change - not enforced" in n for n in findings.notes), findings.notes
        )


class CrosswalkRowNameTests(unittest.TestCase):
    """The authoritative list of cross-walk row names, derived not assumed.

    `crosswalk_rows` values are free strings, so before this there was nothing
    to check them against. They are not arbitrary: each is the framework's own
    name in the "Framework versions cited" table of
    crosswalk/framework-crosswalk.md plus a fixed suffix -- the same first
    column scripts/stale_guard.py already treats as that table's row
    identifier, which is why the two scripts now agree on what a cross-walk
    row is called.
    """

    EXPECTED = {
        "OWASP Top 10 for LLM Applications framework-versions row",
        "MITRE ATLAS framework-versions row",
        "NIST AI 600-1 framework-versions row",
        "CSA AI Controls Matrix (AICM) framework-versions row",
    }

    def names(self) -> set[str]:
        return validate.crosswalk_row_names(validate.CROSSWALK.read_text(encoding="utf-8"))

    def test_names_are_derived_from_the_committed_crosswalk(self):
        """Subset, not equality: adding a framework row is legitimate and
        unclaimed cross-walk rows are deliberately allowed. Deleting,
        renaming, or mis-parsing any of these four still fails, which is the
        property the parser needs pinned."""
        self.assertLessEqual(self.EXPECTED, self.names())

    def test_every_registered_crosswalk_claim_is_one_of_them(self):
        registry = validate.load_registry(validate.Findings())
        claimed = validate.claimed_crosswalk_rows(
            registry["sources"] + registry["human_only_sources"]
        )
        self.assertEqual(claimed - self.names(), set())

    def test_an_unparseable_table_yields_no_names(self):
        """Empty must become a loud error upstream, not 'nothing to check'."""
        self.assertEqual(validate.crosswalk_row_names("# no table here\n\nprose\n"), set())

    def test_the_item_level_crosswalk_table_is_not_mistaken_for_it(self):
        """Only the framework-versions table may define these names."""
        text = (
            "| Microsoft control (matrix row) | OWASP LLM 2026 item | Notes (synthesis) |\n"
            "|---|---|---|\n"
            "| Row 1 - something | LLM02:2026 | prose |\n"
        )
        self.assertEqual(validate.crosswalk_row_names(text), set())

    def test_a_blank_line_inside_the_table_does_not_truncate_it(self):
        """The two parsers must agree on what a cross-walk row is called.

        `stale_guard.parse_table_dates` skips blank lines inside a table. This
        one used to stop at the first, so a stray line after the first data row
        left it seeing one name while the guard still saw four -- and three
        legitimate registry entries would have been reported as claiming
        cross-walk rows that do not exist, blaming the registry for a stray line
        in a markdown file.
        """
        text = (
            "| Framework | Version / edition cited | Primary source | Last verified |\n"
            "|---|---|---|---|\n"
            "| First Framework | v1 | url | 2026-01-01 |\n"
            "\n"
            "| Second Framework | v2 | url | 2026-01-02 |\n"
        )
        self.assertEqual(
            validate.crosswalk_row_names(text),
            {
                "First Framework framework-versions row",
                "Second Framework framework-versions row",
            },
        )

    def test_a_second_table_under_the_same_heading_is_not_absorbed(self):
        """Skipping blank lines must not let a following table in.

        Markdown separates adjacent tables with a blank line -- exactly the
        construct that no longer ends the scan -- so without a width check the
        second table's rows, and its `|---|---|` separator, would become valid
        `crosswalk_rows` values that `stale_guard` never tracks.
        """
        text = (
            "| Framework | Version / edition cited | Primary source | Last verified |\n"
            "|---|---|---|---|\n"
            "| Real Framework | v1 | url | 2026-01-01 |\n"
            "\n"
            "| Other column | Second |\n"
            "|---|---|\n"
            "| Not A Framework | x |\n"
        )
        self.assertEqual(
            validate.crosswalk_row_names(text), {"Real Framework framework-versions row"}
        )

    def test_a_separator_row_never_becomes_a_name(self):
        text = (
            "| Framework | Version / edition cited | Primary source | Last verified |\n"
            "|---|---|---|---|\n"
            "| Real Framework | v1 | url | 2026-01-01 |\n"
            "\n"
            "|---|---|---|---|\n"
        )
        self.assertNotIn("--- framework-versions row", validate.crosswalk_row_names(text))

    def test_the_two_parsers_agree_on_the_committed_crosswalk(self):
        """Asserted against the real file, both directions, no hard-coded list."""
        guard = load_script("stale_guard")
        text = validate.CROSSWALK.read_text(encoding="utf-8")
        from_guard = {
            identifier + validate.CROSSWALK_ROW_SUFFIX
            for identifier, _ in guard.parse_table_dates(text, "Last verified")
        }
        self.assertEqual(from_guard, validate.crosswalk_row_names(text))

    def test_parsing_stops_at_the_end_of_the_table(self):
        text = (
            "| Framework | Version / edition cited | Primary source | Last verified |\n"
            "|---|---|---|---|\n"
            "| Some Framework | v1 | url | 2026-01-01 |\n"
            "\n"
            "> A blockquote that is not a framework.\n"
        )
        self.assertEqual(
            validate.crosswalk_row_names(text), {"Some Framework framework-versions row"}
        )


class OrphanClaimTests(unittest.TestCase):
    """The converse of the coverage check: a claim that points at nothing.

    `check_source_coverage` asked only "is every matrix row claimed?", so
    `"matrix_rows": [99]` on a thirteen-row matrix passed every gate and both
    scripts exited 0. Every consumer of the claimed sets filters by the matrix,
    so a matrix orphan changed no output at all; a cross-walk orphan is
    filtered by nothing and inflates a published count.

    These are the break tests. The orphan registry is injected as a dict
    through check_source_coverage's `registry` parameter -- the matrix and the
    cross-walk are still read from the committed files -- because the defect is
    a registry state this repository must never be in, so it cannot be
    exercised against the tree as committed.
    """

    def registry(
        self,
        extra_matrix=(),
        extra_crosswalk=(),
        drop_row=None,
        human_matrix=(),
        human_crosswalk=(),
    ):
        rows = validate.matrix_row_ids(validate.MATRIX.read_text(encoding="utf-8"))
        claimed = [r for r in rows if r != drop_row]
        return {
            "sources": [
                {
                    "id": "watched",
                    "matrix_rows": claimed + list(extra_matrix),
                    "crosswalk_rows": list(extra_crosswalk),
                }
            ],
            "human_only_sources": [
                {
                    "id": "human-only",
                    "matrix_rows": list(human_matrix),
                    "crosswalk_rows": list(human_crosswalk),
                }
            ],
        }

    def coverage(self, registry) -> "validate.Findings":
        findings = validate.Findings()
        validate.check_source_coverage(findings, registry=registry)
        return findings

    def test_a_clean_registry_still_passes(self):
        """A gate that cannot pass is a tripwire; pin the negative case first."""
        findings = self.coverage(
            self.registry(extra_crosswalk=["MITRE ATLAS framework-versions row"])
        )
        self.assertEqual(findings.errors, [])

    def test_a_claim_on_a_matrix_row_that_does_not_exist_is_an_error(self):
        findings = self.coverage(self.registry(extra_matrix=[99]))
        self.assertTrue(
            any("entry 'watched' (sources) claims matrix row 99" in e for e in findings.errors),
            findings.errors,
        )

    def test_a_human_only_entry_is_checked_too(self):
        """Both arrays, or the array that backs the residue is the unchecked one."""
        findings = self.coverage(self.registry(human_matrix=[99]))
        self.assertTrue(
            any(
                "entry 'human-only' (human_only_sources) claims matrix row 99" in e
                for e in findings.errors
            ),
            findings.errors,
        )

    def test_a_claim_on_a_crosswalk_row_that_does_not_exist_is_an_error(self):
        findings = self.coverage(
            self.registry(human_crosswalk=["Imaginary Framework framework-versions row"])
        )
        self.assertTrue(
            any(
                "claims cross-walk row 'Imaginary Framework framework-versions row'" in e
                for e in findings.errors
            ),
            findings.errors,
        )

    def test_a_typo_of_an_existing_crosswalk_name_is_caught(self):
        """The quietest case, and the one that passed before this check.

        A typo of an existing human-only name keeps the residue set's
        cardinality, so the derived 'N of the dated items' count stays 4 and
        check_doc_counts stays green while the registry names a row that does
        not exist.
        """
        findings = self.coverage(
            self.registry(human_crosswalk=["NIST AI 600-01 framework-versions row"])
        )
        self.assertTrue(
            any("NIST AI 600-01 framework-versions row" in e for e in findings.errors),
            findings.errors,
        )

    def test_an_orphan_is_reported_alongside_a_genuine_gap(self):
        """Ordering: `if uncovered: return` must not mask the orphan.

        Renumbering a row is the likeliest way to create an orphan and it
        creates both faults in one edit, so if the orphan check sat below that
        early return the masking case would be the common case -- the
        maintainer would close the visible gap and leave the stale claim.
        """
        rows = validate.matrix_row_ids(validate.MATRIX.read_text(encoding="utf-8"))
        last = rows[-1]
        findings = self.coverage(self.registry(extra_matrix=[99], drop_row=last))
        self.assertTrue(
            any(f"matrix row {last} is claimed by no entry" in e for e in findings.errors),
            findings.errors,
        )
        self.assertTrue(
            any("claims matrix row 99" in e for e in findings.errors), findings.errors
        )

    def test_an_error_suppresses_the_coverage_notes(self):
        """No reassuring note beside a failure.

        The residue note is a set difference with no authoritative filter of
        its own, so an orphan cross-walk claim would make the note assert a
        dated item that does not exist.
        """
        findings = self.coverage(self.registry(extra_matrix=[99]))
        self.assertEqual(findings.notes, [])

    def test_an_unreadable_crosswalk_fails_rather_than_skips(self):
        """A parse failure must not degrade to a vacuous pass."""
        original = validate.CROSSWALK
        validate.CROSSWALK = validate.REPO_ROOT / "crosswalk" / "does-not-exist.md"
        try:
            findings = self.coverage(self.registry())
        finally:
            validate.CROSSWALK = original
        self.assertTrue(any("not found" in e for e in findings.errors), findings.errors)


class LiveRepositoryTests(unittest.TestCase):
    """The committed repository must pass both checks.

    Written against the real files deliberately: these two checks exist to catch
    drift between three files that are edited separately, and a test on fixtures
    only would not notice that drift.
    """

    def run_check(self, check) -> validate.Findings:
        findings = validate.Findings()
        check(findings)
        return findings

    def test_every_matrix_row_is_claimed_by_a_registry_entry(self):
        findings = self.run_check(validate.check_source_coverage)
        self.assertEqual(findings.errors, [])

    def test_the_human_only_residue_is_reported_on_every_run(self):
        """The invariant needed to read stale_guard output correctly."""
        findings = self.run_check(validate.check_source_coverage)
        residue = [n for n in findings.notes if "human-only sources" in n]
        self.assertEqual(len(residue), 1)
        self.assertIn("[12, 13]", residue[0])
        self.assertIn("can never be advanced by an agent run", residue[0])

    def test_the_documented_counts_match_the_repository(self):
        findings = self.run_check(validate.check_doc_counts)
        self.assertEqual(findings.errors, [])

    def test_every_documented_count_claim_is_present_in_the_doc(self):
        """A removed sentence must fail, not silently disable the check."""
        doc = validate.CADENCE_DOC.read_text(encoding="utf-8")
        for name, pattern in validate.DOC_COUNT_CLAIMS:
            with self.subTest(claim=name):
                self.assertTrue(pattern.search(doc), f"no '{name}' claim in the checked form")


class DocumentedTestCommandTests(unittest.TestCase):
    """The command `docs/agent-cadence.md` publishes must be the one CI runs.

    It was not. The doc shipped `python3 -m unittest discover -s tests -t .`,
    which fails with `ImportError: Start directory is not importable` because
    `tests/` has no `__init__.py`, while the workflow ran the working form — so
    CI stayed green and only the human following the documentation hit the
    error. Same failure class as the drifted counts above: an instruction
    nobody executes is not checked by being written down.
    """

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validate-matrix.yml"
    COMMAND = re.compile(r"python3? -m unittest discover[^\n#]*")

    def documented_command(self) -> str:
        found = self.COMMAND.findall(validate.CADENCE_DOC.read_text(encoding="utf-8"))
        self.assertEqual(len(found), 1, "expected exactly one published unittest command")
        return " ".join(found[0].split())

    def workflow_command(self) -> str:
        found = self.COMMAND.findall(self.WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(len(found), 1, "expected exactly one unittest command in the workflow")
        return " ".join(found[0].split())

    def test_the_documented_command_matches_the_one_ci_runs(self):
        """Equal apart from -v, which is a CI log-verbosity choice, not a flag."""
        self.assertEqual(
            self.documented_command(),
            self.workflow_command().replace(" -v", ""),
        )

    def test_the_documented_command_does_not_use_an_unimportable_top_level(self):
        """`-t .` is the exact spelling that shipped broken. Pin it."""
        self.assertNotIn("-t .", self.documented_command())


class EscalationDirectionTests(unittest.TestCase):
    """The repository's hardest control, and both of its fail-open doors.

    A row may never be moved out of "Requires further validation" by an
    automated run. The column-resolution door was closed earlier in this branch;
    the row-lookup door was still open. `new.get(row_id, [])` returned an empty
    list for a row that could not be found, `if new_labels and ...`
    short-circuited, and the run printed "no row moved out of 'Requires further
    validation'" over a comparison it never made -- so renaming the identifier
    was enough to escape the check, and `matrix_row_ids` strips non-digits, so
    `5` -> `5a` left `check_source_coverage` clean as well.
    """

    HEADER = "| # | Capability | Status | Primary source | Last verified |"
    DIVIDER = "|---|---|---|---|---|"

    def matrix(self, identifier: str, status: str) -> str:
        row = f"| {identifier} | Thing | {status} | https://learn.microsoft.com/x | 2026-09-01 |"
        return "\n".join([self.HEADER, self.DIVIDER, row, ""])

    def check(self, before: str, after: str, bot: bool = True) -> "validate.Findings":
        findings = validate.Findings()
        validate.check_escalation_direction(
            "base", findings, bot, before_text=before, after_text=after
        )
        return findings

    def test_an_unchanged_row_passes(self):
        text = self.matrix("5", "**Requires further validation**")
        findings = self.check(text, text)
        self.assertEqual(findings.errors, [])
        self.assertTrue(
            any("no row moved out" in n for n in findings.notes), findings.notes
        )

    def test_a_direct_transition_is_caught(self):
        findings = self.check(
            self.matrix("5", "**Requires further validation**"), self.matrix("5", "**GA**")
        )
        self.assertTrue(
            any("was moved out of 'Requires further validation'" in e for e in findings.errors),
            findings.errors,
        )

    def test_renaming_the_identifier_does_not_escape_the_check(self):
        """The fail-open: `5` -> `5a` used to be a silent pass."""
        findings = self.check(
            self.matrix("5", "**Requires further validation**"), self.matrix("5a", "**GA**")
        )
        self.assertTrue(
            any("no row with that identifier exists" in e for e in findings.errors),
            findings.errors,
        )

    def test_deleting_the_row_does_not_escape_the_check(self):
        findings = self.check(
            self.matrix("5", "**Requires further validation**"),
            "\n".join([self.HEADER, self.DIVIDER, ""]),
        )
        self.assertTrue(
            any("no row with that identifier exists" in e for e in findings.errors),
            findings.errors,
        )

    def test_an_unreadable_status_cell_does_not_escape_the_check(self):
        findings = self.check(
            self.matrix("5", "**Requires further validation**"), self.matrix("5", "")
        )
        self.assertTrue(
            any("yields no legend label" in e for e in findings.errors), findings.errors
        )

    def test_no_reassuring_note_beside_any_of_them(self):
        for after in (
            self.matrix("5a", "**GA**"),
            self.matrix("5", ""),
            "\n".join([self.HEADER, self.DIVIDER, ""]),
        ):
            with self.subTest(after=after[:40]):
                findings = self.check(self.matrix("5", "**Requires further validation**"), after)
                self.assertEqual(
                    [n for n in findings.notes if "no row moved out" in n], []
                )

    def test_a_human_gets_a_note_rather_than_a_hard_failure(self):
        """Only an automated run is blocked; a human may have done the work."""
        findings = self.check(
            self.matrix("5", "**Requires further validation**"),
            self.matrix("5", "**GA**"),
            bot=False,
        )
        self.assertEqual(findings.errors, [])
        self.assertTrue(
            any("Reviewer must confirm" in n for n in findings.notes), findings.notes
        )


class HumanOnlyContainmentTests(unittest.TestCase):
    """GitHub Docs may be cited, but never watched.

    The README and the new-row-proposal template both publish this to
    contributors as a guarantee -- "registered under `human_only_sources`, never
    under `sources`" -- while nothing enforced it. Per the registry's own
    reason the page is "perfectly fetchable, and that is exactly why the rule
    matters": the containment is what keeps non-Learn page content away from the
    model tier entirely.
    """

    def check(self, registry: dict) -> "validate.Findings":
        findings = validate.Findings()
        validate.check_human_only_containment(findings, registry=registry)
        return findings

    def test_the_committed_registry_passes(self):
        findings = validate.Findings()
        validate.check_human_only_containment(findings)
        self.assertEqual(findings.errors, [])

    def test_a_github_docs_url_in_the_watched_array_is_an_error(self):
        findings = self.check(
            {
                "sources": [
                    {"id": "sneaky", "url": "https://docs.github.com/en/copilot/x"}
                ],
                "human_only_sources": [],
            }
        )
        self.assertTrue(
            any("is a docs.github.com source in the watched" in e for e in findings.errors),
            findings.errors,
        )

    def test_a_github_docs_cite_url_is_caught_too(self):
        """A watched entry can carry a fetch URL and a different citation URL."""
        findings = self.check(
            {
                "sources": [
                    {
                        "id": "sneaky",
                        "url": "https://raw.githubusercontent.com/x/y",
                        "cite_url": "https://docs.github.com/en/copilot/x",
                    }
                ],
                "human_only_sources": [],
            }
        )
        self.assertTrue(any("cite_url" in e for e in findings.errors), findings.errors)

    def test_a_human_only_github_docs_source_is_fine(self):
        """The permitted placement must not be reported."""
        findings = self.check(
            {
                "sources": [],
                "human_only_sources": [
                    {"id": "gh", "cite_url": "https://docs.github.com/en/copilot/x"}
                ],
            }
        )
        self.assertEqual(findings.errors, [])

    def test_the_citation_allowlist_and_the_gate_share_one_pattern(self):
        """Or the condition could drift away from the admission it qualifies."""
        self.assertIn(validate.GITHUB_DOCS_HOST, validate.ALLOWED_SOURCE_HOSTS)


class PublishedTestCountTests(unittest.TestCase):
    """A test total stated in prose must be derived, not transcribed.

    `CHANGELOG.md` advertises the size of this suite. That number was written by
    hand and was wrong within one commit -- the entry said 196 while the suite
    ran 208 -- which is the same defect class `check_doc_counts` exists to stop
    for the registry-derived figures, in the one place no check was looking.

    Pinning it here rather than in `DOC_COUNT_CLAIMS` because the count is a
    property of the test tree, not of the registry, and this is the only file
    that can ask the loader for it.
    """

    CHANGELOG = REPO_ROOT / "CHANGELOG.md"
    CLAIM = re.compile(r"The suite is \*\*(\d+)\*\* tests")

    def discovered(self) -> int:
        """The number of tests unittest actually collects."""
        loader = unittest.TestLoader()
        suite = loader.discover(str(REPO_ROOT / "tests"), top_level_dir=str(REPO_ROOT / "tests"))
        self.assertEqual(loader.errors, [], "test discovery reported import errors")
        return suite.countTestCases()

    def test_the_changelog_states_the_suite_size_in_the_checked_form(self):
        """A removed sentence must fail, not silently disable the check."""
        self.assertIsNotNone(
            self.CLAIM.search(self.CHANGELOG.read_text(encoding="utf-8")),
            "CHANGELOG.md no longer states the suite size in the checked form; "
            "the sentence may be reworded but not removed",
        )

    def test_the_published_suite_size_matches_the_suite(self):
        stated = self.CLAIM.search(self.CHANGELOG.read_text(encoding="utf-8"))
        self.assertEqual(int(stated.group(1)), self.discovered())

    def test_the_matrix_heading_row_count_is_derived(self):
        """The heading advertises a row count that only a human re-derives.

        CONTRIBUTING has to ask for it to be "re-derived by counting the table",
        which is the instruction-in-prose pattern `check_doc_counts` exists to
        replace. The authoritative count is already computed by
        `matrix_row_ids`.
        """
        text = validate.MATRIX.read_text(encoding="utf-8")
        heading = re.search(r"^## The matrix \([^)]*?(\d+) rows", text, re.MULTILINE)
        self.assertIsNotNone(heading, "the matrix heading no longer states a row count")
        self.assertEqual(int(heading.group(1)), len(validate.matrix_row_ids(text)))

    def test_the_documented_phrase_count_matches_the_watcher(self):
        """"Nine status-bearing phrases" is asserted in two files and derived in none.

        It drifts silently the moment a phrase is added to or removed from
        `STATUS_PHRASES`, in a file neither sentence lives in.
        """
        watch = load_script("watch_sources")
        expected = len(watch.STATUS_PHRASES)
        words = {
            1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
            6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
        }
        # Two files, two spellings: "nine status-bearing phrases" in the matrix
        # and "nine status phrases" in the cadence doc.
        stated = re.compile(r"which of (\w+) status(?:[- ]bearing)? phrases")
        found = 0
        for path in (validate.CADENCE_DOC, validate.MATRIX):
            for match in stated.finditer(path.read_text(encoding="utf-8")):
                found += 1
                with self.subTest(document=path.name, stated=match.group(1)):
                    self.assertEqual(match.group(1), words.get(expected, str(expected)))
        self.assertGreaterEqual(found, 2, "the phrase-count sentence has moved or gone")


class PathFilterTests(unittest.TestCase):
    """The two trigger lists in validate-matrix.yml must stay identical.

    They were not: `.github/watch-state/**` sat in the `pull_request` list and
    was missing from the `push` list, so a class of push to main ran no
    validation at all. The remedy for that was a comment saying the lists must
    match -- which is the same unguarded-prose failure the drift itself was, one
    level up. The next entry added to one list and not the other reproduces the
    silent skip, and an absent check reads as a green one.
    """

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validate-matrix.yml"

    def paths_for(self, event: str) -> list[str]:
        """The `paths:` list under `on.<event>`, read as text.

        Text rather than a YAML parser because the suite is stdlib-only, and
        the same precedent is already set by DocumentedTestCommandTests.
        """
        lines = self.WORKFLOW.read_text(encoding="utf-8").splitlines()
        start = next(
            (i for i, l in enumerate(lines) if l.strip() == f"{event}:"), None
        )
        self.assertIsNotNone(start, f"no `{event}:` trigger in {self.WORKFLOW.name}")
        collected: list[str] = []
        in_paths = False
        for line in lines[start + 1 :]:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped == "paths:":
                in_paths = True
                continue
            if in_paths:
                if stripped.startswith("- "):
                    collected.append(stripped[2:].strip().strip("'\""))
                    continue
                break
            if not line.startswith(" " * 2) or stripped.endswith(":") and not line.startswith(" " * 4):
                break
        self.assertTrue(collected, f"no paths parsed for `{event}`")
        return collected

    CONTRIBUTOR_DOCS = (
        REPO_ROOT / "CONTRIBUTING.md",
        REPO_ROOT / ".github" / "pull_request_template.md",
        REPO_ROOT / "SECURITY.md",
    )

    def test_no_document_states_a_narrower_scan_scope_than_the_code(self):
        """The scan's scope is a published property of a security control.

        It was widened to `.ps1` and `.yml` when `.claude/**` entered the path
        filters, while four reader-facing surfaces went on saying `.md`/`.json`
        only — telling a contributor that a literal address in a tracked hook is
        safe when it now fails the build.
        """
        stale = re.compile(r"`\.md`\s*(?:/|or|and)\s*`\.json`\s*files?")
        for path in self.CONTRIBUTOR_DOCS:
            with self.subTest(document=path.name):
                self.assertIsNone(
                    stale.search(path.read_text(encoding="utf-8")),
                    f"{path.name} still states the pre-widening scan scope",
                )

    def test_the_documented_suffixes_match_the_code(self):
        """Where a document enumerates the suffixes, the list must be the live one."""
        for path in self.CONTRIBUTOR_DOCS:
            text = path.read_text(encoding="utf-8")
            if ".ps1" not in text:
                continue
            for suffix in sorted(validate.SCANNED_SUFFIXES):
                with self.subTest(document=path.name, suffix=suffix):
                    self.assertIn(f"`{suffix}`", text)

    def test_contributing_lists_every_path_filter_it_claims_to(self):
        """A real check reported as absent is the mirror of an absent one.

        A contributor whose pull request touches only `tests/` or `.claude/`
        used to read this list, conclude the check would not appear, and take
        the template's escape hatch.
        """
        text = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        marker = "does not trigger on every path"
        self.assertIn(marker, text)
        section = text[text.index(marker) : text.index(marker) + 900]
        for required in ("tests/", ".claude/", "scripts/", ".github/watch-state/"):
            with self.subTest(path=required):
                self.assertIn(required, section)

    def test_the_two_trigger_lists_are_identical(self):
        self.assertEqual(self.paths_for("pull_request"), self.paths_for("push"))

    def test_both_lists_cover_the_machine_written_state(self):
        """The specific entry whose absence caused the original silent skip."""
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                self.assertIn(".github/watch-state/**", self.paths_for(event))

    def test_both_lists_cover_the_tracked_agent_configuration(self):
        """`.claude/**` holds executable influence surfaces and is tracked."""
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                self.assertIn(".claude/**", self.paths_for(event))


class ContributorInstructionTests(unittest.TestCase):
    """The contributor-facing gate lists must match the gates CI runs.

    `CONTRIBUTING.md` and the pull-request template both listed three validator
    commands while `Validate matrix` ran four: the test suite was missing from
    both for two releases, so a contributor following the instructions could not
    reproduce the gate that would fail their pull request.

    Adding the line is only half a fix. `DocumentedTestCommandTests` above pins
    the command in `docs/agent-cadence.md` against the workflow's, but it reads
    neither of these files -- so without this class the two new lines would be
    unguarded prose, free to drift from CI exactly as the doc's `-t .` spelling
    did. An instruction nobody executes is not checked by being written down.
    """

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validate-matrix.yml"
    TARGETS = (
        REPO_ROOT / "CONTRIBUTING.md",
        REPO_ROOT / ".github" / "pull_request_template.md",
    )
    COMMAND = re.compile(r"python3? -m unittest discover[^\n`)]*")

    @staticmethod
    def normalise(command: str) -> str:
        """Compare the discovery arguments, not the interpreter spelling.

        CI runs `python3` because it runs on Linux; these two documents say
        `python` throughout, which is what a Windows contributor has. That
        difference is deliberate and not drift. `-v` is a CI log-verbosity
        choice, not a flag that changes what runs. Everything else -- above all
        the `-s tests` target, whose `-t .` variant shipped broken -- must match.
        """
        return " ".join(command.split()).replace(" -v", "").replace("python3 ", "python ")

    def ci_command(self) -> str:
        found = self.COMMAND.findall(self.WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(len(found), 1, "expected exactly one unittest command in the workflow")
        return self.normalise(found[0])

    def test_each_contributor_document_lists_the_test_suite(self):
        for path in self.TARGETS:
            with self.subTest(document=path.name):
                found = self.COMMAND.findall(path.read_text(encoding="utf-8"))
                self.assertTrue(found, f"{path.name} does not tell a contributor to run the tests")

    def test_the_listed_command_is_the_one_ci_runs(self):
        expected = self.ci_command()
        for path in self.TARGETS:
            for raw in self.COMMAND.findall(path.read_text(encoding="utf-8")):
                with self.subTest(document=path.name, command=raw):
                    self.assertEqual(self.normalise(raw), expected)

    def test_no_contributor_document_uses_the_unimportable_top_level(self):
        """`-t .` is the exact spelling that shipped broken in the cadence doc."""
        for path in self.TARGETS:
            with self.subTest(document=path.name):
                for raw in self.COMMAND.findall(path.read_text(encoding="utf-8")):
                    self.assertNotIn("-t .", raw)

    def test_neither_document_still_promises_zero_stale_items(self):
        """The replaced wording, pinned so it cannot come back.

        "Expect zero stale items" was false whenever the recurring human step
        was merely due rather than skipped, and an instruction to expect an
        impossible state teaches a reader to scroll past the real findings.
        """
        for path in self.TARGETS:
            with self.subTest(document=path.name):
                # Asterisks stripped so the original "**zero** stale" is caught,
                # and matched on adjacency rather than co-occurrence: the phrase
                # "non-zero requires --fail-on-stale" is a true statement about
                # the exit code and must not trip this.
                text = path.read_text(encoding="utf-8").replace("*", "")
                offenders = [
                    line
                    for line in text.splitlines()
                    if "zero stale" in line and "used to say" not in line
                ]
                self.assertEqual(offenders, [])

    def test_each_document_points_at_where_the_residue_is_enumerated(self):
        """A cross-reference that names no location is not a cross-reference."""
        for path in self.TARGETS:
            with self.subTest(document=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("capability-status-verification.md", text)
                self.assertIn("framework-crosswalk.md", text)

    def test_the_referenced_checklist_actually_enumerates_the_residue(self):
        """And the location it names must still contain the list.

        Otherwise both documents would point a contributor at a section that no
        longer says what they were sent there to read.

        Anchored on the Group 9 *heading*, not on the string "Group 9": the
        first occurrence of that string is a cross-reference inside Group 1, so
        slicing from it covered almost the whole document and every assertion
        below passed against unrelated prose.
        """
        checklist = (
            REPO_ROOT / "checklists" / "capability-status-verification.md"
        ).read_text(encoding="utf-8")
        heading = re.search(r"^\*\*Group 9 [^\n]*$", checklist, re.MULTILINE)
        self.assertIsNotNone(heading, "no Group 9 heading in the checklist")
        rest = checklist[heading.end() :]
        # Stop at the footer stamp, which recaps every group and would otherwise
        # satisfy these assertions on its own.
        footer = re.search(r"^\*Version \d", rest, re.MULTILINE)
        group_nine = rest[: footer.start()] if footer else rest
        self.assertLess(
            len(group_nine), len(checklist) // 2, "the Group 9 slice is not a section"
        )
        for expected in ("12", "13", "NIST", "CSA"):
            with self.subTest(item=expected):
                self.assertIn(expected, group_nine)


if __name__ == "__main__":
    unittest.main()
