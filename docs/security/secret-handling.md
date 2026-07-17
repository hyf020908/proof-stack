# Secret handling

ProofStack separates secret configuration from evidence data. GitHub and optional LLM keys
are server-side settings; they are never returned by public configuration or frontend APIs.
Production rejects the development signing secret.

## Detection and masking

The built-in scanner recognizes common cloud, GitHub, JWT, bearer, private-key, database URL,
assigned credential, dotenv, and high-entropy patterns. Obvious placeholders and synthetic
test values reduce noise. A finding stores a stable fingerprint, a masked preview, and a
one-way SHA-256, never the full matched value.

Known configured secrets are also passed into output redaction. Structured logs and runner
stdout/stderr use the same masking boundary and enforce length limits. Evidence generation
recursively redacts values and security tests inspect the complete bundle before it is made
downloadable.

## Operator practices

- Load credentials from an environment injection or secret manager, not a source file.
- Give a GitHub token read-only access to only the repositories it must inspect.
- Keep LLM integration disabled unless the data-processing boundary is approved.
- Never prefix browser variables with `VITE_` unless they are intentionally public.
- Restrict artifact storage and backups as source-sensitive data.
- Rotate a credential immediately if a finding indicates it entered history.
- Avoid putting tokens on command lines where process inspection or shell history can expose them.

Redaction is defense in depth, not permission to ingest unnecessary secrets. Minimize the
data first, then scan, redact, authorize, encrypt, retain briefly, and audit access.
