# Security policy

ProofStack analyzes untrusted code and produces source-sensitive evidence. We appreciate
careful, coordinated vulnerability reports.

## Supported version

The current `0.1.x` development line receives security fixes. Until the project publishes a
stable release policy, users should run the newest available `0.1.x` revision and review
release notes before exposing a deployment to a network.

## Reporting a vulnerability

Use the repository hosting service's private vulnerability-reporting feature under the
**Security** tab. If that feature is unavailable, contact a listed project maintainer through
a private channel and ask for a secure reporting path. Do not open a public issue containing
exploit details, credentials, affected tenant data, or a proof of concept.

Include, when possible:

- affected version and deployment mode;
- clear impact and trust-boundary assumptions;
- minimal reproduction steps using synthetic data;
- relevant logs after removing tokens and source-sensitive content;
- whether archive traversal, command execution, tenant isolation, redaction, or evidence
  integrity is involved; and
- a suggested remediation or patch, if available.

Never include a real credential. If one was exposed, revoke it before reporting and replace it
with a masked synthetic value.

## Response process

Maintainers will acknowledge a complete report as soon as practical, reproduce it privately,
assess severity and affected versions, prepare regression coverage and a fix, and coordinate
disclosure. Timelines depend on impact and project availability; reporters will receive a
status update when the assessment materially changes.

## Security boundaries

The native validation runner is not an operating-system sandbox. Running tests or builds from
an untrusted repository can execute code with the current user's authority. The optional
container runner is defense in depth, not a VM boundary. ProofStack does not mount the Docker
Socket or enable privileged containers by default.

Before deployment, read the [threat model](docs/security/threat-model.md),
[sandbox guidance](docs/security/sandboxing.md), and
[secret handling guide](docs/security/secret-handling.md). Operators remain responsible for
TLS, ingress, host hardening, secret injection, storage encryption, backups, retention,
monitoring, and dependency patching.

## Out of scope

Reports that only restate a documented limitation without demonstrating a boundary violation,
automated scanner output without a reproducible impact, denial of service that ignores the
documented deployment limits, and attacks requiring prior full host administrator access may
not receive a security advisory. Maintainers still welcome practical hardening suggestions.
