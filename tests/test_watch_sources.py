#!/usr/bin/env python3
"""Tests for the tier-D1 watcher's signal extraction and registry validation.

Standard library only, like the scripts they cover: no pytest, no pip install
step in CI. Run with `python3 -m unittest discover -s tests`.

Why these exist. The signal-scoping defect these tests pin down was *silent*:
every scheduled run was green, the `[changed]` line looked plausible, and it took
re-deriving the page's heading counts by hand to see that 84 of 86 headings were
out of scope while every word inside them still drove the fingerprint. A test
whose fixture changes only out-of-scope text is the cheapest thing that would
have caught it, so it is the first test in this file.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script(name: str):
    """Import a file from scripts/ that is a standalone script, not a package."""
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


watch = load_script("watch_sources")

AI_RELEVANCE = ["\\bAI\\b", "\\bFoundry\\b", "artificial intelligence"]

# Shaped like the real Defender for Cloud release notes: a dated month heading,
# one in-scope AI entry under it, and one out-of-scope entry for another product.
RELEASE_NOTES = """---
title: What's new in Microsoft Defender for Cloud
ms.date: 09/09/2026
---

# What's new in Microsoft Defender for Cloud

This article summarizes what's new in Microsoft Defender for Cloud.

## September 2026

### AI security posture management for Azure AI Foundry (Preview)

AI security posture management now covers Foundry agents. This capability is in preview.

### Classic Defender for SQL APIs retirement

The classic Defender for SQL APIs for Vulnerability Assessment and Advanced
Threat Protection is documented here.
"""

# The ONLY difference from RELEASE_NOTES: the SQL entry gains a retirement
# notice. This is the change that escalated on five consecutive days.
RELEASE_NOTES_WITH_SQL_RETIREMENT = RELEASE_NOTES.replace(
    "Threat Protection is documented here.",
    "Threat Protection will be retired on August 16, 2027.",
)


def markdown_signals(document: str, relevance: list[str] | None = AI_RELEVANCE) -> dict:
    body = watch.strip_frontmatter(document)
    return watch.extract_signals(body, watch.markdown_sections(body), relevance)


class RelevanceScopingTests(unittest.TestCase):
    def test_out_of_scope_retirement_notice_reports_no_change(self):
        """The regression test for the defect in issue #27.

        A fixture whose only change is an out-of-scope retirement notice must
        produce no fingerprint change and no change note at all.
        """
        before = markdown_signals(RELEASE_NOTES)
        after = markdown_signals(RELEASE_NOTES_WITH_SQL_RETIREMENT)

        self.assertEqual(watch.fingerprint(before), watch.fingerprint(after))
        self.assertEqual(watch.describe_change(before, after), [])

    def test_out_of_scope_phrase_never_enters_the_signal(self):
        """'retired' must be absent from the phrase set, not merely stable.

        Asserted separately from the no-change test because two different bugs
        produce a passing no-change test: correct scoping, and a phrase set that
        happens to contain the phrase both before and after.
        """
        signals = markdown_signals(RELEASE_NOTES_WITH_SQL_RETIREMENT)
        self.assertNotIn("retired", signals["status_phrases_present"])
        self.assertEqual(signals["status_phrases_present"], ["in preview"])
        self.assertTrue(signals["relevance_filtered"])

    def test_the_out_of_scope_heading_is_also_filtered_out(self):
        """The heading half of the filter still behaves as it always did."""
        signals = markdown_signals(RELEASE_NOTES)
        self.assertEqual(
            signals["headings"],
            ["AI security posture management for Azure AI Foundry (Preview)"],
        )
        self.assertEqual(signals["heading_count"], 1)

    def test_ai_word_boundary_does_not_match_apis(self):
        r"""Pins the regex fact the whole finding rests on: \bAI\b vs "APIs".

        There is no right-hand word boundary between "AI" and the "P" of "APIs",
        so the SQL entry correctly fails the filter. If this ever starts
        matching, the fixture above stops testing what it claims to test.
        """
        kept = watch.apply_relevance_filter(
            ["Classic Defender for SQL APIs retirement"], AI_RELEVANCE
        )
        self.assertEqual(kept, [])

    def test_in_scope_status_phrase_is_still_detected(self):
        """Scoping must not cost sensitivity where it matters."""
        before = markdown_signals(RELEASE_NOTES)
        after = markdown_signals(
            RELEASE_NOTES.replace(
                "This capability is in preview.", "This capability is generally available."
            )
        )
        self.assertNotEqual(watch.fingerprint(before), watch.fingerprint(after))
        notes = watch.describe_change(before, after)
        self.assertIn(
            "status phrase appeared in relevance-scoped sections: 'generally available'", notes
        )
        self.assertIn(
            "status phrase disappeared from relevance-scoped sections: 'in preview'", notes
        )

    def test_nested_subsection_inherits_scope_from_its_parent(self):
        """A matching entry owns its subsections, whose headings say nothing."""
        document = RELEASE_NOTES.replace(
            "AI security posture management now covers Foundry agents. This capability is in preview.",
            "AI security posture management now covers Foundry agents.\n\n"
            "#### Details\n\nThis capability is in preview.",
        )
        signals = markdown_signals(document)
        self.assertEqual(signals["status_phrases_present"], ["in preview"])

    def test_page_level_banner_is_in_scope(self):
        """A page-wide release-state notice under the H1 must not be dropped.

        This is the row-9 case: the Sentinel connector reference states that all
        connectors "are currently in Preview" at page level, and that notice is
        one half of the row's documented conflict.
        """
        document = RELEASE_NOTES.replace(
            "This article summarizes what's new in Microsoft Defender for Cloud.",
            "This article summarizes what's new. Some features are in development.",
        )
        signals = markdown_signals(document)
        self.assertIn("in development", signals["status_phrases_present"])

    def test_page_level_section_does_not_confer_scope_on_children(self):
        """Keeping the H1 must not re-admit the whole page through inheritance."""
        document = RELEASE_NOTES_WITH_SQL_RETIREMENT
        scoped = watch.relevance_scoped_text(
            watch.markdown_sections(watch.strip_frontmatter(document)), AI_RELEVANCE
        )
        self.assertIn("Foundry agents", scoped)
        self.assertNotIn("retired on August 16, 2027", scoped)

    def test_unfiltered_source_sees_the_whole_page(self):
        """Sources with no relevance_filter are unchanged by scoping.

        This is what keeps the stored fingerprints of the unfiltered sources
        valid across this change: only the filtered ones re-baseline.
        """
        signals = markdown_signals(RELEASE_NOTES_WITH_SQL_RETIREMENT, relevance=None)
        self.assertIn("retired", signals["status_phrases_present"])
        self.assertIn("in preview", signals["status_phrases_present"])
        self.assertFalse(signals["relevance_filtered"])

    def test_unfiltered_change_note_says_whole_page(self):
        before = markdown_signals(RELEASE_NOTES, relevance=None)
        after = markdown_signals(RELEASE_NOTES_WITH_SQL_RETIREMENT, relevance=None)
        self.assertEqual(
            watch.describe_change(before, after),
            ["status phrase appeared in whole page: 'retired'"],
        )


class CollapsedFilterTests(unittest.TestCase):
    """A filter that matches nothing must be announced, not silently obeyed.

    This is the condition found live on `sentinel-data-connectors-reference`
    while verifying the scoping fix: its filter matched 0 of 47 headings,
    because the connector entries on that page are not headings. The source had
    looked like it was watching something only because the phrase signal was
    taken over the whole page — so correcting the scope exposed a source whose
    coverage was already gone.

    That source is watched again as of issue #31 — collapsible entries are
    sections now — so it no longer collapses. These tests stay: the condition is
    a property of any filter, not of that one page, and the warning is the only
    reason the gap was ever looked at. See CollapsibleEntryTests for the fix.
    """

    def test_a_filter_matching_no_heading_is_flagged(self):
        signals = markdown_signals(RELEASE_NOTES, relevance=["\\bKubernetes\\b"])
        self.assertEqual(signals["heading_count"], 0)
        self.assertTrue(watch.filter_collapsed(signals))

    def test_a_filter_that_matches_is_not_flagged(self):
        self.assertFalse(watch.filter_collapsed(markdown_signals(RELEASE_NOTES)))

    def test_a_source_with_no_filter_is_never_flagged(self):
        """An unfiltered source has no filter to collapse, however few headings."""
        signals = markdown_signals("body text with no headings at all\n", relevance=None)
        self.assertEqual(signals["heading_count"], 0)
        self.assertFalse(watch.filter_collapsed(signals))

    def test_page_level_text_still_reaches_the_signal_when_the_filter_collapses(self):
        """The collapsed case degrades to page-level text, and says so.

        Asserted because this is what makes the warning readable rather than
        alarming: the source is not broken, it is watching only the preamble.
        """
        signals = markdown_signals(RELEASE_NOTES, relevance=["\\bKubernetes\\b"])
        self.assertEqual(signals["headings"], [])
        self.assertEqual(signals["status_phrases_present"], [])


HTML_PAGE = """<html><body><main>
<h1>Cloud app catalog</h1>
<p>Some services are in development.</p>
<h2>Generative AI category</h2>
<p>This category is generally available.</p>
<h2>Kubernetes hardening</h2>
<p>This other thing is documented.</p>
</main></body></html>"""

HTML_PAGE_WITH_OUT_OF_SCOPE_CHANGE = HTML_PAGE.replace(
    "This other thing is documented.", "This other thing is now deprecated."
)


def html_signals(document: str, relevance: list[str] | None = AI_RELEVANCE) -> dict:
    return watch.extract_signals(
        watch.strip_html(document), watch.html_sections(document), relevance
    )


class HtmlScopingTests(unittest.TestCase):
    def test_out_of_scope_html_section_does_not_move_the_fingerprint(self):
        before = html_signals(HTML_PAGE)
        after = html_signals(HTML_PAGE_WITH_OUT_OF_SCOPE_CHANGE)
        self.assertEqual(watch.fingerprint(before), watch.fingerprint(after))
        self.assertEqual(watch.describe_change(before, after), [])

    def test_in_scope_html_section_and_page_level_text_are_read(self):
        signals = html_signals(HTML_PAGE)
        self.assertEqual(signals["headings"], ["Generative AI category"])
        self.assertEqual(
            signals["status_phrases_present"], ["generally available", "in development"]
        )

    def test_section_headings_match_the_document_order(self):
        headings = watch.section_headings(watch.html_sections(HTML_PAGE))
        self.assertEqual(
            headings, ["Cloud app catalog", "Generative AI category", "Kubernetes hardening"]
        )


# The shape that exposed the defect, reduced from the live Sentinel data
# connectors reference: the release-state word is wrapped in a link, so the
# phrase a reader sees as continuous was split by a tag.
INLINE_SPLIT_PAGE = """<html><body><main>
<h1>Find your data connector</h1>
<p>Note that Microsoft Sentinel data connectors are currently in
<a href="https://example.invalid/terms">Preview</a>. Additional terms apply.</p>
<h2>Generative AI category</h2>
<p>This category is <strong>generally</strong> available.</p>
</main></body></html>"""

# Two separate blocks that must NOT be joined. Whitespace normalisation would
# manufacture "in preview" here; dissolving inline tags cannot.
BLOCK_BOUNDARY_PAGE = """<html><body><main>
<h1>Find your data connector</h1>
<p>This connector is not available in</p>
<p>Preview mode is documented elsewhere.</p>
</main></body></html>"""


class InlineTagPhraseTests(unittest.TestCase):
    """A status phrase interrupted by an inline tag is on the page, so it must be seen.

    Regression for the defect that let `sentinel-data-connectors-reference`
    publish "data connectors are currently in Preview" while the phrase signal
    reported no `in preview` at all: `strip_html` replaced *every* tag with a
    newline, including the `<a>` wrapping the word "Preview".
    """

    def test_phrase_split_by_an_inline_tag_is_detected(self):
        signals = html_signals(INLINE_SPLIT_PAGE, None)
        self.assertIn("in preview", signals["status_phrases_present"])

    def test_phrase_split_by_an_inline_tag_is_detected_when_the_filter_collapses(self):
        # The live case: the filter matches no heading, so only page-level text
        # is in scope -- and the notice lives exactly there.
        signals = html_signals(INLINE_SPLIT_PAGE, ["Copilot"])
        self.assertEqual(signals["heading_count"], 0)
        self.assertTrue(watch.filter_collapsed(signals))
        self.assertIn("in preview", signals["status_phrases_present"])

    def test_the_notice_reads_as_one_continuous_line(self):
        text = watch.strip_html(INLINE_SPLIT_PAGE)
        self.assertIn("are currently in Preview. Additional terms apply.", text)

    def test_block_boundaries_are_still_newlines(self):
        text = watch.strip_html(INLINE_SPLIT_PAGE)
        self.assertNotIn("apply. Generative AI category", text)
        self.assertIn("\nGenerative AI category\n", text)

    def test_a_non_breaking_space_does_not_hide_a_phrase(self):
        page = INLINE_SPLIT_PAGE.replace("currently in\n", "currently&nbsp;in&nbsp;")
        signals = html_signals(page, None)
        self.assertIn("in preview", signals["status_phrases_present"])

    def test_a_source_line_break_does_not_hide_a_phrase(self):
        # The fixture already wraps the source line between "in" and the link,
        # which renders as a space; pin it explicitly so the reason is legible.
        self.assertIn("currently in\n<a", INLINE_SPLIT_PAGE)
        signals = html_signals(INLINE_SPLIT_PAGE, None)
        self.assertIn("in preview", signals["status_phrases_present"])

    def test_a_phrase_inside_an_inline_tag_is_still_detected(self):
        # "generally available" straddles </strong>, so the closing tag must not
        # split it either.
        signals = html_signals(INLINE_SPLIT_PAGE, None)
        self.assertIn("generally available", signals["status_phrases_present"])

    def test_a_block_boundary_does_not_manufacture_a_phrase(self):
        # The false-positive guard. This is what separates dissolving inline
        # tags from normalising whitespace: the words are adjacent in the source
        # but a reader never sees the phrase, so it must not be reported.
        signals = html_signals(BLOCK_BOUNDARY_PAGE, None)
        self.assertNotIn("in preview", signals["status_phrases_present"])

    def test_headings_were_never_affected(self):
        # `html_sections` has always stripped heading tags without a separator,
        # so heading-derived signals need no change. Pin that, because the fix
        # would otherwise look like it should have touched them too.
        page = INLINE_SPLIT_PAGE.replace(
            "<h2>Generative AI category</h2>",
            '<h2>Generative <em>AI</em> category</h2>',
        )
        headings = watch.section_headings(watch.html_sections(page))
        self.assertIn("Generative AI category", headings)

    def test_the_existing_unaffected_page_is_unchanged(self):
        # Sources with no inline markup inside a tracked phrase must keep the
        # signals they had, or the re-baseline would be wider than its cause.
        signals = html_signals(HTML_PAGE)
        self.assertEqual(signals["headings"], ["Generative AI category"])
        self.assertEqual(
            signals["status_phrases_present"], ["generally available", "in development"]
        )


class RegistryValidationTests(unittest.TestCase):
    """`registry_problems` now covers human_only_sources as well as sources."""

    WATCHED = {
        "id": "watched",
        "title": "A watched source",
        "url": "https://learn.microsoft.com/en-us/purview/example",
        "mode": "html",
        "matrix_rows": [1],
    }
    HUMAN_ONLY = {
        "id": "human-only",
        "title": "A human-only source",
        "cite_url": "https://docs.github.com/en/copilot/concepts/policies",
        "matrix_rows": [12],
        "reason": "Human-only by design.",
    }

    def problems(self, sources=None, human_only=None) -> list[str]:
        return watch.registry_problems(
            {
                "sources": sources if sources is not None else [dict(self.WATCHED)],
                "human_only_sources": human_only if human_only is not None else [dict(self.HUMAN_ONLY)],
            }
        )

    def test_a_well_formed_registry_has_no_problems(self):
        self.assertEqual(self.problems(), [])

    def test_human_only_entry_with_no_row_mapping_is_reported(self):
        entry = dict(self.HUMAN_ONLY)
        del entry["matrix_rows"]
        self.assertIn(
            "human-only: declares neither 'matrix_rows' nor 'crosswalk_rows'; "
            "a source that backs nothing cannot be checked for coverage",
            self.problems(human_only=[entry]),
        )

    def test_crosswalk_rows_satisfy_the_mapping_requirement(self):
        entry = dict(self.HUMAN_ONLY)
        del entry["matrix_rows"]
        entry["crosswalk_rows"] = ["NIST AI 600-1 framework-versions row"]
        self.assertEqual(self.problems(human_only=[entry]), [])

    def test_id_duplicated_across_the_two_arrays_is_reported(self):
        """The mis-join that would make an unwatched row look watched."""
        entry = dict(self.HUMAN_ONLY)
        entry["id"] = "watched"
        self.assertIn("watched: duplicate id", self.problems(human_only=[entry]))

    def test_human_only_entry_may_not_carry_a_fetch_url(self):
        entry = dict(self.HUMAN_ONLY)
        entry["url"] = "https://docs.github.com/en/copilot/concepts/policies"
        self.assertTrue(
            any("must not carry 'url'" in problem for problem in self.problems(human_only=[entry]))
        )

    def test_human_only_entry_requires_a_reason(self):
        entry = dict(self.HUMAN_ONLY)
        del entry["reason"]
        self.assertTrue(
            any("require a 'reason'" in problem for problem in self.problems(human_only=[entry]))
        )

    def test_boolean_is_not_accepted_as_a_row_number(self):
        entry = dict(self.WATCHED)
        entry["matrix_rows"] = [True]
        self.assertIn(
            "watched: 'matrix_rows' must be a list of integers", self.problems(sources=[entry])
        )

    def test_missing_id_is_reported_against_its_array(self):
        entry = dict(self.HUMAN_ONLY)
        del entry["id"]
        self.assertIn("human_only_sources[0]: missing 'id'", self.problems(human_only=[entry]))

    def test_the_committed_registry_is_clean(self):
        """The real sources.json passes the checks it just gained."""
        registry = json.loads(
            (REPO_ROOT / ".github" / "watch-state" / "sources.json").read_text(encoding="utf-8")
        )
        self.assertEqual(watch.registry_problems(registry), [])


# Reduced from the live Sentinel data connectors reference, fetched 2026-09-10,
# keeping exactly the four structures that defeated row 9's watch: Learn's
# in-topic table of contents is a <nav> wrapped around an <h2>In this article</h2>
# and the page's release-state banner sits *below* it; the connector entries are
# <details>/<summary> disclosures rather than headings; one entry contains a
# mis-authored <h1>; and the page shell contributes its own <details> popovers.
CONNECTOR_REFERENCE_PAGE = """<html><body><main>
<details id="article-header-breadcrumbs-overflow-popover" class="popover popover-left">
<summary aria-label="All breadcrumbs"><span class="icon"></span></summary>
<div class="popover-content"></div>
</details>
<h1>Find your Microsoft Sentinel data connector</h1>
<nav id="center-doc-outline" class="doc-outline" aria-label="In this article">
<h2 id="ms--in-this-article">In this article</h2>
<ul><li><a href="#prerequisites">Data connector prerequisites</a></li></ul>
</nav>
<div class="content">
<p>This article lists all supported, out-of-the-box data connectors.</p>
<div class="IMPORTANT"><p>Important</p><ul>
<li>Note that Microsoft Sentinel data connectors are currently in <strong>Preview</strong>.
The Azure Preview Supplemental Terms include additional legal terms.</li>
</ul></div>
<h2>Sentinel data connectors</h2>
<details><summary><strong>Microsoft Copilot</strong></summary>
<p>The Microsoft Copilot logs connector ingests Copilot-generated activity logs.</p>
</details>
<details><summary><strong>Microsoft Defender for Office 365 (Preview)</strong></summary>
<p>This connector ingests Defender for Office 365 alerts.</p>
</details>
<details><summary><strong>Kubernetes audit</strong></summary>
<h1>NOTE - UPDATE:</h1>
<p>This connector is deprecated and will be retired.</p>
</details>
</div>
<details class="popover popover-top" id="mobile-help-popover" data-test-id="footer-feedback-popover">
<summary>No</summary>
</details>
</main></body></html>"""

# The two patterns row 9's evidence actually rests on. The notice is deliberately
# NOT among them: it is body text, no heading pattern can ever reach it, and it is
# covered by the page-level rule instead. See the sources.json note.
CONNECTOR_RELEVANCE = ["Copilot", "Microsoft Defender for Office 365"]


def connector_signals(document: str = CONNECTOR_REFERENCE_PAGE) -> dict:
    return html_signals(document, relevance=CONNECTOR_RELEVANCE)


class ChromeHeadingTests(unittest.TestCase):
    """A navigation heading must not own the article it links to.

    `html_sections` split on headings before removing chrome, so Learn's in-topic
    table of contents — a <nav> around an <h2>In this article</h2> — became a
    section boundary and took ownership of everything above the first authored
    heading. That is where a page-wide release-state banner lives, and it is the
    mechanical reason issue #31's row-9 notice was out of scope while
    `relevance_scoped_text` existed specifically to keep it.
    """

    def test_the_navigation_heading_is_not_a_section(self):
        headings = watch.section_headings(watch.html_sections(CONNECTOR_REFERENCE_PAGE))
        self.assertNotIn("In this article", headings)

    def test_the_authored_headings_survive_chrome_removal(self):
        headings = watch.section_headings(watch.html_sections(CONNECTOR_REFERENCE_PAGE))
        self.assertIn("Find your Microsoft Sentinel data connector", headings)
        self.assertIn("Sentinel data connectors", headings)

    def test_the_page_level_banner_reaches_the_signal(self):
        """The row-9 case, end to end: the notice is watched, not merely present."""
        self.assertIn("in preview", connector_signals()["status_phrases_present"])

    def test_the_banner_is_in_the_scoped_text_verbatim(self):
        scoped = watch.relevance_scoped_text(
            watch.html_sections(CONNECTOR_REFERENCE_PAGE), CONNECTOR_RELEVANCE
        )
        self.assertIn("data connectors are currently in Preview", scoped)

    def test_navigation_text_reaches_neither_path(self):
        """Both paths into a page must agree about what chrome is.

        The heading list and the text a filter scopes are derived separately, and
        `section_headings`' contract is that they cannot disagree about the page.
        This pins the property rather than the mechanism.
        """
        document = CONNECTOR_REFERENCE_PAGE
        self.assertNotIn("Data connector prerequisites", watch.strip_html(document))
        joined = "\n".join(body for _level, _heading, body in watch.html_sections(document))
        self.assertNotIn("Data connector prerequisites", joined)


class PositionalPageLevelTests(unittest.TestCase):
    """Only the first heading is the document title; a later <h1> is a stray.

    The Sentinel reference page carries a mis-authored <h1>NOTE - UPDATE:</h1>
    inside one connector entry. Read as a heading *level*, PAGE_LEVEL held that
    entry's whole body — 336,102 of the page's 1,084,895 characters — permanently
    in scope on the one source that declares a filter because an unfiltered
    fingerprint of it would move on nearly every run.
    """

    def test_a_stray_h1_is_not_page_level(self):
        phrases = connector_signals()["status_phrases_present"]
        self.assertNotIn("deprecated", phrases)
        self.assertNotIn("retired", phrases)

    def test_the_stray_h1_body_is_out_of_the_scoped_text(self):
        scoped = watch.relevance_scoped_text(
            watch.html_sections(CONNECTOR_REFERENCE_PAGE), CONNECTOR_RELEVANCE
        )
        self.assertNotIn("NOTE - UPDATE", scoped)

    def test_the_document_title_is_still_page_level(self):
        """The rule narrows what counts as the title; it does not remove it."""
        document = CONNECTOR_REFERENCE_PAGE.replace(
            "This article lists all supported, out-of-the-box data connectors.",
            "This article lists connectors. Some are rolling out.",
        )
        self.assertIn("rolling out", connector_signals(document)["status_phrases_present"])

    def test_a_stray_markdown_h1_is_not_page_level(self):
        """Markdown sources obey the same rule, though none today needs it."""
        document = RELEASE_NOTES + (
            "\n# Appendix\n\nThe classic SQL scanner is retired.\n"
        )
        self.assertNotIn("retired", markdown_signals(document)["status_phrases_present"])

    def test_an_unfiltered_source_is_untouched_by_the_positional_rule(self):
        """Scoping never runs without a filter, so 18 sources cannot be affected."""
        signals = markdown_signals(
            RELEASE_NOTES + "\n# Appendix\n\nThe classic SQL scanner is retired.\n",
            relevance=None,
        )
        self.assertIn("retired", signals["status_phrases_present"])


class CollapsibleEntryTests(unittest.TestCase):
    """A reference entry whose title is a <summary> must be reachable by a filter.

    Row 9's connector is one of ~430 <details>/<summary> disclosures on its page,
    which is why the declared filter matched 0 of 47 headings: there was no
    heading to match. Both halves of row 9's documented conflict live here — the
    entry's own title, which carries no qualifier, and the per-entry "(Preview)"
    suffix the matrix cites from a neighbouring entry.
    """

    def test_an_entry_title_is_a_heading(self):
        headings = watch.section_headings(watch.html_sections(CONNECTOR_REFERENCE_PAGE))
        self.assertIn("Microsoft Copilot", headings)
        self.assertIn("Microsoft Defender for Office 365 (Preview)", headings)

    def test_the_filter_now_reaches_the_tracked_entries(self):
        signals = connector_signals()
        self.assertEqual(
            signals["headings"],
            ["Microsoft Copilot", "Microsoft Defender for Office 365 (Preview)"],
        )
        self.assertEqual(signals["heading_count"], 2)
        self.assertFalse(watch.filter_collapsed(signals))

    def test_a_per_entry_preview_qualifier_is_watched(self):
        """The matrix quotes this suffix as evidence; losing it must escalate."""
        self.assertEqual(
            connector_signals()["preview_qualified_headings"],
            ["Microsoft Defender for Office 365 (Preview)"],
        )

    def test_a_qualifier_appearing_on_the_tracked_entry_escalates(self):
        """The change that would resolve row 9, asserted as a detected change."""
        before = connector_signals()
        after = connector_signals(
            CONNECTOR_REFERENCE_PAGE.replace(
                "<summary><strong>Microsoft Copilot</strong></summary>",
                "<summary><strong>Microsoft Copilot (Preview)</strong></summary>",
            )
        )
        self.assertNotEqual(watch.fingerprint(before), watch.fingerprint(after))
        self.assertIn(
            "(preview) qualifier ADDED to heading: 'Microsoft Copilot (Preview)'",
            watch.describe_change(before, after),
        )

    def test_the_entry_body_is_in_scope_when_its_title_matches(self):
        document = CONNECTOR_REFERENCE_PAGE.replace(
            "ingests Copilot-generated activity logs.",
            "ingests Copilot-generated activity logs. This connector is in development.",
        )
        self.assertIn("in development", connector_signals(document)["status_phrases_present"])

    def test_an_out_of_scope_entry_body_is_not_read(self):
        """430 connectors on one page; only the tracked ones may move a baseline."""
        document = CONNECTOR_REFERENCE_PAGE.replace(
            "This connector is deprecated and will be retired.",
            "This connector is generally available.",
        )
        self.assertNotIn(
            "generally available", connector_signals(document)["status_phrases_present"]
        )

    def test_a_page_shell_popover_is_not_a_heading(self):
        """The "Was this page helpful?" widget is a <details> too, and is not content."""
        headings = watch.section_headings(watch.html_sections(CONNECTOR_REFERENCE_PAGE))
        self.assertNotIn("No", headings)
        self.assertNotIn("All breadcrumbs", headings)

    def test_a_shell_popover_above_the_title_does_not_demote_it(self):
        """Learn emits its breadcrumb popover before the <h1>.

        If a collapsible could claim the title slot, the real <h1> would be read
        as a stray and the page's own lead-in — the banner — would fall out of
        scope. Asserted on the fixture, whose first <details> precedes the <h1>.
        """
        sections = watch.html_sections(CONNECTOR_REFERENCE_PAGE)
        self.assertEqual(sections[0][1], None)
        self.assertEqual(sections[1][1], "Find your Microsoft Sentinel data connector")
        self.assertIn("in preview", connector_signals()["status_phrases_present"])

    def test_a_collapsible_above_the_title_does_not_demote_it(self):
        """An entry can never be the document title, wherever it sits.

        Unreachable on today's pages — Learn's only pre-title `<details>` are the
        shell popovers, which are excluded before this can matter — so the guard
        is pinned here rather than left to be discovered if that class is ever
        renamed. Without it the `<h1>` reads as a stray, and the page's own
        lead-in, which is exactly where the banner lives, falls out of scope.
        """
        document = CONNECTOR_REFERENCE_PAGE.replace(
            "<h1>Find your Microsoft Sentinel data connector</h1>",
            "<details><summary>Choose a portal</summary><p>Azure or Defender.</p></details>\n"
            "<h1>Find your Microsoft Sentinel data connector</h1>",
        )
        self.assertIn("in preview", connector_signals(document)["status_phrases_present"])

    def test_an_unclosed_shell_popover_does_not_swallow_the_page(self):
        """Failing to exclude three shell labels beats dropping every real entry."""
        document = CONNECTOR_REFERENCE_PAGE.replace(
            '<summary aria-label="All breadcrumbs"><span class="icon"></span></summary>\n'
            "<div class=\"popover-content\"></div>\n</details>",
            '<summary aria-label="All breadcrumbs"><span class="icon"></span></summary>',
        )
        self.assertIn(
            "Microsoft Copilot", watch.section_headings(watch.html_sections(document))
        )

    def test_an_empty_entry_title_does_not_become_page_level(self):
        """A heading-less section reads as page-level, so an empty title is not one."""
        document = CONNECTOR_REFERENCE_PAGE.replace(
            "<details><summary><strong>Kubernetes audit</strong></summary>",
            "<details><summary></summary>",
        )
        self.assertNotIn("deprecated", connector_signals(document)["status_phrases_present"])

    def test_a_source_with_no_filter_is_unaffected_by_entry_titles(self):
        """An unfiltered page still reads whole-page text, so nothing re-baselines."""
        signals = html_signals(CONNECTOR_REFERENCE_PAGE, relevance=None)
        self.assertIn("deprecated", signals["status_phrases_present"])
        self.assertFalse(signals["relevance_filtered"])


class CommittedRegistryWatchTests(unittest.TestCase):
    """The registry's row-9 filter must be the one the fix makes work.

    Pinned because the previous filter carried a pattern
    ("data connectors are currently in Preview") that `apply_relevance_filter`
    could never match — it is body text, and the filter matches headings. Issue
    #31 finding 2 is that a stated behaviour the code cannot exhibit is worse than
    no statement at all, so the pattern is gone and the note says what covers the
    notice instead.
    """

    def setUp(self):
        registry = json.loads(
            (REPO_ROOT / ".github" / "watch-state" / "sources.json").read_text(encoding="utf-8")
        )
        self.entry = next(
            s for s in registry["sources"] if s["id"] == "sentinel-data-connectors-reference"
        )

    def test_the_filter_no_longer_declares_a_body_text_pattern(self):
        self.assertNotIn("data connectors are currently in Preview", self.entry["relevance_filter"])

    def test_the_filter_targets_both_halves_of_row_9s_conflict(self):
        self.assertEqual(self.entry["relevance_filter"], CONNECTOR_RELEVANCE)

    def test_the_source_still_backs_row_9(self):
        self.assertIn(9, self.entry["matrix_rows"])


if __name__ == "__main__":
    unittest.main()
