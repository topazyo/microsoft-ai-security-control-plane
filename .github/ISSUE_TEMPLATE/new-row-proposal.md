---
name: New capability row proposal
about: Propose a new row for the capability-status matrix
title: 'New row: <capability name>'
labels: enhancement
---

## Capability

<!-- One capability, one row. If what you are describing shipped as several
     sub-capabilities on different schedules, propose one row per schedule --
     that split is the whole point of this matrix. -->

- **Capability:**
- **Microsoft product:**
- **AI risk class:** <!-- prompt injection (direct/indirect), sensitive-data
     leakage, shadow AI, agentic/MCP blast radius, AI supply chain / model risk -->

## Proposed status

- **Status label** (exactly one of the four):
  - [ ] GA
  - [ ] Public Preview
  - [ ] Roadmap
  - [ ] Requires further validation
- **Primary-source URL:**
- **Date you read that source (YYYY-MM-DD):**

**Allowed source hosts:** Microsoft Learn (`learn.microsoft.com`), the public
Microsoft 365 Roadmap (`microsoft.com/.../microsoft-365/roadmap`), or GitHub Docs
(`docs.github.com`) for a GitHub capability. These are the three hosts
`ALLOWED_SOURCE_HOSTS` in `scripts/validate_bot_pr.py` accepts; anything else
fails the validator. GitHub Docs carries one extra condition, because it is the
first-party documentation for a Microsoft-owned product rather than a relaxation
toward blogs: such a source is registered under `human_only_sources` in
`.github/watch-state/sources.json`, never under `sources`, so no automated run
fetches it and its row's date moves only when a human re-reads it. A launch blog
or Tech Community post is not a source of truth for status, and a Message Center
post has no public URL — cite the Roadmap feature ID and mention the MC ID as a
tenant-side reference only.

## Status-bearing evidence (verbatim)

<!-- Paste the exact sentence(s) that carry the status. This is what makes the
     row verifiable. A paraphrase is not evidence. -->

> 

**If Microsoft's own sources disagree with each other, propose
`Requires further validation` and quote both sides with dates.** Do not resolve
the conflict — recording it is the contribution.

## Scope boundaries and caveats

<!-- What does this control NOT cover? Licensing prerequisites (SKU/plan names
     only, never seat counts)? Platform limits? Rollout gating? The most
     valuable rows here are the ones that prevent a coverage-map error. -->

## Before you open the pull request

A row cannot be split across pull requests — the citation-containment check
fails any matrix that cites an unregistered URL. See `CONTRIBUTING.md`; the
pull request must carry the row, its details section, the `sources.json`
entries for every cited allowed-host URL, and the refreshed watcher baseline,
in one diff.

- [ ] Content is public and synthetic-only — no tenant identifiers, GUIDs,
      hostnames, addresses, license counts, or Message Center content.
