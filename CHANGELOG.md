# Changelog

All notable changes to this repository are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows a **monthly refresh cadence**: every row in the capability-status matrix is re-verified against Microsoft Learn and the Microsoft 365 Message Center each month, and every refresh is recorded below (date, rows touched, status changes).

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
