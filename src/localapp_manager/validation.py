"""Filesystem validation shared by importers and runners."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import LocalAppError
from .models import AppKind


class SourceValidationError(LocalAppError):
    pass


def absolute_user_path(path: str | Path) -> Path:
    """Expand a user path without dereferencing a meaningful symlink."""

    return Path(path).expanduser().absolute()


def validate_executable_source(path: str | Path) -> Path:
    source = absolute_user_path(path)
    if not source.exists():
        raise SourceValidationError(f"source does not exist: {source}")
    if not source.is_file():
        raise SourceValidationError(f"source is not a regular file: {source}")
    if not os.access(source, os.X_OK):
        raise SourceValidationError(f"source is not executable: {source}")
    return source


def validate_working_directory(path: str | Path) -> Path:
    directory = absolute_user_path(path)
    if not directory.exists():
        raise SourceValidationError(f"working directory does not exist: {directory}")
    if not directory.is_dir():
        raise SourceValidationError(f"working directory is not a directory: {directory}")
    return directory


def detect_file_kind(source: Path, requested: str = "auto") -> AppKind:
    if requested == "auto":
        return AppKind.APPIMAGE if source.name.lower().endswith(".appimage") else AppKind.EXECUTABLE
    try:
        kind = AppKind(requested)
    except ValueError as exc:
        raise SourceValidationError(f"unsupported linked file kind: {requested}") from exc
    if kind not in (AppKind.APPIMAGE, AppKind.EXECUTABLE):
        raise SourceValidationError(f"unsupported linked file kind: {requested}")
    return kind

