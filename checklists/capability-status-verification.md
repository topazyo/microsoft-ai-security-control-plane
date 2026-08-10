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

- [ ] Licensing prerequisite recorded per capability with a Learn citation — **and if you cannot find one, say so rather than supplying a plausible SKU.** As verified **2026-08-10** (matrix row 6) Microsoft's references are **circular**: the DSPM considerations page names no SKU and defers to the Purview service description, which defers back to the DSPM article. Do **not** record "M365 E5 / E5 Compliance" for DSPM for AI from memory or from a comparison site — that expectation is currently **unverified**. What Learn does state specifically: a Microsoft 365 Copilot license for the Copilot/agent scope, the enterprise version of Purview data governance for the Fabric/Security Copilot scope, and pay-as-you-go billing for other AI apps.
- [ ] Third-party AI-site monitoring dependency noted (device onboarding + Purview browser extension). As verified **2026-08-10**: the browser extension is deployed to **Windows** users, and endpoint DLP enforcement against AI sites is scoped to **Windows computers onboarded to Microsoft Purview**.
- [ ] Default posture recorded as **audit/monitor**, not "blocks by default"; enforcement noted as configuration + endpoint onboarding. Confirmed verbatim **2026-08-10** (matrix row 7): discovery policies cover all users "in audit mode only", the one blocking policy ships "in test mode", policies are one-click **activated** rather than on by default, and only the weekly SharePoint risk assessment runs with "No activation needed".
- [ ] **Which DSPM version the documentation describes is checked before any claim is carried over.** As verified **2026-08-10** the "DSPM for AI" articles are marked **classic** ("now replaced with a new version"), while a single Learn page calls the replacement both "the preview version" and "the current version of DSPM". Matrix rows 6 and 7 are therefore **Requires further validation** — confirm which version your tenant runs.

**Group 4 — Defender product boundaries & detection surface**

- [ ] Defender for AI recorded as **Azure-hosted / Foundry models only** — **not** covering Microsoft 365 Copilot or GitHub Copilot.
- [ ] Defender for AI GA date and AI-agent support date recorded **only with a Learn citation + last-verified date** (GA 2025-05-01; agents **Preview** 2026-02-02 — per Defender for Cloud release notes, verified 2026-08-07; the release-notes index lists that entry under both 2026-02-02 and 2026-02-03).
- [ ] AI-agent coverage attributed to the **release notes**, not to the AI threat protection availability table — as verified 2026-08-07 that table's "Feature availability" cell lists only activity monitoring and prompt evidence.
- [ ] M365 Copilot prompt-injection coverage attributed to **Defender XDR advanced hunting** — the **exact schema/columns confirmed in your own workspace** before any detection logic is published (no field names asserted from memory).

**Group 5 — Sentinel**

- [ ] Microsoft Copilot connector for Sentinel: current status verified against Learn (historically Public Preview — not GA); destination table name confirmed against Learn. As verified **2026-08-10** (matrix row 9) the status is **Requires further validation**, because the reference page **contradicts itself**: a page-level notice says all Sentinel data connectors "are currently in Preview", while the same page suffixes only *some* entries "(Preview)" and the Microsoft Copilot entry carries no qualifier and no release-state sentence at all. **Do not record this connector as GA.** The destination table is named CopilotActivity, stated in prose on that page.
- [ ] **Connector naming checked before the row is matched to a Microsoft 365 Copilot control.** As verified 2026-08-10 the string "Microsoft 365 Copilot" does not appear on the page; the connector is named "Microsoft Copilot" and spans **Security Copilot** as well, so the scope is broader than M365 Copilot alone.
- [ ] No dedicated Learn page for this connector is assumed to exist — as verified 2026-08-10, six candidate URLs returned 404 and the solutions catalog contains no occurrence of "Copilot"; the aggregate data-connectors reference page is the only primary source.
- [ ] Any detection logic on the connector's schema marked "verified in own workspace" before publication.

**Group 6 — Entra Conditional Access for AI identities**

- [ ] Conditional Access **workload-identity** policies target **single-tenant service principals** directly or by **custom-security-attribute filter**, with the **Microsoft Entra Workload Identities Premium** prerequisite. **The Microsoft 365 Copilot first-party (multitenant) service principal is not a documented CA target and appears excluded** — Microsoft first-party / multitenant apps are out of scope of workload-identity CA; do not claim it can be CA-targeted. (Note: `New-MgServicePrincipal` *creates* a service principal — it is not a targeting mechanism.)
- [ ] Documented that Copilot Studio agents are blocked from responding when Conditional Access blocks token acquisition (verify behavior).

**Group 7 — Shadow AI & GitHub/MCP governance**

- [ ] Defender for Cloud Apps gen-AI discovery recorded with the current **Microsoft Learn catalog figure** (with a last-verified date) — not a marketing figure. As verified **2026-08-10** (matrix row 8) Learn states "over 31,000 discoverable cloud apps" and defines **Generative AI** as a first-class catalog category, with adjacent **AI – MCP Server** and **AI – Model Provider** categories.
- [ ] **Platform coverage stated carefully: Windows is unambiguous, macOS is contradicted by the source.** As verified 2026-08-10, one Learn page says "Supported apps include Windows and macOS apps" and the integration prerequisites list macOS, but the same integration page's "How it works" describes the agent running on **Windows** and discovery "across the Windows devices on your network". Confirm macOS in your own tenant before claiming it. Also note Learn's macOS caveat that "UDP protocols aren't covered for macOS support".
- [ ] **No "shadow AI" feature page is assumed to exist.** As verified 2026-08-10 the phrase does not appear anywhere in this product's documentation and there is no Learn article dedicated to gen-AI app discovery — the evidence is the catalog category table alone. Also record what discovery cannot see: per Learn it "can't discover apps that aren't in the catalog."
- [ ] GitHub Copilot policy recorded as configurable at **enterprise and org** levels (more-restrictive precedence wins).
- [ ] GitHub **MCP registry governance documented as a gap, not a delivered control** (VS Code-centric; bypassable via local stdio servers, workspace/user `mcp.json`, other clients).

**Group 8 — Framework cross-walk hygiene**

- [ ] OWASP references use **2026 (v1.0)** numbering (Sensitive Information Disclosure = **LLM02**, Excessive Agency = **LLM03**, Supply Chain = **LLM04**, Improper Output Handling = **LLM10**).
- [ ] No 2025-era OWASP ID carried over unchanged — only **LLM01** and **LLM02** kept their numbers in the 2026 edition. Re-base every other ID against the renumbering table in [`crosswalk/framework-crosswalk.md`](../crosswalk/framework-crosswalk.md), and note that **System Prompt Leakage (LLM07:2025) is now LLM08:2026 Hidden Context Exposure** — renamed and re-scoped, not a like-for-like rename.
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

*Version 1.3 — Last validated: 2026-08-10 — against Microsoft Learn + the public Microsoft 365 Roadmap as of the verification date. **Scope of this stamp:** the 2026-08-10 pass re-read Microsoft Learn for the capabilities behind matrix rows 6–9 only, so the dated bullets in Groups 3, 5 and 7 carry that date; Groups 1, 2, 4, 6, 8 and 9 were **not** re-run and their content still rests on the dates recorded in their own bullets. Group 8 was separately re-based on the OWASP Top 10 for LLM Applications **2026 edition** on 2026-08-09; that date covers the OWASP items only. **Shipped in v0.1.1:** Group 3's DSPM for AI rows (matrix 6 and 7, both **Requires further validation**), Group 7's Defender for Cloud Apps gen-AI discovery (matrix 8, **GA**), and Group 5's Sentinel Microsoft Copilot connector (matrix 9, **Requires further validation**). **Deferred to v0.1.2, with reasons:** Group 6's Entra Conditional Access row and **Group 4's Defender XDR advanced-hunting row** (not reached in the v0.1.1 verification pass — no status asserted), and Group 7's GitHub Copilot policy row (its primary source is outside the validator's allowed source hosts). Group 7 therefore spans a shipped row and a deferred one. Group 9 covers the automated refresh described in [`docs/agent-cadence.md`](../docs/agent-cadence.md).*
