<!-- Delete any section that does not apply. Keep the confidentiality section. -->

## What this changes

<!-- One or two sentences. If this adds or changes a capability row, say which
     row and which status. -->

## Status hygiene (any pull request touching a matrix row)

- [ ] Status label is exactly one of the four legend labels: **GA** /
      **Public Preview** / **Roadmap** / **Requires further validation**
- [ ] Primary-source URL is Microsoft Learn or the public Microsoft 365
      Roadmap — not a launch blog, not Tech Community, not a Message Center post
- [ ] Last-verified date is the date the source was **actually re-read**
- [ ] The details section carries at least one **verbatim status-bearing quote**
- [ ] Conflicting sources are recorded as **Requires further validation**, not
      resolved by judgement
- [ ] No row was moved **out** of *Requires further validation* without
      in-tenant confirmation by a human

## Atomic row pull request (see CONTRIBUTING.md)

- [ ] `sources.json` entry present for **every** allowed-host URL this row cites,
      with `cite_url` equal to the cited URL
- [ ] Plain `python scripts/watch_sources.py` run first showed no `[changed]`
      line for any **pre-existing** source
- [ ] Baseline refreshed with `--update-baseline --evidence-out evidence.json 2>&1`,
      and: no `[warn]` in the log, `"failed_sources": []`, every new id has
      `"ok": true` and a non-empty `"fingerprint"`, and the `fingerprints.json`
      diff touches only the new ids
- [ ] Matrix heading row count **re-derived by counting the table**
- [ ] Capability removed from the "Planned rows" list
- [ ] Branch is stacked on the preceding row branch, not cut from the same base

## Validators

- [ ] `python -m compileall -q scripts`
- [ ] `python scripts/validate_bot_pr.py --base-ref origin/main`
- [ ] `python scripts/stale_guard.py` (expect **zero** stale items — any stale
      item is a finding, not a known exception; no CI check enforces this, so
      paste the output rather than inferring it from a green run)
- [ ] `Validate matrix` is green **and actually ran** — if this pull request
      touches only paths outside the workflow's filter, the check will not
      appear; paste the local validator output below instead. An absent check
      is not a green check.

## Confidentiality (never delete this section)

The validator mechanically checks only four categories (GUID, email address,
IPv4, `onmicrosoft.com`) and only in `.md`/`.json` files, and it never reads
commit messages. The rest is on review:

- [ ] No organization names
- [ ] No license counts or tenant entitlement state — SKU/plan **names** only
- [ ] No tenant, directory, workspace or subscription identifiers
- [ ] No hostnames, internal URLs, or IP addresses
- [ ] No user names or email addresses (**no literal address in any `.md`/`.json`
      file — it fails the build**)
- [ ] No log excerpts or screenshots
- [ ] No NDA or private-preview-program material
- [ ] No Message Center content — MC ID only, as a tenant-side reference
- [ ] **Commit messages** meet the same bar as the content

## Scope

- [ ] No runnable detections or hunting queries (a fenced block tagged `kql` or
      `kusto` fails the build; runnable detections are out of scope by design)
- [ ] No DevSecOps/CI depth, vendor comparisons, or marketing figures as fact

## Human review

- [ ] Reviewed and merged by a **human**. No automated run merges its own pull
      request. For a bot pull request, every cited URL was confirmed present in
      that run's evidence bundle.
