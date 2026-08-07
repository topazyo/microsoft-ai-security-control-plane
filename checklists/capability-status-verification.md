# Microsoft AI Security Capability Status Verification Checklist

**Who this is for:** security architects and M365 security admins building or reviewing a Microsoft AI-adoption coverage map.
**When to use it:** before briefing leadership, before publishing any capability claim, and at each monthly matrix refresh.

---

**Group 1 — Status hygiene (every capability)**

- [ ] Explicit status label: GA / Public Preview / Roadmap / Requires further validation.
- [ ] Primary-source URL (Microsoft Learn or Message Center) recorded next to it.
- [ ] "Last verified" date within the current monthly window.
- [ ] Status is never sourced from a launch/marketing blog as the source of truth (Tech Community is official-adjacent only).

**Group 2 — Purview DLP for Copilot (three sub-capabilities, three schedules)**

- [ ] Processing of sensitivity-labelled files/emails recorded as **GA** (email coverage: sent on or after 2025-01-01; calendar invites not supported).
- [ ] External web search on SIT-containing prompts: status verified against **Microsoft 365 Roadmap feature 548671** (status **"Launched"** / GA, availability June CY2026, as verified 2026-07-03) and the Message Center rollout reference **MC1263277**; availability confirmed in your own tenant.
- [ ] Typed-prompt SIT blocking recorded as **Requires further validation** — **not** stated as GA (Microsoft Learn still labels it "(preview)", "rolling out to all tenants", as verified 2026-07-03; earlier Microsoft blog coverage described it as entering GA).
- [ ] Configuration verified against current Learn: Custom DLP template only; selecting the Copilot location disables the other locations in that policy; exactly what content DLP evaluates confirmed (per Learn, typed prompt text only — uploaded files in prompts are not scanned).

**Group 3 — DSPM for AI**

- [ ] Licensing prerequisite recorded per capability (e.g. M365 E5 / E5 Compliance) with a Learn citation.
- [ ] Third-party AI-site monitoring dependency noted (device onboarding + Purview browser extension).
- [ ] Default posture recorded as **audit/monitor**, not "blocks by default"; enforcement noted as configuration + endpoint onboarding.

**Group 4 — Defender product boundaries & detection surface**

- [ ] Defender for AI recorded as **Azure-hosted / Foundry models only** — **not** covering Microsoft 365 Copilot or GitHub Copilot.
- [ ] Defender for AI GA date and AI-agent support date recorded **only with a Learn citation + last-verified date** (GA 2025-05-01; agents **Preview** 2026-02-02 — per Defender for Cloud release notes, verified 2026-07-03).
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

---

*Version 1.0 — Last validated: 2026-07-03 — against Microsoft Learn + the public Microsoft 365 Roadmap as of the verification date. Groups 3, 5, 6, and 7 describe verification steps for capabilities whose matrix rows land in v0.1.1; their statuses are not asserted here.*
