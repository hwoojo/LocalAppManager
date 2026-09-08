"""Atomic, per-application JSON manifest persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .errors import LocalAppError
from .migrations import migrate_manifest_data
from .models import AppManifest, ManifestValidationError
from .paths import AppPaths


class ManifestStoreError(LocalAppError):
    """Base class for manifest persistence failures."""


class ManifestNotFoundError(ManifestStoreError):
    pass


class DuplicateManifestError(ManifestStoreError):
    pass


class CorruptManifestError(ManifestStoreError):
    pass


class ManifestStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def manifest_path(self, app_id: str) -> Path:
        # AppManifest owns full validation; this guard also prevents traversal
        # before a manifest object exists.
        if not app_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in app_id):
            raise ValueError("invalid application ID")
        if app_id.startswith("-") or app_id.endswith("-") or "--" in app_id:
            raise ValueError("invalid application ID")
        return self.paths.manifest_dir / f"{app_id}.json"

    def save(self, manifest: AppManifest, *, overwrite: bool = False) -> Path:
        directory = self.paths.ensure_manifest_dir()
        destination = self.manifest_path(manifest.app_id)
        payload = json.dumps(
            manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n"

        temporary_path: Path | None = None
        created_destination = False
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=f".{manifest.app_id}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())

            if overwrite:
                os.replace(temporary_path, destination)
                temporary_path = None
            else:
                try:
                    os.link(temporary_path, destination)
                    created_destination = True
                except FileExistsError as exc:
                    raise DuplicateManifestError(
                        f"application ID already exists: {manifest.app_id}"
                    ) from exc
            self._fsync_directory(directory)
            return destination
        except Exception:
            if created_destination:
                destination.unlink(missing_ok=True)
                try:
                    self._fsync_directory(directory)
                except OSError:
                    pass
            raise
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load(self, app_id: str) -> AppManifest:
        path = self.manifest_path(app_id)
        try:
            with path.open("r", encoding="utf-8") as manifest_file:
                data = json.load(manifest_file)
            migrated_data, _ = migrate_manifest_data(
                data, target_version=AppManifest.CURRENT_SCHEMA_VERSION
            )
            manifest = AppManifest.from_dict(migrated_data)
        except FileNotFoundError as exc:
            raise ManifestNotFoundError(f"application not found: {app_id}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError, ManifestValidationError) as exc:
            raise CorruptManifestError(f"invalid manifest {path}: {exc}") from exc
        if manifest.app_id != app_id:
            raise CorruptManifestError(
                f"manifest ID {manifest.app_id!r} does not match filename {app_id!r}"
            )
        return manifest

    def list_ids(self) -> tuple[str, ...]:
        if not self.paths.manifest_dir.exists():
            return ()
        return tuple(sorted(path.stem for path in self.paths.manifest_dir.glob("*.json")))

    def list_manifests(self) -> tuple[AppManifest, ...]:
        return tuple(self.load(app_id) for app_id in self.list_ids())

    def delete_manifest(self, app_id: str) -> None:
        path = self.manifest_path(app_id)
        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise ManifestNotFoundError(f"application not found: {app_id}") from exc
        self._fsync_directory(path.parent)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
