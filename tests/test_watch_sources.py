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


if __name__ == "__main__":
    unittest.main()
