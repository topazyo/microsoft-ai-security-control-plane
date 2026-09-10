#!/usr/bin/env python3
"""Tests for the two registry-coverage checks in scripts/validate_bot_pr.py.

Standard library only. Run with `python3 -m unittest discover -s tests`.

These checks answer questions the watcher's own validation cannot, because they
need the matrix as well as the registry: does every row have a source at all,
and do the counts `docs/agent-cadence.md` asserts in prose still hold? Both
failed silently before — rows 12 and 13 were unwatched through a full release
while the doc claimed coverage of "every matrix row", and three of the doc's
figures had drifted, one of them by seven.
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


if __name__ == "__main__":
    unittest.main()
