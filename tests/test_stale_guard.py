#!/usr/bin/env python3
"""Tests for scripts/stale_guard.py - the tier D4 staleness guard.

Standard library only. Run with `python3 -m unittest discover -s tests`.

The guard decides one thing - which dated items are past the staleness window -
and two published surfaces read that decision. `.github/workflows/stale-guard.yml`
opens or updates the staleness issue only when the `stale` output is the literal
string `true`, and `.github/pull_request_template.md` asks a human to run the
script and read its item list. Until now nothing pinned either the arithmetic or
the output contract.

**Fixtures for behaviour, live files for shape.** Every assertion about a count,
an exit code or an output value runs against a synthetic repository written into
a temporary directory, because the tracked last-verified dates move whenever a
human re-verifies a row: rows 12 and 13 advanced to 2026-09-10 on the day this
file was written, taking the default-window report from 5 items to 3 and the
`--window-days 0` report from 5 to 16. A test asserting "3 stale items" or "18
dated items" would have been wrong twice in one week, and a rotting test teaches
maintainers to edit tests instead of reading them. The committed files are used
only for assertions that survive re-verification: that every target still parses,
that every date is a real calendar date, that every matrix row carries a date the
guard can reach, that the window quoted in the report is the one the registry
declares, and that the window boundary holds for the data actually shipped (with
the boundary date *derived* from the oldest tracked date, never hard-coded).

Fixture repositories are possible because `main()` dereferences `REPO_ROOT` and
`SOURCES_FILE` as module globals at call time, and because the module is loaded
by file location rather than imported from `sys.path` - so patching the module
object reaches the code under test rather than a copy.

**Patch both, always.** `SOURCES_FILE` is *materialised at import* from the real
`REPO_ROOT` (`stale_guard.py:30`), so rebinding `REPO_ROOT` alone leaves it
pointing at the committed registry: the target files would come from the fixture
while the staleness window kept coming from the real repository. A test meaning
to exercise the window-default branch would then pass for the wrong reason.
`GuardRunner` patches both, plus `sys.argv`.

What these tests do NOT cover, stated rather than implied:

  - The real clock. Every run passes `--today`; the `date.today()` default at
    `stale_guard.py:126` is never exercised, and neither is its local-timezone
    behaviour near midnight. A test that read today's item set would rot.
  - How many items are stale in the tracked files, or which ones. That is a
    property of human re-verification, not of this script.
  - A regex-valid but impossible date. `ISO_DATE` accepts `2026-13-45`, which
    then raises ValueError inside `main()`. `test_every_parsed_date_is_a_real_calendar_date`
    keeps the repository out of that state; it does not make the guard survive
    it. The crash is at least loud now: `stale-guard.yml` names `shell: bash`,
    which selects `-eo pipefail`, so the failure is no longer swallowed by the
    `| tee` pipeline, and the issue step gates on `!= 'false'` so an absent
    output does not read as "nothing is stale".
  - GitHub's own consumption of the heredoc form. These tests assert only that
    the script writes it, and not the case where a value contains the literal
    `__EOF__` delimiter (no tracked content can produce one today).
  - A `TARGETS` entry with a mistyped `kind`, which falls through to the footer
    branch and raises KeyError on the absent `pattern`. `TARGETS` is a
    hand-edited module constant, so the failure is loud and immediate.

Fixture hygiene: every fixture string here is synthetic. No tenant-shaped
identifier, no real URL and no third-party page text appears in this file -
`check_confidentiality` skips anything that is not .md or .json, so tests/ is
outside it and the discipline has to be manual.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script(name: str):
    """Load a script by file location, as tests/test_validate_bot_pr.py does.

    Deliberately not a sys.path import: `scripts/` is not a package, and a break
    test is only meaningful if reverting the real file is what the suite sees.
    """
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = load_script("stale_guard")
# Matrix row identifiers are read with the repository's own parser rather than a
# second regex here, so "what counts as a matrix row" keeps a single definition.
validate = load_script("validate_bot_pr")

# Fixture dates. The window arithmetic is the whole point, so they are chosen to
# make it visible: ANCHOR + WINDOW days == AT_WINDOW, and PAST_WINDOW is the day
# after that.
WINDOW = 30
ANCHOR = "2026-01-01"
AT_WINDOW = "2026-01-31"
PAST_WINDOW = "2026-02-01"


def parse_github_output(text: str) -> dict[str, str]:
    """Read a GITHUB_OUTPUT file the way the runner does.

    Single-line values are `key=value`; a multi-line value is a `key<<DELIMITER`
    block terminated by the delimiter on its own line. Body lines are consumed
    inside the block, so a report line containing `=` cannot be misread as a key.
    """
    values: dict[str, str] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        heredoc = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)<<(\S+)", line)
        if heredoc:
            key, delimiter = heredoc.group(1), heredoc.group(2)
            body: list[str] = []
            index += 1
            while index < len(lines) and lines[index] != delimiter:
                body.append(lines[index])
                index += 1
            values[key] = "\n".join(body)
            index += 1
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
        index += 1
    return values


class GuardRunner(unittest.TestCase):
    """Invokes stale_guard.main() against a chosen repository root.

    `main()` reads REPO_ROOT and SOURCES_FILE as module globals at call time and
    parses sys.argv, so all three are patched per run - without the argv patch it
    would parse the unittest runner's own arguments and exit 2. GITHUB_OUTPUT is
    always redirected into the test's temporary directory: the suite runs as a
    step in validate-matrix.yml, where GITHUB_OUTPUT is set, and an unredirected
    run would append `stale`, `report` and `stale_count` to that step's real
    outputs.
    """

    def setUp(self) -> None:
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.workspace = Path(workspace.name)
        self.output_file = self.workspace / "github-output.txt"
        self.repo = self.workspace / "repo"
        self.repo.mkdir()

    # -- fixture writers --------------------------------------------------

    def write(self, relative: str, text: str) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_matrix(self, dates, column: str = "Last verified") -> None:
        rows = "\n".join(
            f"| {number} | Synthetic capability {number} | **GA** | {iso} | fixture row |"
            for number, iso in enumerate(dates, start=1)
        )
        self.write(
            "matrix/capability-status-matrix.md",
            "# Synthetic matrix fixture\n\n"
            f"| # | Capability | Status | {column} | Notes |\n"
            "|---|---|---|---|---|\n"
            f"{rows}\n\n"
            "Prose after the table, so the parser stops here.\n",
        )

    def write_crosswalk(self, dates) -> None:
        rows = "\n".join(
            f"| Synthetic framework {index} | edition {index} | fixture, no URL | {iso} |"
            for index, iso in enumerate(dates, start=1)
        )
        self.write(
            "crosswalk/framework-crosswalk.md",
            "# Synthetic cross-walk fixture\n\n"
            "| Framework | Version / edition cited | Primary source | Last verified |\n"
            "|---|---|---|---|\n"
            f"{rows}\n\n"
            "Prose after the table, so the parser stops here.\n",
        )

    def write_checklist(self, iso: str) -> None:
        self.write(
            "checklists/capability-status-verification.md",
            "# Synthetic checklist fixture\n\n"
            f"*Version 0.0 - Last validated: {iso} - synthetic fixture stamp.*\n",
        )

    def write_registry(self, text: str) -> None:
        self.write(".github/watch-state/sources.json", text)

    def write_repository(
        self,
        matrix=(ANCHOR,),
        crosswalk=(AT_WINDOW,),
        checklist: str = AT_WINDOW,
        column: str = "Last verified",
    ) -> None:
        """All three targets, so nothing lands in the unparsed list by accident."""
        self.write_matrix(matrix, column=column)
        self.write_crosswalk(crosswalk)
        self.write_checklist(checklist)

    # -- invocation -------------------------------------------------------

    def run_guard(self, *argv: str, root: Path | None = None, sources_file: Path | None = None):
        """Return (exit_code, printed_report, github_outputs)."""
        root = self.repo if root is None else root
        if sources_file is None:
            sources_file = root / ".github" / "watch-state" / "sources.json"
        stdout = io.StringIO()
        with (
            mock.patch.object(guard, "REPO_ROOT", root),
            mock.patch.object(guard, "SOURCES_FILE", sources_file),
            mock.patch.object(sys, "argv", ["stale_guard.py", *argv]),
            mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(self.output_file)}),
            contextlib.redirect_stdout(stdout),
        ):
            code = guard.main()
        outputs: dict[str, str] = {}
        if self.output_file.exists():
            outputs = parse_github_output(self.output_file.read_text(encoding="utf-8"))
        return code, stdout.getvalue().strip(), outputs


class ParseTableDatesTests(unittest.TestCase):
    """Synthetic input only. This is where the silent drops live.

    Every row the parser skips is a dated item that vanishes from the guard's
    report without any signal, which is why the live tests below cross-check the
    matrix row-for-row.
    """

    HEADER = "| # | Capability | Status | Last verified | Notes |\n|---|---|---|---|---|\n"

    def test_reads_the_identifier_and_date_from_every_row(self):
        text = (
            self.HEADER
            + "| 1 | Synthetic one | **GA** | 2026-01-01 | note |\n"
            + "| 2 | Synthetic two | **GA** | 2026-02-02 | note |\n"
        )
        self.assertEqual(
            guard.parse_table_dates(text, "Last verified"),
            [("1", "2026-01-01"), ("2", "2026-02-02")],
        )

    def test_a_bolded_header_cell_is_recognised(self):
        """The tracked files use a plain header; the bold branch is live code."""
        text = (
            "| # | **Last verified** |\n|---|---|\n| 1 | 2026-01-01 |\n"
        )
        self.assertEqual(guard.parse_table_dates(text, "Last verified"), [("1", "2026-01-01")])

    def test_a_row_with_too_few_cells_is_skipped(self):
        text = self.HEADER + "| 1 | only two cells |\n| 2 | Synthetic | **GA** | 2026-01-01 | note |\n"
        self.assertEqual(guard.parse_table_dates(text, "Last verified"), [("2", "2026-01-01")])

    def test_a_row_whose_date_cell_holds_no_iso_date_is_skipped(self):
        """A row reading "pending" silently leaves the guard's scope."""
        text = (
            self.HEADER
            + "| 1 | Synthetic | **GA** | not yet verified | note |\n"
            + "| 2 | Synthetic | **GA** | 2026-01-01 | note |\n"
        )
        self.assertEqual(guard.parse_table_dates(text, "Last verified"), [("2", "2026-01-01")])

    def test_a_row_with_an_empty_first_cell_is_reported_as_a_question_mark(self):
        text = self.HEADER + "|  | Synthetic | **GA** | 2026-01-01 | note |\n"
        self.assertEqual(guard.parse_table_dates(text, "Last verified"), [("?", "2026-01-01")])

    def test_a_date_surrounded_by_other_text_is_still_read(self):
        text = self.HEADER + "| 1 | Synthetic | **GA** | 2026-01-01 (re-checked) | note |\n"
        self.assertEqual(guard.parse_table_dates(text, "Last verified"), [("1", "2026-01-01")])

    def test_a_table_without_the_column_yields_nothing(self):
        """Returning [] is what makes main() report the file as unreadable."""
        text = "| # | Last checked |\n|---|---|\n| 1 | 2026-01-01 |\n"
        self.assertEqual(guard.parse_table_dates(text, "Last verified"), [])
        self.assertEqual(guard.parse_table_dates("# prose only\n\nno table here\n", "Last verified"), [])

    def test_blank_lines_are_tolerated_and_prose_ends_the_table(self):
        text = (
            self.HEADER
            + "| 1 | Synthetic | **GA** | 2026-01-01 | note |\n"
            + "\n"
            + "| 2 | Synthetic | **GA** | 2026-02-02 | note |\n"
            + "\nProse ends the table.\n\n"
            + "| 3 | Synthetic | **GA** | 2026-03-03 | note |\n"
        )
        self.assertEqual(
            guard.parse_table_dates(text, "Last verified"),
            [("1", "2026-01-01"), ("2", "2026-02-02")],
        )

    def test_a_second_table_separated_only_by_a_blank_line_is_also_read(self):
        """Documents, rather than endorses, what "the table" means here.

        Parsing stops at the first non-table line, so prose between two tables
        ends it - which is why the committed matrix and cross-walk yield only
        their own rows. Two tables separated by nothing but a blank line are read
        as one, and the second table's rows are reported under the first table's
        label. If the parser is ever narrowed to a single table, this test should
        be deleted with the change, not repaired around it.
        """
        text = (
            self.HEADER
            + "| 1 | Synthetic | **GA** | 2026-01-01 | note |\n"
            + "\n"
            + "| Other | Table | Header | Last verified | Notes |\n"
            + "|---|---|---|---|---|\n"
            + "| X | Unrelated | n/a | 2026-04-04 | note |\n"
        )
        self.assertEqual(
            guard.parse_table_dates(text, "Last verified"),
            [("1", "2026-01-01"), ("X", "2026-04-04")],
        )


class ParseFooterDateTests(unittest.TestCase):
    PATTERN = r"Last validated:\s*(20\d{2}-\d{2}-\d{2})"

    def test_reads_the_stamp(self):
        text = "*Version 0.0 - Last validated: 2026-01-01 - synthetic fixture stamp.*\n"
        self.assertEqual(guard.parse_footer_date(text, self.PATTERN), [("footer", "2026-01-01")])

    def test_a_missing_stamp_yields_nothing(self):
        """Returning [] is what makes main() report the file as unreadable."""
        self.assertEqual(guard.parse_footer_date("no stamp here\n", self.PATTERN), [])

    def test_the_first_stamp_wins(self):
        text = "Last validated: 2026-01-01\nLast validated: 2026-02-02\n"
        self.assertEqual(guard.parse_footer_date(text, self.PATTERN), [("footer", "2026-01-01")])


class EmitGithubOutputTests(GuardRunner):
    """The step-output contract stale-guard.yml reads."""

    def test_nothing_is_written_when_the_env_var_is_unset(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("GITHUB_OUTPUT", None)
            guard.emit_github_output(stale="true", report="ignored")
        self.assertFalse(self.output_file.exists())

    def test_single_line_values_are_appended_as_key_equals_value(self):
        # read_text applies universal newlines, so this holds on Windows too;
        # do not "fix" it by opening with newline="".
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(self.output_file)}):
            guard.emit_github_output(stale="false", stale_count="0")
            guard.emit_github_output(stale="true")
        self.assertEqual(
            self.output_file.read_text(encoding="utf-8"),
            "stale=false\nstale_count=0\nstale=true\n",
        )

    def test_a_multi_line_value_uses_the_heredoc_form(self):
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(self.output_file)}):
            guard.emit_github_output(report="line one\nline two")
        text = self.output_file.read_text(encoding="utf-8")
        self.assertEqual(text, "report<<__EOF__\nline one\nline two\n__EOF__\n")
        # Also checks the reader the other tests here depend on.
        self.assertEqual(parse_github_output(text), {"report": "line one\nline two"})


class WindowBoundaryTests(GuardRunner):
    """The comparison is strict - `age > window` - so age == window is fresh.

    The two tests below bracket the edge, and each catches a different mutation:
    `test_an_item_exactly_at_the_window_is_fresh` fails if `>` becomes `>=`, and
    `test_the_day_after_the_window_is_stale` fails if the comparison slips the
    other way to `age > window + 1`. No single mutation breaks both, and this
    docstring does not claim one does; what the pair pins is the *position* of
    the boundary, which neither test does alone.

    The dates are fixture dates, not tracked ones, because a tracked date moves
    whenever a human re-verifies a row - rows 12 and 13 moved on the day this
    file was written. The boundary is also checked against the shipped data in
    LiveTrackedFileTests, with the date derived from the oldest tracked item.

    Worth pinning twice over: this repository's own notes and issue #27's
    reproduction block both mis-stated it, reading `--window-days 0` as "every
    item is stale" when an item verified today has age 0 and is fresh.
    """

    def test_an_item_exactly_at_the_window_is_fresh(self):
        self.write_repository(matrix=(ANCHOR, AT_WINDOW))
        code, report, outputs = self.run_guard(
            "--today", AT_WINDOW, "--window-days", str(WINDOW), "--fail-on-stale"
        )
        self.assertEqual(code, 0, report)
        self.assertEqual(
            report,
            f"All 4 dated item(s) are within the {WINDOW}-day window (as of {AT_WINDOW}).",
        )
        self.assertEqual(outputs["stale"], "false")
        self.assertEqual(outputs["stale_count"], "0")

    def test_the_day_after_the_window_is_stale(self):
        self.write_repository(matrix=(ANCHOR, AT_WINDOW))
        code, report, outputs = self.run_guard(
            "--today", PAST_WINDOW, "--window-days", str(WINDOW), "--fail-on-stale"
        )
        self.assertEqual(code, 1)
        self.assertEqual(outputs["stale"], "true")
        self.assertEqual(outputs["stale_count"], "1")
        self.assertIn(
            f"1 item(s) exceed the {WINDOW}-day staleness window (as of {PAST_WINDOW}):",
            report,
        )
        self.assertIn(
            f"matrix row 1: last verified {ANCHOR} ({WINDOW + 1} days ago)",
            report,
        )

    def test_staleness_alone_does_not_change_the_exit_code(self):
        """--fail-on-stale decides the exit code; staleness decides the report.

        validate-matrix.yml runs the guard informationally and stale-guard.yml
        gates on the `stale` output, so a stale repository must still exit 0
        unless the flag is passed.
        """
        self.write_repository(matrix=(ANCHOR,))
        code, report, outputs = self.run_guard("--today", PAST_WINDOW, "--window-days", str(WINDOW))
        self.assertEqual(code, 0, report)
        self.assertEqual(outputs["stale"], "true")
        self.assertEqual(outputs["stale_count"], "1")

    def test_a_future_dated_stamp_is_read_as_fresh(self):
        """Documents, rather than endorses, a negative age.

        A stamp dated after today can never exceed the window, so a mistyped
        future date exempts that item from the guard until the date passes.
        Nothing detects it; the live tests only assert that tracked dates are
        real calendar dates, not that they are in the past.
        """
        self.write_repository(matrix=(AT_WINDOW,), crosswalk=(AT_WINDOW,), checklist=AT_WINDOW)
        code, report, outputs = self.run_guard(
            "--today", ANCHOR, "--window-days", str(WINDOW), "--fail-on-stale"
        )
        self.assertEqual(code, 0, report)
        self.assertEqual(outputs["stale_count"], "0")
        self.assertEqual(
            report,
            f"All 3 dated item(s) are within the {WINDOW}-day window (as of {ANCHOR}).",
        )


class WindowSourceTests(GuardRunner):
    """Where the window comes from when --window-days is absent."""

    def test_the_window_comes_from_the_registry(self):
        self.write_repository(matrix=(ANCHOR,), crosswalk=(ANCHOR,), checklist=ANCHOR)
        self.write_registry(json.dumps({"staleness_window_days": 7}))
        code, report, outputs = self.run_guard("--today", "2026-01-09")
        self.assertEqual(code, 0, report)
        self.assertEqual(outputs["stale_count"], "3")
        self.assertIn("3 item(s) exceed the 7-day staleness window (as of 2026-01-09):", report)

    def test_a_missing_registry_falls_back_to_thirty_days(self):
        self.write_repository(matrix=(ANCHOR,), crosswalk=(ANCHOR,), checklist=ANCHOR)
        code, report, outputs = self.run_guard("--today", "2026-01-09")
        self.assertEqual(report, "All 3 dated item(s) are within the 30-day window (as of 2026-01-09).")
        self.assertEqual(outputs["stale"], "false")

    def test_a_registry_without_a_usable_window_falls_back_to_thirty_days(self):
        self.write_repository(matrix=(ANCHOR,), crosswalk=(ANCHOR,), checklist=ANCHOR)
        for body in ("{ not json", json.dumps({"sources": []})):
            with self.subTest(registry=body):
                self.write_registry(body)
                code, report, outputs = self.run_guard("--today", "2026-01-09")
                self.assertEqual(
                    report,
                    "All 3 dated item(s) are within the 30-day window (as of 2026-01-09).",
                )
                self.assertEqual(outputs["stale"], "false")

    def test_the_command_line_window_overrides_the_registry(self):
        self.write_repository(matrix=(ANCHOR,), crosswalk=(ANCHOR,), checklist=ANCHOR)
        self.write_registry(json.dumps({"staleness_window_days": 7}))
        code, report, outputs = self.run_guard("--today", "2026-01-09", "--window-days", "30")
        self.assertEqual(code, 0, report)
        self.assertEqual(outputs["stale_count"], "0")
        self.assertIn("30-day window", report)


class UnreadableTargetTests(GuardRunner):
    """An unreadable target must be a finding, never a quiet pass.

    Both cases report every *other* item as fresh, which is exactly the shape a
    silent failure takes: the guard says "all fresh" and means "I could not read
    that file". So the `stale` output stays `true` and --fail-on-stale still
    exits 1, even though the stale count is zero.
    """

    def test_a_missing_target_file_is_reported_and_fails_the_guard(self):
        self.write_matrix((AT_WINDOW,))
        self.write_crosswalk((AT_WINDOW,))
        # No checklist file at all.
        code, report, outputs = self.run_guard(
            "--today", AT_WINDOW, "--window-days", str(WINDOW), "--fail-on-stale"
        )
        self.assertEqual(code, 1)
        self.assertEqual(outputs["stale"], "true")
        self.assertEqual(outputs["stale_count"], "0")
        self.assertIn("Could not read a last-verified date from:", report)
        self.assertIn("checklists/capability-status-verification.md (missing)", report)

    def test_a_renamed_column_is_reported_rather_than_read_as_all_fresh(self):
        self.write_repository(matrix=(ANCHOR,), column="Last checked")
        code, report, outputs = self.run_guard(
            "--today", PAST_WINDOW, "--window-days", str(WINDOW), "--fail-on-stale"
        )
        self.assertEqual(code, 1)
        self.assertEqual(outputs["stale"], "true")
        self.assertEqual(outputs["stale_count"], "0")
        # The misleading half: two items really are fresh, and the stale matrix
        # row is simply absent. The finding below is what stops that reading.
        self.assertIn("All 2 dated item(s) are within", report)
        self.assertIn("Could not read a last-verified date from:", report)
        self.assertIn("- `matrix/capability-status-matrix.md`", report)
        self.assertNotIn("(missing)", report)


class WorkflowOutputContractTests(GuardRunner):
    """stale-guard.yml opens the staleness issue by comparing `stale` to a literal.

    The script writes `str(bool(...)).lower()`, so `True` would silently never
    match and the issue would never be opened - a green workflow that reports
    nothing. Both halves are read in one test because the coupling is the point.
    """

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / "stale-guard.yml"
    # Either comparison is legitimate -- `== 'true'` or the fail-closed
    # `!= 'false'` -- but the quoted literal must be one the script can actually
    # emit, in the script's own casing.
    GATE = re.compile(r"outputs\.stale\s*(==|!=)\s*['\"]([^'\"]+)['\"]")

    def emitted_literals(self) -> set[str]:
        """Both values the script can write, derived by running it."""
        self.write_repository(matrix=(ANCHOR,))
        _, stale_report, stale_outputs = self.run_guard(
            "--today", PAST_WINDOW, "--window-days", str(WINDOW)
        )
        self.assertEqual(stale_outputs["stale"], "true", stale_report)
        self.write_repository(matrix=(ANCHOR,))
        _, fresh_report, fresh_outputs = self.run_guard(
            "--today", ANCHOR, "--window-days", str(WINDOW)
        )
        self.assertEqual(fresh_outputs["stale"], "false", fresh_report)
        return {stale_outputs["stale"], fresh_outputs["stale"]}

    def test_the_workflow_gate_matches_a_literal_the_script_emits(self):
        match = self.GATE.search(self.WORKFLOW.read_text(encoding="utf-8"))
        self.assertIsNotNone(match, "stale-guard.yml no longer gates on the `stale` output")
        self.assertIn(match.group(2), self.emitted_literals())

    def test_the_gate_fails_closed_on_an_absent_output(self):
        """An absent output must not read as "not stale".

        If stale_guard.py crashes the step writes no `stale` value at all, and
        a GitHub Actions expression compares the empty string. `== 'true'` reads
        that as "nothing is stale" and skips the issue -- the crash becomes a
        green weekly run with no signal. `!= 'false'` files the issue instead.
        """
        operator, literal = self.GATE.search(
            self.WORKFLOW.read_text(encoding="utf-8")
        ).groups()
        absent = ""
        opens_issue = absent != literal if operator == "!=" else absent == literal
        self.assertTrue(
            opens_issue,
            f"gate `stale {operator} '{literal}'` treats an absent output as not-stale",
        )


class LiveTrackedFileTests(GuardRunner):
    """Structural assertions against the committed files.

    Nothing here asserts how many items are stale, or which: that moves whenever
    a human re-verifies a row. What must hold at every commit is that the guard
    can still read every file it is pointed at, that no dated item has quietly
    fallen out of its reach, and that the window it quotes is the declared one.
    """

    def live_iso_entries(self) -> list[tuple[str, str, str]]:
        entries: list[tuple[str, str, str]] = []
        for target in guard.TARGETS:
            text = (REPO_ROOT / target["path"]).read_text(encoding="utf-8")
            if target["kind"] == "table":
                parsed = guard.parse_table_dates(text, target["column"])
            else:
                parsed = guard.parse_footer_date(text, target["pattern"])
            entries.extend((target["path"], identifier, iso) for identifier, iso in parsed)
        return entries

    def target_for(self, prefix: str) -> dict:
        for target in guard.TARGETS:
            if target["path"].startswith(prefix):
                return target
        self.fail(f"stale_guard.TARGETS no longer covers {prefix}")

    def test_every_target_file_exists(self):
        for target in guard.TARGETS:
            with self.subTest(path=target["path"]):
                self.assertTrue((REPO_ROOT / target["path"]).exists())

    def test_every_target_yields_at_least_one_dated_item(self):
        entries = self.live_iso_entries()
        for target in guard.TARGETS:
            with self.subTest(path=target["path"]):
                found = [entry for entry in entries if entry[0] == target["path"]]
                self.assertGreaterEqual(len(found), 1)

    def test_no_target_is_reported_as_unreadable(self):
        entries = self.live_iso_entries()
        self.assertTrue(entries)
        newest = max(iso for _, _, iso in entries)
        code, report, _ = self.run_guard("--today", newest, root=REPO_ROOT)
        self.assertEqual(code, 0, report)
        self.assertNotIn("Could not read a last-verified date from", report)

    def test_every_parsed_date_is_a_real_calendar_date(self):
        """ISO_DATE accepts 2026-13-45; main() would then raise ValueError.

        In stale-guard.yml that crash is piped into `tee`, so the job stays green
        with no `stale` output and no issue opened. This test keeps the
        repository out of that state; it does not make the guard survive it.
        """
        for path, identifier, iso in self.live_iso_entries():
            with self.subTest(file=path, item=identifier):
                try:
                    datetime.strptime(iso, "%Y-%m-%d")
                except ValueError:
                    self.fail(f"{iso} matches ISO_DATE but is not a real date")

    def test_every_matrix_row_carries_a_date_the_guard_can_read(self):
        """A blank or prose date cell drops a row from the guard in silence.

        Row 9's missing watch survived a release on exactly this shape of gap, so
        the row identifiers the guard reads are compared against the row
        identifiers the matrix declares, using the repository's own parser.
        """
        target = self.target_for("matrix/")
        text = (REPO_ROOT / target["path"]).read_text(encoding="utf-8")
        read = []
        for identifier, _ in guard.parse_table_dates(text, target["column"]):
            digits = re.sub(r"[^0-9]", "", identifier)
            if digits:
                read.append(int(digits))
        self.assertEqual(read, validate.matrix_row_ids(text))
        self.assertGreaterEqual(len(read), 13)

    def test_the_reported_window_is_the_one_the_registry_declares(self):
        registry = json.loads(guard.SOURCES_FILE.read_text(encoding="utf-8"))
        window = registry.get("staleness_window_days")
        self.assertIsInstance(window, int)
        self.assertGreater(window, 0)
        newest = max(iso for _, _, iso in self.live_iso_entries())
        code, report, _ = self.run_guard("--today", newest, root=REPO_ROOT)
        self.assertEqual(code, 0, report)
        self.assertIn(f"{window}-day", report)

    def test_the_window_boundary_holds_for_the_dates_actually_tracked(self):
        """The same strict boundary, against the shipped data shape.

        The pivot is derived from the oldest tracked date rather than written
        down, so re-verifying a row cannot make this test wrong. With today set
        to `oldest + window` every item is at or inside the window; one day later
        exactly the oldest item crosses it.
        """
        entries = self.live_iso_entries()
        self.assertTrue(entries)
        oldest = min(datetime.strptime(iso, "%Y-%m-%d").date() for _, _, iso in entries)
        at_window = oldest + timedelta(days=WINDOW)

        code, report, outputs = self.run_guard(
            "--today", at_window.isoformat(), "--window-days", str(WINDOW), "--fail-on-stale",
            root=REPO_ROOT,
        )
        self.assertEqual(code, 0, report)
        self.assertEqual(outputs["stale_count"], "0")

        code, report, outputs = self.run_guard(
            "--today", (at_window + timedelta(days=1)).isoformat(),
            "--window-days", str(WINDOW), "--fail-on-stale",
            root=REPO_ROOT,
        )
        self.assertEqual(code, 1)
        self.assertGreaterEqual(int(outputs["stale_count"]), 1)
        self.assertIn(oldest.isoformat(), report)


if __name__ == "__main__":
    unittest.main()
