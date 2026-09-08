"""Independent health checks for registered applications."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from .desktop import build_desktop_entry, build_wrapper
from .editing import edit_app
from .fileops import sha256_file
from .models import AppManifest
from .removal import build_removal_plan
from .storage import ManifestStore


@dataclass(frozen=True, slots=True)
class DoctorIssue:
    severity: str
    code: str
    app_id: str
    message: str
    repairable: bool = False


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checked: tuple[str, ...]
    issues: tuple[DoctorIssue, ...]


def _exists(path: str | Path) -> bool:
    candidate = Path(path)
    return candidate.exists() or candidate.is_symlink()


def diagnose(store: ManifestStore, app_id: str | None = None) -> DoctorReport:
    directory = store.paths.manifest_dir
    paths = (
        [store.manifest_path(app_id)]
        if app_id is not None
        else sorted(directory.glob("*.json")) if directory.exists() else []
    )
    issues: list[DoctorIssue] = []
    manifests: list[AppManifest] = []
    embedded_ids: dict[str, list[Path]] = {}
    checked: list[str] = []
    for path in paths:
        stem = path.stem
        checked.append(stem)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            embedded = raw.get("app_id") if isinstance(raw, dict) else None
            if isinstance(embedded, str):
                embedded_ids.setdefault(embedded, []).append(path)
            if isinstance(raw, dict) and raw.get("schema_version") != AppManifest.CURRENT_SCHEMA_VERSION:
                issues.append(
                    DoctorIssue(
                        "warning",
                        "migration-needed",
                        stem,
                        f"manifest uses schema {raw.get('schema_version')}",
                        True,
                    )
                )
            manifest = store.load(stem)
            manifests.append(manifest)
        except Exception as exc:
            issues.append(DoctorIssue("error", "corrupt-manifest", stem, str(exc)))

    for duplicate_id, duplicate_paths in embedded_ids.items():
        if len(duplicate_paths) > 1:
            issues.append(
                DoctorIssue(
                    "error",
                    "duplicate-id",
                    duplicate_id,
                    "same embedded ID appears in: "
                    + ", ".join(str(path) for path in duplicate_paths),
                )
            )

    for manifest in manifests:
        executable = Path(manifest.command[0])
        if not executable.exists():
            issues.append(
                DoctorIssue("error", "executable-missing", manifest.app_id, str(executable))
            )
        elif not os.access(executable, os.X_OK):
            issues.append(
                DoctorIssue("error", "executable-not-executable", manifest.app_id, str(executable))
            )
        if manifest.icon_path and not _exists(manifest.icon_path):
            issues.append(DoctorIssue("warning", "icon-missing", manifest.app_id, manifest.icon_path))
        if manifest.installed_path and not _exists(manifest.installed_path):
            issues.append(
                DoctorIssue("error", "installed-path-missing", manifest.app_id, manifest.installed_path)
            )
        for external in manifest.external_paths:
            if not _exists(external):
                issues.append(
                    DoctorIssue("warning", "external-path-missing", manifest.app_id, external)
                )
        for managed in manifest.managed_files:
            if not _exists(managed):
                issues.append(
                    DoctorIssue("warning", "managed-path-missing", manifest.app_id, managed)
                )
        for managed, expected_hash in manifest.managed_file_hashes:
            managed_path = Path(managed)
            if managed_path.is_file() and not managed_path.is_symlink():
                try:
                    actual_hash = sha256_file(managed_path)
                except OSError as exc:
                    issues.append(
                        DoctorIssue("error", "managed-file-unreadable", manifest.app_id, str(exc))
                    )
                else:
                    if actual_hash != expected_hash:
                        issues.append(
                            DoctorIssue(
                                "warning",
                                "managed-file-modified",
                                manifest.app_id,
                                managed,
                            )
                        )
        unsafe = build_removal_plan(store, manifest.app_id).unsafe_paths
        for path in unsafe:
            issues.append(
                DoctorIssue("error", "unsafe-managed-path", manifest.app_id, str(path))
            )

        if not manifest.integration_managed:
            if manifest.desktop_entry_path and not _exists(manifest.desktop_entry_path):
                issues.append(
                    DoctorIssue(
                        "warning",
                        "external-desktop-missing",
                        manifest.app_id,
                        manifest.desktop_entry_path,
                    )
                )
            continue
        wrapper = store.paths.wrapper_path(manifest.app_id)
        expected_wrapper = build_wrapper(manifest.command)
        if not wrapper.exists():
            issues.append(
                DoctorIssue("warning", "wrapper-missing", manifest.app_id, str(wrapper), True)
            )
        elif not wrapper.is_file() or wrapper.is_symlink():
            issues.append(
                DoctorIssue("error", "wrapper-conflict", manifest.app_id, str(wrapper))
            )
        elif wrapper.read_text(encoding="utf-8", errors="replace") != expected_wrapper:
            issues.append(
                DoctorIssue("warning", "wrapper-mismatch", manifest.app_id, str(wrapper), True)
            )
        desktop = store.paths.desktop_entry_path(manifest.app_id)
        expected_desktop = build_desktop_entry(
            name=manifest.name,
            wrapper_path=wrapper,
            icon_path=Path(manifest.icon_path) if manifest.icon_path else None,
            terminal=manifest.terminal,
            categories=manifest.categories,
            startup_notify=manifest.startup_notify,
            mime_types=manifest.mime_types,
            desktop_argument=manifest.desktop_argument,
        )
        if not desktop.exists():
            issues.append(
                DoctorIssue("warning", "desktop-missing", manifest.app_id, str(desktop), True)
            )
        elif not desktop.is_file() or desktop.is_symlink():
            issues.append(
                DoctorIssue("error", "desktop-conflict", manifest.app_id, str(desktop))
            )
        elif desktop.read_text(encoding="utf-8", errors="replace") != expected_desktop:
            issues.append(
                DoctorIssue("warning", "desktop-mismatch", manifest.app_id, str(desktop), True)
            )
    return DoctorReport(tuple(checked), tuple(issues))


def repair(store: ManifestStore, app_id: str | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    report = diagnose(store, app_id)
    corrupt = {issue.app_id for issue in report.issues if issue.code == "corrupt-manifest"}
    repaired: list[str] = []
    failures: list[str] = []
    for candidate in report.checked:
        if candidate in corrupt:
            continue
        try:
            edit_app(store, candidate)
            repaired.append(candidate)
        except Exception as exc:
            failures.append(f"{candidate}: {exc}")
    return tuple(repaired), tuple(failures)
