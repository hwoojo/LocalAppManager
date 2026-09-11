"""Manifest-driven removal planning and conservative execution."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .errors import LocalAppError
from .models import AppManifest
from .storage import ManifestStore


class RemovalError(LocalAppError):
    pass


@dataclass(frozen=True, slots=True)
class RemovalTarget:
    path: Path
    role: str
    exists: bool


@dataclass(frozen=True, slots=True)
class RemovalPlan:
    manifest: AppManifest
    targets: tuple[RemovalTarget, ...]
    preserved_external: tuple[Path, ...]
    unsafe_paths: tuple[Path, ...]

    @property
    def existing_targets(self) -> tuple[RemovalTarget, ...]:
        return tuple(target for target in self.targets if target.exists)

    @property
    def missing_targets(self) -> tuple[RemovalTarget, ...]:
        return tuple(target for target in self.targets if not target.exists)


@dataclass(frozen=True, slots=True)
class RemovalResult:
    removed: tuple[Path, ...]
    already_missing: tuple[Path, ...]
    failed: tuple[tuple[Path, str], ...]
    manifest_removed: bool


def _absolute_lexical(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _safe_role(store: ManifestStore, manifest: AppManifest, path: Path) -> str | None:
    paths = store.paths
    if path == _absolute_lexical(paths.wrapper_path(manifest.app_id)):
        return "wrapper"
    if (
        manifest.desktop_entry_path is not None
        and path == _absolute_lexical(manifest.desktop_entry_path)
        and path == _absolute_lexical(paths.desktop_entry_path(manifest.app_id))
    ):
        return "desktop-entry"
    if manifest.icon_path is not None and path == _absolute_lexical(manifest.icon_path):
        icon_root = _absolute_lexical(paths.icon_dir / "localapp-manager")
        if _is_within(path, icon_root) and path.stem == manifest.app_id:
            return "icon"
    app_root = _absolute_lexical(paths.managed_app_dir(manifest.app_id))
    if _is_within(path, app_root):
        return "managed-app"
    return None


def build_removal_plan(store: ManifestStore, app_id: str) -> RemovalPlan:
    manifest = store.load(app_id)
    targets: list[RemovalTarget] = []
    unsafe: list[Path] = []
    seen: set[Path] = set()
    for raw_path in manifest.managed_files:
        path = _absolute_lexical(raw_path)
        if path in seen:
            continue
        seen.add(path)
        role = _safe_role(store, manifest, path)
        if role is None:
            unsafe.append(path)
            continue
        exists = path.exists() or path.is_symlink()
        targets.append(RemovalTarget(path=path, role=role, exists=exists))
    return RemovalPlan(
        manifest=manifest,
        targets=tuple(targets),
        preserved_external=tuple(
            _absolute_lexical(path) for path in manifest.external_paths
        ),
        unsafe_paths=tuple(unsafe),
    )


def execute_removal(store: ManifestStore, plan: RemovalPlan) -> RemovalResult:
    if plan.unsafe_paths:
        raise RemovalError("removal blocked by unsafe managed paths")
    current = store.load(plan.manifest.app_id)
    if current != plan.manifest:
        raise RemovalError("manifest changed after the removal plan was created")

    present = [target for target in plan.targets if target.exists]
    present.sort(
        key=lambda target: (
            1 if target.path.is_dir() and not target.path.is_symlink() else 0,
            -len(target.path.parts),
        )
    )
    removed: list[Path] = []
    failed: list[tuple[Path, str]] = []
    for target in present:
        try:
            if target.path.is_dir() and not target.path.is_symlink():
                target.path.rmdir()
            else:
                target.path.unlink(missing_ok=True)
            removed.append(target.path)
        except OSError as exc:
            failed.append((target.path, str(exc)))

    manifest_removed = False
    if not failed:
        store.delete_manifest(plan.manifest.app_id)
        manifest_removed = True
    return RemovalResult(
        removed=tuple(removed),
        already_missing=tuple(target.path for target in plan.missing_targets),
        failed=tuple(failed),
        manifest_removed=manifest_removed,
    )
