"""Registration that reuses desktop integration owned by another manager."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..models import AppKind, AppManifest, InstallMode
from ..identifiers import generate_app_id
from ..storage import ManifestStore
from ..validation import absolute_user_path


def register_external_integration(
    store: ManifestStore,
    source: str | Path,
    *,
    name: str,
    kind: AppKind,
    command: Sequence[str],
    desktop_entry: str | Path | None = None,
    icon: str | Path | None = None,
    terminal: bool = False,
    categories: Sequence[str] = ("Utility",),
    startup_notify: bool = True,
    working_directory: str | Path | None = None,
) -> AppManifest:
    source_path = absolute_user_path(source)
    if not source_path.exists():
        raise ValueError(f"external application source does not exist: {source_path}")
    if not command:
        raise ValueError("external application command must not be empty")
    desktop_path = absolute_user_path(desktop_entry) if desktop_entry else None
    icon_path = absolute_user_path(icon) if icon else None
    selected_id = generate_app_id(name, store.list_ids())
    external_paths = [str(source_path)]
    for path in (desktop_path, icon_path):
        if path is not None and str(path) not in external_paths:
            external_paths.append(str(path))
    manifest = AppManifest(
        app_id=selected_id,
        name=name,
        kind=kind,
        install_mode=InstallMode.LINKED,
        source_path=str(source_path),
        command=tuple(command),
        icon_path=str(icon_path) if icon_path else None,
        desktop_entry_path=str(desktop_path) if desktop_path else None,
        managed_files=(),
        external_paths=tuple(external_paths),
        working_directory=(
            str(absolute_user_path(working_directory)) if working_directory else None
        ),
        terminal=terminal,
        categories=tuple(categories),
        startup_notify=startup_notify,
        integration_managed=False,
    )
    store.save(manifest)
    return manifest
