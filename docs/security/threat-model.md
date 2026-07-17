# Threat model

ProofStack handles attacker-controlled repositories, patches, archives, requirements, and
validation output. An authenticated user is not assumed to supply safe code. The system
protects the host, tenant boundary, credentials, and exported evidence; it does not claim to
make arbitrary native code safe.

| Threat | Boundary and mitigation | Residual risk |
| --- | --- | --- |
| Zip Slip and absolute paths | Canonical path validation rejects traversal and platform-specific absolute members | Parser defects require prompt patching |
| Compression bomb | Compressed and expanded byte, ratio, member-size, and file-count limits | Carefully distributed bombs still consume bounded resources |
| Archive symlink or special file | Symlink and non-regular entries are rejected | Filesystem behavior differs across platforms |
| Malicious repository | Clone timeout, file/byte limits, no hooks, bounded text discovery | Merely parsing complex source consumes CPU |
| Path traversal | All source and artifact paths are resolved under owned roots | New providers must preserve the invariant |
| Arbitrary command execution | Native runner uses an executable allowlist, argument arrays, fixed working root, filtered environment, timeout, and process-group cleanup | Native validation still trusts allowlisted tools and project inputs |
| Malicious tests or builds | Installation and custom execution are opt-in; Docker sandbox is preferred for untrusted validation | A container is not a perfect VM boundary |
| Docker Socket takeover | Socket is never mounted by default; privileged mode is forbidden | Explicit socket access is host-equivalent authority |
| Network escape or exfiltration | Docker runner disables network by default; optional integrations receive scoped tokens | Compose services themselves have normal service-network access |
| Resource exhaustion | Repository, upload, file count, command time, output, CPU, memory, and PID limits | Inline work can still affect API latency |
| GitHub token abuse | Token is optional, server-only, redacted, and should be read-only with minimum scope | Upstream rate and compromise remain external risks |
| Secret and log leakage | Built-in scanning, masking, known-secret redaction, structured logs, and output truncation | Novel secret formats may evade detection |
| Evidence leakage | Bundles are tenant-authorized, recursively redacted, checksummed, and sanitized | Evidence still contains sensitive code metadata by design |
| Cross-tenant IDOR | Repository queries scope every resource through organization ownership; RBAC is enforced server-side | Deployment operators retain database authority |

## Trust zones

The browser is untrusted and never receives server secrets. The API authenticates and
authorizes but does not execute arbitrary user command strings. Workers handle untrusted
source in owned temporary roots. PostgreSQL, Redis, and artifact storage are operator-trusted.
Optional LLM and GitHub services receive only explicitly configured data and credentials.

Operators should terminate TLS, restrict service ingress, use an external secret manager,
encrypt backups, apply retention rules, monitor audit events, and keep dependencies patched.
Report security issues through the private process in [SECURITY.md](../../SECURITY.md).
