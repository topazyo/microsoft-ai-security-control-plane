# Framework Cross-Walk — v0.1, expanding

> **This cross-walk is the author's interpretive synthesis. It is NOT Microsoft's official mapping, and not an official mapping by OWASP, MITRE, NIST, or the Cloud Security Alliance.** It is versioned (**v0.1**) and expands as matrix rows are added. Mappings are made at **item level** (specific framework item IDs), never category-to-product.

## Framework versions cited

| Framework | Version / edition cited | Primary source | Last verified |
|---|---|---|---|
| OWASP Top 10 for LLM Applications | **2025 edition (v2.0**, published 2024-11-18 by the OWASP GenAI Security Project**)** | [genai.owasp.org/llm-top-10](https://genai.owasp.org/llm-top-10/) · [2025 resource page](https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/) | 2026-08-07 |
| MITRE ATLAS | ATLAS knowledge base (technique IDs verified against MITRE's published `atlas-data` dataset, dist v5.6.0) | [atlas.mitre.org](https://atlas.mitre.org/) — technique pages [AML.T0051](https://atlas.mitre.org/techniques/AML.T0051), [AML.T0057](https://atlas.mitre.org/techniques/AML.T0057) | 2026-08-07 |
| NIST AI 600-1 | *Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile*, July 2024 | [nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) · [doi.org/10.6028/NIST.AI.600-1](https://doi.org/10.6028/NIST.AI.600-1) | 2026-08-07 |
| CSA AI Controls Matrix (AICM) | **v1.1.0** (official CSA spreadsheet, generated 2026-06-18): **247 control objectives across 18 security domains** (verified by direct count). Note: the CSA artifact page (v1, released 2025-07-09, updated 2025-10-30) still describes "243 control objectives" — the v1.0 figure. | [cloudsecurityalliance.org/artifacts/ai-controls-matrix](https://cloudsecurityalliance.org/artifacts/ai-controls-matrix) | 2026-07-03 |

> **Why the CSA row's date is older than the others.** AICM control IDs are published only inside a registration-gated spreadsheet, so this row cannot be re-verified without a human downloading the workbook. It is recorded as a human-only source in `.github/watch-state/sources.json` and is deliberately left at its last genuine verification date rather than being advanced along with the rest of the table. See [`docs/agent-cadence.md`](../docs/agent-cadence.md).

**A note on the 2025 OWASP numbering:** this cross-walk uses the **2025** designations (LLM01:2025–LLM10:2025). In the 2025 edition, **Sensitive Information Disclosure is LLM02** and **Supply Chain is LLM03** — the older 2023/24 v1.x numbering (where Sensitive Information Disclosure was LLM06) is **not** used here.

## Cross-walk (item level)

Row numbers refer to [`matrix/capability-status-matrix.md`](../matrix/capability-status-matrix.md).

| Microsoft control (matrix row) | OWASP LLM 2025 item | MITRE ATLAS technique ID | NIST AI 600-1 risk (subcategory) | CSA AICM control ID (version) | Notes (synthesis) |
|---|---|---|---|---|---|
| Row 1 — Purview DLP: block labeled files/emails from Copilot processing | **LLM02:2025** Sensitive Information Disclosure | **AML.T0057** LLM Data Leakage | **2.4 Data Privacy** | **DSP-17** Sensitive Data Protection · **DSP-04** Data Classification (v1.1.0) | Prevents labeled content from entering Copilot responses; classification-label-driven protection of sensitive data through its lifecycle. |
| Row 2 — Purview DLP: block external web search on SIT-containing prompts | **LLM02:2025** Sensitive Information Disclosure | **AML.T0057** LLM Data Leakage | **2.4 Data Privacy** | **DSP-10** Sensitive Data Transfer · **DSP-17** Sensitive Data Protection (v1.1.0) | Egress-side control: stops sensitive prompt content from leaving the tenant boundary toward external search providers. |
| Row 3 — Purview DLP: block SITs typed into prompts | **LLM02:2025** Sensitive Information Disclosure | **AML.T0057** LLM Data Leakage | **2.4 Data Privacy** | **DSP-17** Sensitive Data Protection (v1.1.0) | Input-side control; note the matrix row's status (**Requires further validation**) and its typed-text-only scanning caveat. |
| Row 4 — Defender for Cloud: AI threat protection (Azure-hosted models) | **LLM01:2025** Prompt Injection | **AML.T0051** LLM Prompt Injection (Direct **AML.T0051.000** / Indirect **AML.T0051.001**) | **2.9 Information Security** | **LOG-03** Security Monitoring and Alerting · **LOG-15** Input Monitoring · **LOG-16** Output Monitoring (v1.1.0) | Runtime detection of prompt-injection/jailbreak-class attacks against **Azure-hosted** models only — see the row-4 scope boundary; this mapping must not be read as M365 Copilot coverage. |
| Row 5 — Purview DLP: block external email from Copilot grounding (preview) | **LLM01:2025** Prompt Injection | **AML.T0051.001** LLM Prompt Injection: Indirect | **2.9 Information Security** | *Not yet mapped — requires an AICM v1.1.0 workbook lookup (human step; see the CSA note above)* | Input-side trust boundary rather than an egress control: excludes externally-sourced email from the grounding set. **Read the matrix row's scope caveat before treating this as XPIA coverage** — per Learn the policy evaluates sender-domain metadata only and does not inspect the email body, so injected instructions arriving from an accepted domain are not addressed. |

## About the CSA AICM column

CSA publishes the AICM control-objective IDs inside the downloadable spreadsheet (registration-gated on the CSA artifact page), not on public web pages. The IDs in this cross-walk were verified directly against the official **AICM v1.1.0 spreadsheet** (generated 2026-06-18, obtained from CSA) on 2026-07-03: each cited ID and control title was read from the AICM sheet itself (e.g. **DSP-17** "Sensitive Data Protection", domain *Data Security and Privacy Lifecycle Management*; **LOG-15** "Input Monitoring", domain *Logging and Monitoring*). Only control IDs, titles, and domain/tag labels are reproduced here, with attribution — the control-specification text belongs to CSA; download the AICM from the CSA artifact page for the full control language. The choice of *which* AICM control maps to which Microsoft capability is this repository's synthesis, informed by AICM's own threat-category tagging (the cited DSP controls carry AICM's "Sensitive data disclosure" tag; the cited LOG controls carry its monitoring/"Model manipulation"-relevant tags).

## NIST AI 600-1 context for the cited risks

- **2.4 Data Privacy** — includes "Impacts due to leakage and unauthorized use, disclosure, or de-anonymization of … personally identifiable information or sensitive data" (NIST AI 600-1, Section 2 risk list; verified 2026-07-03).
- **2.9 Information Security** — GAI "expands the available attack surface, as GAI itself is vulnerable to attacks like prompt injection or data poisoning" (NIST AI 600-1, §2.9; verified 2026-07-03).

## Verification method

- OWASP item numbers verified against the OWASP GenAI Security Project's published 2025 list on **2026-08-07** (LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM03 Supply Chain read directly from `genai.owasp.org/llm-top-10`); re-confirm at each refresh.
- MITRE ATLAS technique IDs and names verified against MITRE's published `atlas-data` dataset on **2026-08-07** — dataset `version: 5.6.0`, with `AML.T0051` "LLM Prompt Injection" (sub-techniques `.000` Direct, `.001` Indirect) and `AML.T0057` "LLM Data Leakage" read from the distributed `ATLAS.yaml`. The live technique pages on `atlas.mitre.org` use the `/techniques/<ID>` paths cited above.
- NIST AI 600-1 verified against the official PDF fetched from nvlpubs.nist.gov (full text) on 2026-07-03; the published document is static and its availability was re-confirmed on **2026-08-07**.
- CSA AICM verified two ways on **2026-07-03** (not re-verified since): version, scope, and availability against the CSA artifact page; item-level control IDs, titles, domains, and the 247/18 counts directly against the official AICM v1.1.0 spreadsheet. This row is a human-only source — see the note under the framework-versions table.
