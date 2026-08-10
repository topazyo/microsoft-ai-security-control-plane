# Microsoft AI Security Control Plane

**A living, primary-source-cited map of Microsoft AI-security capabilities by release status (GA / Preview / Roadmap) and risk framework.**

*Capability status (GA / Preview / Roadmap) and framework cross-walk, primary-source-cited.*

## Who this is for

- **Primary:** security architects designing AI-adoption control frameworks on the Microsoft stack.
- **Secondary:** SOC leads and detection engineers, M365 security admins, and AI-governance (GRC) stakeholders.

## What problem it solves

The release status of Microsoft's AI-security capabilities is scattered across Microsoft Learn, the Message Center, the public Microsoft 365 Roadmap, and Tech Community posts — and they do not always agree. Coverage maps built from launch-blog implication treat capabilities as uniformly "available" when they sit at GA, Public Preview, and Roadmap simultaneously. This repository consolidates **verified** status: every row carries a primary-source URL and a last-verified date. **Status accuracy is itself the control.**

## Scope and out of scope

**In scope:**

- A capability-status matrix for the Microsoft AI-security stack — Microsoft Entra, Microsoft Purview, Microsoft Defender XDR / Defender for Cloud, Microsoft Sentinel, and GitHub — one row per capability.
- An item-level framework cross-walk (OWASP LLM 2025, MITRE ATLAS, NIST AI 600-1, CSA AICM), versioned **"v0.1, expanding."**
- A practitioner status-verification checklist and a "how to read status" guide.

**Out of scope:**

- Tenant-specific or non-public configuration, values, or topology.
- Secure SDLC / DevSecOps depth beyond GitHub Copilot policy and MCP governance — no AI-generated-code review gates, dependency/slopsquatting, secret-leakage, or CI/CD-guardrail content in v0.1 (a candidate for a later, separate contribution).
- Runnable detections / KQL — deferred to a separate Sentinel detection-pack repository.
- Anything not backed by a public primary source; no NDA or private-preview-program material.
- Screenshots, marketing figures presented as fact, or vendor-comparison content.

## Status legend

| Label | Meaning |
|---|---|
| **GA** | Generally Available per Microsoft primary sources. |
| **Public Preview** | Labelled preview by Microsoft primary sources; preview terms apply. |
| **Roadmap** | Publicly announced (Microsoft 365 Roadmap), not yet rolling out. |
| **Requires further validation** | Microsoft's own docs conflict (e.g. typed-prompt SIT DLP) or status is otherwise unconfirmable from primary sources — verify in your tenant. |

## How to use this repository

1. Read [`matrix/capability-status-matrix.md`](matrix/capability-status-matrix.md).
2. Follow each row's primary-source URL and check the **last-verified date**.
3. Verify contested rows (and anything rollout-gated) in your own tenant before relying on them.
4. Use [`checklists/capability-status-verification.md`](checklists/capability-status-verification.md) before briefing leadership or publishing any capability claim.

## Microsoft Security alignment

One control plane across the stack: **Microsoft Entra** (identity and Conditional Access for AI identities), **Microsoft Purview** (DLP and DSPM for AI), **Microsoft Defender XDR / Defender for Cloud** (detection and AI-workload threat protection), **Microsoft Sentinel** (SIEM), and **GitHub** (Copilot policy and MCP governance) — anchored to primary sources rather than product marketing.

## AI Security risks covered

Prompt injection (direct/UPIA and indirect/XPIA), sensitive-data leakage into and out of AI systems, shadow AI usage, agentic/MCP blast radius, and AI supply-chain / model risk — each matrix row names the risk class it addresses.

## Repository structure

```
microsoft-ai-security-control-plane/
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md                        # the contribution rule; atomic row PRs; running the validators
├── SECURITY.md                            # what to report here vs to MSRC; no-secrets policy
├── LICENSE                                # MIT — covers scripts/ and .github/workflows/
├── LICENSE-CONTENT                        # CC BY 4.0 — covers the documentation content
├── disclaimer.md
├── matrix/
│   └── capability-status-matrix.md        # the spine: capability → status → source + last-verified date
├── crosswalk/
│   └── framework-crosswalk.md             # item-level; v0.1, expanding; author synthesis
├── checklists/
│   └── capability-status-verification.md  # the 9-group practitioner checklist
├── docs/
│   ├── how-to-read-status.md              # GA vs Preview vs Roadmap; sourcing + verification methodology
│   ├── agent-cadence.md                   # the tiered automated refresh: what is automated, what stays human
│   └── scope-and-out-of-scope.md          # what belongs here, what does not, and where it belongs instead
├── scripts/                               # standard-library only; no third-party dependency
│   ├── watch_sources.py                   # tier D1: deterministic source watcher (no model, no judgement)
│   ├── stale_guard.py                     # tier D4: staleness guard over the recorded last-verified dates
│   ├── validate_bot_pr.py                 # the deterministic gate: sourcing, labelling, confidentiality
│   └── changelog_entry.py                 # appends a refresh record in the existing format
└── .github/
    ├── workflows/                         # daily source watch, monthly refresh, weekly stale guard, validate gate
    ├── watch-state/                       # sources.json (pinned source registry) + fingerprints.json (baseline)
    ├── ISSUE_TEMPLATE/                    # new row proposal, status correction, tenant verification
    └── pull_request_template.md
```

## Quick start

Start with [`matrix/capability-status-matrix.md`](matrix/capability-status-matrix.md). The four **DLP-for-Copilot rows are the worked example of why status matters**: one feature name, four sub-capabilities, four release schedules — and (as of the current verification date) still not one shared status.

## The cross-walk is synthesis, not Microsoft's mapping

[`crosswalk/framework-crosswalk.md`](crosswalk/framework-crosswalk.md) maps each Microsoft control to specific framework items — OWASP LLM 2025 item IDs, MITRE ATLAS technique IDs, NIST AI 600-1 subcategories, CSA AICM (versioned) — at item level, never category-to-product. It is the **author's interpretive synthesis**, versioned "v0.1, expanding," and is not an official mapping by Microsoft, OWASP, MITRE, NIST, or CSA.

## How rows are verified

Every matrix row carries a **primary-source URL** (Microsoft Learn or the public Microsoft 365 Roadmap) and a **last-verified date** — the date the source was actually re-read. Status is taken from the source's own qualifiers, never from launch blogs. Where Microsoft's own documentation conflicts, the row is labelled **Requires further validation** rather than guessed. Methodology: [`docs/how-to-read-status.md`](docs/how-to-read-status.md).

## Confidentiality note

Built entirely from **public primary sources** and a synthetic/lab environment. This repository contains no organization names, directory or workspace GUIDs, subscription GUIDs, hostnames, user names, emails, internal URLs, IP addresses, logs, screenshots, or license counts — and no NDA or private-preview-program material.

## Disclaimer

Starting reference only — **validate every capability's status in your own environment before relying on it.** Statuses change; check the last-verified date. Full text: [`disclaimer.md`](disclaimer.md).

## Maintenance & cadence

Monthly refresh against the Microsoft Learn "What's new" pages and the Message Center. Every refresh is recorded in [`CHANGELOG.md`](CHANGELOG.md) (date, rows touched, status changes). Any row older than the monthly window is treated as stale.

## License & contributing

**Dual-licensed.** The automation (`scripts/`, `.github/workflows/`) is **MIT** — see [`LICENSE`](LICENSE). The documentation content (the matrix, the cross-walk, the checklists, `docs/`, and the prose files) is **CC BY 4.0** — see [`LICENSE-CONTENT`](LICENSE-CONTENT). CC BY keeps the cross-walk's author synthesis attributable as it is reused; MIT keeps the automation reusable without an attribution obligation attaching to code. Third-party material quoted here — Microsoft documentation text, and OWASP / MITRE ATLAS / NIST / CSA identifiers and titles — remains the property of its owners and is covered by neither license; see [`LICENSE-CONTENT`](LICENSE-CONTENT) and [`disclaimer.md`](disclaimer.md).

**Contributing:** see [`CONTRIBUTING.md`](CONTRIBUTING.md). The contribution rule is fixed: **every proposed or changed row must include a primary-source URL and a last-verified date**, use a status label from the legend, and keep to public, synthetic-only content. Where Microsoft's own sources conflict, the row is labelled **Requires further validation** rather than resolved by judgement. Security and confidentiality reports: [`SECURITY.md`](SECURITY.md).
