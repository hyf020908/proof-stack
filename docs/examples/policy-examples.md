# Policy examples

Policies are versioned YAML documents. Each rule reads a dotted metric, applies an operator,
and declares whether a failed comparison blocks (`fail`) or advises (`warn`). The current
pipeline exposes `findings.{info,low,medium,high,critical}`, `validation.{passed,failed,total}`,
`requirements.coverage`, and `tests.evidence_score`.

```yaml
name: service-gate
version: 1
rules:
  - id: no-critical-findings
    description: Critical evidence blocks acceptance
    metric: findings.critical
    operator: eq
    value: 0
    outcome: fail

  - id: test-evidence
    description: Related test evidence should reach 75 percent
    metric: tests.evidence_score
    operator: gte
    value: 0.75
    outcome: warn
```

Supported operators are `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, and `exists`.
Every decision includes its rule, observed value, expected value, outcome, explanation, and
related evidence. A failing rule dominates warnings; warnings dominate pass.

Start with [the default policy](../../examples/sample-policies/default.yml), observe normal
team evidence for several changes, and then tighten thresholds through review. Do not weaken
a policy merely to make a particular change green. Validate before use:

```bash
proofstack policy validate examples/sample-policies/default.yml
```

Policies decide acceptance; the separate 0–100 risk score prioritizes review. A low risk score
does not override a failed policy rule.
