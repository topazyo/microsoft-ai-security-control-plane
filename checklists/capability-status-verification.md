# Microsoft AI Security Capability Status Verification Checklist

**Who this is for:** security architects and M365 security admins building or reviewing a Microsoft AI-adoption coverage map.
**When to use it:** before briefing leadership, before publishing any capability claim, and at each monthly matrix refresh.

---

**Group 1 — Status hygiene (every capability)**

- [ ] Explicit status label: GA / Public Preview / Roadmap / Requires further validation.
- [ ] Primary-source URL (Microsoft Learn or the public Microsoft 365 Roadmap) recorded next to it; a Message Center post has **no public URL** — record the MC ID only, as a tenant-side tracking reference, never as the row's primary source (Group 9; [`docs/how-to-read-status.md`](../docs/how-to-read-status.md)).
- [ ] "Last verified" date within the current monthly window.
- [ ] Status is never sourced from a launch/marketing blog as the source of truth (Tech Community is official-adjacent only).

**Group 2 — Purview DLP for Copilot (four sub-capabilities, different schedules)**

- [ ] Processing of sensitivity-labelled files/emails recorded as **GA** (email coverage: sent on or after 2025-01-01; calendar invites not supported). Note that the "extends to prebuilt agents" sentence present on 2026-07-14 is **no longer on the Learn page** as verified 2026-08-07 — do not claim prebuilt-agent coverage from this source.
- [ ] External web search on SIT-containing prompts: status verified against **Microsoft 365 Roadmap feature 548671** (status **"Launched"** / GA, availability June CY2026, as verified 2026-08-07) and the Message Center rollout reference **MC1263277**; availability confirmed in your own tenant.
- [ ] Typed-prompt SIT blocking recorded as **Requires further validation** — **not** stated as GA. As verified 2026-08-07 the Learn section heading no longer carries the "(preview)" qualifier, but the body of that same section still reads "This feature is in preview and is rolling out to all tenants". **A dropped heading qualifier alone is not GA evidence** — confirm the body wording and the in-tenant behavior before any status change.
- [ ] External-email grounding block recorded as **Public Preview** (Learn heading carries "(preview)", as verified 2026-08-07), and its scope recorded accurately: **sender-domain metadata only; the email body is not inspected**. Do not present it as content-level prompt-injection inspection.
- [ ] Configuration verified against current Learn: Custom DLP template only; selecting the Copilot location disables the other locations in that policy; exactly what content DLP evaluates confirmed (per Learn, typed prompt text only — uploaded files in prompts are not scanned).

**Group 3 — DSPM for AI**

- [ ] Licensing prerequisite recorded per capability (e.g. M365 E5 / E5 Compliance) with a Learn citation.
- [ ] Third-party AI-site monitoring dependency noted (device onboarding + Purview browser extension).
- [ ] Default posture recorded as **audit/monitor**, not "blocks by default"; enforcement noted as configuration + endpoint onboarding.

**Group 4 — Defender product boundaries & detection surface**

- [ ] Defender for AI recorded as **Azure-hosted / Foundry models only** — **not** covering Microsoft 365 Copilot or GitHub Copilot.
- [ ] Defender for AI GA date and AI-agent support date recorded **only with a Learn citation + last-verified date** (GA 2025-05-01; agents **Preview** 2026-02-02 — per Defender for Cloud release notes, verified 2026-08-07; the release-notes index lists that entry under both 2026-02-02 and 2026-02-03).
- [ ] AI-agent coverage attributed to the **release notes**, not to the AI threat protection availability table — as verified 2026-08-07 that table's "Feature availability" cell lists only activity monitoring and prompt evidence.
- [ ] M365 Copilot prompt-injection coverage attributed to **Defender XDR advanced hunting** — the **exact schema/columns confirmed in your own workspace** before any detection logic is published (no field names asserted from memory).

**Group 5 — Sentinel**

- [ ] Microsoft Copilot connector for Sentinel: current status verified against Learn (historically Public Preview — not GA); destination table name confirmed against Learn.
- [ ] Any detection logic on the connector's schema marked "verified in own workspace" before publication.

**Group 6 — Entra Conditional Access for AI identities**

- [ ] Conditional Access **workload-identity** policies target **single-tenant service principals** directly or by **custom-security-attribute filter**, with the **Microsoft Entra Workload Identities Premium** prerequisite. **The Microsoft 365 Copilot first-party (multitenant) service principal is not a documented CA target and appears excluded** — Microsoft first-party / multitenant apps are out of scope of workload-identity CA; do not claim it can be CA-targeted. (Note: `New-MgServicePrincipal` *creates* a service principal — it is not a targeting mechanism.)
- [ ] Documented that Copilot Studio agents are blocked from responding when Conditional Access blocks token acquisition (verify behavior).

**Group 7 — Shadow AI & GitHub/MCP governance**

- [ ] Defender for Cloud Apps gen-AI discovery recorded for **Windows and macOS**, citing the current **Microsoft Learn catalog figure** (with a last-verified date) — not a marketing figure.
- [ ] GitHub Copilot policy recorded as configurable at **enterprise and org** levels (more-restrictive precedence wins).
- [ ] GitHub **MCP registry governance documented as a gap, not a delivered control** (VS Code-centric; bypassable via local stdio servers, workspace/user `mcp.json`, other clients).

**Group 8 — Framework cross-walk hygiene**

- [ ] OWASP references use **2025 (v2.0)** numbering (Sensitive Information Disclosure = **LLM02**, Supply Chain = **LLM03**).
- [ ] Every framework cited **with its version** and mapped at **item level** (OWASP LLM0x; MITRE ATLAS technique ID verified against the ATLAS knowledge base; NIST AI 600-1 subcategory; CSA AICM control-objective ID with version).
- [ ] Cross-walk labelled **author synthesis, "v0.1, expanding"** — never presented as Microsoft's official mapping.

**Group 9 — Automated-refresh escalation (run at every refresh, and when reviewing any automated pull request)**

- [ ] Every automated row change reviewed and merged by a **human**; no automated run merges its own pull request.
- [ ] Every primary-source URL in a changed row appears in the run's evidence bundle — a citation the watcher did not fetch is **not** evidence, regardless of how plausible the URL looks.
- [ ] Last-verified dates advanced **only** for rows whose source was fetched successfully in that run; a row whose source was unreachable keeps its old date and is allowed to age into the staleness window.
- [ ] No row moved **out** of **Requires further validation** by an automated run. That transition requires in-tenant confirmation and is raised as an issue via `.github/ISSUE_TEMPLATE/tenant-verification.md`, never as a row edit.
- [ ] Open `tenant-verification-required` issues triaged this cycle — the escalation queue is part of the refresh, not a backlog.
- [ ] Open staleness issues closed or explained; anything past the monthly window either re-verified or recorded as knowingly stale with a reason.
- [ ] **Message Center checked by a human.** Message Center posts are tenant-scoped and are never fetched by automation. Record the MC ID only — never paste Message Center content into the repository.
- [ ] **CSA AICM control IDs re-verified by a human** against the AICM workbook; they are published only in a registration-gated spreadsheet and cannot be machine-verified.
- [ ] Automated changes confined to the path allowlist (`matrix/`, `crosswalk/`, `checklists/`, `CHANGELOG.md`, `.github/watch-state/`) — no drift into KQL/detections, DevSecOps/CI, or vendor-comparison content.
- [ ] No tenant-specific data introduced by any automated change: no GUIDs, tenant or subscription identifiers, hostnames, user names, email addresses, or screenshots.

---

*Version 1.1 — Last validated: 2026-08-07 — against Microsoft Learn + the public Microsoft 365 Roadmap as of the verification date. Groups 3, 5, 6, and 7 describe verification steps for capabilities whose matrix rows land in v0.1.1; their statuses are not asserted here. Group 9 covers the automated refresh described in [`docs/agent-cadence.md`](../docs/agent-cadence.md).*
