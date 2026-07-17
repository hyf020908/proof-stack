"""Small reusable guards for role checks and sensitive text redaction."""

import re
from collections.abc import Iterable

from proofstack_shared.enums import Role

ROLE_LEVEL: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.REVIEWER: 1,
    Role.MAINTAINER: 2,
    Role.OWNER: 3,
}

_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(postgres(?:ql)?://[^:\s]+:)[^@\s]+(@)"),
    re.compile(r"(?i)(mysql://[^:\s]+:)[^@\s]+(@)"),
]


def has_minimum_role(actual: Role, minimum: Role) -> bool:
    return ROLE_LEVEL[actual] >= ROLE_LEVEL[minimum]


def role_allowed(actual: Role, allowed: Iterable[Role]) -> bool:
    return actual in set(allowed)


def redact_text(value: str, *, limit: int = 12000) -> str:
    """Redact common credential formats and cap untrusted output size."""

    redacted = value[:limit]
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(
            lambda match: (
                f"{match.group(1)}[REDACTED]" + (match.group(2) if match.lastindex == 2 else "")
            ),
            redacted,
        )
    if len(value) > limit:
        redacted += "\n[OUTPUT TRUNCATED]"
    return redacted
