# Changelog

All notable changes to this repository are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows a **monthly refresh cadence**: every row in the capability-status matrix is re-verified against Microsoft Learn and the Microsoft 365 Message Center each month, and every refresh is recorded below (date, rows touched, status changes).

## [Unreleased] — 2026-08-07 refresh

### Changed

- `matrix/capability-status-matrix.md` — all four existing rows re-verified against Microsoft Learn and the Microsoft 365 Roadmap; **every status held**. Row 3 (typed-prompt SIT blocking) **stays Requires further validation**: the Learn section heading has dropped the "(preview)" qualifier it carried on 2026-07-14, while the body of that same section still reads "This feature is in preview and is rolling out to all tenants" — a conflict inside a single page, not evidence of GA. Row 1: Learn no longer carries the "extends to prebuilt agents" sentence recorded on 2026-07-14, so prebuilt-agent coverage is no longer claimed from that source. Row 4: recorded the availability table's "Connected AWS accounts: No", and noted that the table does not enumerate AI-agent protection (that claim rests on the release notes). **Row 5 added** — external-email grounding block, **Public Preview**, found by re-reading the rows 1–3 source page. Last-verified stamps updated from 2026-07-14 to 2026-08-07. Automated re-verification, human-reviewed.
- `crosswalk/framework-crosswalk.md` — row 5 mapped at item level (**LLM01:2025** / **AML.T0051.001** Indirect / NIST **2.9**). OWASP, MITRE ATLAS and NIST AI 600-1 last-verified stamps updated from 2026-07-03 to 2026-08-07 (ATLAS re-read from the distributed dataset at `version: 5.6.0`). **CSA AICM deliberately left at 2026-07-03**: its control IDs are published only in a registration-gated spreadsheet and cannot be re-verified without a human, so row 5's AICM cell is recorded as *not yet mapped* rather than guessed.
- `checklists/capability-status-verification.md` — **Group 9 added** (automated-refresh escalation hygiene). Group 2 extended to the four DLP sub-capabilities and re-dated; Group 4 re-dated, with AI-agent coverage attributed to the release notes rather than the availability table. Footer stamp updated to Version 1.1 / 2026-08-07, resolving the 35-day drift between the checklist and the matrix.

### Added

- Automated refresh cadence — `.github/workflows/` (daily source watch with event-gated adjudication, monthly consolidating refresh, weekly stale guard, and a deterministic validation gate), `scripts/` (source watcher, stale guard, sourcing/labelling validators, CHANGELOG generator), `.claude/agents/` (evidence analyst and status adjudicator, each with an explicit forbidden-actions list), `.github/watch-state/sources.json`, `.github/ISSUE_TEMPLATE/tenant-verification.md`, and `docs/agent-cadence.md`. The Microsoft 365 Message Center and the CSA AICM workbook are recorded as permanently human-only sources: neither is machine-fetchable without introducing tenant-scoped or registration-gated material.

## [Unreleased] — 2026-07-14 refresh

### Changed

- `matrix/capability-status-matrix.md` — all four rows re-verified against Microsoft Learn and the Microsoft 365 Roadmap; every status held (no changes). Last-verified stamps updated from 2026-07-03 to 2026-07-14.

## [0.1.0] — Unreleased (local build 2026-07-03)

> Built locally; **not yet tagged, released, or published**. The v0.1.0 release gate (final confidentiality re-check of the built artifact, in-tenant verification of the open items, and human approval) must clear before this version is tagged.

### Added

- `matrix/capability-status-matrix.md` — the capability-status matrix, seeded with:
  - the three **Purview DLP for Microsoft 365 Copilot** sub-capability rows (the worked example of why status accuracy matters: one feature name, three release statuses);
  - the **Defender for Cloud AI threat protection scope-boundary** row (what it covers — and the common misconception about what it does not).
- `crosswalk/framework-crosswalk.md` — item-level framework cross-walk (**v0.1, expanding**; author synthesis), mapping the seeded controls to OWASP LLM Top 10 2025, MITRE ATLAS, NIST AI 600-1, and CSA AICM.
- `checklists/capability-status-verification.md` — the eight-group practitioner checklist for verifying Microsoft AI-security capability status.
- `docs/how-to-read-status.md` — how to determine, source, and cite GA / Public Preview / Roadmap status from Microsoft Learn, the Message Center, and the public Microsoft 365 Roadmap.
- `README.md`, `disclaimer.md`, `CHANGELOG.md`.

### Deferred to v0.1.1+

- DSPM for AI rows; Sentinel Copilot connector row; Defender XDR advanced-hunting row; Entra Conditional Access for AI identities row; shadow-AI and GitHub/MCP governance rows.
- Full cross-walk coverage beyond the seeded rows.
- `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`, issue and PR templates, `docs/scope-and-out-of-scope.md`.
- Runnable detections/KQL — deferred to a separate Sentinel detection-pack repository by design.
