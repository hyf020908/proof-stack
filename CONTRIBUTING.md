# Contributing to ProofStack

Thank you for helping make AI-generated changes easier to review with evidence. ProofStack
welcomes focused bug fixes, analyzers, security hardening, tests, accessible product work,
documentation, and policy examples.

## Before you start

For a substantial feature, open a design discussion first. Describe the problem, trust
boundary, expected evidence, affected API or schema, and how the change can be tested without
an external paid service. Small fixes can go directly to a pull request.

By participating, you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Security issues must
follow the private process in [SECURITY.md](SECURITY.md), not a public issue.

## Development setup

Prerequisites are Python 3.11+, Node.js 20+, and pnpm 9+.

```bash
cp .env.example .env
make bootstrap
make db-upgrade
make dev
```

Docker is optional. The default SQLite and inline-task profile is enough for backend,
frontend, CLI, and deterministic analysis development. See
[local development](docs/development/local-development.md) for process-level commands.

## Engineering expectations

- Keep core analysis deterministic, offline-capable, and independently testable.
- Put network, filesystem acquisition, and command execution behind a narrow adapter.
- Treat repositories, archives, diffs, requirements, and command output as untrusted.
- Use argument arrays for processes; never concatenate a user-controlled shell command.
- Preserve accurate passed, failed, skipped, unavailable, and timed-out states.
- Add Alembic migrations for every persistent schema change.
- Keep organization scope and RBAC enforcement on the server.
- Redact secrets before logging, returning, or writing artifacts.
- Use English for comments, identifiers, configuration comments, and source documentation.
- Do not add empty implementations, abandoned work markers, fabricated Demo data, or hidden fallbacks.
- Keep the UI connected to real API contracts with accessible loading, empty, error, and success states.

## Tests

Run the focused suite while developing, then the complete local gate:

```bash
make format
make lint
make typecheck
make test
make build
make acceptance
```

New analyzers need positive, negative, malformed, duplicate, fingerprint-stability, and stage
integration coverage. Security-boundary changes need an explicit regression test. UI work
needs a component test for user-visible behavior; a critical workflow change also needs an
offline Playwright scenario.

Do not reduce coverage scope, disable strict TypeScript, loosen lint rules, skip a failing
test, or turn unavailable evidence into pass to make a change green.

## Database and API changes

Review both upgrade and downgrade behavior for migrations. Keep SQLite and PostgreSQL types
portable unless the change explicitly documents a deployment tradeoff. API changes require
response models, validation, authorization, OpenAPI contract coverage, frontend type updates,
and a migration path for breaking fields.

## Documentation and evidence

Update both English and Chinese README files when commands, capabilities, configuration, or
security boundaries change. Do not claim support that the implementation and tests do not
provide. If risk inputs or weights change, update the risk documentation and exact unit tests.
If an Evidence Bundle shape changes, bump its schema version and preserve verifier diagnostics.

## Pull request checklist

- The change solves one clearly stated problem.
- Security and tenant boundaries were considered.
- Source comments and configuration comments are English-only.
- Tests cover success and failure behavior.
- User-facing documentation matches the implementation.
- Format, lint, strict types, tests, build, and relevant smoke checks passed.
- Generated directories, databases, logs, reports, credentials, and local environment files
  were removed with `make clean && make clean-check`.

Maintainers may ask to split an oversized change when doing so makes evidence and review more
reliable.
