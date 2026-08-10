# Scope and Out of Scope

This expands the README's scope summary. It exists so that "why isn't X here?"
has a written answer, and so that scope drift is a visible decision rather than
an accident.

## In scope

**One row per Microsoft AI-security capability**, across Microsoft Entra,
Microsoft Purview, Microsoft Defender XDR / Defender for Cloud, Microsoft
Sentinel, and GitHub — each carrying a release status, a primary-source URL,
and the date that status was last verified against that source.

**An item-level framework cross-walk** (OWASP Top 10 for LLM Applications,
MITRE ATLAS, NIST AI 600-1, CSA AICM), mapped at item level — specific
framework item IDs — never category-to-product. It is the author's
interpretive synthesis and is versioned as such.

**A practitioner verification checklist** and a guide to reading and sourcing
status.

**Documented gaps.** Where no delivered control exists, that is recorded as a
gap rather than forced into a status label. The four-label legend describes
*capabilities that exist*; it has no honest label for "nothing ships here."

## Out of scope, and where each belongs instead

### Runnable detections and hunting queries

No queries, no rule logic, no schema-dependent field lists. This is enforced
mechanically: a fenced code block tagged `kql` or `kusto` fails CI.

*Why:* detection content has a different lifecycle, a different review
standard, and a hard dependency on schemas that must be confirmed in a real
workspace. A stale query is a false sense of coverage; a stale status row is at
least dated. *Where instead:* a separate Sentinel detection-pack repository.

Naming a hunting table in prose to say "coverage lives here" is in scope.
Publishing the query is not.

### Tenant-specific or non-public configuration

No organization names, tenant, directory, workspace or subscription
identifiers, hostnames, internal URLs, IP addresses, user names, addresses, log
excerpts, screenshots, or license counts.

*Why:* this repository is public and asserts publicly that it contains none of
these. *Where instead:* nowhere — where a claim can only be verified against a
private tenant, the row is marked **Requires further validation** and the
private detail is simply not included. Licensing prerequisites are recorded as
SKU or plan **names** as Microsoft Learn states them, never as counts or
entitlement state.

### Secure-SDLC / DevSecOps depth

Beyond GitHub Copilot policy and MCP governance, v0.1 carries no
AI-generated-code review gates, dependency or slopsquatting analysis,
secret-leakage tooling, or CI/CD guardrail content.

*Why:* it is a different discipline with a different audience, and doing it
shallowly would dilute the one thing this repository does well. *Where
instead:* a candidate for a later, separate contribution.

### Anything not backed by a public primary source

No NDA material, no private-preview-program content, no "a Microsoft contact
said." Launch blogs and Tech Community posts are official-adjacent context, not
status sources — enforced mechanically by the allowed-source-host check.

*Why:* the repository's only claim is that every status is verifiable by the
reader following the same link. *Where instead:* if it matters and cannot be
publicly cited, the row is **Requires further validation** with the conflict or
gap recorded.

### Vendor comparisons, marketing figures as fact, and screenshots

*Why:* comparisons age badly and invite advocacy; marketing figures are not
primary sources; screenshots leak tenant detail and cannot be diffed or
re-verified. *Where instead:* cite the current Microsoft Learn figure with a
last-verified date.

### Architecture recommendations and product selection advice

The matrix reports what exists and at what status. It does not tell you what to
deploy — that depends on tenant, licensing, and risk appetite this repository
cannot see.

## The boundary that matters most

The scope rules above are conveniences. This one is the product:

**A status is never asserted without a primary source read on the recorded
date, and conflicting sources are labelled rather than resolved.**

Anything that erodes that — a plausible status filled in from memory, a date
advanced without a re-read, a conflict quietly settled in favour of the newer
page — is out of scope no matter which folder it lands in.
