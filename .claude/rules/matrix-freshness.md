---
paths:
  - "matrix/**/*.md"
  - "crosswalk/**/*.md"
  - "checklists/**/*.md"
---

# Status & Freshness Discipline

This repo's entire value is verified, dated capability status (see README
"How rows are verified"). When creating or editing rows in these folders:

- Every capability row must carry a primary-source URL (Microsoft Learn or
  the public Microsoft 365 Roadmap) and a last-verified date — the date the
  source was actually re-read, not the date of this edit.
- Status labels must come from the legend in README.md (GA / Public Preview /
  Roadmap / Requires further validation) — never inferred from a launch blog.
- If Microsoft's own docs conflict, label the row **Requires further
  validation** instead of guessing.
- The framework cross-walk (`crosswalk/framework-crosswalk.md`) is
  author-synthesis, item-level, never category-to-product — do not present it
  as an official mapping by Microsoft, OWASP, MITRE, NIST, or CSA.
- Any row older than the monthly refresh window (see README "Maintenance &
  cadence") is stale; flag it rather than leaving it unmarked.
