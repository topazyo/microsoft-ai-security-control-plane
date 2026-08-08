# Automated Refresh Cadence

How the monthly refresh committed to in the README's **Maintenance & cadence**
section is actually executed, and what the automation is and is not allowed to do.

The README states the rule: *"Monthly refresh against the Microsoft Learn 'What's
new' pages and the Message Center. Every refresh is recorded in CHANGELOG.md
(date, rows touched, status changes). Any row older than the monthly window is
treated as stale."* This document describes the machinery that carries it out.

## The problem the design solves

Two facts about this repository shape everything below.

**Retrieval is cheap; judgement is expensive and risky.** The complete watch
surface is four pinned sources (`.github/watch-state/sources.json`) covering all
matrix rows. Fetching them costs seconds and no tokens. What costs tokens — and
what can go wrong — is deciding what a change *means*. A fabricated status change
carrying a plausible-looking URL would destroy the repository's entire premise,
which is that status is verified rather than asserted.

**Real status changes are rare.** The 2026-07-14 refresh re-verified every row
and every status held. Documentation pages of this kind move on a monthly-to-
quarterly rhythm. Any design that invokes a model daily is therefore paying full
false-positive risk for almost no true positives.

So detection and judgement are put on different clocks: detection runs daily and
contains no model at all; judgement runs about fifteen times a year and only when
detection has already found something.

## The four tiers

| Tier | Trigger | Engine | Writes | Never writes |
|---|---|---|---|---|
| **D1 detect** | daily, `17 6 * * *` | deterministic Python, **no model** | fingerprint baseline, evidence bundle | any content file; any status label |
| **D2 adjudicate** | **event** — only when D1 reports a change | model, **no network** | draft PR touching matrix rows and the month's CHANGELOG bullet | anything outside the path allowlist |
| **D3 monthly** | monthly, `23 6 6 * *` | model, **no network** | last-verified stamps, the month's CHANGELOG heading, checklist footer stamp | prose inside `docs/` and checklist items (flagged for humans instead) |
| **D4 stale guard** | weekly, `41 8 * * 1` | deterministic Python, **no model** | a GitHub issue | any content file |

D1 and D2 share `.github/workflows/source-watch.yml` as two jobs with separate
permissions. They are separate tiers; they are co-located because a workflow
dispatched by `GITHUB_TOKEN` does not reliably start another workflow, and a
conditional job is the dependable way to keep judgement event-gated.

## Separating gathering from deciding

The layer that touches the outside world cannot form a judgement, and the layer
that forms judgements cannot touch the outside world.

- `scripts/watch_sources.py` fetches and fingerprints. It is ordinary code, so it
  cannot invent a status no matter how it fails.
- `.claude/agents/evidence-analyst.md` reads evidence and reports verbatim
  quotes. It may not assign a label or edit a file.
- `.claude/agents/status-adjudicator.md` assigns labels and is the only agent
  permitted to change a row. It has no network tools and may cite only URLs the
  watcher actually fetched.
- `scripts/validate_bot_pr.py` gates the result deterministically.

This separation is worth its complexity at four rows because it converts prose
rules into mechanical invariants. "Never cite a source you did not read" is
unenforceable as an instruction and trivially enforceable as a set-membership
test: every primary-source URL in the matrix must appear in the evidence bundle's
`allowed_citation_urls`, or CI fails.

## What the detector actually compares

Fingerprinting a whole rendered page produces a false positive nearly every run —
navigation, feedback widgets and per-render tokens all change independently of
the documentation. The watcher instead extracts **status signals** and
fingerprints those: section headings, which headings carry a `(preview)`
qualifier, and which status-bearing phrases are present.

Broad release-notes pages need a further narrowing. The Defender for Cloud
release notes carry seventy-five headings for products outside this repository's
scope; the `relevance_filter` in `sources.json` reduces that to the AI-related
entries, so the detector does not escalate for Kubernetes and SQL notes that
cannot affect any row.

## Direction of change decides what automation may do

| Transition | Automation may |
|---|---|
| Anything → **Requires further validation**, or adding a caveat | open a pull request |
| **Public Preview → GA** | open a pull request, with the qualifier removal quoted |
| **Requires further validation → anything else** | **open an issue only — never a pull request** |

The last row follows from `docs/how-to-read-status.md`: a row leaves that state
only when primary sources converge **and** the behaviour is confirmed in a real
tenant. Automation cannot confirm anything in a tenant, so it can never satisfy
the exit condition. It raises
`.github/ISSUE_TEMPLATE/tenant-verification.md` instead, and
`scripts/validate_bot_pr.py` fails any pull request that attempts the transition.

**No tier merges anything.** Every automated change arrives as a draft pull
request for human approval.

## Failure behaviour

The governing rule is that **absence of evidence never mutates a row**. When a
source cannot be fetched, the watcher records `ok: false`, preserves the previous
baseline, reports no change, and the adjudicator leaves that row's last-verified
date alone. The row then ages naturally into the staleness window, where the
stale guard raises it. A fetch failure routes into the repository's own staleness
rule rather than needing separate error handling, and one unreachable source
degrades exactly one evidence item.

## What automation is forbidden to touch

**The Microsoft 365 Message Center is never fetched.** Message Center posts are
tenant-scoped and have no public URL. Reading them would require a tenant
credential in repository secrets and would introduce tenant-scoped data, which
`disclaimer.md` and the README's confidentiality note forbid. The README's cadence
rule names the Message Center, and that part of the rule remains a human step —
recorded in `checklists/capability-status-verification.md`, Group 9. Cite the MC
ID; never the content.

**The CSA AICM control IDs are never fetched.** They are published only inside a
registration-gated spreadsheet, so cross-walk mappings against AICM must be
re-verified by a human.

Both exclusions are recorded as `human_only_sources` in `sources.json`, with
their reasons, so that a future maintainer does not "fix" them by adding a
credential.

## CHANGELOG discipline

The unit is **one heading per calendar month**, not one per run. Tiered cadences
run far more often than they change anything, and a heading per run would bury
the signal under "checked, nothing changed" entries. D1 and D4 never write to
`CHANGELOG.md` at all; D2 appends a bullet under the current month's heading, and
D3 creates that heading. `scripts/changelog_entry.py` enforces this.

D3 writes an entry even when nothing changed. That matches the existing
2026-07-14 entry, which records that every status held — and it guarantees
monthly repository activity, which matters because GitHub disables scheduled
workflows after roughly sixty days of inactivity. A quiet reference repository
whose automation never commits can silently switch its own schedule off.

## Secrets

Only `ANTHROPIC_API_KEY` is used, and only by the two model tiers. D1 and D4 hold
no secret at all, so the large majority of scheduled runs never touch one.
Workflows use `pull_request`, never `pull_request_target`, so fork pull requests
never receive secrets. Each job declares least-privilege `permissions`; the
top-level default is `permissions: {}`.

`anthropics/claude-code-action` is pinned to a commit SHA rather than the `v1`
tag, because a tag can be repointed at new code and that step holds both an API
key and write permissions. Upgrading is therefore a deliberate edit: resolve the
new tag to a SHA (`gh api repos/anthropics/claude-code-action/commits/v1 --jq .sha`)
and update both workflows together.

## Operating the cadence

```bash
python3 scripts/watch_sources.py                       # detect changes (read-only)
python3 scripts/watch_sources.py --update-baseline     # accept the current state as the baseline
python3 scripts/stale_guard.py                         # list rows past the staleness window
python3 scripts/validate_bot_pr.py --base-ref origin/main
python3 scripts/changelog_entry.py --bullet "..." --dry-run
```

Adding a capability row means adding its source to `sources.json` with the matrix
rows it backs. A source that is not in the registry is never fetched.
