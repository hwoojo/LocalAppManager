"""Atomic file creation and exact-path rollback helpers."""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from .errors import LocalAppError


class FileCreationError(LocalAppError):
    pass


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def managed_hashes(paths: Iterable[Path]) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for path in paths:
        if path.is_file() and not path.is_symlink():
            result.append((str(path), sha256_file(path)))
    return tuple(result)


class CreationTransaction:
    """Track only paths created by one registration and undo them in reverse."""

    def __init__(self) -> None:
        self._created: list[tuple[Path, bool]] = []
        self._committed = False

    def record_file(self, path: Path) -> None:
        self._created.append((path, False))

    def record_directory(self, path: Path) -> None:
        self._created.append((path, True))

    @property
    def created_paths(self) -> tuple[Path, ...]:
        return tuple(path for path, _ in self._created)

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        failures: list[str] = []
        for path, is_directory in reversed(self._created):
            try:
                if is_directory:
                    path.rmdir()
                else:
                    path.unlink(missing_ok=True)
            except OSError as exc:
                failures.append(f"{path}: {exc}")
        if failures:
            raise FileCreationError("rollback could not remove: " + "; ".join(failures))

    def __enter__(self) -> "CreationTransaction":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if not self._committed:
            self.rollback()
        return False


def ensure_private_directory(path: Path, transaction: CreationTransaction) -> None:
    """Create one app-owned directory, refusing any pre-existing path."""

    try:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise FileCreationError(f"managed path already exists: {path}") from exc
    transaction.record_directory(path)


def _prepare_parent(path: Path) -> None:
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)


def _publish_temporary(temporary_path: Path, destination: Path) -> None:
    published = False
    try:
        os.link(temporary_path, destination)
        published = True
    except FileExistsError as exc:
        raise FileCreationError(
            f"refusing to overwrite existing path: {destination}"
        ) from exc
    finally:
        temporary_path.unlink(missing_ok=True)
    if published:
        descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic_copy(
    source: Path,
    destination: Path,
    *,
    mode: int,
    transaction: CreationTransaction,
) -> None:
    _prepare_parent(destination)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            with source.open("rb") as source_file:
                shutil.copyfileobj(source_file, temporary)
            temporary.flush()
            os.fchmod(temporary.fileno(), mode)
            os.fsync(temporary.fileno())
        _publish_temporary(temporary_path, destination)
        temporary_path = None
        transaction.record_file(destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def atomic_write_text(
    destination: Path,
    content: str,
    *,
    mode: int,
    transaction: CreationTransaction,
) -> None:
    _prepare_parent(destination)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fchmod(temporary.fileno(), mode)
            os.fsync(temporary.fileno())
        _publish_temporary(temporary_path, destination)
        temporary_path = None
        transaction.record_file(destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def create_symlink(
    destination: Path,
    target: str,
    *,
    transaction: CreationTransaction,
) -> None:
    _prepare_parent(destination)
    try:
        destination.symlink_to(target)
    except FileExistsError as exc:
        raise FileCreationError(
            f"refusing to overwrite existing path: {destination}"
        ) from exc
    transaction.record_file(destination)


def paths_are_available(paths: Iterable[Path]) -> bool:
    return all(not path.exists() and not path.is_symlink() for path in paths)


def atomic_replace_many(changes: Mapping[Path, tuple[bytes, int]]) -> None:
    """Best-effort transactional replacement of a small set of regular files."""

    prepared: dict[Path, Path] = {}
    states: list[tuple[Path, Path | None]] = []
    try:
        for destination, (content, mode) in changes.items():
            _prepare_parent(destination)
            if destination.exists() and destination.is_dir():
                raise FileCreationError(f"cannot replace directory: {destination}")
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".new",
                delete=False,
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fchmod(temporary.fileno(), mode)
                os.fsync(temporary.fileno())
                prepared[destination] = Path(temporary.name)

        for destination, temporary_path in prepared.items():
            backup: Path | None = None
            if destination.exists() or destination.is_symlink():
                descriptor, backup_name = tempfile.mkstemp(
                    dir=destination.parent,
                    prefix=f".{destination.name}.",
                    suffix=".backup",
                )
                os.close(descriptor)
                backup = Path(backup_name)
                backup.unlink()
                os.replace(destination, backup)
            states.append((destination, backup))
            os.replace(temporary_path, destination)
            prepared[destination] = Path()

        for _, backup in states:
            if backup is not None:
                backup.unlink(missing_ok=True)
        for directory in {path.parent for path in changes}:
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except Exception as original_error:
        rollback_failures: list[str] = []
        for destination, backup in reversed(states):
            try:
                destination.unlink(missing_ok=True)
                if backup is not None:
                    os.replace(backup, destination)
            except OSError as exc:
                rollback_failures.append(f"{destination}: {exc}")
        if rollback_failures:
            raise FileCreationError(
                f"replacement failed ({original_error}); rollback failed: "
                + "; ".join(rollback_failures)
            ) from original_error
        raise
    finally:
        for temporary_path in prepared.values():
            if temporary_path != Path():
                temporary_path.unlink(missing_ok=True)
        for _, backup in states:
            if backup is not None:
                backup.unlink(missing_ok=True)
