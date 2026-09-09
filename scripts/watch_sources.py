#!/usr/bin/env python3
"""Tier D1 — deterministic source watcher.

Fetches every pinned source in .github/watch-state/sources.json, reduces each one
to a *status-signal fingerprint*, and compares that fingerprint against the
committed baseline.

This tier contains no model and makes no judgement. It answers exactly one
question — "did anything status-relevant change?" — and never decides what a
change means. Assigning a status label is tier D2's job (see
.claude/agents/status-adjudicator.md).

Design notes
------------
* The fingerprint is taken over extracted *signals* (section headings, which
  headings carry a "(preview)" qualifier, and status-bearing phrases), not over
  the raw page. Rendered Microsoft Learn pages carry navigation, feedback
  widgets and per-render tokens that change constantly; fingerprinting the whole
  page would produce a false positive nearly every run.
* Every signal field is computed at the *same scope*. Where a source declares a
  `relevance_filter`, that scope is the filtered sections and nothing else. An
  earlier version filtered the heading fields but took the phrase field over the
  whole page, so a Defender for SQL retirement notice - a section the filter
  correctly rejected - moved the fingerprint and escalated for five consecutive
  days. A mixed-scope fingerprint is worse than an unfiltered one, because the
  report line looks scoped and is not.
* Failure isolation: each source is fetched independently. A source that cannot
  be fetched is recorded with ok=false, is never reported as changed, and never
  overwrites its stored baseline. Absence of evidence must never look like a
  status change, and must never advance a last-verified date.

Forbidden actions for this script (enforced by review and by
scripts/validate_bot_pr.py's path allowlist):
  - It must never write to matrix/, crosswalk/, checklists/, docs/ or CHANGELOG.md.
  - It must never emit a status label.
  - It must never fetch a source that is not in the registry (in particular, it
    must never touch the Microsoft 365 Message Center, which is tenant-scoped).

Standard library only: no third-party dependency, no pip install step in CI.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / ".github" / "watch-state"
SOURCES_FILE = STATE_DIR / "sources.json"
BASELINE_FILE = STATE_DIR / "fingerprints.json"

USER_AGENT = (
    "microsoft-ai-security-control-plane-watcher/1.0 "
    "(+https://github.com/topazyo/microsoft-ai-security-control-plane)"
)
TIMEOUT_SECONDS = 45

# Phrases that carry release-status meaning. Presence/absence of each of these
# is part of the fingerprint; ordinary prose edits are not.
STATUS_PHRASES = [
    "generally available",
    "release state",
    "in preview",
    "public preview",
    "rolling out",
    "launched",
    "in development",
    "retired",
    "deprecated",
]

PREVIEW_QUALIFIER = re.compile(r"\(preview\)", re.IGNORECASE)

# Heading levels at or below this are treated as page-level rather than as a
# product entry, so a relevance filter never scopes them out. See
# relevance_scoped_text for why they must not confer scope on their children.
PAGE_LEVEL = 1

# Shape guard for `mode: "version"` captures. Whatever a framework publishes ends
# up stored verbatim in fingerprints.json and in the evidence bundle the
# adjudicator reads, so what may leave a fetch is bounded rather than trusted.
VERSION_TOKEN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._:-]{0,31}$")
# A four-component numeric version is indistinguishable from an IPv4 address to
# the confidentiality scan in scripts/validate_bot_pr.py, which reads every
# changed .json — including this script's baseline file. Rejecting it here turns
# a would-be CI failure on an upstream string nobody wrote into a loud, ordinary
# fetch failure that the stale guard escalates.
FOUR_COMPONENT_NUMERIC = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------
def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------
def strip_html(document: str) -> str:
    """Reduce a rendered Learn page to its article text.

    Everything outside <main> is navigation/chrome that changes independently of
    the documentation, so it is discarded before any comparison.
    """
    main = re.search(r"<main\b[^>]*>(.*?)</main>", document, re.DOTALL | re.IGNORECASE)
    body = main.group(1) if main else document
    body = re.sub(r"<(script|style|nav|header|footer)\b.*?</\1>", " ", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<[^>]+>", "\n", body)
    return html.unescape(body)


# A *section* is (heading_level, heading_or_None, body_text). A section's body
# includes its own heading, and the text before the first heading is carried as a
# level-0 section with heading None. Sections exist so that a relevance filter can
# scope the page *text* as well as the heading list -- see relevance_scoped_text.
HTML_HEADING = re.compile(r"<h([1-4])\b[^>]*>(.*?)</h\1>", re.DOTALL | re.IGNORECASE)
MARKDOWN_HEADING = re.compile(r"^\s{0,3}(#{1,4})\s+(.*?)\s*#*\s*$")


def html_sections(document: str) -> list[tuple[int, str | None, str]]:
    main = re.search(r"<main\b[^>]*>(.*?)</main>", document, re.DOTALL | re.IGNORECASE)
    body = main.group(1) if main else document
    sections: list[tuple[int, str | None, str]] = []
    level = 0
    heading: str | None = None
    start = 0
    for match in HTML_HEADING.finditer(body):
        sections.append((level, heading, strip_html(body[start : match.start()])))
        level = int(match.group(1))
        text = html.unescape(re.sub(r"<[^>]+>", "", match.group(2)))
        heading = re.sub(r"\s+", " ", text).strip() or None
        start = match.start()
    sections.append((level, heading, strip_html(body[start:])))
    return sections


def markdown_sections(document: str) -> list[tuple[int, str | None, str]]:
    sections: list[tuple[int, str | None, str]] = []
    level = 0
    heading: str | None = None
    buffer: list[str] = []
    for line in document.splitlines():
        match = MARKDOWN_HEADING.match(line)
        if not match:
            buffer.append(line)
            continue
        sections.append((level, heading, "\n".join(buffer)))
        level = len(match.group(1))
        heading = re.sub(r"\s+", " ", match.group(2)).strip() or None
        buffer = [line]
    sections.append((level, heading, "\n".join(buffer)))
    return sections


def section_headings(sections: list[tuple[int, str | None, str]]) -> list[str]:
    """Headings in document order.

    Derived from the sections rather than extracted separately, so the heading
    list a filter is applied to and the text that filter scopes to cannot
    disagree about what counts as a heading.
    """
    return [heading for _level, heading, _body in sections if heading]


def strip_frontmatter(document: str) -> str:
    """Remove YAML frontmatter — ms.date changes on every docs build."""
    if document.lstrip().startswith("---"):
        parts = document.split("---", 2)
        if len(parts) >= 3:
            return parts[2]
    return document


# --------------------------------------------------------------------------
# signal extraction
# --------------------------------------------------------------------------
def apply_relevance_filter(headings: list[str], patterns: list[str] | None) -> list[str]:
    """Keep only headings relevant to the capabilities this repository tracks.

    Broad release-notes pages carry dozens of entries for products outside this
    repository's scope; without a filter the fingerprint would change almost
    every run and the detector would escalate constantly for Kubernetes and SQL
    notes. Filtering is applied to the *watched signal*, never to the evidence a
    human reads.
    """
    if not patterns:
        return headings
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    return [h for h in headings if any(c.search(h) for c in compiled)]


def relevance_scoped_text(
    sections: list[tuple[int, str | None, str]], patterns: list[str] | None
) -> str:
    """Concatenate only the page text a relevance filter keeps in scope.

    This is the other half of apply_relevance_filter, and the half that was
    missing. Scope rules, each chosen so that dropping a section can only ever
    drop out-of-scope text:

    * A section whose heading matches the filter is in scope.
    * So is every section nested under it. A matching ``## Defender for AI ...``
      entry owns its ``### Details`` subsection, whose own heading says nothing
      about AI; scoping by heading alone would discard the entry's own body.
    * **Page-level text is always in scope** -- the text before the first
      heading, and the H1's own section. Neither belongs to a product entry, so
      no per-entry pattern can be expected to claim it, and a page-wide
      release-state banner lives in exactly that position. Dropping it would
      lose real signal: the notice that "all Sentinel data connectors are
      currently in Preview" is one half of matrix row 9's documented conflict.

    Page-level text is kept **without conferring scope on anything nested under
    it**. That is the whole subtlety of the third rule: marking the H1 in scope
    as an *ancestor* would make every section on the page inherit it and restore
    the unfiltered behaviour this function exists to remove.
    """
    if not patterns:
        return "\n".join(body for _level, _heading, body in sections)
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    kept: list[str] = []
    ancestors: list[tuple[int, bool]] = []
    for level, heading, body in sections:
        while ancestors and ancestors[-1][0] >= level:
            ancestors.pop()
        if heading is None or level <= PAGE_LEVEL:
            # Kept, and pushed as *not* in scope so children do not inherit it.
            kept.append(body)
            ancestors.append((level, False))
            continue
        in_scope = bool(ancestors and ancestors[-1][1]) or any(
            c.search(heading) for c in compiled
        )
        ancestors.append((level, in_scope))
        if in_scope:
            kept.append(body)
    return "\n".join(kept)


def extract_signals(
    text: str,
    sections: list[tuple[int, str | None, str]],
    relevance: list[str] | None = None,
) -> dict:
    """Reduce a page to the four status signals that make up its fingerprint.

    All four are computed at one scope, which is what the signature is for: the
    heading fields come from `sections`, and so does the text the phrase field is
    taken over whenever a relevance filter narrows the source.

    `text` is used verbatim when there is no filter, so an unfiltered source's
    phrase set is computed exactly as it was before scoping existed and its
    stored fingerprint is untouched by this change. Only the filtered sources
    re-baseline.
    """
    headings = section_headings(sections)
    filtered = apply_relevance_filter(headings, relevance)
    scoped = relevance_scoped_text(sections, relevance) if relevance else text
    lowered = scoped.lower()
    return {
        "headings": filtered,
        "preview_qualified_headings": sorted(h for h in filtered if PREVIEW_QUALIFIER.search(h)),
        "status_phrases_present": sorted(p for p in STATUS_PHRASES if p in lowered),
        "heading_count": len(filtered),
        "relevance_filtered": bool(relevance),
    }


def version_signals(raw: str, pattern: str) -> dict:
    """Fingerprint the version/edition tokens a framework publishes.

    Why this mode exists: `extract_signals` fingerprints headings, preview
    qualifiers and nine fixed status phrases. None of those changes when a
    framework ships a new edition or bumps a dataset version, so registering a
    framework source under `html`/`markdown` would produce a source that reports
    "unchanged" forever — worse than not registering it, because the registry
    would then claim coverage it does not have. That blind spot is how the OWASP
    LLM Top 10 2026 edition went unnoticed here.

    Captures are shape-checked, not trusted: only bounded version-like tokens
    survive. A pattern that captures nothing raises, so the source is recorded
    ok=false and announced, rather than silently fingerprinting an empty set and
    reporting "no change" for the rest of time.
    """
    found = re.findall(pattern, raw, re.MULTILINE)
    tokens = {(m if isinstance(m, str) else m[0]).strip() for m in found}
    accepted = sorted(
        t for t in tokens if VERSION_TOKEN.match(t) and not FOUR_COMPONENT_NUMERIC.match(t)
    )
    rejected = sorted(tokens - set(accepted))
    if not accepted:
        raise LookupError(
            f"version_pattern matched no acceptable token "
            f"(raw matches: {len(found)}, rejected by shape guard: {rejected[:5]})"
        )
    return {
        "versions": accepted,
        "version_count": len(accepted),
        "rejected_token_count": len(rejected),
    }


def signals_for_source(source: dict) -> dict:
    mode = source["mode"]
    relevance = source.get("relevance_filter")
    raw = fetch(source["url"])

    if mode == "version":
        return version_signals(raw, source["version_pattern"])

    if mode == "roadmap":
        features = json.loads(raw)
        feature_id = str(source["feature_id"])
        match = next((f for f in features if str(f.get("id")) == feature_id), None)
        if match is None:
            raise LookupError(f"feature {feature_id} not present in roadmap collection")
        return {
            "feature_id": feature_id,
            "title": match.get("title"),
            "status": match.get("status"),
            "modified": match.get("modified"),
            "tags": sorted(str(t) for t in (match.get("tags") or [])),
        }

    if mode == "markdown":
        body = strip_frontmatter(raw)
        return extract_signals(body, markdown_sections(body), relevance)

    if mode == "html":
        return extract_signals(strip_html(raw), html_sections(raw), relevance)

    raise ValueError(f"unknown mode: {mode}")


def fingerprint(signals: dict) -> str:
    canonical = json.dumps(signals, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# diffing
# --------------------------------------------------------------------------
def describe_change(previous: dict, current: dict) -> list[str]:
    """Human-readable, evidence-only description. Never interprets."""
    notes: list[str] = []
    if "status" in current or "status" in previous:
        if previous.get("status") != current.get("status"):
            notes.append(f"roadmap status: {previous.get('status')!r} -> {current.get('status')!r}")
        if previous.get("modified") != current.get("modified"):
            notes.append(f"roadmap modified: {previous.get('modified')!r} -> {current.get('modified')!r}")
        return notes

    # Version-mode signals share none of the keys the heading diff below reads,
    # so without this branch a framework-edition change would be reported as a
    # bare "[changed] <id>" with no notes at all, and the evidence bundle would
    # carry an empty change_notes entry for the one event this mode exists for.
    if "versions" in current or "versions" in previous:
        before_versions = set(previous.get("versions") or [])
        after_versions = set(current.get("versions") or [])
        for version in sorted(after_versions - before_versions):
            notes.append(f"version/edition token appeared: {version!r}")
        for version in sorted(before_versions - after_versions):
            notes.append(f"version/edition token disappeared: {version!r}")
        return notes

    before_headings = set(previous.get("headings") or [])
    after_headings = set(current.get("headings") or [])
    for heading in sorted(after_headings - before_headings):
        notes.append(f"heading added: {heading!r}")
    for heading in sorted(before_headings - after_headings):
        notes.append(f"heading removed: {heading!r}")

    before_preview = set(previous.get("preview_qualified_headings") or [])
    after_preview = set(current.get("preview_qualified_headings") or [])
    for heading in sorted(after_preview - before_preview):
        notes.append(f"(preview) qualifier ADDED to heading: {heading!r}")
    for heading in sorted(before_preview - after_preview):
        notes.append(f"(preview) qualifier REMOVED from heading: {heading!r}")

    # Scope attribution. A reader of "status phrase appeared: 'retired'" cannot
    # tell an in-scope trigger from an out-of-scope one without re-fetching and
    # re-reading the page, and a detector that cries wolf trains its maintainer
    # to stop looking. Naming the scope costs one word and makes the line
    # evidence rather than an alarm.
    scope = (
        "relevance-scoped sections"
        if (current.get("relevance_filtered") or previous.get("relevance_filtered"))
        else "whole page"
    )
    before_phrases = set(previous.get("status_phrases_present") or [])
    after_phrases = set(current.get("status_phrases_present") or [])
    for phrase in sorted(after_phrases - before_phrases):
        notes.append(f"status phrase appeared in {scope}: {phrase!r}")
    for phrase in sorted(before_phrases - after_phrases):
        notes.append(f"status phrase disappeared from {scope}: {phrase!r}")
    return notes


def citable_urls(entries: list[dict]) -> set[str]:
    """Citable URL for each registry entry that declares one.

    `entry.get("cite_url") or entry["url"]`, never `entry.get("cite_url",
    entry["url"])`: a `dict.get` default is evaluated *eagerly*, so the second
    form raises KeyError on an entry carrying `cite_url` but no `url` — the
    shape of a human-only source, which has no fetch URL by definition.

    Deliberately duplicated in scripts/validate_bot_pr.py: these scripts are
    standalone by design (standard library only, no package, no import path to
    share), and the trap is subtle enough to be worth stating in both places.
    """
    return {
        entry.get("cite_url") or entry["url"]
        for entry in entries
        if entry.get("cite_url") or entry.get("url")
    }


def registry_problems(registry: dict) -> list[str]:
    """Structural faults in sources.json that failure isolation cannot absorb.

    Two of the three keys checked here are read *outside* the per-source
    try/except — `id` is needed to file the failure under, and a missing `mode`
    or `version_pattern` is a repository defect rather than a network condition.
    A malformed registry is therefore reported up front and fails the run, which
    is the one case where this script is *meant* to go red: a fetch failure is
    expected and isolated, a broken registry is neither.

    **Both arrays are validated.** `human_only_sources` was originally
    unchecked, so a malformed human-only entry, an id colliding with a watched
    source, or a row mapping of the wrong shape was invisible to every automated
    run. Those entries are the *sole* backing for four of this repository's
    eighteen dated items (matrix rows 12 and 13, and the NIST and CSA cross-walk
    rows), which makes them the last place an unnoticed defect can be afforded.

    Scope boundary worth stating: this function sees only the registry, so it
    answers "is every entry well-formed and does it declare what it backs?" and
    never "does every matrix row have a source?". That second question needs the
    matrix, and is answered by `check_source_coverage` in
    scripts/validate_bot_pr.py — the layer that already reads it.
    """
    problems: list[str] = []
    seen: set[str] = set()

    def check_shared(entry: dict, array: str, index: int) -> str | None:
        """Rules every registry entry obeys, whichever array it lives in."""
        identifier = entry.get("id")
        if not identifier:
            problems.append(f"{array}[{index}]: missing 'id'")
            return None
        if identifier in seen:
            # Deliberately checked across both arrays: the same id appearing as
            # watched and as human-only is exactly the mis-join that would make
            # a row look covered by automation when nothing fetches it.
            problems.append(f"{identifier}: duplicate id")
        seen.add(identifier)

        rows = entry.get("matrix_rows", [])
        crosswalk = entry.get("crosswalk_rows", [])
        # `isinstance(True, int)` is True, so bools are excluded explicitly:
        # `"matrix_rows": [true]` would otherwise pass as a row number.
        if not isinstance(rows, list) or any(
            isinstance(r, bool) or not isinstance(r, int) for r in rows
        ):
            problems.append(f"{identifier}: 'matrix_rows' must be a list of integers")
        if not isinstance(crosswalk, list) or any(not isinstance(r, str) for r in crosswalk):
            problems.append(f"{identifier}: 'crosswalk_rows' must be a list of strings")
        if not rows and not crosswalk:
            problems.append(
                f"{identifier}: declares neither 'matrix_rows' nor 'crosswalk_rows'; "
                "a source that backs nothing cannot be checked for coverage"
            )
        return identifier

    for index, source in enumerate(registry.get("sources", [])):
        identifier = check_shared(source, "sources", index)
        if identifier is None:
            continue
        mode = source.get("mode")
        if not mode:
            problems.append(f"{identifier}: missing 'mode'")
        elif mode == "version" and not source.get("version_pattern"):
            problems.append(f"{identifier}: mode 'version' requires 'version_pattern'")
        elif mode == "roadmap" and source.get("feature_id") is None:
            problems.append(f"{identifier}: mode 'roadmap' requires 'feature_id'")
        if not source.get("url"):
            problems.append(f"{identifier}: missing 'url'")

    for index, entry in enumerate(registry.get("human_only_sources", [])):
        identifier = check_shared(entry, "human_only_sources", index)
        if identifier is None:
            continue
        # `url` is the key signals_for_source fetches. Its presence here is the
        # shape of an entry that has drifted into the watched array's schema,
        # which is the one mistake that would quietly widen what automation
        # reaches; `cite_url` is the human-readable page and is correct.
        if entry.get("url"):
            problems.append(
                f"{identifier}: human-only entries must not carry 'url' — nothing fetches "
                "them, and 'cite_url' is the key for the page a human reads"
            )
        if not entry.get("reason"):
            problems.append(
                f"{identifier}: human-only entries require a 'reason' — the reason is what "
                "stops a future maintainer 'fixing' the entry by adding a credential"
            )
    return problems


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def emit_github_output(**values) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic source watcher (tier D1).")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write the new fingerprints to the baseline file (used by the monthly tier).",
    )
    parser.add_argument(
        "--evidence-out",
        type=Path,
        default=None,
        help="Write an evidence bundle for the adjudicator to this path.",
    )
    args = parser.parse_args()

    registry = load_json(SOURCES_FILE, {"sources": []})
    problems = registry_problems(registry)
    if problems:
        for problem in problems:
            print(f"[error] registry: {problem}", file=sys.stderr)
        print(f"{len(problems)} registry problem(s); fix {SOURCES_FILE.name}.", file=sys.stderr)
        return 1

    baseline = load_json(BASELINE_FILE, {"sources": {}})
    previous_sources = baseline.get("sources", {})

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results: dict[str, dict] = {}
    changed_ids: list[str] = []
    failed_ids: list[str] = []
    change_notes: dict[str, list[str]] = {}

    for source in registry.get("sources", []):
        source_id = source["id"]
        try:
            signals = signals_for_source(source)
        # re.error is listed explicitly: it subclasses Exception directly, not
        # ValueError, so a malformed version_pattern or relevance_filter would
        # otherwise escape failure isolation and abort the whole run — every
        # source, not just the bad one. (KeyError needs no entry: it subclasses
        # LookupError, which is already here.)
        except (urllib.error.URLError, urllib.error.HTTPError, LookupError, ValueError, re.error, json.JSONDecodeError, TimeoutError, OSError) as exc:
            # Failure isolation: keep the previous baseline untouched and do not
            # report a change. The row simply ages and the stale guard raises it.
            failed_ids.append(source_id)
            kept = dict(previous_sources.get(source_id, {}))
            kept.update({"ok": False, "error": f"{type(exc).__name__}: {exc}", "checked_at": now})
            results[source_id] = kept
            print(f"[warn] {source_id}: fetch/parse failed — baseline preserved: {exc}", file=sys.stderr)
            continue

        digest = fingerprint(signals)
        record = {
            "ok": True,
            "fingerprint": digest,
            "signals": signals,
            "checked_at": now,
            "cite_url": source.get("cite_url") or source["url"],
            "matrix_rows": source.get("matrix_rows", []),
        }
        prior = previous_sources.get(source_id)
        if prior and prior.get("ok") and prior.get("fingerprint") and prior["fingerprint"] != digest:
            changed_ids.append(source_id)
            change_notes[source_id] = describe_change(prior.get("signals", {}), signals)
        elif not prior:
            changed_ids.append(source_id)
            change_notes[source_id] = ["no prior baseline - first observation"]
        results[source_id] = record

    for source_id in sorted(changed_ids):
        print(f"[changed] {source_id}")
        for note in change_notes.get(source_id, []):
            print(f"    - {note}")
    if not changed_ids:
        print("[ok] no status-relevant change detected in any pinned source")

    if args.evidence_out:
        bundle = {
            "generated_at": now,
            "generator": "scripts/watch_sources.py",
            "changed_sources": sorted(changed_ids),
            "failed_sources": sorted(failed_ids),
            "change_notes": change_notes,
            "sources": results,
            # Strictly what this run was able to reach, minus the watch-only
            # sources. The adjudicator is told this is the complete set of URLs
            # it may cite — see .claude/agents/status-adjudicator.md — so a
            # framework source, which is watched to detect an edition change and
            # is never a capability row's primary source, is deliberately kept
            # out of it. Watching something must not enlarge what may be claimed.
            "allowed_citation_urls": sorted(
                citable_urls(
                    [s for s in registry.get("sources", []) if not s.get("watch_only")]
                )
            ),
            # Registered, deliberately never fetched, and therefore NOT citable by
            # any automated run. Emitted only so scripts/validate_bot_pr.py can
            # tell a human-maintained citation apart from a fabricated one.
            "human_only_citation_urls": sorted(
                citable_urls(registry.get("human_only_sources", []))
            ),
        }
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[evidence] wrote {args.evidence_out}")

    if args.update_baseline:
        BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_FILE.write_text(
            json.dumps({"updated_at": now, "sources": results}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[baseline] wrote {BASELINE_FILE}")

    emit_github_output(
        changed=str(bool(changed_ids)).lower(),
        changed_sources=",".join(sorted(changed_ids)),
        failed_sources=",".join(sorted(failed_ids)),
    )

    # Exit 0 even when sources fail: a fetch failure is an expected, isolated
    # condition, not a pipeline error. The stale guard is what escalates. The one
    # non-zero exit is a structurally broken registry, checked before the loop —
    # that is a repository defect, and silently degrading it into "every source
    # unreachable" would hide it behind the very mechanism built for outages.
    return 0


if __name__ == "__main__":
    sys.exit(main())
