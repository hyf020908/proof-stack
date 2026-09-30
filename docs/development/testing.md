# Testing and quality gates

ProofStack separates fast domain tests from transport, security, browser, and acceptance
tests so failures point to the correct boundary.

GitHub CI runs the Python and frontend checks in two jobs within one workflow. The Python
job includes unit, integration, contract, and security tests with branch coverage; the
frontend job includes component tests and the production build. Smoke, browser, and full
acceptance checks are local commands. CI does not schedule background scans, query online
audit or Semgrep services, upload reports, or deploy the application. Installing dependencies
requires package downloads from PyPI and npm.

| Suite | Command | Scope |
| --- | --- | --- |
| Python | `make test-python` | Unit, integration, contract, and security tests with coverage |
| Integration | `make test-integration` | API/database/worker boundaries and OpenAPI contracts |
| Security | `make test-security` | Archive, runner, IDOR, token, and redaction boundaries |
| Frontend | `make test-web` | Vitest and Testing Library component flows |
| Browser | `make e2e` | Three offline Playwright user journeys |
| Smoke | `make smoke` | Live API, Demo analysis, Evidence download, and CLI |
| Full gate | `make acceptance` | Format, lint, types, all tests, builds, smoke, and cleanup |

Python coverage is branch-aware and must not fall below the configured project threshold.
Do not exclude core behavior or weaken assertions to improve a number. Frontend tests should
exercise accessible labels and user-visible states rather than implementation details.

Security tests use temporary directories and local fake values. They must never call an
external network, execute repository-provided arbitrary shell, or leave archives, databases,
reports, screenshots, or credentials behind.

When a tool is genuinely unavailable, report it as unavailable. A skipped, unavailable, or
timed-out validation is not a pass. Local coverage and Playwright reports are diagnostic
only and are removed by `make clean`.

To reproduce a failure, run the narrowest suite first, repair the root cause, rerun that
suite, then rerun `make acceptance`. Finish with `make clean-check` and
`python scripts/verify_repository.py`.
