#!/usr/bin/env python3
"""Tests for scripts/changelog_entry.py - the one script that writes CHANGELOG.md.

Standard library only. Run with `python3 -m unittest discover -s tests`.

Nothing pinned this script, and it holds the invariant `docs/agent-cadence.md`
publishes as enforced: **one heading per calendar month**, except across a
release. That exception is the part worth testing, because it is carried by a
single word.

`find_month_heading` matches a month's heading only if the heading text contains
"refresh". Every heading the script creates carries that token; a released
heading (`## [0.1.3] - 2026-09-10`) does not. So a bullet written after a release
does not land inside the released section - it opens a fresh
`## [Unreleased] - <date> refresh` heading above it. Dropping the token test
would "fix" a phantom bug and introduce a real one: automation appending into a
tagged, published section.

The two halves are therefore pinned together, plus the self-consistency property
that ties them: a heading this script *creates* must be one it can later *find*,
or the second bullet of any month would silently start a second heading.

What these tests do NOT cover, stated rather than implied:

  - `date.today()`. Every test passes an explicit date; the default is not
    exercised.
  - The real CHANGELOG.md's content. `main()` is driven against a synthetic
    document, because assertions about the committed file's headings would rot
    at the next release.
  - `--dry-run`'s truncation at the `## [0.1.0]` marker, which is presentation.

Fixture hygiene: every string here is synthetic. `check_confidentiality` skips
anything that is not .md or .json, so tests/ is outside it.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

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


entry = load_script("changelog_entry")

REFRESH_MONTH = "## [Unreleased] — 2026-09-09 refresh"
RELEASED_MONTH = "## [0.1.3] — 2026-09-10"

DOCUMENT = "\n".join(
    [
        "# Changelog",
        "",
        "Preamble prose that is not a heading.",
        "",
        REFRESH_MONTH,
        "",
        "### Changed",
        "",
        "- An existing bullet.",
        "",
        "## [0.1.2] — 2026-08-10",
        "",
        "### Changed",
        "",
        "- An older bullet.",
        "",
    ]
)


class FindMonthHeadingTests(unittest.TestCase):
    def test_a_refresh_heading_for_the_month_is_found(self):
        match = entry.find_month_heading(DOCUMENT, "2026-09")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), REFRESH_MONTH)

    def test_a_heading_for_another_month_is_not_found(self):
        self.assertIsNone(entry.find_month_heading(DOCUMENT, "2026-07"))

    def test_a_released_heading_is_deliberately_not_found(self):
        """The protection, stated as a test so it cannot be 'simplified' away.

        A released section has been tagged and published. Appending a bullet
        into it would rewrite a published record, so the month match requires
        the `refresh` token that only an unreleased heading carries.
        """
        document = DOCUMENT.replace(REFRESH_MONTH, RELEASED_MONTH)
        self.assertIsNone(entry.find_month_heading(document, "2026-09"))

    def test_a_released_and_a_refresh_heading_can_coexist_for_one_month(self):
        document = "\n".join(
            [
                "# Changelog",
                "",
                REFRESH_MONTH,
                "",
                "### Changed",
                "",
                "- Newer.",
                "",
                RELEASED_MONTH,
                "",
                "### Changed",
                "",
                "- Released.",
                "",
            ]
        )
        match = entry.find_month_heading(document, "2026-09")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), REFRESH_MONTH)


class SectionBoundsTests(unittest.TestCase):
    def test_a_section_ends_at_the_next_top_level_heading(self):
        start = DOCUMENT.index(REFRESH_MONTH)
        end = entry.section_bounds(DOCUMENT, start)
        block = DOCUMENT[start:end]
        self.assertIn("- An existing bullet.", block)
        self.assertNotIn("- An older bullet.", block)

    def test_the_last_section_ends_at_the_end_of_the_document(self):
        start = DOCUMENT.index("## [0.1.2]")
        self.assertEqual(entry.section_bounds(DOCUMENT, start), len(DOCUMENT))


class InsertBulletTests(unittest.TestCase):
    def bullet_into(self, document: str, section: str) -> str:
        match = entry.find_month_heading(document, "2026-09")
        self.assertIsNotNone(match)
        return entry.insert_bullet(document, match, section, "- A new bullet.")

    def test_a_bullet_is_appended_under_an_existing_subsection(self):
        updated = self.bullet_into(DOCUMENT, "Changed")
        self.assertIn("- An existing bullet.\n- A new bullet.", updated)

    def test_a_missing_subsection_is_created(self):
        updated = self.bullet_into(DOCUMENT, "Fixed")
        self.assertIn("### Fixed", updated)
        self.assertIn("- A new bullet.", updated)

    def test_the_bullet_does_not_leak_into_the_next_section(self):
        updated = self.bullet_into(DOCUMENT, "Changed")
        older = updated.index("## [0.1.2]")
        self.assertLess(updated.index("- A new bullet."), older)

    def test_the_older_section_is_left_byte_identical(self):
        updated = self.bullet_into(DOCUMENT, "Changed")
        tail = DOCUMENT[DOCUMENT.index("## [0.1.2]") :]
        self.assertTrue(updated.endswith(tail))


class InsertNewHeadingTests(unittest.TestCase):
    def test_a_new_heading_goes_above_the_most_recent_entry(self):
        updated = entry.insert_new_heading(
            DOCUMENT, "## [Unreleased] — 2026-10-01 refresh", "Changed", "- October."
        )
        self.assertLess(
            updated.index("2026-10-01"), updated.index(REFRESH_MONTH.split("—")[1].strip())
        )

    def test_the_preamble_is_preserved_above_the_new_heading(self):
        updated = entry.insert_new_heading(
            DOCUMENT, "## [Unreleased] — 2026-10-01 refresh", "Changed", "- October."
        )
        self.assertLess(updated.index("Preamble prose"), updated.index("2026-10-01"))

    def test_a_document_with_no_heading_gets_the_entry_appended(self):
        updated = entry.insert_new_heading(
            "# Changelog\n\nJust prose.\n", "## [Unreleased] — 2026-10-01 refresh", "Changed", "- x."
        )
        self.assertTrue(updated.rstrip().endswith("- x."))


class HeadingRoundTripTests(unittest.TestCase):
    """A heading the script creates must be one it can later find.

    Without this, the first bullet of a month would create a heading and the
    second would fail to match it and create another - silently breaking the
    one-heading-per-calendar-month invariant the documentation publishes as
    enforced. It is the property that ties `insert_new_heading`'s format to
    `find_month_heading`'s test.
    """

    def test_a_created_heading_is_found_by_the_month_lookup(self):
        created = entry.insert_new_heading(
            DOCUMENT, "## [Unreleased] — 2026-10-01 refresh", "Changed", "- October."
        )
        self.assertIsNotNone(entry.find_month_heading(created, "2026-10"))

    def test_a_second_bullet_lands_in_the_heading_the_first_one_created(self):
        created = entry.insert_new_heading(
            DOCUMENT, "## [Unreleased] — 2026-10-01 refresh", "Changed", "- First."
        )
        match = entry.find_month_heading(created, "2026-10")
        updated = entry.insert_bullet(created, match, "Changed", "- Second.")
        self.assertEqual(updated.count("2026-10-01"), 1)
        self.assertIn("- First.\n- Second.", updated)


class MainTests(unittest.TestCase):
    """End-to-end against a synthetic CHANGELOG, via the module's own constant."""

    def setUp(self):
        self.changelog = REPO_ROOT / "tests" / "__changelog_fixture__.md"
        self.addCleanup(self.changelog.unlink, missing_ok=True)

    def run_entry(self, document: str, *argv: str) -> str:
        self.changelog.write_text(document, encoding="utf-8")
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(entry, "CHANGELOG", self.changelog))
            stack.enter_context(mock.patch.object(sys, "argv", ["changelog_entry.py", *argv]))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            code = entry.main()
        self.assertEqual(code, 0)
        return self.changelog.read_text(encoding="utf-8")

    def test_a_bullet_joins_the_months_refresh_heading(self):
        updated = self.run_entry(
            DOCUMENT, "--bullet", "Something happened.", "--date", "2026-09-20"
        )
        self.assertEqual(updated.count("2026-09-09 refresh"), 1)
        self.assertNotIn("2026-09-20", updated)
        self.assertIn("- Something happened.", updated)

    def test_a_bullet_after_a_release_opens_a_new_heading_instead(self):
        """The invariant that matters: a published section is never reopened."""
        document = DOCUMENT.replace(REFRESH_MONTH, RELEASED_MONTH)
        updated = self.run_entry(
            document, "--bullet", "Post-release note.", "--date", "2026-09-20"
        )
        self.assertIn("## [Unreleased] — 2026-09-20 refresh", updated)
        self.assertLess(updated.index("2026-09-20"), updated.index(RELEASED_MONTH))
        released = updated[updated.index(RELEASED_MONTH) :]
        self.assertNotIn("- Post-release note.", released)

    def test_dry_run_writes_nothing(self):
        before = DOCUMENT
        after = self.run_entry(
            DOCUMENT, "--bullet", "Not written.", "--date", "2026-09-20", "--dry-run"
        )
        self.assertEqual(after, before)


class ConsoleEncodingTests(unittest.TestCase):
    """The published `--dry-run` command must not depend on the console's code page.

    It did. `docs/agent-cadence.md` publishes
    `python3 scripts/changelog_entry.py --bullet "..." --dry-run`, and running
    it verbatim on a Windows console raised

        UnicodeEncodeError: 'charmap' codec can't encode character '\\u2192'

    because the CHANGELOG it echoes contains an arrow and cp1252 has no arrow.
    An em dash *is* in cp1252, so the failure depended on which characters the
    file happened to contain -- and CI runs UTF-8, so it stayed green while a
    documented command was broken on the maintainer's own platform.

    All four scripts echo text taken from tracked files or fetched pages, so all
    four call the same helper. The watcher is the sharpest case: its `[changed]`
    notes quote live Learn headings, where "Settings -> Privacy" is unremarkable.
    """

    UNENCODABLE = "→"  # cp1252 has no arrow; an em dash would not prove it

    def test_the_arrow_is_genuinely_unencodable_in_the_legacy_code_page(self):
        """Guard the guard: if this character were encodable, the rest proves nothing."""
        with self.assertRaises(UnicodeEncodeError):
            self.UNENCODABLE.encode("cp1252")

    def test_every_script_reconfigures_its_streams(self):
        for name in (
            "changelog_entry",
            "stale_guard",
            "validate_bot_pr",
            "watch_sources",
        ):
            with self.subTest(script=name):
                source = (REPO_ROOT / "scripts" / f"{name}.py").read_text(encoding="utf-8")
                self.assertIn("def use_utf8_streams()", source)
                self.assertIn("use_utf8_streams()\n    parser", source)

    def test_a_dry_run_over_unencodable_content_succeeds(self):
        """The end-to-end case, driven through main() as the docs invoke it."""
        document = DOCUMENT.replace(
            "- An existing bullet.", f"- A bullet containing {self.UNENCODABLE} an arrow."
        )
        changelog = REPO_ROOT / "tests" / "__encoding_fixture__.md"
        self.addCleanup(changelog.unlink, missing_ok=True)
        changelog.write_text(document, encoding="utf-8")
        buffer = io.TextIOWrapper(
            io.BytesIO(), encoding="cp1252", errors="strict", write_through=True
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(entry, "CHANGELOG", changelog))
            stack.enter_context(
                mock.patch.object(
                    sys,
                    "argv",
                    ["changelog_entry.py", "--bullet", "x", "--date", "2026-09-20", "--dry-run"],
                )
            )
            stack.enter_context(contextlib.redirect_stdout(buffer))
            self.assertEqual(entry.main(), 0)

    def test_the_same_content_would_have_crashed_without_the_reconfiguration(self):
        """Proves the test above is load-bearing rather than vacuously passing."""
        buffer = io.TextIOWrapper(
            io.BytesIO(), encoding="cp1252", errors="strict", write_through=True
        )
        with contextlib.redirect_stdout(buffer):
            with self.assertRaises(UnicodeEncodeError):
                print(f"an arrow {self.UNENCODABLE} here")


class DocumentedInvariantTests(unittest.TestCase):
    """The published claim and the code must agree.

    `docs/agent-cadence.md` states the one-heading-per-calendar-month rule and
    names this script as what enforces it. The released-section exception was
    unstated for two releases, so a reader had no way to know that keeping the
    word `refresh` out of a release heading is a requirement rather than a
    stylistic choice.
    """

    DOC = REPO_ROOT / "docs" / "agent-cadence.md"

    def test_the_documentation_states_the_released_section_exception(self):
        text = self.DOC.read_text(encoding="utf-8")
        self.assertIn("one heading per calendar month", text.lower())
        self.assertIn("refresh", text)
        self.assertRegex(text, r"released heading")

    def test_the_script_docstring_states_it_too(self):
        self.assertIn("refresh", entry.__doc__ or "")
        self.assertIn("tagged", (entry.__doc__ or "").lower())


if __name__ == "__main__":
    unittest.main()
