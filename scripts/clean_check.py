#!/usr/bin/env python3
"""Find or safely remove generated repository artifacts."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_DIRECTORIES = {
    ".mypy_cache",
    ".next",
    ".nox",
    ".nyc_output",
    ".playwright",
    ".pnpm-store",
    ".proofstack",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".turbo",
    ".venv",
    ".vite",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "env",
    "htmlcov",
    "node_modules",
    "playwright-report",
    "temp",
    "test-results",
    "tmp",
    "venv",
}
FORBIDDEN_DIRECTORY_SUFFIXES = (".egg-info",)
FORBIDDEN_FILE_NAMES = {
    ".coverage",
    ".eslintcache",
    ".DS_Store",
    "Thumbs.db",
    "coverage.xml",
}
FORBIDDEN_FILE_SUFFIXES = (
    ".db",
    ".log",
    ".pid",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".whl",
)
ARCHIVE_SUFFIXES = (".tar.gz", ".tar.bz2")


def validate_root() -> None:
    """Refuse to operate unless the expected repository markers are present."""
    required = (ROOT / "pyproject.toml", ROOT / "apps", ROOT / "packages")
    if ROOT.parent == ROOT or not all(path.exists() for path in required):
        raise RuntimeError(f"Refusing to inspect an unexpected root: {ROOT}")


def generated_paths() -> list[Path]:
    """Return generated paths without descending into matched directories."""
    found: list[Path] = []
    pending = [ROOT]
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            if path.name == ".git":
                continue
            if path.is_symlink():
                lowered = path.name.lower()
                if (
                    path.name in FORBIDDEN_DIRECTORIES
                    or path.name.endswith(FORBIDDEN_DIRECTORY_SUFFIXES)
                    or path.name in FORBIDDEN_FILE_NAMES
                    or lowered.endswith(FORBIDDEN_FILE_SUFFIXES)
                    or lowered.endswith(ARCHIVE_SUFFIXES)
                ):
                    found.append(path)
                continue
            if path.is_dir():
                if path.name in FORBIDDEN_DIRECTORIES or path.name.endswith(
                    FORBIDDEN_DIRECTORY_SUFFIXES
                ):
                    found.append(path)
                else:
                    pending.append(path)
                continue
            lowered = path.name.lower()
            if (
                path.name in FORBIDDEN_FILE_NAMES
                or lowered.endswith(FORBIDDEN_FILE_SUFFIXES)
                or lowered.endswith(ARCHIVE_SUFFIXES)
            ):
                found.append(path)
    return sorted(found, key=lambda item: item.relative_to(ROOT).as_posix())


def remove_generated(paths: list[Path]) -> None:
    """Remove only paths returned by the explicit generated-artifact matcher."""
    resolved_root = ROOT.resolve()
    for path in sorted(paths, key=lambda item: len(item.parts), reverse=True):
        resolved = path.resolve()
        if resolved_root not in resolved.parents:
            raise RuntimeError(f"Refusing to remove a path outside the repository: {path}")
        if path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        print(f"removed {path.relative_to(ROOT)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove matched generated artifacts before checking again.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_root()
    paths = generated_paths()
    if args.clean and paths:
        remove_generated(paths)
        paths = generated_paths()
    if paths:
        print("Repository cleanliness check failed. Generated artifacts remain:")
        for path in paths:
            print(f"  - {path.relative_to(ROOT)}")
        return 1
    print("Repository cleanliness check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
