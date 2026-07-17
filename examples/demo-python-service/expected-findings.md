# Expected evidence from the demo change

The exact risk score can evolve with documented weight changes, but the deterministic demo
must produce a failing verdict because it crosses critical security policy.

| Expected rule or signal | Why it is present |
| --- | --- |
| `impact.python-signature-changed` | `calculate_total` now requires a currency argument and has several callers. |
| `test.changed-source-without-evidence` | The new export route and exporter have no related tests. |
| `requirement.unsupported` | REQ-103 requests an audit trail that the changed snapshot does not implement. |
| `config.undocumented-environment-variable` | `DEMO_EXPORT_BUCKET` is required but absent from `.env.example`. |
| `python.subprocess-shell` | The new exporter passes interpolated input to `shell=True`. |
| `secret.github-token` | A synthetic token-shaped fixture exercises redaction and fingerprinting. |
| `dependency.unpinned` | `requests>=2` is broad and has no lock evidence. |
| `database.model-change-without-migration` | `Order.review_note` is non-null but there is no migration. |
| `docker.floating-base-image` | The changed Dockerfile uses `python:latest`. |
| `docker.root-user` | The changed Dockerfile never selects a non-root user. |
| `docker.world-writable` | The changed Dockerfile applies mode `777`. |

The token-like string is fabricated for this fixture. ProofStack must mask it in findings,
logs, Evidence Bundles, and UI responses.
