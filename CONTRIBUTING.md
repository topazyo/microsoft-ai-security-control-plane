# Contributing

This repository's entire value is **verified, dated capability status**. Status
accuracy is itself the control. A row that looks right but was never checked
against a primary source is worse than no row, because it will be trusted.

Everything below follows from that.

## The contribution rule

Every proposed or changed capability row must carry:

1. A **primary-source URL** — Microsoft Learn or the public Microsoft 365
   Roadmap. Nothing else is a source of truth for status. Tech Community and
   launch blogs are official-adjacent context only, never the citation.
2. A **last-verified date** — the date you actually re-read the source, not the
   date you edited the file.
3. A **status label from the legend**, exactly: `GA`, `Public Preview`,
   `Roadmap`, or `Requires further validation`.
4. **Public, synthetic-only content.** No tenant-specific anything.

If Microsoft's own sources disagree with each other, the row is
**Requires further validation**. Do not resolve the conflict by judgement, and
do not pick the more recent page — record the conflict.

A row **never leaves** `Requires further validation` on documentation alone.
That transition needs in-tenant confirmation by a human, and the validator
enforces the direction for automated changes (see
`docs/how-to-read-status.md`).

## Atomic row pull requests

The citation-containment check hard-fails any pull request whose matrix cites
an allowed-host URL that is not already a registered source. So a row cannot be
split across pull requests. **One row = one pull request containing all of:**

1. The table row.
2. The `### Row N — …` details section, including at least one **verbatim
   status-bearing quote** from the source.
3. A `.github/watch-state/sources.json` entry for **every** allowed-host URL
   the row and its details section cite, with `cite_url` exactly equal to the
   cited URL. A Roadmap-status row also needs a roadmap-mode entry whose `url`
   is the release-communications **collection** endpoint and whose `feature_id`
   selects the feature.
4. The refreshed watcher baseline (see below).
5. The matrix heading's row count, **re-derived by counting the table** rather
   than incremented.
6. Removal of the capability from the "Planned rows" list.

### Refreshing the baseline without destroying detection state

`--update-baseline` rewrites the fingerprint for **every** registered source,
not just yours. Done carelessly, your row pull request silently swallows a real
pending status change to somebody else's source. So:

```
# 1. Plain run first -- writes nothing, detects only.
python scripts/watch_sources.py
```

If that prints `[changed]` for a source you did not add, **stop**. That is a
real undetected upstream change; let the daily watcher handle it, or record it
explicitly. Only once it reports no status-relevant change:

```
# 2. Now baseline, capturing stderr -- [warn] lines go to stderr, not stdout.
python scripts/watch_sources.py --update-baseline --evidence-out evidence.json 2>&1 | tee baseline-run.log
```

Then check all four: no `[warn]` in the log; `"failed_sources": []` in
`evidence.json`; every new id in the committed `fingerprints.json` has
`"ok": true` and a non-empty `"fingerprint"`; and the diff touches only your
new ids. **The exit code proves nothing** — the watcher exits 0 on fetch
failure by design.

### Stacked branches, never parallel

Row pull requests all touch the same few lines — the matrix heading, the table,
the Planned-rows list, the sources array, the baseline file. Two row branches
cut from the same base will conflict, and two of those collisions are *silent*:
both making the identical "5 rows" → "6 rows" heading edit merges cleanly while
seven rows exist, and two rows both numbered `6` produce duplicate identifiers
that the validators silently collapse.

So stack them:

```
git switch -c feat/row-6-dspm-licensing main
# ... open its PR against main ...
git switch -c feat/row-7-dspm-posture feat/row-6-dspm-licensing
gh pr create --base feat/row-6-dspm-licensing
```

GitHub retargets each child automatically when its parent merges. One pull
request with a commit per row is also fine.

## Running the validators locally

```
python -m compileall -q scripts
python scripts/validate_bot_pr.py --base-ref origin/main
python scripts/stale_guard.py
```

All three must pass before you mark a pull request ready. **`stale_guard.py` is
expected to report zero stale items.** Any stale item is a finding to act on,
not a known exception to scroll past. This instruction previously told you to
expect exactly one — the CSA AICM framework row — which stopped being true on
2026-08-10 when that row was re-verified against the workbook. A checklist that
teaches you to normalise one stale item teaches you to miss the second.

Note that the guard's own output is **not** enforced by any CI check: the
`Validate matrix` workflow pipes it into the run summary with `|| true`, so it
can never fail a build. Paste the output into the pull request instead of
inferring it from a green check.

**The CI workflow does not trigger on every path.** `Validate matrix` runs on
changes under `matrix/`, `crosswalk/`, `checklists/`, `scripts/`,
`.github/workflows/`, `.github/watch-state/`, `CHANGELOG.md`, and the
documentation paths listed in the workflow. If your pull request touches only
paths outside that list, the check will not appear at all — paste your local
validator output into the pull request body instead. **Never report an absent
check as a green one.**

## Two mechanical traps worth knowing before you write

Both are hard CI failures, and both are easy to hit while writing something
perfectly reasonable:

- **No literal email address in any `.md` or `.json` file.** The
  confidentiality regex exempts only `example.*` and cannot tell a public
  support address from a tenant identifier. Reference organizations by URL.
- **No detection-query content.** A fenced code block tagged `kql` or `kusto`,
  or a line beginning with a hunting table name followed by a pipe, trips the
  out-of-scope check. Name hunting tables in prose or inside a markdown table
  cell. Runnable detections are out of scope by design and belong in a separate
  detection-pack repository.

Also avoid **four-component version numbers** in content files — the
confidentiality check reads any four dot-separated number groups as an IP
address, and its "that's a version string, not an IP" guard never fires. Three
components are fine. (Writing an example of one here would fail the build; that
is how the guard was confirmed dead.)

## How the automated cadence interacts with human pull requests

A tiered automation watches the pinned sources daily, consolidates monthly, and
raises staleness weekly. See `docs/agent-cadence.md`. Two rules matter to you:

- **No automated run ever merges its own pull request.** Every bot change is a
  draft for human review, and reviewing one means checking that each cited URL
  was actually fetched in that run's evidence bundle — a citation the watcher
  did not fetch is not evidence, however plausible the URL looks.
- **A last-verified date advances only for a source that was actually fetched
  successfully.** A source that could not be reached keeps its old date and is
  allowed to age into the staleness window. Never advance a date to silence a
  stale-guard finding.

## Branch naming

`feat/<description>` · `fix/<description>` · `sec/<description>` ·
`chore/<description>`

## Confidentiality

This repository is public and built entirely from public primary sources and a
synthetic/lab environment. Never add organization names, tenant, directory,
workspace or subscription identifiers, hostnames, user names, email addresses,
internal URLs, IP addresses, log excerpts, screenshots, license counts, or NDA
and private-preview material — **in files or in commit messages**. The
validator mechanically checks only four of those categories and never reads
commit messages, so the rest is on review.

If something can only be verified against a private tenant or an NDA source,
mark the row **Requires further validation** rather than including the private
detail. Full text: `disclaimer.md`.

## Reporting a security or confidentiality problem

See `SECURITY.md`. Do not open a public issue for a suspected confidentiality
failure.
