# Capability-Status Matrix

**The spine of this repository:** one row per Microsoft AI-security capability, with its release status, a primary-source URL, and the date the status was last verified against that source.

> **Read `docs/how-to-read-status.md` first** if you are unsure what GA / Public Preview / Roadmap / Requires further validation mean here, or how each status is sourced.
>
> **Statuses change.** Verify any row whose last-verified date is older than the current monthly refresh window, and confirm contested rows in your own tenant before relying on them.

## Status legend

| Label | Meaning |
|---|---|
| **GA** | Generally Available per Microsoft primary sources (Microsoft Learn without a preview qualifier, and/or Microsoft 365 Roadmap status "Launched"). |
| **Public Preview** | Microsoft primary sources label the capability preview (e.g. a "(preview)" qualifier on Microsoft Learn). Preview terms apply — see `docs/how-to-read-status.md`. |
| **Roadmap** | Announced with a Microsoft 365 Roadmap entry; not yet rolling out. |
| **Requires further validation** | Microsoft's own sources conflict or the status cannot be confirmed from primary sources alone; verify in your own tenant before relying on it. |

## The matrix (v0.1.0 — 5 rows, expanding)

The four **DLP for Microsoft 365 Copilot** rows (1, 2, 3 and 5) are the worked example of why this matrix exists: what most people name as *one* feature is **four sub-capabilities that shipped on different schedules** — and as of the current verification date they still do not share one status.

| # | Capability | Microsoft product | AI risk class | Status | Primary source | Last verified | Notes / caveats |
|---|---|---|---|---|---|---|---|
| 1 | Restrict Copilot from processing files and emails with sensitivity labels | Microsoft Purview DLP — **Microsoft 365 Copilot and Copilot Chat** policy location | Sensitive-data leakage to AI | **GA** | [Microsoft Purview DLP for Microsoft 365 Copilot and Copilot Chat (Microsoft Learn)](https://learn.microsoft.com/en-us/purview/dlp-microsoft365-copilot-location-learn-about) | 2026-08-07 | See [row 1 details](#row-1--sensitivity-label-processing-restriction). |
| 2 | Block Copilot's external web search when a prompt contains sensitive info types (SITs) | Microsoft Purview DLP — same policy location | Sensitive-data leakage to AI (egress to external search providers) | **GA** (Roadmap 548671 status **"Launched"**, availability June CY2026) | [Microsoft Learn](https://learn.microsoft.com/en-us/purview/dlp-microsoft365-copilot-location-learn-about) · [Microsoft 365 Roadmap, feature ID 548671](https://www.microsoft.com/en-us/microsoft-365/roadmap?id=548671) | 2026-08-07 | See [row 2 details](#row-2--external-web-search-block-on-sensitive-prompts). |
| 3 | Block sensitive info types typed into the Copilot prompt itself | Microsoft Purview DLP — same policy location | Sensitive-data leakage to AI (prompt content) | **Requires further validation** | [Microsoft Learn](https://learn.microsoft.com/en-us/purview/dlp-microsoft365-copilot-location-learn-about) | 2026-08-07 | **Not GA.** Learn's heading qualifier changed on this refresh while its body did not — see [row 3 details](#row-3--typed-prompt-sit-blocking). |
| 4 | Runtime threat protection for Azure-hosted AI workloads (Defender for AI Services) | Microsoft Defender for Cloud — AI threat protection | Prompt injection (direct/indirect), jailbreak, data exposure, wallet abuse against Azure-hosted models | **GA** (since 2025-05-01); AI-agent (Foundry) protection: **Public Preview** (since 2026-02-02) | [AI threat protection in Microsoft Defender for Cloud (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/defender-for-cloud/ai-threat-protection) | 2026-08-07 | **Scope boundary — read [row 4 details](#row-4--defender-for-ai-scope-boundary) before mapping coverage.** It does **not** cover Microsoft 365 Copilot or GitHub Copilot. |
| 5 | Block Copilot from processing email received from external senders | Microsoft Purview DLP — same policy location | Prompt injection (indirect/XPIA carried in untrusted inbound email) | **Public Preview** | [Microsoft Learn](https://learn.microsoft.com/en-us/purview/dlp-microsoft365-copilot-location-learn-about) | 2026-08-07 | Evaluates **sender domain metadata only** — the email body is not inspected. See [row 5 details](#row-5--external-email-grounding-block). |

---

## Row details

### Row 1 — Sensitivity-label processing restriction

- **What it does:** DLP policies using the **Microsoft 365 Copilot and Copilot Chat** location with the **Content contains > Sensitivity labels** condition exclude labeled items from being processed. Per Microsoft Learn: "Identified items still appear in the citations of the response, but the content of the item isn't used in the response or accessed by Copilot."
- **Status evidence (verified 2026-08-07):** the Learn section "Block files and emails with sensitivity labels from being processed" carries **no preview qualifier** and states "This feature is available in Microsoft 365 Copilot, Copilot Chat, and Copilot in Word, Excel, PowerPoint."
- **Source-wording change at this refresh:** on 2026-07-14 the same section additionally stated "This protection also extends to prebuilt agents in Microsoft 365 Copilot and Copilot Chat." That sentence is **no longer present** on the page as of 2026-08-07. The row's status is unaffected — the section still carries no preview qualifier — but **prebuilt-agent coverage should no longer be claimed from this source**. Confirm agent coverage in your own tenant before relying on it.
- **Caveats (from the same Learn page, verified 2026-08-07):**
  - Emails are covered only if **sent on or after January 1, 2025**; calendar invites are **not** supported.
  - When a labeled file is open in Word/Excel/PowerPoint under such a policy, Copilot skills in those apps are disabled; certain experiences that don't reference file content "aren't currently blocked."
- **Configuration reality (applies to rows 1–3 and 5):** the Copilot location is available **only in the Custom policy template**, and "when you select the Microsoft 365 Copilot and Copilot Chat policy location, **all other locations for that policy are disabled**." Policy updates can take up to four hours to take effect.

### Row 2 — External web search block on sensitive prompts

- **What it does:** a rule with **Content contains > Sensitive information types** and the action **Prevent Copilot from processing content > Performing Web Searches** stops Copilot from sending prompts containing configured SITs to external web search providers; responses continue from permitted internal Microsoft 365 sources.
- **Status evidence (verified 2026-08-07):**
  - The Learn section "Block sensitive information types in web search" carries **no preview qualifier**.
  - Microsoft 365 Roadmap feature **548671** shows status **"Launched"** with availability **June CY2026** (the Roadmap defines Launched as "fully released updates that are now generally available for applicable customers"). Confirmed via the public roadmap and Microsoft's public release-communications API for feature 548671; the API record was last modified **2026-06-12**.
- **History / caveats:** this sub-capability rolled out later than row 1 and was tracked in the Message Center as **MC1263277** (Message Center posts are tenant-scoped and have no public URL — cite the Roadmap ID publicly). Per the Roadmap description it "currently extends to Microsoft 365 Copilot and agents built in Copilot Studio that are published to Microsoft 365 Copilot." **Confirm availability in your own tenant** — regional/tenant rollout can lag a Launched status.

### Row 3 — Typed-prompt SIT blocking

- **What it does:** a rule with **Content contains > Sensitive information types** and the action **Restrict Copilot from processing content > Processing prompts** prevents Copilot from returning a response when the typed prompt contains configured SITs.
- **Why "Requires further validation":** Microsoft's own sources have described this sub-capability's status inconsistently (Ignite-era Microsoft blog coverage described it as entering GA while Microsoft Learn labeled it preview). As of **2026-08-07** the disagreement sits **inside a single Learn page**:
  - The section heading **no longer carries the "(preview)" qualifier** it carried on 2026-07-14. It now reads "**Block sensitive information types in prompts**".
  - The body of that same section is **unchanged** and still states, verbatim: "This feature is in preview and is rolling out to all tenants with access to Microsoft 365 Copilot and Copilot Chat. Check whether rollout has reached your tenant."
- **The dropped heading qualifier is not evidence of GA.** A removed qualifier sitting alongside an unchanged "This feature is in preview" sentence is precisely the conflicting-source condition this label exists for. The status therefore **holds at Requires further validation** on this refresh rather than moving to GA.
- **Do not record this row as GA.** Verify the rollout state in your own tenant. Treat this row as GA only when the page's own body text stops describing the feature as in preview **and** the behavior is confirmed in-tenant.
- **Scanning-scope caveat (verified 2026-08-07, Learn, verbatim):** "DLP can't scan the contents of files that you upload directly into prompts, so evaluation of the uploaded file for sensitive data doesn't occur. **DLP only checks the text you type into the prompt itself.**" Treat "what gets scanned" as a question to confirm at each verification pass, not an assumption.
- **Preview UX caveat (Learn):** during preview, blocking messages in Word/Excel/PowerPoint "might not clearly state" that the interaction was blocked by policy — the prompt is still restricted.

### Row 4 — Defender for AI scope boundary

- **What it does:** Microsoft Defender for Cloud's **AI threat protection** (Defender for AI Services plan) provides runtime threat detection for **Azure-hosted AI workloads** — per Learn, supported services are **Azure OpenAI supported models** and **Azure AI Model Inference service supported models**; alerts cover threats such as jailbreak, wallet abuse, data exposure, and suspicious access patterns.
- **Status evidence (verified 2026-08-07):**
  - The Learn availability table states **"Release state: Generally available (GA)."**
  - Defender for Cloud release-notes archive, May 2025: "**General Availability for Defender for AI Services** — May 1, 2025."
  - Defender for Cloud release notes: "**Threat protection for AI agents (Preview)** — … threat protection for AI agents built with Foundry, available in **preview** as part of the Defender for AI Services plan." The release-notes index lists this entry under both **February 2, 2026** and **February 3, 2026**; the matrix records the earlier date.
  - The availability table's **Feature availability** cell lists only "Activity monitoring (security alerts)" and "Prompt evidence (security alerts)" — it does **not** enumerate AI-agent protection. Agent coverage is evidenced by the release notes above, not by this table.
- **Common misconception — the scope boundary this row exists to document:** Defender for AI protects **Azure-hosted / Foundry model workloads only**. It does **not** cover **Microsoft 365 Copilot** and does **not** cover **GitHub Copilot**. Drawing Defender for AI as blanket "AI coverage" on an architecture diagram is a product-boundary error: M365 Copilot risk is addressed through Defender XDR and Microsoft Purview capabilities (rows planned for v0.1.1).
- **Additional Learn caveats (verified 2026-08-07):** text tokens only (image/audio tokens aren't scanned); commercial clouds only — the availability table records **Azure Government: No**, **21Vianet: No**, and **Connected AWS accounts: No**; enabling at subscription level requires Owner or equivalent data-action roles.
- **Sources:** [AI threat protection (Learn)](https://learn.microsoft.com/en-us/azure/defender-for-cloud/ai-threat-protection) · [Defender for Cloud release notes](https://learn.microsoft.com/en-us/azure/defender-for-cloud/release-notes) · [release-notes archive](https://learn.microsoft.com/en-us/azure/defender-for-cloud/release-notes-archive).

### Row 5 — External-email grounding block

- **What it does:** a rule using the **Microsoft 365 Copilot and Copilot Chat** location with the **Email is received from > External users** condition excludes externally-sent email from Copilot grounding. Per Microsoft Learn: "When the policy detects that an email was received from a sender outside your organization's accepted domains, Copilot excludes that email from grounding, summarization, and citation. Copilot continues to use internal Microsoft 365 data sources where permitted, and the user's access to the email itself isn't affected."
- **Status evidence (verified 2026-08-07):** the Learn section heading carries a preview qualifier — "**Block external email from being processed (preview)**" — and the body states "This feature is in preview. It applies to Microsoft 365 Copilot and Copilot Chat, including email summarization and reasoning experiences that use email data." Preview terms apply; see [`docs/how-to-read-status.md`](../docs/how-to-read-status.md).
- **Why this row is a prompt-injection control, not a data-leakage control:** the other DLP-for-Copilot rows restrict what *leaves*. This one restricts what *enters* the model's grounding set. Per Learn, "This protection helps organizations reduce the risk of prompt injection and untrusted data influence."
- **Scope caveat — read before treating this as XPIA coverage (Learn, verbatim):** "The policy evaluates email metadata only - specifically, the sender domain compared against your tenant's accepted domains. **The body of the email isn't inspected.**" It is a sender-domain trust boundary, not content inspection: injected instructions inside an email from an *accepted* domain are not addressed by this control.
- **New at the 2026-08-07 refresh.** This sub-capability was not present in the matrix at v0.1.0 and was found by re-reading the row 1–3 source page. Confirm availability in your own tenant before relying on it.

---

## Planned rows (v0.1.1+, not yet verified — no status asserted)

DSPM for AI (licensing + default-posture rows) · Microsoft Sentinel Copilot connector · Defender XDR advanced hunting for M365 Copilot prompt-injection signals · Entra Conditional Access for AI workload identities · Defender for Cloud Apps gen-AI discovery (shadow AI) · GitHub Copilot policy management · MCP governance (documented as a gap, not a delivered control).

## How rows are verified

Every row carries a primary-source URL (Microsoft Learn or the public Microsoft 365 Roadmap) and a last-verified date. Status is never sourced from launch or marketing blogs (Tech Community is treated as official-adjacent context only). Where Microsoft's own sources conflict, the row is labelled **Requires further validation** — never guessed. Rows are re-verified monthly against Microsoft Learn "What's new" pages and the Message Center; every change is recorded in [`CHANGELOG.md`](../CHANGELOG.md). How that refresh is executed — which checks are automated, which remain human, and why a row can never be moved out of "Requires further validation" automatically — is described in [`docs/agent-cadence.md`](../docs/agent-cadence.md).
