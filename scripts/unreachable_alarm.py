#!/usr/bin/env python3
"""Raise an issue when a watched source fails on consecutive Source watch runs.

Issue #50. Row 4's three sources returned HTTP 404 on every daily run from
2026-09-24 to 2026-11-04 -- 42 runs -- and every one of those runs concluded
*success*. The watcher exits 0 on a fetch failure by design and `source-watch.yml`
reported it as a `::warning::` annotation, which notifies nobody, so the loss
surfaced only through staleness six weeks later (#47). A source that is gone and
a source that failed once looked identical to the cadence.

The rule here: a source in `failed_sources` on **two consecutive observations**
-- this run's evidence bundle and the previous run's -- is confirmed unreachable,
and that opens an issue. One failure alone never notifies. Over the 91 Source
watch runs measured on 2026-11-05 there was no transient failure at all, so the
threshold costs one day of latency against a hazard that has not yet occurred.

There is deliberately no streak file. The evidence bundle every run already
uploads carries `failed_sources` and each failing source's `error`, so "two
consecutive observations" is the intersection of two bundles. An earlier design
chained a counter through a new artifact; its adversarial review found that every
way the chain could break -- a cancelled run, an expired artifact, a lookup that
silently found nothing -- restarted the counter, and a restart either closed a
live alarm or kept the alarm from ever firing, on a green run. Those are the two
fail-quiet shapes this script exists to remove, so the state machine below is
built around them:

* **Close needs positive evidence**: an empty `failed_sources` in a bundle that
  lists sources, or two real consecutive observations that confirm nothing. A
  missing or unusable previous observation can never close an alarm.
* **A missing previous observation holds; a broken lookup is red.** Only "no
  earlier completed run on this branch within the bound" holds. Any `gh` error,
  an unparseable bundle, or a previous run whose `detect` job succeeded but has no
  `evidence-bundle` exits 1, because each of those means the mechanism is broken
  rather than that there is nothing to compare.
* **While an alarm is open, its own marker stands in for a missing observation**
  -- but only for sources it already confirmed. That keeps a gap in the run
  history from reading as a recovery.

Writes no repository file and makes no status judgement. Reads the registry only
to name the matrix rows an alarmed source backs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = REPO_ROOT / ".github" / "watch-state" / "sources.json"

TITLE = "Unreachable sources: failing on consecutive watch runs"
WORKFLOW = "source-watch.yml"
ARTIFACT = "evidence-bundle"
BUNDLE_FILE = "evidence.json"
# The `name:` of the job in source-watch.yml that produces the bundle. Pinned by
# a contract test, because matching it is how a crashed run is told apart from a
# run that should have uploaded and did not.
DETECT_JOB_NAME = "Detect status-relevant change"
# How many earlier completed runs to walk past cancelled or crashed ones before
# concluding there is no previous observation. Runs are daily, so five is five
# days of gap, and the bundle retention is 30.
LOOKBACK = 5
MARKER = re.compile(r"<!-- unreachable-alarm: ([^>]*?) -->")


class AlarmError(Exception):
    """The mechanism itself is broken. Always a red run, never a hold."""


Gh = Callable[[list[str]], str]


# Calls that change nothing, and so may be repeated. An issue write is never
# retried: one that succeeded but reported failure would be repeated as a
# duplicate issue or comment.
READ_ONLY = {("api",), ("run", "list"), ("run", "view"), ("run", "download"), ("issue", "list")}
RETRY_DELAY_SECONDS = 10


def run_gh(args: list[str]) -> str:
    """Run the GitHub CLI; any non-zero exit is an AlarmError, never a default.

    A read-only call is retried once. The job runs on clean days too, so a single
    5xx from the API would otherwise turn a healthy morning red; a second failure
    is still red.
    """
    attempts = 2 if (tuple(args[:1]) in READ_ONLY or tuple(args[:2]) in READ_ONLY) else 1
    for attempt in range(attempts):
        completed = subprocess.run(
            ["gh", *args], capture_output=True, text=True, encoding="utf-8", check=False
        )
        if completed.returncode == 0:
            return completed.stdout
        if attempt + 1 < attempts:
            time.sleep(RETRY_DELAY_SECONDS)
    raise AlarmError(f"gh {' '.join(args[:2])} failed: {completed.stderr.strip()}")


# --------------------------------------------------------------------------
# bundles
# --------------------------------------------------------------------------
def load_bundle(path: Path) -> dict:
    """Read an evidence bundle, refusing anything that could fake a recovery.

    A bundle with no `sources` is what a run that fingerprinted nothing would
    produce, and its empty `failed_sources` must never be read as "every source
    fetched".
    """
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AlarmError(f"evidence bundle not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise AlarmError(f"evidence bundle unreadable: {path}: {exc}") from exc
    if not isinstance(bundle, dict):
        raise AlarmError(f"evidence bundle is not an object: {path}")
    sources, failed = bundle.get("sources"), bundle.get("failed_sources")
    if not isinstance(sources, dict) or not sources:
        raise AlarmError(f"evidence bundle lists no sources: {path}")
    if not isinstance(failed, list):
        raise AlarmError(f"evidence bundle has no failed_sources list: {path}")
    return bundle


def failure_errors(bundle: dict) -> dict[str, str]:
    """Failed source id -> the error the watcher recorded for it this run."""
    sources = bundle["sources"]
    return {
        source_id: str((sources.get(source_id) or {}).get("error") or "no error recorded")
        for source_id in bundle["failed_sources"]
    }


# --------------------------------------------------------------------------
# previous observation
# --------------------------------------------------------------------------
def previous_observation(gh: Gh, repo: str, run_id: str, ref: str) -> tuple[str, dict] | None:
    """The newest earlier run on this branch that observed the sources.

    Returns (run id, bundle), or None when there is no candidate within
    LOOKBACK -- the first run on a branch, the only case that may hold.

    Candidates are earlier *completed* runs of this workflow on the same branch.
    Anything newer than this run is excluded: with `concurrency: source-watch`,
    a dispatch made during a run sits queued and is "newest" in the list without
    having observed anything.

    **Whether a run observed anything is read from its `detect` job, never from
    the run's conclusion.** A run whose `detect` did not succeed uploaded nothing
    and is passed over; a crashed one was already red. A run's conclusion says
    nothing either way: one whose *alarm* job failed concludes `failure`, and one
    cancelled while its alarm job ran concludes `cancelled`, and both hold a valid
    bundle from a `detect` that finished. An earlier version skipped cancelled
    runs by conclusion, and a mutation test showed the skip was both redundant
    for a run cancelled before `detect` finished and wrong for one cancelled
    after -- it discarded a real observation.
    """
    current = json.loads(gh(["api", f"repos/{repo}/actions/runs/{run_id}"]))
    created_at = current["created_at"]
    runs = json.loads(
        gh(
            [
                "run", "list", "-R", repo, "--workflow", WORKFLOW, "--branch", ref,
                "--status", "completed", "--limit", "20",
                "--json", "databaseId,createdAt",
            ]
        )
    )
    earlier = sorted(
        (r for r in runs if str(r["databaseId"]) != str(run_id) and r["createdAt"] < created_at),
        key=lambda r: r["createdAt"],
        reverse=True,
    )
    for candidate in earlier[:LOOKBACK]:
        candidate_id = str(candidate["databaseId"])
        jobs = json.loads(gh(["run", "view", candidate_id, "-R", repo, "--json", "jobs"]))["jobs"]
        detect = next((job for job in jobs if job.get("name") == DETECT_JOB_NAME), None)
        if detect is None or detect.get("conclusion") != "success":
            continue
        with tempfile.TemporaryDirectory() as directory:
            try:
                gh(["run", "download", candidate_id, "-R", repo, "-n", ARTIFACT, "-D", directory])
            except AlarmError as exc:
                # Red either way, but the message must not guess which. Missing
                # means the chain is broken; expired means no run happened for 30
                # days (a schedule GitHub disabled, then re-enabled), which the
                # next run repairs by itself.
                raise AlarmError(
                    f"run {candidate_id}'s detect job succeeded but its {ARTIFACT!r} artifact "
                    f"could not be downloaded (missing, or expired after the bundle's 30-day "
                    f"retention); not treated as 'nothing to compare': {exc}"
                ) from exc
            return candidate_id, load_bundle(Path(directory) / BUNDLE_FILE)
    return None


# --------------------------------------------------------------------------
# issue
# --------------------------------------------------------------------------
def alarm_title(ref: str, default_branch: str) -> str:
    """Branch-scoped off the default branch, so a test can never touch the real alarm."""
    return TITLE if ref == default_branch else f"{TITLE} [branch: {ref}]"


def open_alarm(issues: list[dict], title: str) -> dict | None:
    """The open issue with exactly this title; a word-overlap match is not enough."""
    matches = sorted((i for i in issues if i.get("title") == title), key=lambda i: i["number"])
    return matches[0] if matches else None


def alarmed_in(body: str | None) -> set[str]:
    match = MARKER.search(body or "")
    return {s for s in match.group(1).split(",") if s} if match else set()


@dataclass
class Decision:
    action: str  # "open" | "edit" | "close" | "none"
    confirmed: set[str] = field(default_factory=set)
    comment: bool = False


def decide(current_failed: set[str], previous_failed: set[str] | None, issue: dict | None) -> Decision:
    """The whole policy, and the only place it is stated.

    `previous_failed` is None when there is no previous observation. Then the
    open alarm's own marker stands in for it, for the sources it already
    confirmed and nothing else, so a gap neither opens a new alarm nor shrinks a
    live one.

    Two things close an open alarm, and both are positive evidence:

    * this run fetched every source; or
    * two real, consecutive observations confirm nothing. Without that second
      rule, an alarm whose sources had all recovered stayed open as long as
      some *other* source kept failing on alternate runs, never twice in a row,
      saying "No source is confirmed" indefinitely. With no previous observation
      this rule cannot apply, and the marker holds the alarm instead.
    """
    already = alarmed_in(issue.get("body")) if issue else set()
    evidence = previous_failed if previous_failed is not None else already
    confirmed = current_failed & evidence
    if not current_failed:
        return Decision("close" if issue else "none")
    if issue is None:
        return Decision("open", confirmed) if confirmed else Decision("none")
    if not confirmed and previous_failed is not None:
        return Decision("close")
    # Open, and this run still has failures: rewrite the live state. Opening a
    # new issue already notifies, so only a *change* in what is confirmed earns a
    # comment -- a 42-day outage is one notification plus one per change.
    return Decision("edit", confirmed, comment=confirmed != already)


def render_body(
    decision: Decision,
    current: dict[str, str],
    previous: dict[str, str] | None,
    registry: dict,
    run_url: str,
) -> str:
    entries = {source["id"]: source for source in registry.get("sources", [])}
    lines = [f"<!-- unreachable-alarm: {','.join(sorted(decision.confirmed))} -->", ""]
    if decision.confirmed:
        lines += [
            "These watched sources failed to fetch on **two consecutive** Source watch",
            "observations. Their baselines are preserved and no last-verified date",
            "advances while they are dark, so the matrix rows they back are ageing",
            "unwatched.",
            "",
            "| Source | Matrix rows | This run | Previous run | Cites |",
            "|---|---|---|---|---|",
        ]
        for source_id in sorted(decision.confirmed):
            entry = entries.get(source_id, {})
            rows = ", ".join(str(r) for r in entry.get("matrix_rows", [])) or "none"
            before = (
                code_span((previous or {})[source_id])
                if source_id in (previous or {})
                else "not observed (alarm already open)"
            )
            lines.append(
                f"| `{source_id}` | {rows} | {code_span(current.get(source_id, ''))} | {before} "
                f"| {entry.get('cite_url', '')} |"
            )
    else:
        lines.append("No source is confirmed failing on consecutive runs this run.")
    unconfirmed = sorted(set(current) - decision.confirmed)
    if unconfirmed:
        lines += ["", "Failed this run only, not yet confirmed: "
                  + ", ".join(f"`{s}` ({code_span(current[s])})" for s in unconfirmed) + "."]
    lines += [
        "",
        f"Latest run: {run_url}",
        "",
        "**What to do:** re-read each source's entry in `.github/watch-state/sources.json`",
        "against the live page it cites, then repoint or remove it. Do not re-baseline",
        "to silence this: a failed fetch writes nothing, and a re-baseline would store",
        "a `ok: false` record that the tests reject.",
        "",
        "_Raised by `scripts/unreachable_alarm.py`. A source is confirmed after failing on",
        "two consecutive observations; a manual dispatch counts as one. The body is",
        "rewritten every run, a comment is added only when the confirmed set changes,",
        "and the issue closes itself on the first run that fetches every source, or",
        "once two consecutive observations confirm nothing._",
    ]
    return "\n".join(lines) + "\n"


def code_span(text: str) -> str:
    """Render an error string inertly inside a table cell.

    The error is `f"{type(exc).__name__}: {exc}"`, and part of it can come from
    the server -- a reason phrase, a URL. A `|` or a newline would break the
    table row, and outside a code span an `@name` would notify a real account.
    """
    flat = " ".join(text.replace("`", "'").split()).replace("|", "\\|")
    return f"`{flat}`" if flat else ""


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def act(
    gh: Gh,
    repo: str,
    title: str,
    decision: Decision,
    issue: dict | None,
    body: str,
    run_url: str,
    current: dict[str, str],
) -> str:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "body.md"
        path.write_text(body, encoding="utf-8")
        if decision.action == "open":
            gh(["issue", "create", "-R", repo, "--title", title, "--body-file", str(path)])
            return f"opened an alarm for {', '.join(sorted(decision.confirmed))}"
        if decision.action == "edit":
            number = str(issue["number"])
            gh(["issue", "edit", number, "-R", repo, "--body-file", str(path)])
            if decision.comment:
                gh(["issue", "comment", number, "-R", repo, "--body-file", str(path)])
                return f"updated #{number} and commented: the confirmed set changed"
            return f"updated #{number}; the confirmed set is unchanged"
        if decision.action == "close":
            number = str(issue["number"])
            if current:
                reason = ("No source has failed on two consecutive observations any more, so "
                          "this episode is over. Failing on this run only, not confirmed: "
                          + ", ".join(f"`{s}`" for s in sorted(current)) + ".")
            else:
                reason = "Every watched source fetched on this run, so this episode is over."
            gh(["issue", "close", number, "-R", repo, "--comment", f"{reason} {run_url}"])
            return f"closed #{number}: " + ("nothing confirmed" if current else "every source fetched")
    return "no alarm: nothing is confirmed unreachable and none is open"


def use_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None, gh: Gh = run_gh) -> int:
    use_utf8_streams()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evidence", type=Path, required=True, help="This run's evidence bundle.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ref", required=True, help="Branch name this run is on.")
    parser.add_argument(
        "--default-branch",
        default=None,
        help="Default: asked of the API. Not taken from the event payload, because a "
        "`schedule` event carries no repository object.",
    )
    parser.add_argument("--server-url", default="https://github.com")
    parser.add_argument("--registry", type=Path, default=SOURCES_FILE)
    parser.add_argument("--dry-run", action="store_true", help="Decide and print; write no issue.")
    args = parser.parse_args(argv)

    try:
        current_bundle = load_bundle(args.evidence)
        current = failure_errors(current_bundle)
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        default_branch = args.default_branch or json.loads(
            gh(["api", f"repos/{args.repo}"])
        )["default_branch"]
        title = alarm_title(args.ref, default_branch)
        issues = json.loads(
            gh(["issue", "list", "-R", args.repo, "--state", "open", "--limit", "500",
                "--json", "number,title,body"])
        )
        issue = open_alarm(issues, title)
        found = previous_observation(gh, args.repo, args.run_id, args.ref)
        previous = failure_errors(found[1]) if found else None
        if found is None:
            print(f"::notice::No earlier observation on {args.ref}; holding, not comparing.")
        decision = decide(set(current), set(previous) if previous is not None else None, issue)
        run_url = f"{args.server_url}/{args.repo}/actions/runs/{args.run_id}"
        body = render_body(decision, current, previous, registry, run_url)
        if args.dry_run:
            print(f"[dry-run] {decision.action} confirmed={sorted(decision.confirmed)} "
                  f"comment={decision.comment}")
            return 0
        outcome = act(gh, args.repo, title, decision, issue, body, run_url, current)
    except AlarmError as exc:
        print(f"::error::Unreachable-source alarm could not run: {exc}", file=sys.stderr)
        return 1

    compared = f"run {found[0]}" if found else "nothing (no earlier observation)"
    print(f"Unreachable-source alarm: {outcome}. Failed this run: "
          f"{', '.join(sorted(current)) or 'none'}; compared against {compared}.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"## Unreachable-source alarm\n\n{outcome}.\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
