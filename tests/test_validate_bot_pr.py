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


if __name__ == "__main__":
    unittest.main()
