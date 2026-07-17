# Analysis pipeline

An analysis is a sequence of small stages implementing the shared `AnalysisStage` contract.
Each stage receives `AnalysisContext`, returns a `StageResult`, records timing and findings,
and exposes a user-readable failure when it cannot complete.

```mermaid
flowchart TD
    A[PREPARE_SOURCE] --> B[PARSE_DIFF]
    B --> C[DISCOVER_FILES]
    C --> D[EXTRACT_SYMBOLS]
    D --> E[BUILD_DEPENDENCY_GRAPH]
    E --> F[MAP_REQUIREMENTS]
    F --> G[ANALYZE_IMPACT]
    G --> H[ANALYZE_TEST_GAPS]
    H --> I[SCAN_SECURITY]
    I --> J[SCAN_DEPENDENCIES]
    J --> K[DETECT_CONFIG_CHANGES]
    K --> L[EXECUTE_VALIDATION]
    L --> M[EVALUATE_POLICIES]
    M --> N[BUILD_EVIDENCE]
    N --> O[FINALIZE]
```

## Data flow

Source preparation returns a safe local root and optional diff. Demo mode selects the
checked-in `changed` snapshot and separately reads the `base` snapshot for compatibility
comparison. ZIP and GitHub providers enforce size, count, path, timeout, and cleanup limits.

Discovery reads bounded text files and ignores VCS metadata, dependencies, build output,
binary content, large files, and symlinks. The diff, Python AST, import and call graph,
FastAPI routes, requirements, tests, secrets, dangerous patterns, dependency manifests,
configuration, and database models then produce normalized evidence.

Validation uses a fixed command allowlist and argument arrays. Its stdout and stderr are
bounded and redacted. Policy evaluation consumes severity counts, validation counts,
requirement coverage, and test evidence. Risk scoring is deterministic and produces named
components. Evidence generation writes stable JSON, Markdown, HTML, and checksums before the
analysis is finalized.

## Failure and cancellation

The orchestrator captures stage exceptions into a failed `StageResult`; it does not expose a
server stack to the caller. Progress callbacks persist stage transitions. Cancellation is
checked between stages, producing a distinct cancelled result. Prepared temporary sources
are cleaned in a `finally` path for local and worker executions.

This model allows a future stage retry without making the analysis result ambiguous: inputs,
stage outcome, and artifacts remain explicit.
