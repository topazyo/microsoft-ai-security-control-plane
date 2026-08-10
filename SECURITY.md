# Security Policy

## What this policy covers

This repository is documentation and a small set of standard-library Python
automation scripts. It ships no service, no runtime, and no product.

**In scope for a report here:**

- A vulnerability in the automation under `scripts/` or `.github/workflows/`
  (for example: a workflow that could leak a token, an injection path into a
  workflow step, an unpinned or hijackable action reference).
- A confidentiality failure in the repository content itself — any tenant
  identifier, GUID, hostname, IP address, license count, internal URL, log
  excerpt, Message Center content, or NDA / private-preview material that has
  been committed. See `.claude/rules/security.md` and `disclaimer.md`.
- A supply-chain concern about this repository's own dependencies or actions.

**Not in scope here — report these to Microsoft, not to this repository:**

- Any vulnerability in a Microsoft product, service, or Microsoft Learn page.
  Report those through the Microsoft Security Response Center at
  <https://msrc.microsoft.com/>.
- Any vulnerability in GitHub, OWASP, MITRE, NIST or CSA material. Use those
  organizations' own reporting channels.

A **wrong or outdated capability status** is not a security vulnerability —
open a status-correction issue instead (see
`.github/ISSUE_TEMPLATE/status-correction.md`). Status accuracy matters a great
deal here, but it is handled in the open.

## How to report

Use **GitHub private vulnerability reporting**: go to the repository's
**Security** tab and choose **Report a vulnerability**. That channel is private
until a fix is published.

Please do not open a public issue for a suspected confidentiality failure —
that would amplify the exposure. Report it privately so the content can be
removed and, where the content is already public, so the history rewrite can be
planned deliberately.

Include: what you found, where (file and line, or workflow and step), why you
believe it is a problem, and — for a confidentiality report — whether you
believe the material is already public elsewhere.

## Response expectations

This is a single-maintainer project with no service-level commitment. Expect an
acknowledgement within a week. Confidentiality failures are triaged first,
because the repository's public claim (`README.md`, "Confidentiality note") is
that no such material is present.

## No secrets, ever

This repository contains no secrets, tokens, passwords, API keys, certificates,
or private keys, and none may be added — not in code, not in workflows, not in
examples, not in test fixtures. The automation deliberately runs on the
auto-provided `GITHUB_TOKEN` where it can.

Two mechanical notes for contributors:

- **No literal email address anywhere in a `.md` or `.json` file.** The
  confidentiality validator (`scripts/validate_bot_pr.py`) treats any address
  outside `example.*` as a possible tenant identifier and fails the build.
  Reference an organization by URL instead. This policy file follows its own
  rule — that is why MSRC appears above as a link.
- The validator scans only `.md` and `.json` files and never reads commit
  messages, so the confidentiality rules apply to commit messages by review,
  not by automation. Write every commit message to the same public-safe bar as
  the content.
