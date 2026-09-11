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
* The fingerprint is taken over extracted *signals*, not over the raw page.
  Rendered Microsoft Learn pages carry navigation, feedback widgets and
  per-render tokens that change constantly; fingerprinting the whole page would
  produce a false positive nearly every run. The signals are: section headings
  **and the titles of collapsible reference entries**, since a page may list its
  entries as `<details>` disclosures and never as headings; which of those carry
  a "(preview)" qualifier; and which status-bearing phrases appear. For a
  filtered source the phrases are reported for the page's own page-level text and
  for its in-scope entries *separately* — see relevance_scoped_parts, and note
  that anything reading the `headings` field is reading entry titles too.
* Every signal field is computed at the *same scope*. Where a source declares a
  `relevance_filter`, that scope is the filtered sections and nothing else. An
  earlier version filtered the heading fields but took the phrase field over the
  whole page, so a Defender for SQL retirement notice - a section the filter
  correctly rejected - moved the fingerprint and escalated for five consecutive
  days. A mixed-scope fingerprint is worse than an unfiltered one, because the
  report line looks scoped and is not.
* A relevance filter that matches no heading is announced as a `[warn]` and
  listed in the evidence bundle's `collapsed_filter_sources`. It is not a
  failure and not a change -- it is a source that fetches cleanly while watching
  almost nothing, which every later run reports as "unchanged".
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
import bisect
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

# Bumped whenever a change to signal *extraction* moves stored fingerprints while
# no source has changed. It exists because a re-baseline is otherwise
# self-confirming: the only thing validating the new stored signal is the
# mechanism that produced it, and "the extractor changed" is exactly the
# explanation a genuine upstream change could hide behind. Recorded at the top
# level of fingerprints.json, outside every per-source `signals` object, so it
# changes no fingerprint; a baseline with no marker predates this and is version 1.
# tests/test_watch_sources.py fails when the committed baseline disagrees, which
# turns "re-baselined without bumping" and "bumped without re-baselining" into a
# red CI run instead of a silent drift in what the repository believes it watches.
EXTRACTOR_VERSION = 2

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

# The document title's heading level. Page-level means the text above the first
# heading plus the title's own section, and a relevance filter never scopes those
# out. Read *positionally*: only the first heading is the title, because a stray
# heading at this level deeper in a page belongs to whatever entry contains it.
# See relevance_scoped_text for that, and for why page-level text must not confer
# scope on its children.
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
# Elements that carry no line break when the page is rendered. Their tags must
# be removed *without* a separator: a reader sees `in <a>Preview</a>` as the
# continuous phrase "in Preview", so replacing the tag with a newline splits a
# phrase that is plainly on the page and makes it invisible to phrase matching.
#
# Every element NOT listed here is treated as a block boundary and still becomes
# a newline. That asymmetry is the point, and it is why this is not fixed by
# normalising whitespace afterwards: collapsing all whitespace would also join
# adjacent blocks, so a paragraph ending "available in" followed by a heading
# "Preview features" would manufacture the phrase "in preview" that no reader
# sees. Healing inline splits can only ever recover text the page really shows;
# dissolving block boundaries can invent text it does not.
INLINE_TAGS = frozenset(
    """
    a abbr b bdi bdo cite code data dfn em i ins kbd mark q rp rt ruby s samp
    small span strong sub sup time u var wbr del
    """.split()
)

# Named tags only; `<!-- comments -->`, doctypes and malformed fragments fall
# through to the catch-all below and are treated as block boundaries.
NAMED_TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)\b[^>]*>", re.DOTALL)

# Block boundaries are marked with a sentinel rather than a newline so that the
# whitespace collapse below can tell them apart from whitespace that was already
# in the source. A fetched page has no legitimate NUL, and any it did carry is
# removed before the marker is introduced.
BLOCK_MARKER = "\x00"

# Page shell rather than documentation: these change independently of the article
# and must not reach any watched signal. Held as one constant because *both*
# paths into a page have to agree about what counts as chrome — `strip_html` for
# the text, `html_sections` for the headings. They did not, and that disagreement
# is what let Learn's in-topic table of contents own an article's lead-in; see
# html_sections.
CHROME_ELEMENTS = re.compile(r"<(script|style|nav|header|footer)\b.*?</\1>", re.DOTALL | re.IGNORECASE)


def _tag_separator(match: "re.Match[str]") -> str:
    return "" if match.group(1).lower() in INLINE_TAGS else BLOCK_MARKER


def strip_html(document: str) -> str:
    """Reduce a rendered Learn page to its article text.

    Everything outside <main> is navigation/chrome that changes independently of
    the documentation, so it is discarded before any comparison.

    Within a block, the text is reduced to what a reader actually sees, because
    three different things used to split a phrase that is plainly on the page and
    hide it from phrase matching:

    * an **inline tag**, e.g. ``in <a>Preview</a>`` -- every tag became a newline;
    * a **source line break** inside a paragraph, which renders as a space;
    * a **non-breaking space** (``&nbsp;``), which survived unescaping as U+00A0
      and matches no plain-space pattern.

    Block boundaries are still hard. That asymmetry is the whole design -- see
    INLINE_TAGS. Heading extraction in `html_sections` has always removed tags
    without a separator, so headings were never affected by any of this; body
    text was, which is why one page could publish a release-state notice that
    the phrase signal reported as absent.
    """
    main = re.search(r"<main\b[^>]*>(.*?)</main>", document, re.DOTALL | re.IGNORECASE)
    body = main.group(1) if main else document
    body = CHROME_ELEMENTS.sub(" ", body)
    body = body.replace(BLOCK_MARKER, " ")
    body = NAMED_TAG.sub(_tag_separator, body)
    body = re.sub(r"<[^>]+>", BLOCK_MARKER, body)
    # Entities first: `&lt;script&gt;` must not become a tag, and `&nbsp;` must
    # become U+00A0 before the collapse can fold it into an ordinary space.
    body = html.unescape(body)
    # `\s` covers U+00A0 in str mode, so this is what folds `&nbsp;` away. The
    # block marker is not whitespace, so it survives the collapse intact.
    body = re.sub(r"\s+", " ", body)
    return body.replace(BLOCK_MARKER, "\n")


# A *section* is (heading_level, heading_or_None, body_text). A section's body
# includes its own heading, and the text before the first heading is carried as a
# level-0 section with heading None. Sections exist so that a relevance filter can
# scope the page *text* as well as the heading list -- see relevance_scoped_text.
HTML_HEADING = re.compile(r"<h([1-4])\b[^>]*>(.*?)</h\1>", re.DOTALL | re.IGNORECASE)
MARKDOWN_HEADING = re.compile(r"^\s{0,3}(#{1,4})\s+(.*?)\s*#*\s*$")

# A `<details>`/`<summary>` disclosure is how Learn renders a *reference entry*
# whose title is not a heading. On the Sentinel data connectors reference every
# one of ~430 connectors is one of these, which is why a heading filter reached 0
# of that page's 47 headings while the page plainly carried the entry row 9
# tracks — and why the per-entry "(Preview)" suffix that row 9 cites as evidence
# was invisible to `preview_qualified_headings`.
COLLAPSIBLE_ENTRY = re.compile(r"<summary\b[^>]*>(.*?)</summary>", re.DOTALL | re.IGNORECASE)
# Learn builds its own page furniture from `<details class="popover ...">`: the
# breadcrumb overflow, the page-actions menu, and the "Was this page helpful?"
# widget whose summary text is the bare word "No". Excluding the shell by its
# class, rather than allow-listing what article markup looks like, is deliberate,
# and the direction of failure is the whole reason: if Learn renames the class, a
# shell label turns up in a heading list, which is visible noise and re-baselines
# once. An allow-list that stopped matching would silently drop real entries
# instead, and a watched signal that goes quiet is the failure this repository can
# least afford — it is indistinguishable from "nothing changed" forever.
#
# Matched as *open tag immediately followed by its own `<summary>`*, and the
# lookahead leaves `match.end()` exactly at that summary's offset. Deliberately a
# purely local test: the first attempt bounded each shell widget by searching
# forward for `</details>`, and an unclosed one then ran to the *next* element's
# close tag and silently excluded a real entry — the failure this exclusion exists
# to avoid, reintroduced by the mechanism meant to prevent it. Nothing here can
# reach past one tag, so malformed markup anywhere else cannot cost an entry.
SHELL_COLLAPSIBLE = re.compile(
    r"<details\b(?=[^>]*\bclass=\"[^\"]*\bpopover\b)[^>]*>\s*(?=<summary\b)", re.IGNORECASE
)
# Below `<h4>`, so a collapsible entry always nests under the heading that
# precedes it, is never mistaken for the document title, and is never page-level.
COLLAPSIBLE_LEVEL = 5
DISCLOSURE_EDGE = re.compile(r"<details\b[^>]*>|</details\s*>", re.IGNORECASE)


def heading_text(fragment: str) -> str | None:
    """Reduce a heading or entry-title fragment to the text a reader sees.

    Tags are removed with *no* separator, which is why heading extraction was
    never affected by the inline-tag phrase splitting fixed in `strip_html`:
    `<strong>Preview</strong>` inside a title has always read as "Preview".
    """
    text = html.unescape(re.sub(r"<[^>]+>", "", fragment))
    return re.sub(r"\s+", " ", text).strip() or None


def shell_entry_offsets(body: str) -> set[int]:
    """Offsets of the `<summary>` elements that label Learn's own page furniture.

    One offset per shell widget, and no ranges: see SHELL_COLLAPSIBLE for why a
    span-based version was wrong in the one direction that matters.
    """
    return {match.end() for match in SHELL_COLLAPSIBLE.finditer(body)}


def disclosure_depths(body: str) -> tuple[list[int], list[int]] | None:
    """Nesting depth inside `<details>` after each disclosure edge, or None.

    `None` means the page's disclosures do not balance, and every caller then
    treats the whole document as depth 0 — i.e. stops clipping. **That direction
    is deliberate.** Clipping is what makes an entry atomic, so over-counting
    depth after one unclosed tag would drop every later entry out of the heading
    list silently; refusing to clip at all merely restores the noisier behaviour
    that predates it. Measured on all 16 live html sources on 2026-09-10: every
    one balances exactly (432/432 disclosures on the Sentinel reference, 3/3 —
    the page shell's own — everywhere else), so this is a guard, not a workaround.
    """
    positions: list[int] = []
    depths: list[int] = []
    depth = 0
    for match in DISCLOSURE_EDGE.finditer(body):
        depth += 1 if match.group(0)[1] != "/" else -1
        if depth < 0:
            return None
        positions.append(match.start())
        depths.append(depth)
    return None if depth else (positions, depths)


def disclosure_depth_at(marks: tuple[list[int], list[int]] | None, position: int) -> int:
    """How many `<details>` elements enclose `position`."""
    if marks is None:
        return 0
    positions, depths = marks
    index = bisect.bisect_right(positions, position) - 1
    return depths[index] if index >= 0 else 0


def html_sections(document: str) -> list[tuple[int, str | None, str]]:
    """Split a page into sections at every heading and every collapsible entry.

    **Chrome is removed before the split, and that ordering is a fix.** Learn
    wraps its in-topic table of contents in `<nav aria-label="In this article">`
    around an `<h2>In this article</h2>`. This function used to split on headings
    while only `strip_html` removed chrome, so that navigation heading became a
    section boundary and took ownership of the article's lead-in — the intro
    paragraph and any page-wide release-state banner standing above the first real
    heading. `relevance_scoped_text` keeps page-level text precisely so such a
    banner can never be scoped out; on all 16 html sources it was keeping the
    breadcrumbs while the banner sat one section below it, out of scope. The rule
    that the heading list and the text a filter scopes must not disagree about the
    page is stated in `section_headings`; `CHROME_ELEMENTS` is now the single
    place either path asks what is chrome.

    Collapsible entries are boundaries too, at `COLLAPSIBLE_LEVEL` — see
    `COLLAPSIBLE_ENTRY` for why a page can carry its real entries there and
    nowhere else.

    **A collapsible entry is atomic: everything inside it is its body, including
    any heading or nested disclosure.** Without that, an entry's own sub-heading
    became a *sibling* section — a heading is always a shallower level than
    `COLLAPSIBLE_LEVEL`, so it popped the entry off `relevance_scoped_text`'s
    ancestor stack and silently evicted the remainder of the entry's body from
    scope. Measured on the Sentinel reference: one `<h3>` placed inside the
    matched Copilot entry dropped the scoped text from 5,184 to 4,010 characters
    **with the fingerprint unchanged**, so a "generally available" sentence under
    that heading went undetected while the identical sentence without the heading
    was caught. Not hypothetical — 37 of that page's 46 authored headings already
    sit inside connector entries; the tracked entry simply had none yet. A nested
    disclosure did the same thing for the same reason. Treating an entry as a leaf
    fixes both, and it is also what makes the mis-authored `<h1>` inside one
    connector entry stop being page-level at the root rather than by rule.
    """
    main = re.search(r"<main\b[^>]*>(.*?)</main>", document, re.DOTALL | re.IGNORECASE)
    body = CHROME_ELEMENTS.sub(" ", main.group(1) if main else document)

    shell = shell_entry_offsets(body)
    marks = disclosure_depths(body)
    boundaries: list[tuple[int, int, str]] = [
        (match.start(), int(match.group(1)), match.group(2))
        for match in HTML_HEADING.finditer(body)
        if disclosure_depth_at(marks, match.start()) == 0
    ]
    boundaries += [
        (match.start(), COLLAPSIBLE_LEVEL, match.group(1))
        for match in COLLAPSIBLE_ENTRY.finditer(body)
        # Depth 1 is an entry's own label. Deeper is a disclosure nested inside
        # an entry, which belongs to that entry's body like any other markup.
        if match.start() not in shell and disclosure_depth_at(marks, match.start()) <= 1
    ]
    boundaries.sort(key=lambda boundary: boundary[0])

    sections: list[tuple[int, str | None, str]] = []
    level = 0
    heading: str | None = None
    start = 0
    for position, boundary_level, fragment in boundaries:
        # A boundary with no visible title is still a boundary; it simply has no
        # title for a filter to match, so its section is out of scope unless it
        # inherits. Skipping it instead would hand its body to the *previous*
        # section — and if that one matched the filter, an untitled disclosure
        # would quietly donate its contents to a watched entry.
        text = heading_text(fragment)
        sections.append((level, heading, strip_html(body[start:position])))
        level = boundary_level
        heading = text
        start = position
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
      heading, and the document title's own section. Neither belongs to a
      product entry, so no per-entry pattern can be expected to claim it, and a
      page-wide release-state banner lives in exactly that position. Dropping it
      would lose real signal: the notice that all Sentinel data connectors "are
      currently in Preview" is one half of matrix row 9's documented conflict.

      **That justification was false when it was first written here, and issue
      #31 is the record of it.** The banner does stand above the first *authored*
      heading -- but below Learn's navigation heading, and `html_sections` used
      to split on headings before removing chrome. So the notice was owned by an
      `<h2>In this article</h2>` and this rule kept the breadcrumbs instead. The
      rule was sound and simply never reached the thing it was justified by. A
      rationale the code cannot exhibit is the defect class issue #31 filed, so
      the ordering fix in `html_sections` and this paragraph belong together.

    * **Page-level is positional, not a heading level.** Only the *first* heading
      is the title. This used to read as "any heading at `PAGE_LEVEL` or above",
      and the Sentinel reference page carries a mis-authored
      `<h1>NOTE - UPDATE:</h1>` buried inside one connector entry: it held
      336,102 of that page's 1,084,895 characters -- 31% -- permanently in scope,
      on the one source whose entire reason for declaring a filter was that an
      unfiltered fingerprint of it would change on nearly every run. A stray
      heading deep in a document belongs to the entry containing it, whatever
      level it is marked up at.

    Page-level text is kept **without conferring scope on anything nested under
    it**. That is the whole subtlety of the third rule: marking the title in
    scope as an *ancestor* would make every section on the page inherit it and
    restore the unfiltered behaviour this function exists to remove.
    """
    return "\n".join(body for _page_level, body in relevance_scoped_parts(sections, patterns))


def relevance_scoped_parts(
    sections: list[tuple[int, str | None, str]], patterns: list[str] | None
) -> list[tuple[bool, str]]:
    """The scoped text, in document order, each part tagged page-level or not.

    `relevance_scoped_text` is the concatenation; the tag exists because the two
    regions have to be fingerprinted *separately*. Unioning them hid the change
    row 9 exists to catch: the page-wide banner permanently contributes the phrase
    `in preview`, so a per-entry preview sentence appearing in the watched entry
    produced an identical fingerprint and no change note at all — while the same
    sentence phrased "in public preview" was caught, which is what makes the gap
    so easy to miss. Row 9's whole conflict is *page-wide banner versus per-entry
    label*, and a detector that cannot tell the two regions apart cannot see that
    conflict resolve in either direction. It is also the exact falsifier of the
    matrix's published claim that the tracked entry's "body contains no
    release-state sentence at all".
    """
    if not patterns:
        return [(False, "\n".join(body for _level, _heading, body in sections))]
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    kept: list[tuple[bool, str]] = []
    ancestors: list[tuple[int, bool]] = []
    title_seen = False
    for index, (level, heading, body) in enumerate(sections):
        while ancestors and ancestors[-1][0] >= level:
            ancestors.pop()
        # Two page-level cases and no others. The text above the first boundary,
        # which is section 0 alone -- **the index matters**: a later section can
        # also carry no heading, when a boundary has no visible title, and reading
        # *that* as page-level would force an untitled disclosure's body into
        # scope on every page that has one. And the document title, which does not
        # include a heading at PAGE_LEVEL appearing after one already has.
        if heading is None:
            if index == 0:
                kept.append((True, body))
                ancestors.append((level, False))
                continue
        elif level <= PAGE_LEVEL and not title_seen:
            title_seen = True
            kept.append((True, body))
            ancestors.append((level, False))
            continue
        # **Only a heading at PAGE_LEVEL can consume the title slot.** An earlier
        # version let any authored heading do it, on the theory that a level-1
        # heading appearing after other headings must be a stray. The cost was
        # far worse than the case it guarded: a single `<h2>` above the article
        # `<h1>` — one Learn template edit away — demoted the real title, so the
        # page's own lead-in left scope and row 9's banner vanished from the
        # phrase set with no warning, reported only as a phrase *disappearing*.
        # That is the shape of the false absence claim this change retracts,
        # rebuilt in code. `title_missing` announces the residual case instead.
        in_scope = bool(ancestors and ancestors[-1][1]) or (
            heading is not None and any(c.search(heading) for c in compiled)
        )
        ancestors.append((level, in_scope))
        if in_scope:
            kept.append((False, body))
    return kept


def title_missing(sections: list[tuple[int, str | None, str]]) -> bool:
    """True when a page has no heading at `PAGE_LEVEL` for the title rule to keep.

    Only meaningful for a filtered source, and it is a coverage warning rather
    than an error. Page-level text is what carries a page-wide release-state
    banner, and it is kept in scope by exactly two things: the text above the
    first heading, and the document title's section. A page with no title-level
    heading has only the first of those, so a banner sitting below any other
    heading is out of scope — silently, and reported at most as a phrase that
    disappeared, which reads as a source change rather than as lost coverage.
    That misreading is precisely what this change retracts a published claim for,
    so the condition is announced in the same way a collapsed filter is.
    """
    return not any(
        heading is not None and level <= PAGE_LEVEL for level, heading, _body in sections
    )


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
    parts = relevance_scoped_parts(sections, relevance) if relevance else []
    scoped = "\n".join(body for _page_level, body in parts) if relevance else text
    lowered = scoped.lower()
    signals = {
        "headings": filtered,
        "preview_qualified_headings": sorted(h for h in filtered if PREVIEW_QUALIFIER.search(h)),
        "status_phrases_present": sorted(p for p in STATUS_PHRASES if p in lowered),
        "heading_count": len(filtered),
        "relevance_filtered": bool(relevance),
    }
    if relevance:
        # Only a filtered source has two regions to tell apart; an unfiltered one
        # reads its whole page and the split would be meaningless. Omitted rather
        # than emitted empty, so the 18 unfiltered sources' stored fingerprints
        # are untouched by this field existing at all.
        for field, page_level_wanted in (
            ("page_level_status_phrases", True),
            ("entry_status_phrases", False),
        ):
            region = "\n".join(
                body for page_level, body in parts if page_level is page_level_wanted
            ).lower()
            signals[field] = sorted(p for p in STATUS_PHRASES if p in region)
    return signals


def filter_collapsed(signals: dict) -> bool:
    """True when a source declares a relevance filter that matched no heading.

    Not an error and not a change: the fetch succeeded and the fingerprint is
    honest about what it saw. It is the *coverage* that has gone -- the source is
    now watching only its page-level text, and every later run will call that
    "unchanged". Observed live on `sentinel-data-connectors-reference` in
    September 2026, whose filter matched 0 of 47 headings -- not because a
    heading filter cannot reach a collapsible entry, which was the original and
    since-retracted diagnosis, but because section extraction did not then treat
    a collapsible entry as a section. That source no longer collapses: its
    filter now matches 2 of the page's 437 entry titles. The check stays because
    the condition is a property of any filter, not of that page.
    """
    return bool(signals.get("relevance_filtered")) and not signals.get("heading_count")


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


def signals_for_source(source: dict) -> tuple[dict, list[str]]:
    """The source's signals, plus any *coverage* warnings about how they were taken.

    Warnings are returned beside the signals rather than stored in them, because
    everything in the signals dict is fingerprinted wholesale: a coverage note
    inside it would make "this source is watching less than it claims" look like a
    status change, which is the one confusion this tier exists to prevent.
    """
    mode = source["mode"]
    relevance = source.get("relevance_filter")
    raw = fetch(source["url"])

    if mode == "version":
        return version_signals(raw, source["version_pattern"]), []

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
        }, []

    if mode == "markdown":
        body = strip_frontmatter(raw)
        sections = markdown_sections(body)
        text = body
    elif mode == "html":
        sections = html_sections(raw)
        text = strip_html(raw)
    else:
        raise ValueError(f"unknown mode: {mode}")

    warnings: list[str] = []
    if relevance and title_missing(sections):
        warnings.append(
            "no heading at page level, so the only page-level text in scope is "
            "whatever precedes the first heading — a page-wide release-state "
            "banner below any other heading is not being watched"
        )
    return extract_signals(text, sections, relevance), warnings


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
    # A filtered source reports its two regions separately, because the union
    # cannot express the event row 9 turns on: a page-wide banner already
    # supplying a phrase masks the same phrase appearing in a watched entry. Where
    # the split fields are present they replace the union note rather than adding
    # to it -- they say everything it said and locate it as well.
    regions = [
        ("page_level_status_phrases", "page-level text"),
        ("entry_status_phrases", "in-scope entries"),
    ]
    # The regions replace the union note only when *both* snapshots carry them.
    # Then nothing is lost: no status phrase contains a newline and the regions are
    # joined with one, so a phrase matches inside a single region and the union is
    # exactly their union. When only one snapshot has them -- the run right after
    # this field was added -- that identity does not hold across the pair, and
    # reporting regions alone silently dropped a real change: the phrase
    # `deprecated` leaving row 9's scope went unnamed, because the older snapshot
    # had no region to lose it from.
    split = [
        (field, label)
        for field, label in regions
        if field in current and field in previous
    ]
    if not split:
        scope = (
            "relevance-scoped sections"
            if (current.get("relevance_filtered") or previous.get("relevance_filtered"))
            else "whole page"
        )
        split = [("status_phrases_present", scope)]
    for field, label in split:
        before_phrases = set(previous.get(field) or [])
        after_phrases = set(current.get(field) or [])
        for phrase in sorted(after_phrases - before_phrases):
            notes.append(f"status phrase appeared in {label}: {phrase!r}")
        for phrase in sorted(before_phrases - after_phrases):
            notes.append(f"status phrase disappeared from {label}: {phrase!r}")
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


def use_utf8_streams() -> None:
    """Print fetched page text without depending on the console's code page.

    This one matters most of the four scripts: the `[changed]` notes and the
    `[warn]` lines echo headings and phrases taken verbatim from live Microsoft
    Learn pages, and a heading as ordinary as "Settings -> Privacy" contains
    U+2192, which a cp1252 console cannot encode. The run would die with
    UnicodeEncodeError *after* fetching, mid-report. CI runs UTF-8 so it never
    sees this, and tiers D2 and D3 are currently operated locally, so the local
    path is the one that actually runs. See scripts/changelog_entry.py, where a
    published command was found crashing for exactly this reason.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main() -> int:
    use_utf8_streams()
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
    collapsed_filter_ids: list[str] = []
    coverage_warning_ids: list[str] = []
    change_notes: dict[str, list[str]] = {}

    for source in registry.get("sources", []):
        source_id = source["id"]
        try:
            signals, coverage_warnings = signals_for_source(source)
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

        # A relevance filter matching zero headings is not a fingerprint event --
        # it carries no status meaning and must not move a baseline -- but it must
        # not be silent either. It means the registry is claiming a narrowing it is
        # not achieving: either the filter is wrong, or the page restructured out
        # from under it. Either way that source's watched signal has collapsed to
        # its page-level text, which is indistinguishable from "nothing changed" on
        # every subsequent run. That indistinguishability is how this class of gap
        # survives a release, so it is announced.
        if filter_collapsed(signals):
            collapsed_filter_ids.append(source_id)
            print(
                f"[warn] {source_id}: relevance_filter matched 0 headings — this source's "
                "watched signal has collapsed to page-level text. The filter or the page "
                "structure needs a human look; nothing here is a status change.",
                file=sys.stderr,
            )

        # The other coverage condition, reported the same way and for the same
        # reason: it costs the source part of what it claims to watch, it is not a
        # status change, and every later run would call it "unchanged".
        for warning in coverage_warnings:
            coverage_warning_ids.append(source_id)
            print(f"[warn] {source_id}: {warning}", file=sys.stderr)

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
            # A `[changed]` line with no notes is an alarm nobody can act on, and
            # the docs' own argument against unattributed alarms applies hardest
            # here: the reader cannot tell an unreportable difference from a bug in
            # the reporter. Reachable whenever the signals schema gains a field,
            # which moves every affected fingerprint while no *reported* field
            # differs.
            change_notes[source_id] = describe_change(prior.get("signals", {}), signals) or [
                "fingerprint moved but no field this report covers differs — compare the "
                "stored `signals` objects directly; a signals-schema addition does this"
            ]
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
            # Fetched fine, fingerprinted fine, and watching almost nothing. Kept
            # separate from failed_sources because the two need opposite responses:
            # a failed source recovers by itself on the next run, a collapsed
            # filter never does.
            "collapsed_filter_sources": sorted(collapsed_filter_ids),
            # Same class as collapsed_filter_sources -- a source watching less
            # than its registry entry claims -- kept as its own key because the
            # remedy differs: a collapsed filter needs a new filter, a lost
            # page level needs a different source or a body-scoped mode.
            "coverage_warning_sources": sorted(set(coverage_warning_ids)),
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
            json.dumps(
                {
                    "updated_at": now,
                    "extractor_version": EXTRACTOR_VERSION,
                    "sources": results,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"[baseline] wrote {BASELINE_FILE}")

    emit_github_output(
        changed=str(bool(changed_ids)).lower(),
        changed_sources=",".join(sorted(changed_ids)),
        failed_sources=",".join(sorted(failed_ids)),
        collapsed_filter_sources=",".join(sorted(collapsed_filter_ids)),
        coverage_warning_sources=",".join(sorted(set(coverage_warning_ids))),
    )

    # Exit 0 even when sources fail: a fetch failure is an expected, isolated
    # condition, not a pipeline error. The stale guard is what escalates. The one
    # non-zero exit is a structurally broken registry, checked before the loop —
    # that is a repository defect, and silently degrading it into "every source
    # unreachable" would hide it behind the very mechanism built for outages.
    return 0


if __name__ == "__main__":
    sys.exit(main())
