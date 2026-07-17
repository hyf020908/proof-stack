"""Heuristic database migration safety checks for SQLAlchemy and Alembic."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from proofstack_core import Finding, FindingCategory, Severity


@dataclass(slots=True)
class DatabaseImpactResult:
    operations: list[str] = field(default_factory=list)
    model_fields_added: list[str] = field(default_factory=list)
    model_fields_removed: list[str] = field(default_factory=list)
    migration_present: bool = False
    findings: list[Finding] = field(default_factory=list)


class DatabaseImpactAnalyzer:
    def analyze(
        self,
        current_files: Mapping[str, str],
        *,
        previous_files: Mapping[str, str] | None = None,
    ) -> DatabaseImpactResult:
        previous_files = previous_files or {}
        result = DatabaseImpactResult()
        all_migration_files = {
            path: source
            for path, source in current_files.items()
            if "migrations/" in path.lower() or "alembic/versions/" in path.lower()
        }
        migration_files = (
            {
                path: source
                for path, source in all_migration_files.items()
                if previous_files.get(path) != source
            }
            if previous_files
            else all_migration_files
        )
        result.migration_present = bool(migration_files)
        for path, source in migration_files.items():
            for pattern, operation, severity, message in (
                (
                    r"op\.drop_column\s*\(",
                    "drop_column",
                    Severity.HIGH,
                    "A database column is dropped.",
                ),
                (
                    r"op\.drop_table\s*\(",
                    "drop_table",
                    Severity.CRITICAL,
                    "A database table is dropped.",
                ),
                (
                    r"op\.alter_column\s*\([^)]*new_column_name",
                    "rename_column",
                    Severity.HIGH,
                    "A database column is renamed.",
                ),
                (r"op\.execute\s*\(", "raw_sql", Severity.MEDIUM, "A migration executes raw SQL."),
                (
                    r"op\.create_index\s*\(",
                    "create_index",
                    Severity.MEDIUM,
                    "An index creation may lock a large table.",
                ),
            ):
                for match in re.finditer(pattern, source, re.S):
                    line = source.count("\n", 0, match.start()) + 1
                    result.operations.append(operation)
                    result.findings.append(
                        _finding(
                            f"database.{operation.replace('_', '-')}",
                            severity,
                            "Potentially risky database migration",
                            message,
                            path,
                            line,
                            "Confirm a reversible, production-safe rollout and backup strategy.",
                        )
                    )
            for match in re.finditer(
                r"op\.add_column\s*\([^)]*nullable\s*=\s*False(?![^)]*(?:server_default|default))",
                source,
                re.S,
            ):
                line = source.count("\n", 0, match.start()) + 1
                result.findings.append(
                    _finding(
                        "database.non-null-column-without-default",
                        Severity.HIGH,
                        "Non-null column may fail on existing rows",
                        "A migration adds a non-null column without an apparent server default.",
                        path,
                        line,
                        "Backfill in phases before enforcing the non-null constraint.",
                    )
                )
            if "def downgrade" not in source or re.search(
                r"def downgrade\([^)]*\):\s+(?:pass|raise NotImplementedError)", source
            ):
                result.findings.append(
                    _finding(
                        "database.irreversible-migration",
                        Severity.MEDIUM,
                        "Migration has no usable downgrade",
                        "The migration does not expose an obvious downgrade path.",
                        path,
                        1,
                        (
                            "Provide a tested downgrade or document why recovery is "
                            "intentionally manual."
                        ),
                    )
                )
        before_fields = _model_fields(previous_files)
        after_fields = _model_fields(current_files)
        result.model_fields_added = sorted(after_fields - before_fields)
        result.model_fields_removed = sorted(before_fields - after_fields)
        if (
            result.model_fields_added or result.model_fields_removed
        ) and not result.migration_present:
            changed_fields = [*result.model_fields_added, *result.model_fields_removed]
            result.findings.append(
                _finding(
                    "database.model-change-without-migration",
                    Severity.HIGH,
                    "Database model changed without a migration",
                    f"Model field changes were detected: {', '.join(changed_fields[:8])}.",
                    None,
                    None,
                    "Generate and review a database migration for the model change.",
                )
            )
        return result


def _model_fields(files: Mapping[str, str]) -> set[str]:
    fields: set[str] = set()
    for path, source in files.items():
        if not path.endswith(".py") or not any(
            token in source for token in ("Mapped[", "Column(", "mapped_column(")
        ):
            continue
        current_class = ""
        for line in source.splitlines():
            class_match = re.match(r"\s*class\s+(\w+)", line)
            if class_match:
                current_class = class_match.group(1)
            field_match = re.match(r"\s+(\w+)\s*(?::[^=]+)?=\s*(?:mapped_column|Column)\s*\(", line)
            if field_match and current_class:
                fields.add(f"{current_class}.{field_match.group(1)}")
    return fields


def _finding(
    rule_id: str,
    severity: Severity,
    title: str,
    description: str,
    path: str | None,
    line: int | None,
    remediation: str,
) -> Finding:
    fingerprint = hashlib.sha256(f"{rule_id}:{path}:{line}:{description}".encode()).hexdigest()
    return Finding(
        category=FindingCategory.COMPATIBILITY,
        severity=severity,
        title=title,
        description=description,
        rule_id=rule_id,
        remediation=remediation,
        fingerprint=fingerprint,
        file_path=path,
        start_line=line,
        end_line=line,
    )
