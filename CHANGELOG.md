# Changelog

All notable changes to this repository are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows a **monthly refresh cadence**: every row in the capability-status matrix is re-verified against Microsoft Learn and the Microsoft 365 Message Center each month, and every refresh is recorded below (date, rows touched, status changes).

## [Unreleased] — 2026-08-09 OWASP framework-edition update

### Changed

- `crosswalk/framework-crosswalk.md` — re-based on the **OWASP Top 10 for LLM Applications 2026 edition (v1.0**, published 2026-08-03 by the OWASP GenAI Security Project**)**, superseding the 2025 (v2.0) edition. The five mapped rows keep their item numbers, because **only LLM01 Prompt Injection and LLM02 Sensitive Information Disclosure retained the numbers they held in 2025** — the `:2025` suffixes simply become `:2026`. OWASP last-verified stamp advanced from 2026-08-07 to 2026-08-09. **MITRE ATLAS, NIST AI 600-1 and CSA AICM stamps deliberately left untouched**: none of those sources was re-read in this pass, and the OWASP edition bump is not evidence about them.
- `checklists/capability-status-verification.md` — Group 8 re-based on the 2026 numbering (Sensitive Information Disclosure **LLM02**, Excessive Agency **LLM03**, Supply Chain **LLM04**, Improper Output Handling **LLM10**) and extended with a check that no 2025-era ID is carried over unchanged. Footer bumped to Version 1.2, but the **"Last validated" date stays 2026-08-07** — the Microsoft-source pass was not re-run, so the OWASP re-base is dated separately rather than advancing a stamp it does not cover.
- `README.md`, `disclaimer.md` — cross-walk description updated from "OWASP LLM 2025" to the 2026 edition.

### Added

- `crosswalk/framework-crosswalk.md` — a **2025 → 2026 renumbering table**, because every slot other than LLM01 and LLM02 changed occupant: Supply Chain LLM03→LLM04, Data and Model Poisoning LLM04→LLM05, Improper Output Handling LLM05→LLM10, Excessive Agency LLM06→LLM03, Vector and Embedding Weaknesses LLM08→LLM09, Misinformation LLM09→LLM07, Unbounded Consumption LLM10→LLM06, and **System Prompt Leakage (LLM07:2025) renamed and re-scoped as LLM08:2026 Hidden Context Exposure**. Silent reuse of a 2025 ID is the main hazard of this edition change, so the mapping is recorded rather than left implicit.
- `crosswalk/framework-crosswalk.md` — a note on **Appendix A: Related Framework Mappings**, new in the 2026 edition, which maps each of the ten risks to nine external frameworks and replaces the per-entry "Related Frameworks and Taxonomies" sections. Recorded as OWASP's own work, pinned to OWASP's own framework versions, and explicitly neither a validation nor an endorsement of this repository's synthesis.
- `crosswalk/framework-crosswalk.md` — verification evidence for the edition bump: the artifact read was confirmed byte-identical to OWASP's published download by SHA-256. Two caveats recorded with it — the released v1.0 PDF prints **no publication date** (its title page still carries an unfilled "[Publication date to be set]" placeholder), so the date is cited from the OWASP resource page; and the `genai.owasp.org/llm-top-10` landing page **still presented the 2025 edition** at verification time, so it is no longer cited as the edition-defining URL.

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
