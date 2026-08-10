---
name: Status correction
about: Report a matrix row whose status, date, or caveat is wrong or outdated
title: 'Status correction: row <N>'
labels: documentation
---

## Which row

- **Row number:**
- **Capability as currently stated:**
- **Status currently recorded:**

## What is wrong

- [ ] The status label is incorrect
- [ ] The last-verified date is stale and the source has since changed
- [ ] The caveat or scope boundary is wrong or missing
- [ ] The primary-source URL is dead, redirected, or no longer carries the claim

## What the status should be

- **Claimed correct status** (exactly one of GA / Public Preview / Roadmap /
  Requires further validation):
- **Primary-source URL:**
- **Date you read that source (YYYY-MM-DD):**

## Evidence (verbatim)

<!-- Paste the exact status-bearing sentence from the source as it reads today.
     If the page changed, quote both the old and the new wording if you have
     them. -->

> 

## If you are proposing to move a row OUT of "Requires further validation"

That transition is **not** made from documentation alone. It requires the
sources to have converged **and** the behavior to be confirmed in a real
tenant. Please state:

- [ ] Microsoft's sources now agree (quote them above — including the page
      *body*, not just a heading qualifier; a dropped "(preview)" qualifier
      beside an unchanged "this feature is in preview" sentence is exactly the
      conflict the label exists for)
- [ ] Behavior confirmed in a tenant

Describe the in-tenant confirmation **without** tenant-specific detail — no
organization name, tenant or subscription identifier, hostname, screenshot, or
license count. "Confirmed in a test tenant on <date>" is the right level.

## Confidentiality

- [ ] This report contains no tenant identifiers, GUIDs, hostnames, addresses,
      IP addresses, license counts, log excerpts, screenshots, or Message
      Center content.

If the correction can only be evidenced by private or NDA material, say so
without pasting it — the row stays **Requires further validation**, which is
the honest outcome.
