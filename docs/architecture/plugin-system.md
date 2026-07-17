# Providers and extension points

ProofStack uses narrow Python protocols and adapters instead of importing external services
inside the analysis domain.

## Source providers

`SourceProvider.prepare(SourceRequest) -> PreparedSource` is implemented for local paths,
safe ZIP archives, and public GitHub repositories or pull requests. A provider must return a
resolved root, source metadata, optional revisions and diff, and an owned cleanup path. It
must apply `SourceLimits` before exposing content to analyzers.

## Execution runners

`ExecutionRunner.execute(ExecutionPlan) -> ExecutionResult` is implemented by
`NativeSafeRunner` and `DockerSandboxRunner`. Runners receive structured command arguments,
never a concatenated user shell command. New runners must preserve passed, failed, skipped,
unavailable, and timed-out outcomes and must redact bounded output.

## Language analyzers

The first release intentionally provides deep Python AST analysis only. Its analyzer returns
symbols, imports, calls, inheritance, routes, complexity, and warnings in normalized data
structures consumed by the graph and impact stages. A future language adapter should expose
the same concepts without changing policy, evidence, or API models. TypeScript, Java, and Go
support is roadmap work, not an implied current capability.

## Requirement mappers

The deterministic mapper is the default and works offline. A mock mapper supports tests. The
OpenAI-compatible adapter is opt-in, has bounded retries and timeout, reads credentials from
configuration, and must never log them. Disabling or losing the optional provider cannot
disable the deterministic path.

## Adding an extension safely

1. Define or implement the narrow protocol in the package that owns the boundary.
2. Normalize provider-specific errors into a user-actionable domain error.
3. Enforce size, timeout, resource, and output limits at the boundary.
4. Add unit tests with a fake adapter and an integration test for the selected implementation.
5. Register the adapter in the application assembly, not in core analysis code.
6. Document configuration, security implications, and unavailable behavior.

For a concrete analyzer walkthrough, see
[adding an analyzer](../development/adding-an-analyzer.md).
