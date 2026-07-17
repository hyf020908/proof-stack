# Adding a deterministic analyzer

An analyzer converts bounded source text and existing normalized evidence into a result with
findings. It must be deterministic, independent of database sessions, and safe to run with
no network.

## Recommended shape

```python
from dataclasses import dataclass, field
from typing import Mapping

from proofstack_core import Finding


@dataclass(slots=True)
class ExampleResult:
    facts: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


class ExampleAnalyzer:
    def analyze(self, files: Mapping[str, str]) -> ExampleResult:
        result = ExampleResult()
        for path, source in sorted(files.items()):
            result.facts.extend(self._facts(path, source))
        return result

    def _facts(self, path: str, source: str) -> list[str]:
        return [f"{path}:example"] if "example" in source.casefold() else []
```

Keep parsing in the analyzer and orchestration in a small `DeterministicStage` subclass.
Return data through the stage output dictionary so later impact, policy, evidence, and API
layers consume a stable normalized shape.

## Finding requirements

Every finding needs a category, severity, title, precise explanation, stable rule ID,
actionable remediation, and deterministic fingerprint. Include file and line when known. Put
only structured, already-redacted facts in `evidence`; never place an entire secret or
unbounded source excerpt there.

## Verification checklist

1. Unit test positive, negative, malformed, and duplicate inputs.
2. Prove output ordering and fingerprints are stable.
3. Add a fixture representing a realistic change, not a hard-coded result.
4. Test stage failure containment and the user-facing error.
5. Add result serialization and Evidence Bundle coverage.
6. Document risk weighting if the analyzer changes risk.
7. Run format, lint, strict types, focused tests, then acceptance.

If the analyzer wraps an optional executable, add an adapter and mock runner. Missing optional
software must produce `unavailable`, not a failed pipeline and never a fabricated pass.
