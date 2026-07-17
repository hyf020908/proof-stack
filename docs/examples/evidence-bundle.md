# Evidence Bundle

Every completed analysis can export a portable directory and ZIP. A bundle is designed for
human review, automation, and later integrity verification without a running ProofStack
server.

```text
evidence-bundle/
├── manifest.json
├── summary.md
├── analysis.json
├── changed-files.json
├── requirements.json
├── dependency-graph.json
├── findings.json
├── test-results.json
├── policy-decisions.json
├── audit-events.json
├── checksums.sha256
└── report.html
```

JSON files carry a schema version and stable structure. `manifest.json` records ProofStack
version, execution time, input digests, and artifact metadata. `checksums.sha256` covers every
other bundle file. `summary.md` is the concise review narrative; `report.html` is a
self-contained, CSP-protected offline view.

Verify before relying on a copied artifact:

```bash
proofstack evidence verify ./evidence-bundle
proofstack evidence verify ./evidence-bundle.zip
```

Verification checks required files, safe archive paths, symlink and compression behavior,
schema identity, checksums, and credential exposure. A valid checksum proves that bytes did
not change after bundle generation; it does not prove the analyzed source or executing host
was trustworthy.

Bundle content is recursively redacted, but it still includes file paths, findings, change
metadata, policy decisions, and audit context. Treat it as source-sensitive. Authorize API
downloads, protect storage and backups, and apply a retention policy. The small files under
`examples/sample-reports` are sanitized illustrations, not a substitute for a generated
bundle.
