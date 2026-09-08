"""Safe edits that keep manifest, wrapper, and desktop entry synchronized."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from .desktop import build_desktop_entry, build_wrapper
from .errors import LocalAppError
from .fileops import atomic_replace_many, sha256_bytes
from .models import AppKind, AppManifest, ManifestValidationError
from .removal import build_removal_plan
from .storage import ManifestStore
from .validation import validate_working_directory


class EditError(LocalAppError):
    pass


UNSET = object()


def _manifest_bytes(manifest: AppManifest) -> bytes:
    return (
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _command_base_length(manifest: AppManifest) -> int:
    if manifest.kind is not AppKind.PYTHON_PROJECT:
        return 1
    return 3 if manifest.python_entry_type == "module" else 2


def _ensure_integration_path_is_owned(
    path: Path, manifest: AppManifest, expected_current: bytes
) -> None:
    if str(path) in manifest.managed_files or not (path.exists() or path.is_symlink()):
        return
    if path.is_file() and not path.is_symlink() and path.read_bytes() == expected_current:
        return
    raise EditError(f"refusing to replace untracked integration path: {path}")


def edit_app(
    store: ManifestStore,
    app_id: str,
    *,
    name: str | None = None,
    arguments: Sequence[str] | None = None,
    working_directory: str | Path | None | object = UNSET,
    terminal: bool | None = None,
    categories: Sequence[str] | None = None,
    startup_notify: bool | None = None,
    mime_types: Sequence[str] | None = None,
    desktop_argument: str | None | object = UNSET,
) -> AppManifest:
    current = store.load(app_id)
    if not current.integration_managed:
        raise EditError("settings are owned by an external desktop integration")
    if build_removal_plan(store, app_id).unsafe_paths:
        raise EditError("cannot edit a manifest containing unsafe managed paths")
    wrapper_path = store.paths.wrapper_path(app_id)
    desktop_path = store.paths.desktop_entry_path(app_id)
    current_wrapper = build_wrapper(current.command).encode("utf-8")
    current_desktop = build_desktop_entry(
        name=current.name,
        wrapper_path=wrapper_path,
        icon_path=Path(current.icon_path) if current.icon_path else None,
        terminal=current.terminal,
        categories=current.categories,
        startup_notify=current.startup_notify,
        mime_types=current.mime_types,
        desktop_argument=current.desktop_argument,
    ).encode("utf-8")
    _ensure_integration_path_is_owned(wrapper_path, current, current_wrapper)
    _ensure_integration_path_is_owned(desktop_path, current, current_desktop)

    new_name = current.name if name is None else name.strip()
    if not new_name:
        raise EditError("application name must not be empty")
    if arguments is None:
        new_command = current.command
    else:
        base_length = _command_base_length(current)
        new_command = (*current.command[:base_length], *tuple(arguments))
    if working_directory is UNSET:
        new_working = current.working_directory
    elif working_directory is None:
        new_working = None
    else:
        new_working = str(validate_working_directory(working_directory))

    managed_files = list(current.managed_files)
    for path in (wrapper_path, desktop_path):
        if str(path) not in managed_files:
            managed_files.append(str(path))
    new_wrapper_bytes = build_wrapper(new_command).encode("utf-8")
    new_desktop_bytes = build_desktop_entry(
        name=new_name,
        wrapper_path=wrapper_path,
        icon_path=Path(current.icon_path) if current.icon_path else None,
        terminal=current.terminal if terminal is None else terminal,
        categories=current.categories if categories is None else tuple(categories),
        startup_notify=current.startup_notify if startup_notify is None else startup_notify,
        mime_types=current.mime_types if mime_types is None else tuple(mime_types),
        desktop_argument=(
            current.desktop_argument if desktop_argument is UNSET else desktop_argument
        ),
    ).encode("utf-8")
    hashes: list[tuple[str, str]] = []
    current_hashes = dict(current.managed_file_hashes)
    for managed in managed_files:
        managed_path = Path(managed)
        if managed_path == wrapper_path:
            hashes.append((managed, sha256_bytes(new_wrapper_bytes)))
        elif managed_path == desktop_path:
            hashes.append((managed, sha256_bytes(new_desktop_bytes)))
        elif managed in current_hashes:
            hashes.append((managed, current_hashes[managed]))
    try:
        updated = replace(
            current,
            name=new_name,
            command=new_command,
            working_directory=new_working,
            terminal=current.terminal if terminal is None else terminal,
            categories=current.categories if categories is None else tuple(categories),
            startup_notify=(
                current.startup_notify if startup_notify is None else startup_notify
            ),
            mime_types=current.mime_types if mime_types is None else tuple(mime_types),
            desktop_argument=(
                current.desktop_argument if desktop_argument is UNSET else desktop_argument
            ),
            desktop_entry_path=str(desktop_path),
            managed_files=tuple(managed_files),
            managed_file_hashes=tuple(hashes),
            schema_version=AppManifest.CURRENT_SCHEMA_VERSION,
        )
    except ManifestValidationError as exc:
        raise EditError(str(exc)) from exc

    changes = {
        wrapper_path: (new_wrapper_bytes, 0o755),
        desktop_path: (new_desktop_bytes, 0o644),
        store.manifest_path(app_id): (_manifest_bytes(updated), 0o600),
    }
    atomic_replace_many(changes)
    return updated
