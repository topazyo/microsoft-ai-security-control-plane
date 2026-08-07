# How to Read (and Verify) Capability Status

Microsoft AI-security capabilities sit at Generally Available, Public Preview, and Roadmap **simultaneously** — and the answer to "is this available?" is scattered across Microsoft Learn, the Message Center, the public Microsoft 365 Roadmap, and Tech Community posts that do not always agree. This guide defines the status labels used in this repository, shows where each one is sourced, and documents how matrix rows are verified.

## The four status labels

### GA (Generally Available)

The capability is fully released for applicable customers. Evidence looks like:

- A Microsoft Learn feature section **without** a "(preview)" qualifier in its heading or an availability table stating "Release state: Generally available (GA)".
- A Microsoft 365 Roadmap entry with status **"Launched"** — which the Roadmap defines as "fully released updates that are now generally available for applicable customers."
- A dated GA entry in the product's What's-new/release-notes page (e.g. "General Availability for Defender for AI Services — May 1, 2025" in the Defender for Cloud release-notes archive).

**GA still doesn't mean "on in your tenant."** Regional rollout, licensing, and configuration prerequisites all gate actual availability — verify in-tenant.

### Public Preview

Microsoft's primary sources label the capability preview. Evidence looks like:

- A "(preview)" qualifier on the Microsoft Learn section heading — e.g., as of 2026-07-03, "Block sensitive information types in prompts **(preview)**" on the Purview DLP for Copilot page.
- Learn wording such as "This feature is in preview and is rolling out to all tenants… Check whether rollout has reached your tenant."
- A Roadmap entry in "Rolling out" with a preview-availability date, or a release-note entry titled "(Preview)".

Treat previews as functionally and contractually different from GA: per the Microsoft Product Terms for Online Services, previews are provided "AS-IS," "WITH ALL FAULTS," and "AS AVAILABLE," and "are not included in the SLA for the corresponding Online Service." Some products document their own preview behavior (e.g. [Preview features in Microsoft Defender XDR](https://learn.microsoft.com/en-us/defender-xdr/preview)).

### Roadmap

Announced with a public Microsoft 365 Roadmap entry (status "In development"), but not yet rolling out. Cite the **Roadmap feature ID** and its URL — dates on roadmap entries move.

### Requires further validation

Used when Microsoft's own sources conflict, or when a status cannot be confirmed from primary sources alone. The typed-prompt SIT DLP sub-capability (matrix row 3) is the canonical example: Microsoft blog coverage and Microsoft Learn described its status differently, so this repository labels it rather than guesses. A row leaves this state only when primary sources converge **and** the behavior is confirmed in a real tenant.

## Where to source each status (the verification sources)

| Source | What it gives you | URL |
|---|---|---|
| Microsoft Learn product docs | The authoritative per-feature status (preview qualifiers, availability tables, config constraints) | e.g. [Purview DLP for M365 Copilot](https://learn.microsoft.com/en-us/purview/dlp-microsoft365-copilot-location-learn-about) · [Defender for Cloud AI threat protection](https://learn.microsoft.com/en-us/azure/defender-for-cloud/ai-threat-protection) |
| Learn "What's new" / release notes | Dated status-change entries (the evidence for GA/preview dates) | [Purview](https://learn.microsoft.com/en-us/purview/whats-new) · [Defender for Cloud](https://learn.microsoft.com/en-us/azure/defender-for-cloud/release-notes) ([archive](https://learn.microsoft.com/en-us/azure/defender-for-cloud/release-notes-archive)) · [Defender XDR](https://learn.microsoft.com/en-us/defender-xdr/whats-new) |
| Microsoft 365 Message Center | Tenant-targeted rollout communications (MC IDs, e.g. MC1263277) | [About the Message center](https://learn.microsoft.com/en-us/microsoft-365/admin/manage/message-center) — posts are tenant-scoped; cite the MC ID, not a URL |
| Public Microsoft 365 Roadmap | Public per-feature status (In development / Rolling out / Launched) with feature IDs | [microsoft.com/en-us/microsoft-365/roadmap](https://www.microsoft.com/en-us/microsoft-365/roadmap) — deep-link with `?id=<featureID>` |
| Tech Community / launch blogs | Context and announcements — **official-adjacent only, never the source of truth for status** | — |

**Message Center vs Roadmap:** Message Center posts (MC IDs) are visible only inside a tenant's admin center, so they cannot be publicly cited by URL. The public, linkable equivalent is the Microsoft 365 Roadmap feature ID — this repository cites Roadmap URLs and mentions MC IDs as tenant-side tracking references.

## How rows in this repository are verified

1. **Primary source per row.** Every matrix row carries a Microsoft Learn or public Roadmap URL. No row's status is ever sourced from a launch/marketing blog.
2. **Last-verified date per row.** The date the source was actually re-read — not the date the row was written. A row older than the monthly window is treated as stale.
3. **Exact-wording discipline.** Status is taken from the source's own qualifiers ("(preview)", "Release state: Generally available", Roadmap "Launched") — not inferred from tone or headlines.
4. **Conflicts are labelled, not resolved by assumption.** Conflicting sources ⇒ **Requires further validation**, plus a note quoting both sides with dates.
5. **In-tenant confirmation for contested or rollout-gated rows.** A Launched/GA label still gets a "confirm in your tenant" caveat where regional rollout applies.
6. **Monthly refresh, recorded.** Rows are re-verified monthly against the What's-new pages and Message Center; every status change lands in [`CHANGELOG.md`](../CHANGELOG.md) (date, rows touched, status changes).

## Worked example — why this discipline matters

"DLP for Microsoft 365 Copilot" is commonly discussed as one switch. The matrix's three DLP rows show what verification actually finds (as of 2026-07-03): sensitivity-label processing restriction — **GA**; external-web-search blocking on sensitive prompts — **GA only as of June CY2026** (Roadmap 548671 "Launched"); typed-prompt SIT blocking — **still "(preview)" on Learn and previously described otherwise in blog coverage**, so it is labelled Requires further validation. One feature name, three schedules, three different pieces of evidence — a coverage map that says "DLP covers Copilot: done" hides all three.
