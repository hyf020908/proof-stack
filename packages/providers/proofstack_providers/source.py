"""Source provider contracts and safe local repository preparation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class SourceType(StrEnum):
    DEMO = "demo"
    PATH = "path"
    ZIP = "zip"
    GITHUB = "github"


class SourcePreparationError(RuntimeError):
    def __init__(self, code: str, user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


@dataclass(slots=True)
class SourceLimits:
    max_repository_bytes: int = 100 * 1024 * 1024
    max_file_bytes: int = 10 * 1024 * 1024
    max_file_count: int = 20_000
    max_archive_ratio: float = 100.0
    max_diff_bytes: int = 10 * 1024 * 1024


@dataclass(slots=True)
class SourceRequest:
    source_type: SourceType
    source_path: Path | None = None
    archive_path: Path | None = None
    diff_path: Path | None = None
    github_url: str | None = None
    reference: str | None = None
    destination_parent: Path | None = None
    github_token: str = field(default="", repr=False)
    limits: SourceLimits = field(default_factory=SourceLimits)


@dataclass(slots=True)
class PreparedSource:
    root: Path
    source_type: SourceType
    source_reference: str
    diff_text: str = ""
    base_revision: str | None = None
    head_revision: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    cleanup_path: Path | None = None


@runtime_checkable
class SourceProvider(Protocol):
    def prepare(self, request: SourceRequest) -> PreparedSource:
        """Prepare a validated source tree for deterministic analysis."""


class LocalSourceProvider:
    def prepare(self, request: SourceRequest) -> PreparedSource:
        if request.source_path is None:
            raise SourcePreparationError("source_path_missing", "A local source path is required.")
        root = request.source_path.expanduser().resolve()
        if not root.is_dir():
            raise SourcePreparationError(
                "source_not_found", "The selected source directory does not exist."
            )
        stats = validate_source_tree(root, request.limits)
        diff_text = read_optional_diff(request.diff_path, request.limits.max_diff_bytes)
        return PreparedSource(
            root=root,
            source_type=request.source_type,
            source_reference=str(request.source_path),
            diff_text=diff_text,
            metadata=stats,
        )


def validate_source_tree(root: Path, limits: SourceLimits) -> dict[str, int]:
    resolved_root = root.resolve()
    total_bytes = 0
    file_count = 0
    for directory, directory_names, file_names in os.walk(resolved_root, followlinks=False):
        directory_path = Path(directory)
        safe_directories: list[str] = []
        for name in sorted(directory_names):
            candidate = directory_path / name
            if candidate.is_symlink():
                raise SourcePreparationError(
                    "symlink_rejected", "Symbolic links are not accepted in analysis sources."
                )
            try:
                candidate.resolve().relative_to(resolved_root)
            except ValueError as exc:
                raise SourcePreparationError(
                    "path_escape", "A repository path escapes the source root."
                ) from exc
            safe_directories.append(name)
        directory_names[:] = safe_directories
        for name in sorted(file_names):
            candidate = directory_path / name
            if candidate.is_symlink():
                raise SourcePreparationError(
                    "symlink_rejected", "Symbolic links are not accepted in analysis sources."
                )
            try:
                candidate.resolve().relative_to(resolved_root)
            except ValueError as exc:
                raise SourcePreparationError(
                    "path_escape", "A repository file escapes the source root."
                ) from exc
            if not candidate.is_file():
                continue
            file_count += 1
            if file_count > limits.max_file_count:
                raise SourcePreparationError(
                    "file_count_exceeded", "The repository contains too many files."
                )
            size = candidate.stat().st_size
            if size > limits.max_file_bytes:
                raise SourcePreparationError(
                    "file_too_large", f"The file {name} exceeds the per-file limit."
                )
            total_bytes += size
            if total_bytes > limits.max_repository_bytes:
                raise SourcePreparationError(
                    "repository_too_large", "The repository exceeds the configured size limit."
                )
    return {"file_count": file_count, "repository_bytes": total_bytes}


def read_optional_diff(path: Path | None, max_bytes: int) -> str:
    if path is None:
        return ""
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.suffix.lower() not in {".diff", ".patch"}:
        raise SourcePreparationError(
            "invalid_diff", "The optional diff must be a readable .diff or .patch file."
        )
    if resolved.stat().st_size > max_bytes:
        raise SourcePreparationError(
            "diff_too_large", "The diff exceeds the configured size limit."
        )
    content = resolved.read_bytes()
    if b"\x00" in content:
        raise SourcePreparationError("invalid_diff", "The diff contains binary data.")
    return content.decode("utf-8", errors="replace")
