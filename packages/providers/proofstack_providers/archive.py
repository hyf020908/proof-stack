"""Bounded ZIP extraction that rejects traversal, links, devices, and bombs."""

from __future__ import annotations

import shutil
import stat
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from .source import (
    PreparedSource,
    SourceLimits,
    SourcePreparationError,
    SourceRequest,
    SourceType,
    read_optional_diff,
    validate_source_tree,
)


class SafeZipExtractor:
    def extract(
        self, archive_path: Path, destination: Path, limits: SourceLimits
    ) -> dict[str, int]:
        resolved_archive = archive_path.resolve()
        if not resolved_archive.is_file():
            raise SourcePreparationError(
                "archive_not_found", "The selected ZIP archive does not exist."
            )
        if resolved_archive.stat().st_size > limits.max_repository_bytes:
            raise SourcePreparationError(
                "archive_too_large", "The ZIP archive exceeds the configured size limit."
            )
        destination.mkdir(parents=True, exist_ok=False)
        resolved_destination = destination.resolve()
        total_uncompressed = 0
        extracted_files = 0
        seen: set[str] = set()
        try:
            with zipfile.ZipFile(resolved_archive) as archive:
                infos = archive.infolist()
                if len(infos) > limits.max_file_count * 2:
                    raise SourcePreparationError(
                        "archive_entry_count_exceeded", "The ZIP archive contains too many entries."
                    )
                for info in infos:
                    relative = _safe_member_path(info.filename)
                    if relative is None:
                        continue
                    normalized = unicodedata.normalize("NFC", relative.as_posix()).casefold()
                    if normalized in seen:
                        raise SourcePreparationError(
                            "duplicate_archive_path",
                            "The ZIP archive contains duplicate file paths.",
                        )
                    seen.add(normalized)
                    mode = info.external_attr >> 16
                    file_type = stat.S_IFMT(mode)
                    if file_type == stat.S_IFLNK:
                        raise SourcePreparationError(
                            "archive_symlink", "Symbolic links are not accepted in ZIP archives."
                        )
                    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                        raise SourcePreparationError(
                            "archive_special_file",
                            "Special files are not accepted in ZIP archives.",
                        )
                    if info.flag_bits & 0x1:
                        raise SourcePreparationError(
                            "encrypted_archive", "Encrypted ZIP entries are not supported."
                        )
                    total_uncompressed += info.file_size
                    if info.file_size > limits.max_file_bytes:
                        raise SourcePreparationError(
                            "archive_file_too_large", f"The archive entry {relative} is too large."
                        )
                    if total_uncompressed > limits.max_repository_bytes:
                        raise SourcePreparationError(
                            "archive_expansion_too_large",
                            "The expanded ZIP exceeds the repository size limit.",
                        )
                    if (
                        info.compress_size > 0
                        and info.file_size / info.compress_size > limits.max_archive_ratio
                    ):
                        raise SourcePreparationError(
                            "archive_compression_ratio",
                            "The ZIP archive has a suspicious compression ratio.",
                        )
                    target = (resolved_destination / relative).resolve()
                    try:
                        target.relative_to(resolved_destination)
                    except ValueError as exc:
                        raise SourcePreparationError(
                            "zip_slip", "The ZIP archive contains a path traversal entry."
                        ) from exc
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    extracted_files += 1
                    if extracted_files > limits.max_file_count:
                        raise SourcePreparationError(
                            "file_count_exceeded", "The expanded ZIP contains too many files."
                        )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    remaining = info.file_size
                    with archive.open(info, "r") as source, target.open("xb") as output:
                        while remaining:
                            chunk = source.read(min(1024 * 1024, remaining))
                            if not chunk:
                                break
                            output.write(chunk)
                            remaining -= len(chunk)
                    if remaining != 0:
                        raise SourcePreparationError(
                            "truncated_archive_entry", "A ZIP entry ended before its declared size."
                        )
        except zipfile.BadZipFile as exc:
            raise SourcePreparationError(
                "invalid_archive", "The uploaded file is not a valid ZIP archive."
            ) from exc
        return {"file_count": extracted_files, "repository_bytes": total_uncompressed}


class SafeZipSourceProvider:
    def __init__(self, extractor: SafeZipExtractor | None = None) -> None:
        self.extractor = extractor or SafeZipExtractor()

    def prepare(self, request: SourceRequest) -> PreparedSource:
        if request.archive_path is None:
            raise SourcePreparationError("archive_missing", "A ZIP archive is required.")
        parent = request.destination_parent.resolve() if request.destination_parent else None
        temporary_root = Path(tempfile.mkdtemp(prefix="proofstack-source-", dir=parent))
        destination = temporary_root / "repository"
        try:
            stats = self.extractor.extract(request.archive_path, destination, request.limits)
            root = _single_root(destination)
            validate_source_tree(root, request.limits)
            diff_text = read_optional_diff(request.diff_path, request.limits.max_diff_bytes)
            return PreparedSource(
                root=root,
                source_type=SourceType.ZIP,
                source_reference=request.archive_path.name,
                diff_text=diff_text,
                metadata=stats,
                cleanup_path=temporary_root,
            )
        except Exception:
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise


def _safe_member_path(name: str) -> PurePosixPath | None:
    if "\x00" in name or len(name) > 1024:
        raise SourcePreparationError("invalid_archive_path", "A ZIP entry has an invalid filename.")
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized in {".", "./"}:
        return None
    if path.is_absolute() or ".." in path.parts or re_drive_prefix(normalized):
        raise SourcePreparationError("zip_slip", "The ZIP archive contains a path traversal entry.")
    if any(part in {"", "."} for part in path.parts):
        raise SourcePreparationError(
            "invalid_archive_path", "A ZIP entry has an ambiguous filename."
        )
    reserved = {
        "aux",
        "com1",
        "com2",
        "com3",
        "com4",
        "com5",
        "com6",
        "com7",
        "com8",
        "com9",
        "con",
        "lpt1",
        "lpt2",
        "lpt3",
        "lpt4",
        "lpt5",
        "lpt6",
        "lpt7",
        "lpt8",
        "lpt9",
        "nul",
        "prn",
    }
    for part in path.parts:
        stem = part.rstrip(" .").split(".", 1)[0].casefold()
        if (
            len(part.encode("utf-8")) > 255
            or any(ord(character) < 32 for character in part)
            or ":" in part
            or part.endswith((" ", "."))
            or stem in reserved
        ):
            raise SourcePreparationError(
                "invalid_archive_path", "A ZIP entry has a non-portable filename."
            )
    return path


def re_drive_prefix(value: str) -> bool:
    return len(value) >= 2 and value[0].isalpha() and value[1] == ":"


def _single_root(destination: Path) -> Path:
    children = [item for item in destination.iterdir() if item.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return destination
