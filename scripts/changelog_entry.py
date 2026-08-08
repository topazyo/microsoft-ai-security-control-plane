#!/usr/bin/env python3
"""Append a refresh record to CHANGELOG.md in the repository's existing format.

The unit is **one heading per calendar month**, not one per run. The existing
file already works this way: the 2026-07-14 entry records a whole refresh, not a
single automated action. Tiered cadences run far more often than they change
anything, so a heading per run would bury the signal under "checked, nothing
changed" entries.

Behaviour:
  * If a heading for the current calendar month already exists, the new bullet is
    appended under that heading's section.
  * Otherwise a new heading is inserted above the most recent existing entry.

Only tiers D2 (event-gated adjudication) and D3 (monthly consolidation) may call
this. Tiers D1 and D4 never write to CHANGELOG.md.

Format reference — the two real entries in the file's history:
    ## [Unreleased] — 2026-07-14 refresh
    ### Changed
    - `matrix/capability-status-matrix.md` — ... Last-verified stamps updated from X to Y.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\][^\n]*?(?P<date>20\d{2}-\d{2}-\d{2})[^\n]*$", re.MULTILINE)
ANY_HEADING = re.compile(r"^## ", re.MULTILINE)


def find_month_heading(text: str, year_month: str) -> re.Match | None:
    for match in HEADING.finditer(text):
        if match.group("date").startswith(year_month) and "refresh" in match.group(0):
            return match
    return None


def section_bounds(text: str, start: int) -> int:
    """Index at which the section beginning at `start` ends."""
    next_heading = ANY_HEADING.search(text, start + 1)
    return next_heading.start() if next_heading else len(text)


def insert_bullet(text: str, heading_match: re.Match, section: str, bullet: str) -> str:
    start = heading_match.start()
    end = section_bounds(text, start)
    block = text[start:end]

    subheading = f"### {section}"
    if subheading in block:
        # Append after the last bullet of that subsection.
        sub_start = block.index(subheading) + len(subheading)
        next_sub = block.find("\n### ", sub_start)
        sub_end = next_sub if next_sub != -1 else len(block)
        sub_block = block[sub_start:sub_end].rstrip()
        new_sub_block = f"{sub_block}\n{bullet}\n\n"
        block = block[:sub_start] + new_sub_block + block[sub_end:]
    else:
        block = block.rstrip() + f"\n\n{subheading}\n\n{bullet}\n\n"
    return text[:start] + block + text[end:]


def insert_new_heading(text: str, heading: str, section: str, bullet: str) -> str:
    entry = f"{heading}\n\n### {section}\n\n{bullet}\n\n"
    first = ANY_HEADING.search(text)
    if first:
        return text[: first.start()] + entry + text[first.start() :]
    return text.rstrip() + "\n\n" + entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a refresh record to CHANGELOG.md.")
    parser.add_argument("--bullet", required=True, help="The bullet text (without the leading '- ').")
    parser.add_argument("--section", default="Changed", help="Keep a Changelog section name (default: Changed).")
    parser.add_argument("--date", default=None, help="Refresh date (YYYY-MM-DD); defaults to today.")
    parser.add_argument("--version", default="Unreleased", help="Version label for a new heading.")
    parser.add_argument("--dry-run", action="store_true", help="Print the result instead of writing it.")
    args = parser.parse_args()

    refresh_date = args.date or date.today().isoformat()
    year_month = refresh_date[:7]
    bullet = f"- {args.bullet.strip()}"

    text = CHANGELOG.read_text(encoding="utf-8")
    existing = find_month_heading(text, year_month)

    if existing:
        updated = insert_bullet(text, existing, args.section, bullet)
        action = f"appended to existing {year_month} heading"
    else:
        heading = f"## [{args.version}] — {refresh_date} refresh"
        updated = insert_new_heading(text, heading, args.section, bullet)
        action = f"created new heading for {year_month}"

    updated = re.sub(r"\n{4,}", "\n\n\n", updated)

    if args.dry_run:
        print(f"--- dry run: {action} ---")
        print(updated[: updated.find("## [0.1.0]") if "## [0.1.0]" in updated else 1500])
        return 0

    CHANGELOG.write_text(updated, encoding="utf-8")
    print(f"CHANGELOG.md: {action}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
