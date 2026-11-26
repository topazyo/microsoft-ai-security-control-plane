# Microsoft AI Security Control Plane

**A living, primary-source-cited map of Microsoft AI-security capabilities by release status (GA / Preview / Roadmap) and risk framework.**

[![Validate matrix](https://github.com/topazyo/microsoft-ai-security-control-plane/actions/workflows/validate-matrix.yml/badge.svg?branch=main)](https://github.com/topazyo/microsoft-ai-security-control-plane/actions/workflows/validate-matrix.yml)

[Start here](#start-here) · [Status legend](#status-legend) · [What it covers](#what-it-covers) · [How rows are verified](#how-rows-are-verified) · [Scope](#scope-and-out-of-scope) · [Maintenance & cadence](#maintenance--cadence) · [Contributing](#contributing) · [License](#license)

> [!IMPORTANT]
> Starting reference only — **validate every capability's status in your own environment before relying on it.** Statuses change; check the last-verified date. Full text: [`disclaimer.md`](disclaimer.md).

## Start here

| If you want to… | Go to |
|---|---|
| See which capabilities are GA, Public Preview or Roadmap | [Capability-status matrix](matrix/capability-status-matrix.md) |
| Understand what each status label means and how it is sourced | [How to read (and verify) capability status](docs/how-to-read-status.md) |
| Check a capability claim before briefing leadership or publishing it | [Status-verification checklist](checklists/capability-status-verification.md) |
| Map a Microsoft control to OWASP, MITRE ATLAS, NIST or CSA items | [Framework cross-walk](crosswalk/framework-crosswalk.md) |
| Find out why a topic is not covered here, and where it belongs instead | [Scope and out of scope](docs/scope-and-out-of-scope.md) |
| See what changed at each refresh | [`CHANGELOG.md`](CHANGELOG.md) |
| Learn what the automation does, and what stays with a human | [Automated refresh cadence](docs/agent-cadence.md) |
| Propose a row, correct a status, or report a tenant verification | [`CONTRIBUTING.md`](CONTRIBUTING.md), then [open an issue from a template](https://github.com/topazyo/microsoft-ai-security-control-plane/issues/new/choose) |
| Report a security or confidentiality problem | [`SECURITY.md`](SECURITY.md) |

**Using a row:**

1. Read [`matrix/capability-status-matrix.md`](matrix/capability-status-matrix.md).
2. Follow each row's primary-source URL and check the **last-verified date**.
3. Verify contested rows (and anything rollout-gated) in your own tenant before relying on them.
4. Use [`checklists/capability-status-verification.md`](checklists/capability-status-verification.md) before briefing leadership or publishing any capability claim.

> [!TIP]
> The four **DLP-for-Copilot rows are the worked example of why status matters**: one feature name, four sub-capabilities, four release schedules — and (as of the current verification date) still not one shared status. Start with them in the [matrix](matrix/capability-status-matrix.md).

## Why this exists

The release status of Microsoft's AI-security capabilities is scattered across Microsoft Learn, the Message Center, the public Microsoft 365 Roadmap, and Tech Community posts — and they do not always agree. Coverage maps built from launch-blog implication treat capabilities as uniformly "available" when they sit at GA, Public Preview, and Roadmap simultaneously. This repository consolidates **verified** status: every row carries a primary-source URL and a last-verified date. **Status accuracy is itself the control.**

### Who this is for

- **Primary:** security architects designing AI-adoption control frameworks on the Microsoft stack.
- **Secondary:** SOC leads and detection engineers, M365 security admins, and AI-governance (GRC) stakeholders.

## Status legend

| Label | Meaning |
|---|---|
| **GA** | Generally Available per Microsoft primary sources. |
| **Public Preview** | Labelled preview by Microsoft primary sources; preview terms apply. |
| **Roadmap** | Publicly announced (Microsoft 365 Roadmap), not yet rolling out. |
| **Requires further validation** | Microsoft's own docs conflict (e.g. typed-prompt SIT DLP) or status is otherwise unconfirmable from primary sources — verify in your tenant. |

How each label is sourced, and what preview terms mean in practice: [`docs/how-to-read-status.md`](docs/how-to-read-status.md).

## What it covers

### Microsoft products

One control plane across the stack, anchored to primary sources rather than product marketing:

| Product | Role in the control plane |
|---|---|
| **Microsoft Entra** | Identity and Conditional Access for AI identities |
| **Microsoft Purview** | DLP and DSPM for AI |
| **Microsoft Defender XDR / Defender for Cloud** | Detection and AI-workload threat protection |
| **Microsoft Sentinel** | SIEM |
| **GitHub** | Copilot policy and MCP governance |

### AI-security risks

Each matrix row names the risk class it addresses:

- Prompt injection (direct/UPIA and indirect/XPIA)
- Sensitive-data leakage into and out of AI systems
- Shadow AI usage
- Agentic/MCP blast radius
- AI supply-chain / model risk

### Framework cross-walk

[`crosswalk/framework-crosswalk.md`](crosswalk/framework-crosswalk.md) maps each Microsoft control to specific framework items — OWASP LLM 2026 item IDs, MITRE ATLAS technique IDs, NIST AI 600-1 subcategories, CSA AICM (versioned) — at item level, never category-to-product. It also carries practitioner pointers for the agentic rows into OWASP's *Securing Agentic Applications V2* guide.

> [!NOTE]
> **The cross-walk is synthesis, not Microsoft's mapping.** It is the **author's interpretive synthesis**, versioned "v0.2," and is not an official mapping by Microsoft, OWASP, MITRE, NIST, or CSA.

## How rows are verified

- **Every matrix row carries a primary-source URL and a last-verified date** — the date the source was actually re-read.
- **Primary sources are Microsoft Learn or the public Microsoft 365 Roadmap.** For the two GitHub rows (12 and 13) the source is GitHub Docs, which is the first-party documentation site for a Microsoft-owned product and so the same *class* of source rather than a relaxation toward blogs; it is admitted only as a human-only source that no automated run may fetch.
- **Status is taken from the source's own qualifiers**, never from launch blogs.
- **Where Microsoft's own documentation conflicts**, the row is labelled **Requires further validation** rather than guessed.

Methodology: [`docs/how-to-read-status.md`](docs/how-to-read-status.md).

## Scope and out of scope

| In scope | Out of scope |
|---|---|
| A capability-status matrix for the Microsoft AI-security stack — Microsoft Entra, Microsoft Purview, Microsoft Defender XDR / Defender for Cloud, Microsoft Sentinel, and GitHub — one row per capability. | Tenant-specific or non-public configuration, values, or topology. |
| An item-level framework cross-walk (OWASP LLM 2026, MITRE ATLAS, NIST AI 600-1, CSA AICM), versioned **"v0.2"** — every cell resolved, including the registration-gated CSA AICM column. | Secure SDLC / DevSecOps depth beyond GitHub Copilot policy and MCP governance — no AI-generated-code review gates, dependency/slopsquatting, secret-leakage, or CI/CD-guardrail content in v0.1 (a candidate for a later, separate contribution). |
| A practitioner status-verification checklist and a "how to read status" guide. | Runnable detections / KQL — deferred to a separate Sentinel detection-pack repository. |
| | Anything not backed by a public primary source; no NDA or private-preview-program material. |
| | Screenshots, marketing figures presented as fact, or vendor-comparison content. |

Why each exclusion exists, and where that content belongs instead: [`docs/scope-and-out-of-scope.md`](docs/scope-and-out-of-scope.md).

## Maintenance & cadence

Monthly refresh against the Microsoft Learn "What's new" pages and the Message Center. Every refresh is recorded in [`CHANGELOG.md`](CHANGELOG.md) (date, rows touched, status changes). Any row older than the monthly window is treated as stale.

**Which half of that refresh is automated, stated precisely because the two halves fail differently:**

- **Automated: drift on rows that already exist.** The automated cadence fetches each row's pinned sources and reports changes in their status signals.
- **Human: finding a capability that should become a *new* row.** The watched surface cannot be relied on for discovery. Most sources are per-capability pages, which can only ever speak about a row that already exists.
  - The two Defender for Cloud release-notes pages are a partial exception worth stating rather than glossing: their filter is topical, so a new AI entry there *does* move the fingerprint and *is* reported — the committed baseline already holds in-scope entries no row cites. But that is one product's what's-new page and there is no Purview, Defender XDR, Defender for Cloud Apps, Entra or Sentinel equivalent under watch, and a reported change is a prompt to re-adjudicate an existing row, never a proposal for a new one.
  - Sweeping the other products' pages, and deciding that anything found deserves a row, stays with a human.
- **Human: the Message Center**, which is tenant-scoped, has no public URL, and is never fetched by anything here.
- **Human only, by construction: some dated items are backed *only* by sources no automation may reach** — matrix rows 12 and 13 (GitHub Docs pages, deliberately kept outside the automated path) and the NIST and CSA cross-walk rows (a static PDF and a registration-gated spreadsheet) — so no agent run can ever advance them, and their going stale means a human is overdue rather than that the automation broke.

How all of this is executed, and what the automation is forbidden to do: [`docs/agent-cadence.md`](docs/agent-cadence.md).

> [!TIP]
> A weekly stale guard opens an issue labelled [`stale-rows`](https://github.com/topazyo/microsoft-ai-security-control-plane/issues?q=is%3Aissue+is%3Aopen+label%3Astale-rows) while any dated item is past the window, and closes it once nothing is. An empty list is not proof of freshness — the last-verified date on the row is the evidence.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). The contribution rule is fixed: **every proposed or changed row must include a primary-source URL and a last-verified date**, use a status label from the legend, and keep to public, synthetic-only content. Where Microsoft's own sources conflict, the row is labelled **Requires further validation** rather than resolved by judgement.

Security and confidentiality reports: [`SECURITY.md`](SECURITY.md). If you open this repository in an AI coding agent, read that file's section on the tracked `.claude/` configuration first.

## License

**Dual-licensed.**

| What | License |
|---|---|
| The automation (`scripts/`, `.github/workflows/`) | **MIT** — see [`LICENSE`](LICENSE) |
| The documentation content (the matrix, the cross-walk, the checklists, `docs/`, and the prose files) | **CC BY 4.0** — see [`LICENSE-CONTENT`](LICENSE-CONTENT) |

CC BY keeps the cross-walk's author synthesis attributable as it is reused; MIT keeps the automation reusable without an attribution obligation attaching to code. Third-party material quoted here — Microsoft documentation text, and OWASP / MITRE ATLAS / NIST / CSA identifiers and titles — remains the property of its owners and is covered by neither license; see [`LICENSE-CONTENT`](LICENSE-CONTENT) and [`disclaimer.md`](disclaimer.md).

## Confidentiality note

Built entirely from **public primary sources** and a synthetic/lab environment. This repository contains no organization names, directory or workspace GUIDs, subscription GUIDs, hostnames, user names, emails, internal URLs, IP addresses, logs, screenshots, or license counts — and no NDA or private-preview-program material.

## Repository structure

<details>
<summary>Show the file tree</summary>

```
microsoft-ai-security-control-plane/
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md                        # the contribution rule; atomic row PRs; running the validators
├── SECURITY.md                            # what to report here vs to MSRC; no-secrets policy; the tracked .claude/ config
├── LICENSE                                # MIT — covers scripts/ and .github/workflows/
├── LICENSE-CONTENT                        # CC BY 4.0 — covers the documentation content
├── disclaimer.md
├── matrix/
│   └── capability-status-matrix.md        # the spine: capability → status → source + last-verified date
├── crosswalk/
│   └── framework-crosswalk.md             # item-level; v0.2; author synthesis
├── checklists/
│   └── capability-status-verification.md  # the 9-group practitioner checklist
├── docs/
│   ├── how-to-read-status.md              # GA vs Preview vs Roadmap; sourcing + verification methodology
│   ├── agent-cadence.md                   # the tiered automated refresh: what is automated, what stays human
│   └── scope-and-out-of-scope.md          # what belongs here, what does not, and where it belongs instead
├── scripts/                               # standard-library only; no third-party dependency
│   ├── watch_sources.py                   # tier D1: deterministic source watcher (no model, no judgement)
│   ├── unreachable_alarm.py               # opens an issue when a watched source fails on two consecutive runs
│   ├── stale_guard.py                     # tier D4: staleness guard over the recorded last-verified dates
│   ├── validate_bot_pr.py                 # the deterministic gate: sourcing, labelling, confidentiality
│   └── changelog_entry.py                 # appends a refresh record in the existing format
├── tests/                                 # standard-library unittest; `python -m unittest discover -s tests`
│   ├── test_watch_sources.py              # signal scoping, registry shape, invariants over the committed baseline
│   ├── test_unreachable_alarm.py          # the two-consecutive-failure rule and its quiet-failure paths
│   ├── test_validate_bot_pr.py            # the gates themselves, including the cases where one could not run
│   ├── test_stale_guard.py                # the staleness arithmetic and the step-output contract CI reads
│   └── test_changelog_entry.py            # one heading per calendar month, and the released-section protection
├── .claude/                               # Claude Code agents, rules and hooks — described in SECURITY.md
└── .github/
    ├── workflows/                         # daily source watch, monthly refresh, weekly stale guard, validate gate
    ├── watch-state/                       # sources.json (pinned source registry) + fingerprints.json (baseline)
    ├── ISSUE_TEMPLATE/                    # new row proposal, status correction, tenant verification
    └── pull_request_template.md
```

</details>
