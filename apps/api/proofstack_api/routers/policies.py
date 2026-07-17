"""Built-in policy discovery and safe YAML validation."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from proofstack_api.auth import get_current_user
from proofstack_api.models import User
from proofstack_api.schemas import PolicyValidateRequest, PolicyValidateResponse

router = APIRouter(prefix="/policies", tags=["policies"])

DEFAULT_POLICY = """name: default
version: 1
rules:
  - id: no-critical-findings
    description: Critical findings are not allowed
    metric: findings.critical
    operator: eq
    value: 0
    outcome: fail
  - id: limit-high-findings
    description: No more than two high-severity findings
    metric: findings.high
    operator: lte
    value: 2
    outcome: fail
  - id: require-validation
    description: At least one validation command must pass
    metric: validation.passed
    operator: gte
    value: 1
    outcome: fail
  - id: requirement-coverage
    description: Requirement evidence coverage must reach 70 percent
    metric: requirements.coverage
    operator: gte
    value: 0.7
    outcome: warn
  - id: test-evidence
    description: Changed production code should have related tests
    metric: tests.evidence_score
    operator: gte
    value: 0.6
    outcome: warn
"""


def get_default_policy() -> str:
    candidates = [
        Path.cwd() / "examples/sample-policies/default.yml",
        Path.cwd() / "examples/demo-python-service/policy.yml",
    ]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return DEFAULT_POLICY


@router.get("")
def list_policies(_: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    from proofstack_policies import parse_policy

    policy = parse_policy(get_default_policy())
    return [policy.to_dict()]


@router.post("/validate", response_model=PolicyValidateResponse)
def validate_policy(
    payload: PolicyValidateRequest, _: User = Depends(get_current_user)
) -> PolicyValidateResponse:
    from proofstack_policies import PolicyValidationError, parse_policy

    try:
        policy = parse_policy(payload.yaml)
    except PolicyValidationError as exc:
        return PolicyValidateResponse(valid=False, errors=[str(exc)])
    return PolicyValidateResponse(
        valid=True,
        name=policy.name,
        version=policy.version,
        rules=len(policy.rules),
    )
