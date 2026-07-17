"""Structured JSON logging with automatic credential redaction."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from proofstack_shared.security import redact_text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        for field in (
            "request_id",
            "analysis_id",
            "stage",
            "duration_ms",
            "error_category",
            "method",
            "path",
            "status_code",
            "action",
            "finding_count",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, sort_keys=True, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
