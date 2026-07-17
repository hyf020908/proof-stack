"""Recursive secret redaction for logs, reports, and evidence artifacts."""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = re.compile(
    r"(?:^|_)(?:api_?key|access_?key|auth(?:orization)?|bearer|client_?secret|"
    r"cookie|credential|database_?url|password|passwd|private_?key|refresh_?token|"
    r"secret|session|token)(?:$|_)",
    re.IGNORECASE,
)

_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)

_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|authorization|client[_-]?secret|"
    r"database[_-]?url|password|passwd|private[_-]?key|refresh[_-]?token|secret|token)"
    r"\s*[:=]\s*)(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;]+)"
)
_URI_CREDENTIAL_PATTERN = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^\s/@:]+):([^\s/@]+)@")


def is_sensitive_key(key: str) -> bool:
    """Return whether a mapping key conventionally contains sensitive data."""

    with_word_boundaries = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", with_word_boundaries).strip("_")
    return bool(_SENSITIVE_KEYS.search(normalized))


def redact_text(text: str, *, known_secrets: tuple[str, ...] = ()) -> str:
    """Redact high-confidence credential patterns without exposing matched values."""

    result = text
    for secret in sorted({item for item in known_secrets if len(item) >= 4}, key=len, reverse=True):
        result = result.replace(secret, REDACTED)
    result = _URI_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]@", result)
    result = _ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", result)
    for pattern in _TEXT_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def redact_data(value: Any, *, known_secrets: tuple[str, ...] = ()) -> Any:
    """Return a JSON-compatible deep copy with sensitive values removed."""

    active: set[int] = set()

    def visit(item: Any, depth: int) -> Any:
        if depth > 64:
            return "[MAX_DEPTH]"
        if item is None or isinstance(item, bool | int | float):
            return item
        if isinstance(item, str):
            return redact_text(item, known_secrets=known_secrets)
        if isinstance(item, bytes):
            return redact_text(item.decode("utf-8", errors="replace"), known_secrets=known_secrets)
        if isinstance(item, datetime | date):
            return item.isoformat()
        if isinstance(item, Path):
            return str(item)
        if isinstance(item, Enum):
            return visit(item.value, depth + 1)
        if is_dataclass(item) and not isinstance(item, type):
            return visit(asdict(item), depth + 1)

        identity = id(item)
        if isinstance(item, dict):
            if identity in active:
                return "[CIRCULAR]"
            active.add(identity)
            try:
                cleaned: dict[str, Any] = {}
                for key, child in item.items():
                    clean_key = redact_text(str(key), known_secrets=known_secrets)
                    cleaned[clean_key] = (
                        REDACTED if is_sensitive_key(str(key)) else visit(child, depth + 1)
                    )
                return cleaned
            finally:
                active.remove(identity)
        if isinstance(item, list | tuple | set | frozenset):
            if identity in active:
                return "[CIRCULAR]"
            active.add(identity)
            try:
                children = [visit(child, depth + 1) for child in item]
                if isinstance(item, set | frozenset):
                    return sorted(children, key=repr)
                return children
            finally:
                active.remove(identity)
        if hasattr(item, "to_dict") and callable(item.to_dict):
            return visit(item.to_dict(), depth + 1)
        return redact_text(str(item), known_secrets=known_secrets)

    return visit(value, 0)


def contains_high_confidence_secret(text: str) -> bool:
    """Detect credential forms that must never appear in a generated bundle."""

    if _URI_CREDENTIAL_PATTERN.search(text):
        return True
    for pattern in _TEXT_PATTERNS:
        if pattern.search(text):
            return True
    return any(REDACTED not in match.group(2) for match in _ASSIGNMENT_PATTERN.finditer(text))


__all__ = [
    "REDACTED",
    "contains_high_confidence_secret",
    "is_sensitive_key",
    "redact_data",
    "redact_text",
]
