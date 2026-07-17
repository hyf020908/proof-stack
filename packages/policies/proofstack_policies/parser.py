"""Safe YAML parsing and structural validation for ProofStack policies."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from .models import Policy, PolicyOperator, PolicyOutcome, PolicyRule


class PolicyValidationError(ValueError):
    """Raised when a policy document is malformed or unsafe to evaluate."""

    def __init__(self, message: str, *, location: str = "policy") -> None:
        self.location = location
        super().__init__(f"{location}: {message}")


def _require_string(value: Any, *, location: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise PolicyValidationError("must be a string", location=location)
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise PolicyValidationError("must not be empty", location=location)
    return normalized


def _parse_rule(raw: Any, index: int) -> PolicyRule:
    location = f"policy.rules[{index}]"
    if not isinstance(raw, Mapping):
        raise PolicyValidationError("must be an object", location=location)

    rule_id = _require_string(raw.get("id"), location=f"{location}.id")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", rule_id) is None:
        raise PolicyValidationError("contains unsupported characters", location=f"{location}.id")
    description = _require_string(
        raw.get("description", rule_id), location=f"{location}.description"
    )
    metric = _require_string(raw.get("metric"), location=f"{location}.metric")
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*", metric) is None:
        raise PolicyValidationError(
            "must be a dot-separated metric path", location=f"{location}.metric"
        )

    try:
        operator = PolicyOperator(
            _require_string(raw.get("operator"), location=f"{location}.operator")
        )
    except ValueError as exc:
        supported = ", ".join(member.value for member in PolicyOperator)
        raise PolicyValidationError(
            f"must be one of: {supported}", location=f"{location}.operator"
        ) from exc

    if operator is not PolicyOperator.EXISTS and "value" not in raw:
        raise PolicyValidationError("is required for this operator", location=f"{location}.value")
    value = raw.get("value", True if operator is PolicyOperator.EXISTS else None)
    if operator in {PolicyOperator.IN, PolicyOperator.NOT_IN} and not isinstance(
        value, list | tuple | set | frozenset | str
    ):
        raise PolicyValidationError(
            "must be a collection or string for membership operators",
            location=f"{location}.value",
        )
    if operator is PolicyOperator.EXISTS and not isinstance(value, bool):
        raise PolicyValidationError(
            "must be a boolean for the exists operator", location=f"{location}.value"
        )

    try:
        outcome = PolicyOutcome(
            _require_string(raw.get("outcome", "fail"), location=f"{location}.outcome")
        )
    except ValueError as exc:
        raise PolicyValidationError(
            "must be either warn or fail", location=f"{location}.outcome"
        ) from exc
    if outcome is PolicyOutcome.PASS:
        raise PolicyValidationError("must be either warn or fail", location=f"{location}.outcome")

    raw_evidence = raw.get("evidence", ())
    if not isinstance(raw_evidence, list | tuple) or not all(
        isinstance(item, str) and item.strip() for item in raw_evidence
    ):
        raise PolicyValidationError(
            "must be a list of non-empty strings", location=f"{location}.evidence"
        )

    return PolicyRule(
        id=rule_id,
        description=description,
        metric=metric,
        operator=operator,
        value=value,
        outcome=outcome,
        evidence=tuple(item.strip() for item in raw_evidence),
    )


def parse_policy(document: str | bytes | Mapping[str, Any]) -> Policy:
    """Parse a policy from safe YAML text or an already decoded mapping."""

    if isinstance(document, Mapping):
        raw: Any = dict(document)
    else:
        try:
            raw = yaml.safe_load(document)
        except yaml.YAMLError as exc:
            raise PolicyValidationError(f"invalid YAML: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise PolicyValidationError("must be a YAML object")

    name = _require_string(raw.get("name"), location="policy.name")
    version = raw.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise PolicyValidationError("must be a positive integer", location="policy.version")

    raw_rules = raw.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise PolicyValidationError("must be a non-empty list", location="policy.rules")
    rules = tuple(_parse_rule(rule, index) for index, rule in enumerate(raw_rules))
    rule_ids = [rule.id for rule in rules]
    duplicates = sorted({rule_id for rule_id in rule_ids if rule_ids.count(rule_id) > 1})
    if duplicates:
        raise PolicyValidationError(
            f"duplicate rule identifiers: {', '.join(duplicates)}", location="policy.rules"
        )
    return Policy(name=name, version=version, rules=rules)


def load_policy(path: str | Path, *, max_bytes: int = 1_048_576) -> Policy:
    """Load and parse a UTF-8 policy file with a conservative size limit."""

    policy_path = Path(path)
    try:
        size = policy_path.stat().st_size
    except OSError as exc:
        raise PolicyValidationError(f"cannot read file: {exc}", location=str(policy_path)) from exc
    if size > max_bytes:
        raise PolicyValidationError(
            f"file exceeds the {max_bytes}-byte limit", location=str(policy_path)
        )
    try:
        content = policy_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PolicyValidationError(
            f"cannot read UTF-8 file: {exc}", location=str(policy_path)
        ) from exc
    return parse_policy(content)
