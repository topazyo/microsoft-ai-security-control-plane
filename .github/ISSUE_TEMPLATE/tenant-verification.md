---
name: In-tenant verification required
about: A row cannot be resolved from primary sources alone and needs confirmation in a real tenant
title: 'Tenant verification: <capability>'
labels: tenant-verification-required
---

## Why this is here

A row is marked **Requires further validation**, or an automated run found
evidence that would change such a row. Per `docs/how-to-read-status.md`, a row
leaves that state only when primary sources converge **and** the behaviour is
confirmed in a real tenant. No automated run can confirm anything in a tenant, so
this step is always human.

Automated runs may raise this issue. They may not change the row.

## Row

- Matrix row number and capability:
- Current status label:
- Proposed status label (if any):

## Primary-source evidence

Quote the source verbatim — headings with or without a `(preview)` qualifier,
availability-table values, Roadmap status. Paraphrase is not evidence.

- Source URL (Microsoft Learn or public Microsoft 365 Roadmap only):
- Quoted wording:
- Do Microsoft's own sources agree with each other? If not, quote both sides.

## Tenant checks to perform

- [ ] Feature is present in the admin experience described by Learn.
- [ ] Behaviour matches the documented behaviour, including its caveats.
- [ ] Licensing and role prerequisites confirmed.
- [ ] Regional or rollout gating noted, if any.
- [ ] Message Center checked for a related MC ID (record the ID only — Message
      Center content is tenant-scoped and must never be pasted into this
      repository).

## Before closing

- [ ] The matrix row carries a primary-source URL and a new last-verified date.
- [ ] The status label is one of the four legend labels.
- [ ] The change is recorded under this month's `CHANGELOG.md` heading.
- [ ] **No tenant-specific data was added to the repository** — no GUIDs,
      tenant or subscription identifiers, hostnames, user names, email
      addresses, screenshots, or Message Center text.
