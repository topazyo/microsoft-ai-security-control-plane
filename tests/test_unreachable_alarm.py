#!/usr/bin/env python3
"""Tests for the unreachable-source alarm (issue #50).

Standard library only, like the script. Every `gh` call goes through an injected
fake, so the lookup's failure paths -- the ones an adversarial review of the first
design showed would fail *quietly* -- are driven directly rather than hoped for.

The fixtures are shaped like the real event: row 4's three Defender sources
failing with `HTTPError: HTTP Error 404: Not Found` on consecutive daily runs.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
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


alarm = load_script("unreachable_alarm")

A = "defender-ai-threat-protection"
B = "defender-release-notes"
ERROR_404 = "HTTPError: HTTP Error 404: Not Found"
REGISTRY = {
    "sources": [
        {"id": A, "matrix_rows": [4], "cite_url": "https://learn.microsoft.com/a"},
        {"id": B, "matrix_rows": [4], "cite_url": "https://learn.microsoft.com/b"},
    ]
}


def bundle(*failed: str) -> dict:
    sources = {s: {"ok": True} for s in (A, B, "purview-dlp-copilot")}
    for source_id in failed:
        sources[source_id] = {"ok": False, "error": ERROR_404}
    return {"failed_sources": list(failed), "sources": sources}


def issue(*alarmed: str, number: int = 51, title: str = alarm.TITLE) -> dict:
    return {
        "number": number,
        "title": title,
        "body": f"<!-- unreachable-alarm: {','.join(sorted(alarmed))} -->\n\nbody",
    }


def detect_job(conclusion: str = "success") -> list[dict]:
    return [{"name": alarm.DETECT_JOB_NAME, "conclusion": conclusion},
            {"name": "Alarm on sources unreachable on consecutive runs", "conclusion": "failure"}]


class FakeGh:
    """Answers the handful of `gh` calls the script makes, and records them."""

    def __init__(self, runs=(), jobs=None, bundles=None, issues=(), current_created="2026-09-25T06:30:00Z",
                 fail_on: str | None = None):
        self.runs = list(runs)
        self.jobs = jobs or {}
        self.bundles = bundles or {}
        self.issues = list(issues)
        self.current_created = current_created
        self.fail_on = fail_on
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        verb = " ".join(args[:2])
        if self.fail_on and verb == self.fail_on:
            raise alarm.AlarmError(f"gh {verb} failed: HTTP 502")
        if args[0] == "api" and "/actions/runs/" in args[1]:
            return json.dumps({"created_at": self.current_created})
        if args[0] == "api":
            return json.dumps({"default_branch": "main"})
        if verb == "run list":
            return json.dumps(self.runs)
        if verb == "run view":
            return json.dumps({"jobs": self.jobs.get(args[2], [])})
        if verb == "run download":
            run_id = args[2]
            if run_id not in self.bundles:
                raise alarm.AlarmError("no valid artifacts found to download")
            directory = Path(args[args.index("-D") + 1])
            (directory / alarm.BUNDLE_FILE).write_text(json.dumps(self.bundles[run_id]), encoding="utf-8")
            return ""
        if verb == "issue list":
            return json.dumps(self.issues)
        if args[0] == "issue":
            return ""
        raise AssertionError(f"unexpected gh call: {args}")

    def issue_writes(self) -> list[str]:
        return [" ".join(call[:2]) for call in self.calls if call[0] == "issue" and call[1] != "list"]


def run(created: str, run_id: int, conclusion: str = "success") -> dict:
    return {"databaseId": run_id, "createdAt": created, "conclusion": conclusion}


def temp_dir(case: unittest.TestCase) -> Path:
    """A directory removed when the test ends."""
    holder = tempfile.TemporaryDirectory()
    case.addCleanup(holder.cleanup)
    return Path(holder.name)


class DecisionTests(unittest.TestCase):
    """The policy table. Each row is one sentence of the script's docstring."""

    def test_two_consecutive_failures_open_an_alarm(self):
        decision = alarm.decide({A, B}, {A, B}, None)
        self.assertEqual((decision.action, decision.confirmed), ("open", {A, B}))

    def test_a_single_failure_never_notifies(self):
        """#50's acceptance: one transient failure does not produce a notification."""
        self.assertEqual(alarm.decide({A}, set(), None).action, "none")

    def test_only_the_intersection_is_confirmed(self):
        decision = alarm.decide({A, B}, {A}, None)
        self.assertEqual(decision.confirmed, {A})

    def test_no_previous_observation_and_no_alarm_holds(self):
        self.assertEqual(alarm.decide({A}, None, None).action, "none")

    def test_a_missing_previous_observation_never_closes_a_live_alarm(self):
        """Blocker B1 of the plan review: a chain restart closed a live alarm."""
        decision = alarm.decide({A}, None, issue(A))
        self.assertEqual(decision.action, "edit")
        self.assertEqual(decision.confirmed, {A})
        self.assertFalse(decision.comment)

    def test_a_gap_does_not_confirm_a_source_the_alarm_never_had(self):
        decision = alarm.decide({A, B}, None, issue(A))
        self.assertEqual(decision.confirmed, {A})

    def test_an_unchanged_alarm_is_rewritten_silently(self):
        decision = alarm.decide({A}, {A}, issue(A))
        self.assertEqual((decision.action, decision.comment), ("edit", False))

    def test_a_newly_confirmed_source_earns_a_comment(self):
        decision = alarm.decide({A, B}, {A, B}, issue(A))
        self.assertEqual((decision.action, decision.confirmed, decision.comment), ("edit", {A, B}, True))

    def test_a_partial_recovery_earns_a_comment(self):
        decision = alarm.decide({A}, {A, B}, issue(A, B))
        self.assertEqual((decision.action, decision.confirmed, decision.comment), ("edit", {A}, True))

    def test_only_a_run_that_fetched_everything_closes(self):
        self.assertEqual(alarm.decide(set(), {A}, issue(A)).action, "close")
        self.assertEqual(alarm.decide(set(), None, issue(A)).action, "close")

    def test_a_clean_run_with_no_alarm_does_nothing(self):
        self.assertEqual(alarm.decide(set(), {A}, None).action, "none")

    def test_two_observations_confirming_nothing_close_a_recovered_alarm(self):
        """Review low finding: A recovered while B flaps, so no run is fully clean."""
        self.assertEqual(alarm.decide({B}, {A}, issue(A)).action, "close")

    def test_without_a_previous_observation_that_rule_cannot_close(self):
        decision = alarm.decide({B}, None, issue(A))
        self.assertEqual((decision.action, decision.confirmed), ("edit", set()))


class LookupTests(unittest.TestCase):
    """Finding the previous observation, and refusing to guess when it cannot."""

    def lookup(self, gh: FakeGh, run_id: str = "900"):
        return alarm.previous_observation(gh, "o/r", run_id, "main")

    def test_the_newest_earlier_run_with_a_successful_detect_is_used(self):
        gh = FakeGh(
            runs=[run("2026-09-24T06:30:00Z", 800), run("2026-09-23T06:30:00Z", 700)],
            jobs={"800": detect_job(), "700": detect_job()},
            bundles={"800": bundle(A), "700": bundle()},
        )
        found = self.lookup(gh)
        self.assertEqual(found[0], "800")
        self.assertEqual(found[1]["failed_sources"], [A])

    def test_the_current_run_and_any_newer_run_are_excluded(self):
        """Review M1: anything created after this run is not a *previous* observation.

        The newer run is given a successful detect and a bundle on purpose. The
        first version of this test left it bare, and a mutation that deleted the
        time filter survived, because the missing detect job excluded the run
        anyway -- the test pinned a different rule from the one it named.
        """
        gh = FakeGh(
            runs=[run("2026-09-25T06:45:00Z", 950), run("2026-09-25T06:30:00Z", 900),
                  run("2026-09-24T06:30:00Z", 800)],
            jobs={"950": detect_job(), "900": detect_job(), "800": detect_job()},
            bundles={"950": bundle(B), "900": bundle(B), "800": bundle(A)},
        )
        self.assertEqual(self.lookup(gh)[0], "800")

    def test_a_run_cancelled_before_detect_finished_is_walked_past(self):
        gh = FakeGh(
            runs=[run("2026-09-24T06:30:00Z", 800, "cancelled"), run("2026-09-23T06:30:00Z", 700)],
            jobs={"800": detect_job("cancelled"), "700": detect_job()},
            bundles={"700": bundle(A)},
        )
        self.assertEqual(self.lookup(gh)[0], "700")

    def test_a_run_cancelled_after_detect_finished_still_observed(self):
        """Its conclusion is `cancelled`, and its bundle is real; the conclusion is not read."""
        gh = FakeGh(
            runs=[run("2026-09-24T06:30:00Z", 800, "cancelled"), run("2026-09-23T06:30:00Z", 700)],
            jobs={"800": detect_job(), "700": detect_job()},
            bundles={"800": bundle(A, B), "700": bundle()},
        )
        self.assertEqual(self.lookup(gh)[0], "800")

    def test_a_run_whose_detect_crashed_is_walked_past(self):
        gh = FakeGh(
            runs=[run("2026-09-24T06:30:00Z", 800, "failure"), run("2026-09-23T06:30:00Z", 700)],
            jobs={"800": detect_job("failure"), "700": detect_job()},
            bundles={"700": bundle(A)},
        )
        self.assertEqual(self.lookup(gh)[0], "700")

    def test_a_failed_alarm_job_does_not_disqualify_the_bundle(self):
        """Review M1: conclusion `failure` with a successful detect still observed."""
        gh = FakeGh(runs=[run("2026-09-24T06:30:00Z", 800, "failure")],
                    jobs={"800": detect_job()}, bundles={"800": bundle(A)})
        self.assertEqual(self.lookup(gh)[0], "800")

    def test_no_earlier_run_is_the_only_hold(self):
        self.assertIsNone(self.lookup(FakeGh(runs=[run("2026-09-25T06:30:00Z", 900)])))

    def test_the_walk_is_bounded(self):
        runs = [run(f"2026-09-{24 - i:02d}T06:30:00Z", 800 - i, "failure")
                for i in range(alarm.LOOKBACK)]
        runs.append(run("2026-09-01T06:30:00Z", 100))
        jobs = {str(800 - i): detect_job("failure") for i in range(alarm.LOOKBACK)}
        jobs["100"] = detect_job()
        gh = FakeGh(runs=runs, jobs=jobs, bundles={"100": bundle(A)})
        self.assertIsNone(self.lookup(gh))

    def test_a_missing_bundle_behind_a_successful_detect_is_red(self):
        """Review B2: a broken chain must not read as 'nothing to compare'."""
        gh = FakeGh(runs=[run("2026-09-24T06:30:00Z", 800)], jobs={"800": detect_job()})
        with self.assertRaisesRegex(alarm.AlarmError, "not treated as 'nothing to compare'"):
            self.lookup(gh)

    def test_a_gh_failure_is_red_not_a_hold(self):
        gh = FakeGh(runs=[run("2026-09-24T06:30:00Z", 800)], fail_on="run list")
        with self.assertRaises(alarm.AlarmError):
            self.lookup(gh)

    def test_the_lookup_is_scoped_to_this_workflow_and_branch(self):
        gh = FakeGh()
        alarm.previous_observation(gh, "o/r", "900", "chore/break-test")
        listing = next(call for call in gh.calls if call[:2] == ["run", "list"])
        self.assertEqual(listing[listing.index("--workflow") + 1], "source-watch.yml")
        self.assertEqual(listing[listing.index("--branch") + 1], "chore/break-test")
        self.assertEqual(listing[listing.index("--status") + 1], "completed")


class BundleTests(unittest.TestCase):
    """A bundle that could fake a recovery is an error, never an empty failure list."""

    def write(self, text: str) -> Path:
        path = temp_dir(self) / "evidence.json"
        path.write_text(text, encoding="utf-8")
        return path

    def test_fail_closed_shapes(self):
        cases = {
            "missing": temp_dir(self) / "absent.json",
            "unparseable": self.write("{not json"),
            "no sources": self.write(json.dumps({"failed_sources": [], "sources": {}})),
            "no failure list": self.write(json.dumps({"sources": {A: {"ok": True}}})),
            "not an object": self.write("[]"),
        }
        for label, path in cases.items():
            with self.subTest(case=label), self.assertRaises(alarm.AlarmError):
                alarm.load_bundle(path)

    def test_errors_come_from_the_bundle(self):
        self.assertEqual(alarm.failure_errors(bundle(A)), {A: ERROR_404})


class IssueTests(unittest.TestCase):
    def test_exact_title_only(self):
        """Review minor 3: a word-overlap match could edit and close #50 itself."""
        issue_50 = {"number": 50, "title": "A source that fails on consecutive runs raises no alarm",
                    "body": ""}
        self.assertIsNone(alarm.open_alarm([issue_50], alarm.TITLE))
        self.assertEqual(alarm.open_alarm([issue_50, issue(A)], alarm.TITLE)["number"], 51)

    def test_a_branch_off_the_default_gets_its_own_title(self):
        """Review M2: a break test on a throwaway branch must not touch the real alarm."""
        self.assertEqual(alarm.alarm_title("main", "main"), alarm.TITLE)
        branch_title = alarm.alarm_title("chore/break-test", "main")
        self.assertNotEqual(branch_title, alarm.TITLE)
        self.assertIn("[branch: chore/break-test]", branch_title)
        self.assertIsNone(alarm.open_alarm([issue(A)], branch_title))

    def test_the_marker_round_trips_and_errors_are_rendered(self):
        decision = alarm.Decision("open", {A, B})
        body = alarm.render_body(decision, {A: ERROR_404, B: ERROR_404}, {A: ERROR_404, B: ERROR_404},
                                 REGISTRY, "https://example.invalid/run")
        self.assertEqual(alarm.alarmed_in(body), {A, B})
        self.assertIn(ERROR_404, body)
        self.assertIn("| 4 |", body)
        self.assertIn("https://learn.microsoft.com/a", body)

    def test_error_text_is_rendered_inertly(self):
        """Server-supplied text must not break the table or notify an account."""
        hostile = "HTTPError: bad | gateway\nping @someone `x`"
        body = alarm.render_body(alarm.Decision("open", {A}), {A: hostile}, {A: hostile},
                                 REGISTRY, "https://example.invalid/run")
        row = next(line for line in body.splitlines() if line.startswith(f"| `{A}`"))
        # Five cells, four separators; an unescaped `|` in the error adds more.
        self.assertEqual(row.count(" | "), 4, row)
        self.assertIn("`HTTPError: bad \\| gateway ping @someone 'x'`", row)

    def test_unconfirmed_failures_are_named_but_not_marked(self):
        body = alarm.render_body(alarm.Decision("edit", {A}), {A: ERROR_404, B: "TimeoutError: timed out"},
                                 None, REGISTRY, "https://example.invalid/run")
        self.assertEqual(alarm.alarmed_in(body), {A})
        self.assertIn("TimeoutError: timed out", body)


class MainTests(unittest.TestCase):
    """End to end through `main`, with the fake standing in for GitHub."""

    def call(self, gh: FakeGh, current: dict, *extra: str, ref: str = "main") -> int:
        directory = temp_dir(self)
        evidence = directory / "evidence.json"
        evidence.write_text(json.dumps(current), encoding="utf-8")
        registry = directory / "sources.json"
        registry.write_text(json.dumps(REGISTRY), encoding="utf-8")
        argv = ["--evidence", str(evidence), "--repo", "o/r", "--run-id", "900", "--ref", ref,
                "--registry", str(registry), *extra]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return alarm.main(argv, gh=gh)

    def history(self, previous: dict, issues=()) -> FakeGh:
        return FakeGh(runs=[run("2026-09-24T06:30:00Z", 800)], jobs={"800": detect_job()},
                      bundles={"800": previous}, issues=issues)

    def test_second_consecutive_failure_opens_the_issue(self):
        gh = self.history(bundle(A, B))
        self.assertEqual(self.call(gh, bundle(A, B)), 0)
        self.assertEqual(gh.issue_writes(), ["issue create"])
        create = next(call for call in gh.calls if call[:2] == ["issue", "create"])
        self.assertEqual(create[create.index("--title") + 1], alarm.TITLE)

    def test_first_failure_writes_nothing(self):
        gh = self.history(bundle())
        self.assertEqual(self.call(gh, bundle(A)), 0)
        self.assertEqual(gh.issue_writes(), [])

    def test_recovery_closes_the_open_alarm(self):
        gh = self.history(bundle(A), issues=[issue(A)])
        self.assertEqual(self.call(gh, bundle()), 0)
        self.assertEqual(gh.issue_writes(), ["issue close"])
        close = next(call for call in gh.calls if call[:2] == ["issue", "close"])
        self.assertEqual(close[2], "51")
        self.assertIn("Every watched source fetched", close[close.index("--comment") + 1])

    def test_an_unchanged_alarm_is_edited_without_a_comment(self):
        gh = self.history(bundle(A), issues=[issue(A)])
        self.assertEqual(self.call(gh, bundle(A)), 0)
        self.assertEqual(gh.issue_writes(), ["issue edit"])

    def test_a_grown_alarm_is_edited_and_commented(self):
        """Review: deleting the comment call used to pass every test."""
        gh = self.history(bundle(A, B), issues=[issue(A)])
        self.assertEqual(self.call(gh, bundle(A, B)), 0)
        self.assertEqual(gh.issue_writes(), ["issue edit", "issue comment"])
        writes = [call for call in gh.calls if call[0] == "issue" and call[1] != "list"]
        self.assertEqual([call[2] for call in writes], ["51", "51"])

    def test_a_branch_run_never_touches_the_real_alarm(self):
        """Review: scoping was only tested on alarm_title(), not through main()."""
        gh = self.history(bundle(A, B), issues=[issue(A)])
        self.assertEqual(self.call(gh, bundle(A, B), ref="chore/x"), 0)
        self.assertEqual(gh.issue_writes(), ["issue create"])
        create = next(call for call in gh.calls if call[:2] == ["issue", "create"])
        self.assertEqual(create[create.index("--title") + 1], f"{alarm.TITLE} [branch: chore/x]")

    def test_a_close_without_a_clean_run_says_so(self):
        gh = self.history(bundle(A), issues=[issue(A)])
        self.assertEqual(self.call(gh, bundle(B)), 0)
        close = next(call for call in gh.calls if call[:2] == ["issue", "close"])
        comment = close[close.index("--comment") + 1]
        self.assertNotIn("Every watched source fetched", comment)
        self.assertIn(f"`{B}`", comment)

    def test_dry_run_writes_nothing(self):
        gh = self.history(bundle(A, B))
        self.assertEqual(self.call(gh, bundle(A, B), "--dry-run"), 0)
        self.assertEqual(gh.issue_writes(), [])

    def test_a_broken_lookup_is_a_red_run_and_writes_nothing(self):
        gh = FakeGh(runs=[run("2026-09-24T06:30:00Z", 800)], jobs={"800": detect_job()})
        self.assertEqual(self.call(gh, bundle(A, B)), 1)
        self.assertEqual(gh.issue_writes(), [])

    def test_a_bundle_that_lists_no_sources_is_red_even_with_an_alarm_open(self):
        """The fake-recovery case: it must not close anything."""
        gh = self.history(bundle(A), issues=[issue(A)])
        self.assertEqual(self.call(gh, {"failed_sources": [], "sources": {}}), 1)
        self.assertEqual(gh.issue_writes(), [])

    def test_the_default_branch_comes_from_the_api_when_not_given(self):
        gh = self.history(bundle(A, B))
        self.call(gh, bundle(A, B))
        self.assertIn(["api", "repos/o/r"], gh.calls)


class RetryTests(unittest.TestCase):
    """One retry for a read, none for a write."""

    def setUp(self):
        self.calls = 0
        self.real_run, self.real_sleep = alarm.subprocess.run, alarm.time.sleep
        alarm.time.sleep = lambda seconds: None

        def failing(*args, **kwargs):
            self.calls += 1
            return alarm.subprocess.CompletedProcess(args, 1, stdout="", stderr="HTTP 502")

        alarm.subprocess.run = failing
        self.addCleanup(self.restore)

    def restore(self):
        alarm.subprocess.run, alarm.time.sleep = self.real_run, self.real_sleep

    def test_a_read_is_retried_once_then_red(self):
        with self.assertRaises(alarm.AlarmError):
            alarm.run_gh(["run", "list", "-R", "o/r"])
        self.assertEqual(self.calls, 2)

    def test_a_write_is_never_retried(self):
        """A retried create that had in fact succeeded would open a duplicate issue."""
        with self.assertRaises(alarm.AlarmError):
            alarm.run_gh(["issue", "create", "-R", "o/r"])
        self.assertEqual(self.calls, 1)


class BacktestTests(unittest.TestCase):
    """The measured history, replayed through the policy.

    Source watch ran daily from 2026-08-08; the three row-4 sources failed on
    every run from 2026-09-24 to 2026-11-04 (42 runs) and nothing else ever
    failed. The alarm must open on 2026-09-25, stay silent for the rest of the
    outage, and close on the first clean run.
    """

    def test_the_row_4_outage(self):
        row4 = {A, B, "defender-release-notes-archive"}
        days = [("2026-09-22", set()), ("2026-09-23", set())]
        days += [(f"2026-09-{d}", row4) for d in range(24, 31)]
        days += [(f"2026-10-{d:02d}", row4) for d in range(1, 32)]
        days += [(f"2026-11-{d:02d}", row4) for d in range(1, 5)]
        days += [("2026-11-05", set())]
        self.assertEqual(sum(1 for _, failed in days if failed), 42)

        issue_state: dict | None = None
        previous: set[str] | None = None
        events = []
        for day, failed in days:
            decision = alarm.decide(failed, previous, issue_state)
            if decision.action == "open":
                issue_state = issue(*decision.confirmed)
            elif decision.action == "edit":
                issue_state = issue(*decision.confirmed)
            elif decision.action == "close":
                issue_state = None
            if decision.action != "none" and (decision.action != "edit" or decision.comment):
                events.append((day, decision.action))
            previous = failed
        self.assertEqual(events, [("2026-09-25", "open"), ("2026-11-05", "close")])

    def test_a_missing_observation_mid_outage_holds_the_alarm(self):
        row4 = {A, B}
        decision = alarm.decide(row4, None, issue(*row4))
        self.assertEqual((decision.action, decision.confirmed, decision.comment), ("edit", row4, False))


def executable_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


def job_block(text: str, job: str) -> str:
    """One job's lines, comments removed; empty when the job is absent."""
    lines = executable_lines(text)
    start = next((i for i, line in enumerate(lines) if line == f"  {job}:"), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[i])),
               len(lines))
    return "\n".join(lines[start:end])


class WorkflowContractTests(unittest.TestCase):
    """What source-watch.yml must keep true for the script to mean anything.

    Asserted over comment-stripped job blocks, because the steps are introduced
    by comments that name them: a raw-text check would pass over a deleted step
    whose explanation was left behind.
    """

    WORKFLOW = REPO_ROOT / ".github" / "workflows" / alarm.WORKFLOW

    def setUp(self):
        self.text = self.WORKFLOW.read_text(encoding="utf-8")
        self.detect = job_block(self.text, "detect")
        self.alarm_job = job_block(self.text, "unreachable-alarm")

    def test_both_jobs_are_present(self):
        self.assertIn("name: Fingerprint pinned sources", self.detect)
        self.assertIn("scripts/unreachable_alarm.py", self.alarm_job)

    def test_the_detect_job_name_matches_the_lookup(self):
        """The lookup recognises a crashed run by this name; a rename must not unwire it."""
        self.assertIn(f"    name: {alarm.DETECT_JOB_NAME}", self.detect.splitlines())

    def test_detect_stays_read_only_and_tokenless(self):
        permissions = re.search(r"    permissions:\n((?:      .*\n?)+)", self.detect)
        self.assertEqual(permissions.group(1).split(), ["contents:", "read"])
        self.assertNotIn("GH_TOKEN", self.detect)

    def test_the_alarm_job_has_exactly_its_permissions(self):
        permissions = re.search(r"    permissions:\n((?:      [a-z-]+: \w+\n?)+)", self.alarm_job)
        granted = dict(line.strip().split(": ") for line in permissions.group(1).splitlines())
        self.assertEqual(granted, {"contents": "read", "actions": "read", "issues": "write"})

    def test_the_alarm_job_needs_detect(self):
        self.assertIn("    needs: detect", self.alarm_job.splitlines())

    def test_the_artifact_names_agree(self):
        uploaded = re.findall(r"name: (\S+)\n\s+path: \$\{\{ runner.temp \}\}/evidence.json", self.detect)
        downloaded = re.findall(r"uses: actions/download-artifact@\S+\n\s+with:\n\s+name: (\S+)",
                                self.alarm_job)
        self.assertEqual(uploaded, [alarm.ARTIFACT])
        self.assertEqual(downloaded, [alarm.ARTIFACT])
        self.assertIn(f"--evidence evidence/{alarm.BUNDLE_FILE}", self.alarm_job)

    def test_the_script_step_names_its_shell_and_splices_no_expression(self):
        step = self.alarm_job[self.alarm_job.index("- name: Raise, update or close"):]
        self.assertIn("shell: bash", step)
        run_body = step[step.index("run: |"):]
        self.assertNotIn("${{", run_body, "context values must reach the script through env:")

    def test_the_alarm_job_cannot_be_made_non_blocking(self):
        """Review: `continue-on-error` or a job `if:` would turn red back into green.

        Every broken lookup is meant to be a red run, and the job runs on clean
        days so that a broken lookup surfaces the next morning. Either key undoes
        one of those without failing anything else.
        """
        job_level = [line for line in self.alarm_job.splitlines() if re.match(r"^    \S", line)]
        self.assertFalse([line for line in job_level if line.strip().startswith("if:")], job_level)
        self.assertNotIn("continue-on-error", self.alarm_job)

    def test_the_alarm_checkout_keeps_no_credentials(self):
        self.assertIn("persist-credentials: false", self.alarm_job)

    def test_the_job_block_helper_is_not_vacuous(self):
        """Guard the guard: an absent job must read as empty, not as everything."""
        self.assertEqual(job_block(self.text, "no-such-job"), "")
        self.assertNotIn("Fingerprint pinned sources", self.alarm_job)


if __name__ == "__main__":
    unittest.main()
