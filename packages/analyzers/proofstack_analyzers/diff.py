"""A dependency-free parser for Git-style unified diffs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath


class DiffParseError(ValueError):
    """Raised when a diff cannot be parsed without ambiguity."""


class ChangeType(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class DiffLineType(StrEnum):
    CONTEXT = "context"
    ADDED = "added"
    REMOVED = "removed"


@dataclass(slots=True, frozen=True)
class DiffLine:
    line_type: DiffLineType
    content: str
    old_line_number: int | None
    new_line_number: int | None


@dataclass(slots=True)
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str = ""
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def changed_new_lines(self) -> tuple[int, ...]:
        return tuple(
            line.new_line_number
            for line in self.lines
            if line.line_type is DiffLineType.ADDED and line.new_line_number is not None
        )

    @property
    def changed_old_lines(self) -> tuple[int, ...]:
        return tuple(
            line.old_line_number
            for line in self.lines
            if line.line_type is DiffLineType.REMOVED and line.old_line_number is not None
        )


_TEST_PATTERN = re.compile(
    r"(^|/)(tests?|specs?)(/|$)|(^|/)(test_|.*(_test|\.spec|\.test)\.)", re.I
)
_CONFIG_NAMES = {
    ".env",
    ".env.example",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "pyproject.toml",
    "package.json",
    "setup.cfg",
    "tox.ini",
}
_DEPENDENCY_NAMES = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "uv.lock",
    "pipfile",
    "pipfile.lock",
}


@dataclass(slots=True)
class DiffFile:
    old_path: str | None
    new_path: str | None
    change_type: ChangeType = ChangeType.MODIFIED
    hunks: list[DiffHunk] = field(default_factory=list)
    is_binary: bool = False
    old_mode: str | None = None
    new_mode: str | None = None
    similarity: int | None = None

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""

    @property
    def additions(self) -> int:
        return sum(
            1 for hunk in self.hunks for line in hunk.lines if line.line_type is DiffLineType.ADDED
        )

    @property
    def deletions(self) -> int:
        return sum(
            1
            for hunk in self.hunks
            for line in hunk.lines
            if line.line_type is DiffLineType.REMOVED
        )

    @property
    def is_test(self) -> bool:
        return bool(_TEST_PATTERN.search(self.path))

    @property
    def is_config(self) -> bool:
        path = PurePosixPath(self.path.lower())
        return (
            path.name in _CONFIG_NAMES
            or path.suffix in {".yaml", ".yml", ".toml", ".ini"}
            or ".github/workflows" in str(path)
        )

    @property
    def is_dependency_manifest(self) -> bool:
        path = PurePosixPath(self.path.lower())
        return path.name in _DEPENDENCY_NAMES or (
            path.name.startswith("requirements") and path.suffix == ".txt"
        )

    @property
    def is_migration(self) -> bool:
        lowered = self.path.lower()
        return "migrations/" in lowered or "alembic/versions/" in lowered

    @property
    def is_api_schema(self) -> bool:
        lowered = self.path.lower()
        return any(token in lowered for token in ("openapi", "swagger", "asyncapi"))

    @property
    def is_ci(self) -> bool:
        lowered = self.path.lower()
        return ".github/workflows/" in lowered or lowered in {".gitlab-ci.yml", "jenkinsfile"}

    @property
    def is_security_sensitive(self) -> bool:
        lowered = self.path.lower()
        return any(
            token in lowered
            for token in (
                "auth",
                "security",
                "permission",
                "secret",
                ".env",
                "private",
                "credential",
            )
        )

    @property
    def language(self) -> str:
        suffix = PurePosixPath(self.path).suffix.lower()
        return {
            ".py": "python",
            ".pyi": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".java": "java",
            ".rs": "rust",
            ".json": "json",
            ".toml": "toml",
            ".yaml": "yaml",
            ".yml": "yaml",
        }.get(suffix, "text")

    @property
    def changed_new_ranges(self) -> tuple[tuple[int, int], ...]:
        ranges: list[tuple[int, int]] = []
        for hunk in self.hunks:
            lines = hunk.changed_new_lines
            if lines:
                ranges.append((min(lines), max(lines)))
        return tuple(ranges)


@dataclass(slots=True)
class DiffDocument:
    files: list[DiffFile] = field(default_factory=list)

    @property
    def additions(self) -> int:
        return sum(item.additions for item in self.files)

    @property
    def deletions(self) -> int:
        return sum(item.deletions for item in self.files)

    def by_path(self) -> dict[str, DiffFile]:
        return {item.path: item for item in self.files}


_DIFF_HEADER = re.compile(r'^diff --git\s+("(?:\\.|[^"\\])*"|\S+)\s+("(?:\\.|[^"\\])*"|\S+)$')
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: ?(.*))?$")


class UnifiedDiffParser:
    def parse(self, text: str) -> DiffDocument:
        if "\x00" in text:
            raise DiffParseError("Diff input contains a NUL byte")
        document = DiffDocument()
        current_file: DiffFile | None = None
        current_hunk: DiffHunk | None = None
        current_has_git_header = False
        old_line = 0
        new_line = 0

        lines = text.splitlines()
        for line_index, raw_line in enumerate(lines):
            header = _DIFF_HEADER.match(raw_line)
            if header:
                current_file = DiffFile(
                    old_path=_decode_git_path(header.group(1)),
                    new_path=_decode_git_path(header.group(2)),
                )
                document.files.append(current_file)
                current_hunk = None
                current_has_git_header = True
                continue
            if current_file is None:
                if raw_line.startswith("--- "):
                    current_file = DiffFile(old_path=_header_path(raw_line[4:]), new_path=None)
                    if current_file.old_path is None:
                        current_file.change_type = ChangeType.ADDED
                    document.files.append(current_file)
                    current_hunk = None
                    current_has_git_header = False
                    continue
                if raw_line.startswith(("+++ ", "@@ ")):
                    raise DiffParseError("Diff content is missing a diff --git file header")
                continue
            if raw_line.startswith("new file mode "):
                current_file.change_type = ChangeType.ADDED
                current_file.new_mode = raw_line.removeprefix("new file mode ")
                continue
            if raw_line.startswith("deleted file mode "):
                current_file.change_type = ChangeType.DELETED
                current_file.old_mode = raw_line.removeprefix("deleted file mode ")
                continue
            if raw_line.startswith("old mode "):
                current_file.old_mode = raw_line.removeprefix("old mode ")
                continue
            if raw_line.startswith("new mode "):
                current_file.new_mode = raw_line.removeprefix("new mode ")
                continue
            if raw_line.startswith("similarity index "):
                value = raw_line.removeprefix("similarity index ").removesuffix("%")
                current_file.similarity = int(value) if value.isdigit() else None
                continue
            if raw_line.startswith("rename from "):
                current_file.old_path = _decode_git_path(
                    raw_line.removeprefix("rename from "), strip_prefix=False
                )
                current_file.change_type = ChangeType.RENAMED
                continue
            if raw_line.startswith("rename to "):
                current_file.new_path = _decode_git_path(
                    raw_line.removeprefix("rename to "), strip_prefix=False
                )
                current_file.change_type = ChangeType.RENAMED
                continue
            if raw_line.startswith(("Binary files ", "GIT binary patch")):
                current_file.is_binary = True
                continue
            if raw_line.startswith("--- "):
                next_line = lines[line_index + 1] if line_index + 1 < len(lines) else ""
                starts_next_file = (
                    current_hunk is not None and _hunk_is_complete(current_hunk)
                ) or (current_hunk is None and current_file.new_path is not None)
                if not current_has_git_header and starts_next_file and next_line.startswith("+++ "):
                    current_file = DiffFile(old_path=_header_path(raw_line[4:]), new_path=None)
                    if current_file.old_path is None:
                        current_file.change_type = ChangeType.ADDED
                    document.files.append(current_file)
                    current_hunk = None
                    current_has_git_header = False
                    continue
                current_file.old_path = _header_path(raw_line[4:])
                if current_file.old_path is None:
                    current_file.change_type = ChangeType.ADDED
                continue
            if raw_line.startswith("+++ "):
                current_file.new_path = _header_path(raw_line[4:])
                if current_file.new_path is None:
                    current_file.change_type = ChangeType.DELETED
                continue
            hunk_match = _HUNK_HEADER.match(raw_line)
            if hunk_match:
                current_hunk = DiffHunk(
                    old_start=int(hunk_match.group(1)),
                    old_count=int(hunk_match.group(2) or 1),
                    new_start=int(hunk_match.group(3)),
                    new_count=int(hunk_match.group(4) or 1),
                    section=hunk_match.group(5) or "",
                )
                current_file.hunks.append(current_hunk)
                old_line = current_hunk.old_start
                new_line = current_hunk.new_start
                continue
            if raw_line.startswith("@@"):
                raise DiffParseError("Diff contains an invalid hunk header")
            if current_hunk is None or raw_line == "\\ No newline at end of file":
                continue
            if raw_line.startswith("+"):
                current_hunk.lines.append(
                    DiffLine(DiffLineType.ADDED, raw_line[1:], None, new_line)
                )
                new_line += 1
            elif raw_line.startswith("-"):
                current_hunk.lines.append(
                    DiffLine(DiffLineType.REMOVED, raw_line[1:], old_line, None)
                )
                old_line += 1
            elif raw_line.startswith(" ") or raw_line == "":
                content = raw_line[1:] if raw_line else ""
                current_hunk.lines.append(
                    DiffLine(DiffLineType.CONTEXT, content, old_line, new_line)
                )
                old_line += 1
                new_line += 1
            else:
                raise DiffParseError(f"Unexpected line inside a diff hunk: {raw_line[:80]}")
        return document


def parse_unified_diff(text: str) -> DiffDocument:
    return UnifiedDiffParser().parse(text)


def _hunk_is_complete(hunk: DiffHunk) -> bool:
    old_count = sum(
        line.line_type in {DiffLineType.CONTEXT, DiffLineType.REMOVED} for line in hunk.lines
    )
    new_count = sum(
        line.line_type in {DiffLineType.CONTEXT, DiffLineType.ADDED} for line in hunk.lines
    )
    return old_count >= hunk.old_count and new_count >= hunk.new_count


def _header_path(value: str) -> str | None:
    path_value = value.split("\t", 1)[0]
    if path_value == "/dev/null":
        return None
    return _decode_git_path(path_value)


def _decode_git_path(value: str, *, strip_prefix: bool = True) -> str:
    value = value.strip()
    if value.startswith('"'):
        value = _decode_quoted_path(value)
    if value.startswith("/"):
        raise DiffParseError("Diff contains an unsafe path")
    value = re.sub(r"/{2,}", "/", value)
    if strip_prefix and (value.startswith("a/") or value.startswith("b/")):
        value = value[2:]
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not value:
        raise DiffParseError("Diff contains an unsafe path")
    return str(path)


def _decode_quoted_path(value: str) -> str:
    if len(value) < 2 or not value.endswith('"'):
        raise DiffParseError("Diff contains an invalid quoted path")
    body = value[1:-1]
    decoded = bytearray()
    index = 0
    escapes = {
        "a": b"\a",
        "b": b"\b",
        "f": b"\f",
        "n": b"\n",
        "r": b"\r",
        "t": b"\t",
        "v": b"\v",
        "\\": b"\\",
        '"': b'"',
    }
    while index < len(body):
        character = body[index]
        if character != "\\":
            decoded.extend(character.encode("utf-8"))
            index += 1
            continue
        index += 1
        if index >= len(body):
            raise DiffParseError("Diff contains an invalid quoted path escape")
        escaped = body[index]
        if escaped in "01234567":
            end = index
            while end < min(len(body), index + 3) and body[end] in "01234567":
                end += 1
            octet = int(body[index:end], 8)
            if octet > 255:
                raise DiffParseError("Diff contains an invalid quoted path octet")
            decoded.append(octet)
            index = end
            continue
        replacement = escapes.get(escaped)
        if replacement is None:
            raise DiffParseError("Diff contains an unsupported quoted path escape")
        decoded.extend(replacement)
        index += 1
    return decoded.decode("utf-8", errors="replace")
