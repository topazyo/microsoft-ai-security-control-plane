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
surface is **22 watched sources** (`.github/watch-state/sources.json`), plus
**11 human-only sources** that no workflow may fetch, against **13 matrix rows**.
Those numbers are re-derived from the registry and the matrix by
`check_doc_counts` in `scripts/validate_bot_pr.py`, and CI fails when this
sentence drifts from them. It previously carried a written instruction to
re-derive the count by hand instead — the instruction was correct, was followed,
and the figure still sat seven short for a release, which is why the instruction
is now a test.

**The watch surface does not cover every matrix row.** The sentence above used to
say it did. Matrix rows **12** and **13** — GitHub Copilot policy management and
MCP governance — are backed only by `docs.github.com` pages registered under
`human_only_sources`, and the NIST and CSA cross-walk rows only by a static PDF
and a registration-gated spreadsheet. **4 of the dated items** are therefore
permanently human-only: no agent run can ever advance them. That invariant is
load-bearing for reading `scripts/stale_guard.py` correctly — for those four,
stale means *a human is overdue*, not *the automation is failing* — and it is
enforced rather than asserted, by `check_source_coverage`, which fails CI if any
matrix row is claimed by no registry entry and prints the human-only residue on
every run.

Fetching the watched sources costs seconds and no tokens. What costs tokens — and
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

`validate-matrix.yml` also lints the workflow definitions themselves with a
pinned `actionlint` image, and its path filter includes `.github/workflows/**`,
so a change that breaks the automation is caught by the automation.

This separation is worth its complexity even at **13 matrix rows** because it
converts prose rules into mechanical invariants. "Never cite a source you did not read" is
unenforceable as an instruction and trivially enforceable as a set-membership
test: every primary-source URL in the matrix must appear in the evidence bundle's
`allowed_citation_urls`, or CI fails.

## What the detector actually compares

Fingerprinting a whole rendered page produces a false positive nearly every run —
navigation, feedback widgets and per-render tokens all change independently of
the documentation. The watcher instead extracts **status signals** and
fingerprints those: section headings **and the titles of collapsible reference
entries**, because a page may list every entry it documents as a `<details>`
disclosure and never as a heading; which of those titles carry a `(preview)`
qualifier; and which status-bearing phrases are present — reported for the
page's own page-level text and for its in-scope entries *separately*, since a
page-wide release-state banner and a per-entry label are different claims.

Broad release-notes pages need a further narrowing. The Defender for Cloud
release notes carry dozens of entries for products outside this repository's
scope — 84 of 86 headings when measured on 2026-09-09 — so the
`relevance_filter` in `sources.json` reduces the watched signal to the AI-related
entries. That measurement is dated deliberately and is not maintained as a
standing figure: a live page's heading count drifts continuously, and a number in
prose that nobody re-derives becomes a false claim just by sitting still. This
paragraph used to assert "seventy-five" for the same reason.

**The filter scopes the page text, not only the heading list** — and that
distinction is the entire value of the filter. `apply_relevance_filter` narrows
the headings; `relevance_scoped_text` narrows the text the status phrases are
counted over, to the matching sections, everything nested under them, and the
page-level text — what precedes the first heading, plus the document title's own
section. All three rules are deliberate. A matching entry owns its `### Details`
subsection, whose own heading mentions nothing. A page-wide release-state banner
belongs to no entry at all, so no per-entry pattern can be expected to claim it,
and dropping it would lose real signal: the notice that all Sentinel data
connectors "are currently in Preview" is one half of matrix row 9's documented
conflict. And page-level text is kept **without conferring scope on what nests
under it** — treating the title as an in-scope *ancestor* would make every
section on the page inherit it and restore precisely the unfiltered behaviour
being removed.

**That banner justification did not hold when it was written, and issue #31 is
the record.** The rule was sound and reached nothing. The notice it cites stands
above the first *authored* heading but below Learn's navigation heading, and
section extraction used to split on headings before removing chrome — so an
`<h2>In this article</h2>` sitting inside a `<nav>` owned the article's lead-in on
every one of this repository's html sources, and what the rule actually kept was
the breadcrumbs. The ordering is fixed and the rule now reaches the thing it was
always justified by. A stated rationale the code cannot exhibit is worse than no
rationale, which is the defect that issue filed.

**Page-level is positional, not a heading level.** Only the first heading is the
title. Read as "any heading at level 1", the rule handed page-level standing to a
mis-authored `<h1>NOTE - UPDATE:</h1>` buried inside one Sentinel connector
entry, which held 31% of that 1.7 MB page permanently in scope — on the single
source whose whole reason for declaring a filter is that an unfiltered
fingerprint of it would move on nearly every run. A stray heading deep in a
document belongs to whatever entry contains it, whatever level it is marked up
at.

**And not every entry title is a heading.** The Sentinel connectors reference
lists each of its ~430 connectors as a `<details>`/`<summary>` disclosure, so a
heading filter had nothing there to match — 0 of 47 headings — while the page
plainly carried both the entry row 9 tracks and the per-entry "(Preview)" suffix
the matrix quotes as evidence for that row. A collapsible entry is now a section
in its own right, below `<h4>` so that it always nests under the heading above it
and can never be mistaken for the document title. Learn's own furniture is built
from `<details class="popover">` — breadcrumb overflow, page actions, the "Was
this page helpful?" widget — and is excluded by that class. The direction of
failure decided the shape of that exclusion: if Learn renames the class, a shell
label turns up in a heading list, which is visible noise that re-baselines once,
whereas an allow-list that stopped matching would drop real entries silently —
and a watched signal that goes quiet is indistinguishable from "nothing changed"
for as long as nobody re-derives it.

Before that second function existed, three of the four signal fields were scoped
and `status_phrases_present` was computed over the **whole page**. The result was
a fingerprint that looked filtered and was not: a *Classic Defender for SQL APIs
retirement* entry — a section the filter correctly rejected, since `\bAI\b` does
not match "APIs" — introduced the phrase `retired` on **2026-09-05**, and the
daily watcher re-reported it on five successive days while row 4's two in-scope
AI headings stayed byte-identical to baseline. The hole was symmetric, which is
the worse half: an out-of-scope phrase *disappearing* fired it just as readily,
and that escalation would have had no visible cause on the page at all.

Two consequences to know before reading a `[changed]` line:

- **The change note states its scope**, in one of three forms: `status phrase
  appeared in page-level text: 'retired'` and `... in in-scope entries: ...` for
  a filtered source, and `... in whole page: ...` for an unfiltered one. A line
  that cannot be attributed to a scope cannot be interpreted without re-fetching
  and re-reading the page, and a detector whose alarms cannot be interpreted
  trains its maintainer to stop reading them. That is the cost that mattered
  here, more than the wasted runs. For the same reason a `[changed]` line is
  never left without a note: where no reported field differs — which a signals
  *schema* addition does, since it moves every affected fingerprint while no
  measured value changed — the run says exactly that instead of printing a bare
  source id.
- **Scoping moved the fingerprint of the filtered sources only.** An unfiltered
  source's phrase set is still taken over its whole page text verbatim, so its
  stored fingerprint is untouched. Measured against the live sources on
  **2026-09-09**, **three** of the four filtered sources re-baseline —
  `defender-release-notes`, `defender-release-notes-archive` and
  `sentinel-data-connectors-reference`; `purview-service-description` is
  unaffected, because its phrase set is empty at either scope. Every phrase they
  lose was traced to the section holding it before this was shipped, and all of
  them sit under SQL, container, Kubernetes, multicloud or deprecated-connector
  headings. So the first run after this change reports three sources with a
  documented cause and no status meaning: run
  `python3 scripts/watch_sources.py --update-baseline` and record it in
  `CHANGELOG.md`, exactly as any adjudicated non-status change is recorded.

### When a filter matches nothing

Scoping the text correctly exposed a source that was watching almost nothing.
`sentinel-data-connectors-reference` declared
`["Copilot", "data connectors are currently in Preview"]` and matched **0 of the
page's 47 headings** — the connector entries on that page are not headings, so a
heading filter could not reach them, and the second pattern names body text that
a heading filter can never match at all. The source had *appeared* to be watching
something only because the phrase signal was taken over the whole page; correct
the scope and the coverage that was never really there becomes visible.

**That warning is what surfaced issue #31, and the source it flagged is now
watched.** Collapsible entries are sections, so the filter reaches the two entry
titles row 9's published evidence rests on — **2 of that page's 437 titles**, as
measured on **2026-09-10**; the page-level notice is covered by the page-level
rule rather than by a pattern; and the filter no longer declares a pattern the
code could not match. As of that date **no source's filter collapses**, so this
warning fires on nothing — which is worth stating, because a section describing a
warning nobody has seen fire is otherwise indistinguishable from a warning that
is broken. The mechanism is left exactly as it was: it did what it was built to
do, and it is the only reason anyone looked at this source at all.

### The decision this took, and the two options that were not taken

Issue #31 escalated row 9's watch to a human as a design decision and named two
remedies. **(a) Add a body-scoped relevance mode**, so a filter could select
sections by content rather than by heading — the general fix, and the one that
would have made the registry's claim about the page-level notice true. **(b)
Accept that the page cannot usefully be watched**, move it to
`human_only_sources`, and stop implying row 9 has automated coverage — cheaper,
and honest.

Neither was taken, and the reason is that re-deriving the page refuted the
premise both rested on. The page *can* be watched. Three separable defects in
section extraction were preventing it: chrome headings owning the article
lead-in, page-level being read as a heading *level* rather than a position, and
collapsible entries not being sections at all. Fixing those three needs no new
registry key, no new mode, and no schema change, and it left the declared filter
matching exactly the two entry titles row 9's own quotes cite.

So (a) was declined as unnecessary — a body-scoped mode would have worked around
a heading extractor that was simply wrong about what a heading is on this page —
and (b) was declined because it would have been an honest answer to a false
premise: conceding a page is unwatchable is only honest once you have established
that it is. Recording this here rather than leaving it implied, because a design
decision that shows up only as an absence is the failure mode this document
argues against elsewhere; the issue itself carries the measurements.

The watcher says so. `filter_collapsed` flags any source whose declared
filter matches no heading, the run prints a `[warn]`, the evidence bundle
carries `collapsed_filter_sources`, and both the source watch and the monthly
refresh turn that list — with the narrower `coverage_warning_sources` beside
it, raised when a filtered source's page has no heading at page level — into a
`::warning::` annotation and a run-summary entry. The condition is deliberately
**not** a failure and
**not** a change: the fetch succeeded and the fingerprint is honest about what it
saw. What has gone is coverage — and a source watching only its preamble reports
"unchanged" forever, which is indistinguishable from a healthy one. That
indistinguishability is how the OWASP edition gap survived, so it is announced
rather than inferred. `collapsed_filter_sources` is kept separate from
`failed_sources` because the two need opposite responses: a failed fetch
recovers by itself on the next run, a collapsed filter never does.

Two limits on that announcement, stated because the difference decides who has
to act. Both channels are visible to whoever opens the run and neither notifies
anyone, so a collapsed filter is still found by somebody looking rather than by
being told. And the stale guard is not an automatic second net for it: because
the fetch succeeded, a refresh that advances the row's last-verified date keeps
that row out of the staleness window altogether, so withholding the advance is a
judgement someone has to make. What *is* mechanical is the committed baseline —
`CommittedBaselineInvariantTests` in `tests/test_watch_sources.py` fails the
build if a stored fingerprint shows a filtered source with no headings, so a
collapse cannot be quietly re-baselined into the new normal even though it can
be quietly present in a single day's run.

## What the cadence cannot find at all

The watched surface cannot be relied on for discovery — which is a weaker and
truer claim than "no watched source can ever surface a new capability", and the
difference is worth stating precisely because the registry refutes the stronger
form.

Most of the registry is per-capability pages, which can only ever report drift on
a row that **already exists**. The two framework sources watch an edition token,
not Microsoft's product surface at all.

**The release-notes and aggregate reference pages are a partial exception.** Their
`relevance_filter` is *topical*, not an enumeration of the entries existing rows
cite: `defender-release-notes` and its archive filter on `\bAI\b`, `\bFoundry\b`
and `artificial intelligence`, and `apply_relevance_filter` keeps every heading
matching one of those. So a brand-new AI entry on those pages is in scope, moves
`headings` and `heading_count`, and is reported as a change. The committed
baseline already holds in-scope headings for capabilities no matrix row cites —
AI posture management on GCP Vertex, the Data and AI security dashboard,
threat protection for AI agents. Saying those are "filtered out by construction"
would be false, and it was.

What is true is narrower, and it is still enough to make discovery a human step:

- **Coverage.** Defender for Cloud is the only product with a watched what's-new
  page. Nothing watches the Purview, Defender XDR, Defender for Cloud Apps,
  Entra or Sentinel equivalents, so a new capability announced there is invisible
  to every tier.
- **Interpretation.** A reported change is an instruction to re-adjudicate the
  rows that source backs. Nothing in the cadence turns an unrecognised heading
  into a row proposal, and the adjudicator's permitted writes do not include
  adding a row. A new entry therefore surfaces as "this source changed", and a
  human decides whether it means a new row.

**So the cadence can occasionally show you a capability you have no row for, and
it can never propose the row.** Treat the watched what's-new coverage as one
narrow product's early warning, not as discovery.

That gap is stated rather than closed, and the README and the matrix now say the
same thing rather than promising more: the automated half of the monthly refresh
covers **drift on existing rows**, and **discovery of new capabilities is a human
step** — the product "What's new" pages and the Message Center, checked at each
refresh under `checklists/capability-status-verification.md`, Group 9.

Registering a "what's new" source per product family was the alternative. It was
not chosen because every such source would escalate on entries for products
outside this repository's scope, and a discovery escalation needs human triage by
definition — nothing in tier D2 can decide that a capability deserves a row. It
would convert a known human step into an automated queue that a human still has
to empty, while adding the maintenance surface of five more relevance filters.
That trade is worth revisiting if the matrix grows enough that a human sweep
stops being credible; it is recorded here so the choice is visible rather than
implied by an absence.

The failure class is worth naming, because this repository has already paid for
it once. A registry that claims a coverage shape it does not have is exactly how
the OWASP LLM Top 10 2026 edition landed unnoticed. The remedy there was a new
extraction mode; the remedy here is an honest sentence in the README, plus
`check_source_coverage` failing CI if a row ever ships with no source at all.

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
`scripts/validate_bot_pr.py --bot` fails any **automated** change that attempts
the transition.

**Read that scoping precisely, because it is easy to overstate.** Two checks —
the path allowlist and the escalation direction — are hard failures only under
`--bot`, which the two automation workflows pass and the `Validate matrix`
pull-request gate does not. That asymmetry is deliberate: a human who has
completed the in-tenant verification may make exactly this change, and blocking
it would block the only legitimate route out of *Requires further validation*.
On a human pull request both conditions are therefore **reported for reviewer
attention, not blocked** — so the reviewer, not the gate, is what stops an
unearned transition. The same holds for the path allowlist: `matrix/`,
`crosswalk/`, `checklists/`, `CHANGELOG.md` and `.github/watch-state/` bound
what an *automated* run may touch, while ordinary maintenance of `scripts/`,
`docs/`, `tests/` and the workflows is expected from a human and only noted.

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

They are not the only entries in that array, and the others sit there for the
opposite kind of reason. The `docs.github.com` Copilot-policy and MCP pages are
perfectly fetchable; they are kept out of `sources` *precisely* so that no
non-Microsoft-Learn page content ever reaches the model tier. A `reason` is a
required key on every human-only entry for exactly this: "cannot be fetched" and
"must not be fetched" are indistinguishable from the outside and have opposite
remedies.

## CHANGELOG discipline

The unit is **one heading per calendar month**, not one per run. Tiered cadences
run far more often than they change anything, and a heading per run would bury
the signal under "checked, nothing changed" entries. D1 and D4 never write to
`CHANGELOG.md` at all; D2 appends a bullet under the current month's heading, and
D3 creates that heading. `scripts/changelog_entry.py` enforces this.

**One heading per calendar month, except across a release.** `find_month_heading`
matches a month's heading only if it carries the word *refresh*, which every
heading the script creates does and a released heading — `## [0.1.3] — …` — does
not. So automation can never append a bullet into a section that has already been
tagged and published: a post-tag bullet for the same month opens a fresh
`## [Unreleased] — <date> refresh` heading above the release instead. That is why
two headings for one calendar month legitimately coexist, and why the `refresh`
token must be kept out of a released heading.

D3 writes an entry even when nothing changed. That matches the existing
2026-07-14 entry, which records that every status held — and it guarantees
monthly repository activity, which matters because GitHub disables scheduled
workflows after roughly sixty days of inactivity. A quiet reference repository
whose automation never commits can silently switch its own schedule off.

## Secrets

> **Current status, as of 2026-08-10: `ANTHROPIC_API_KEY` is not configured in this
> repository** (`gh api repos/<owner>/<repo>/actions/secrets` returns
> `total_count: 0`). The consequence is specific and worth stating plainly rather
> than discovering later: **tiers D2 and D3 cannot run.** `claude-code-action`
> aborts with an environment-validation error when the key renders empty, so the
> adjudication path has never completed successfully. Tiers **D1 (daily detection)
> and D4 (weekly stale guard) are unaffected** — they hold no secret and run on the
> auto-provided `GITHUB_TOKEN`.
>
> A green scheduled `Source watch` run is therefore **not** evidence that
> adjudication works: when `detect` finds no change, the `Adjudicate` job is
> skipped entirely and the run is green regardless. To verify the path after
> provisioning the key, dispatch `Source watch` with `force_adjudication: true` and
> confirm the `Adjudicate` job itself is green.
>
> **Interim operating model: the model tiers are run locally by a human.** This is
> a deployment gap, not a design gap, and the cadence still functions — see
> "Running tiers D2 and D3 locally" below. The controls that make the automated
> path trustworthy live in `scripts/validate_bot_pr.py` and the `Validate matrix`
> gate, **not** in the workflow definitions, so a locally-produced pull request is
> checked identically: allowed source hosts, legend labels, last-verified dates,
> citation containment, the escalation-direction rule and the confidentiality scan
> all run on any pull request regardless of who or what opened it.

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
python3 -m unittest discover -s tests                  # signal-scoping, registry, gate and staleness tests
python3 scripts/watch_sources.py                       # detect changes (read-only)
python3 scripts/watch_sources.py --update-baseline     # accept the current state as the baseline
python3 scripts/stale_guard.py                         # list rows past the staleness window
python3 scripts/validate_bot_pr.py --base-ref origin/main
python3 scripts/changelog_entry.py --bullet "..." --dry-run
```

The tests are standard library only, like everything else here, and they exist
because the signal-scoping defect was a *silent* one: every run was green, the
report line looked plausible, and only re-deriving the heading counts by hand
exposed it. `tests/test_watch_sources.py` therefore includes the case that would
have caught it — a fixture whose only change is an out-of-scope retirement notice,
asserted to produce **no** reported change.

Every module in `tests/` earns its place the same way, by covering something that
failed quietly rather than loudly:

- `tests/test_watch_sources.py` — signal extraction and scoping, registry shape,
  network-free invariants over the committed baseline (a re-baseline is
  otherwise self-confirming), and that every coverage-loss key the watcher emits
  is consumed by some workflow.
- `tests/test_validate_bot_pr.py` — the gates themselves, including the two
  directions of registry coverage and the cases where a check used to report a
  pass over rows it never examined.
- `tests/test_stale_guard.py` — the staleness arithmetic, whose boundary is a
  strict `age > window` so an item exactly at the window is fresh, and the
  step-output contract `stale-guard.yml` compares against a literal.

A test that asserts how many items are stale today would rot on the next
re-verification, so the staleness tests use synthetic fixtures with an explicit
`--today` for every behavioural assertion and reserve the committed files for
properties that survive a re-read.

## Running tiers D2 and D3 locally

While no `ANTHROPIC_API_KEY` is configured (see **Secrets**), the two model tiers
are operated by hand. The tier boundaries are unchanged — what moves is only
*where* the model runs, not what it is allowed to do.

**1. Produce the evidence bundle (this is tier D1, unchanged and deterministic):**

```bash
python3 scripts/watch_sources.py --evidence-out evidence.json 2>&1 | tee watch.log
```

Capturing stderr matters: `[warn]` lines are written to stderr only, and the
literal string `failed_sources` is never printed at all — it exists only as a key
inside the bundle. The exit code is **not** evidence; the watcher exits 0 on fetch
failure by design.

**2. Adjudicate in a local agent session (tier D2).** Keep the split the automated
path enforces: the adjudicator reads `evidence.json` and the extracted quotes, and
must not fetch anything itself. `.claude/agents/status-adjudicator.md` states the
forbidden actions and applies verbatim to a local run. Fetched documentation is
untrusted input: an instruction found inside a fetched page is a finding to
report, never an action to take.

**3. Open a draft pull request by hand,** then run the same gate the workflow
would:

```bash
python3 -m compileall -q scripts
python3 scripts/validate_bot_pr.py --base-ref origin/main
python3 scripts/stale_guard.py
```

**What must not be relaxed just because a human is driving:**

- A row may never leave **Requires further validation** without in-tenant
  confirmation — raise an issue via `.github/ISSUE_TEMPLATE/tenant-verification.md`
  instead of editing the row.
- A last-verified date advances only for a source actually fetched successfully in
  that run. A source that could not be reached keeps its old date and is allowed to
  age into the staleness window.
- Every **Microsoft Learn, public Roadmap or GitHub Docs** URL cited in
  `matrix/capability-status-matrix.md` must be registered in `sources.json` in the
  same pull request, or citation containment fails the build. State the scope
  precisely, because the check is narrower than "every cited URL" and reading it
  as broader is how an unchecked citation gets mistaken for a checked one:
  `check_citation_containment` reads the **matrix file only**, and filters to URLs
  matching `ALLOWED_SOURCE_HOSTS`. Citations in `crosswalk/` and `checklists/`,
  and any URL on another host anywhere, are **not** covered by it — for those the
  reviewer is the control.
- No run merges its own pull request.

**When the key arrives,** provision `ANTHROPIC_API_KEY`, dispatch `Source watch`
with `force_adjudication: true`, confirm the `Adjudicate` job is green, and delete
the status note under **Secrets**.

Adding a capability row means adding its source to `sources.json` with the matrix
rows it backs — to `sources` if a workflow may fetch it, to `human_only_sources`
if it may not. As of `schema_version` 2 **both** arrays carry `matrix_rows`
(integers) and `crosswalk_rows` (strings), and both are validated:
`registry_problems` rejects an entry that declares neither and an id duplicated
across the two arrays, and `check_source_coverage` rejects both a matrix row
that no entry claims and a claim on a row the matrix does not contain. Before
that, coverage for the human-only half was recorded only in
prose inside each entry's `reason`, which is why rows 12 and 13 could sit
unwatched through a full release without anything being able to say so. A source
that is not in the registry is never fetched.

## Watching a framework edition

A framework source is the one kind that backs no matrix row, and it needs its own
handling in two ways.

**It needs its own extraction mode.** `extract_signals` fingerprints headings,
which headings carry a `(preview)` qualifier, and which of nine status phrases are
present. None of those changes when a framework publishes a new edition or bumps a
dataset version, so registering a framework source under `html` or `markdown`
would produce a source that reports "unchanged" forever — worse than not
registering it, because the registry would then claim coverage it does not have.
That blind spot is exactly how the OWASP LLM Top 10 2026 edition went unnoticed
here. `mode: "version"` instead regex-captures the version or edition tokens a
source publishes and fingerprints that set.

Three constraints, all enforced in code:

- **Captures are bounded, not trusted.** Whatever a framework publishes is stored
  verbatim in `fingerprints.json` and in the evidence bundle the adjudicator
  reads, so only short version-shaped tokens survive the shape guard. A
  four-component numeric version is rejected outright: it is indistinguishable
  from an IPv4 address to the confidentiality scan that reads this file.
- **A pattern that captures nothing is a failure, not a quiet success.** It
  records `ok: false`, which surfaces as a `[warn]` and a `failed_sources` entry,
  and the framework's row in the cross-walk then ages into the staleness window
  where the stale guard raises it. Note that chain: the stale guard reads dates
  out of content files, never watcher output.
- **`watch_only: true` keeps a framework source out of `allowed_citation_urls`.**
  Watching something must not enlarge what an automated run may claim. Framework
  sources back cross-walk rows, not matrix rows, so `matrix_rows` is omitted;
  `crosswalk_rows` names the cross-walk row a framework source backs, as that
  row's own name in the "Framework versions cited" table plus
  " framework-versions row". It is read, not decorative: `registry_problems` in
  `scripts/watch_sources.py` type-checks it and rejects an entry that declares
  neither key, `check_source_coverage` rejects a value that is not a row of that
  table, and `claimed_crosswalk_rows` is part of how the human-only-backed
  dated-item count is derived.

**Detection is not judgement, and here it is also not fast.** This tier reports
*that* an edition changed, never what it means — that stays tier D2 or a human.
And the OWASP entry watches a landing page that is known to lag its own
publication, so treat a change there as confirmation rather than the earliest
possible warning; the reason it is watched anyway is recorded in the entry's note.
While no `ANTHROPIC_API_KEY` is configured, a detected framework change produces a
green run with a warning annotation and a locally-queued adjudication, not a pull
request.
