"""Managed and linked registration for AppImages and executable files."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import re

from ..desktop import build_desktop_entry, build_wrapper
from ..errors import LocalAppError
from ..fileops import (
    CreationTransaction,
    atomic_copy,
    atomic_write_text,
    ensure_private_directory,
    managed_hashes,
    paths_are_available,
)
from ..identifiers import generate_app_id
from ..models import AppKind, AppManifest, InstallMode, ManifestValidationError
from ..storage import ManifestStore
from ..validation import (
    SourceValidationError,
    absolute_user_path,
    detect_file_kind,
    validate_executable_source,
    validate_working_directory,
)


class RegistrationError(LocalAppError):
    pass


def _default_name(source: Path, kind: AppKind) -> str:
    if kind is AppKind.APPIMAGE and source.name.lower().endswith(".appimage"):
        return source.name[: -len(".appimage")]
    return source.stem or source.name


def _icon_suffix(icon: Path) -> str:
    suffix = icon.suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else ".icon"


def _validate_icon(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    icon = absolute_user_path(path)
    if not icon.exists():
        raise SourceValidationError(f"icon does not exist: {icon}")
    if not icon.is_file():
        raise SourceValidationError(f"icon is not a regular file: {icon}")
    return icon


def _reserved_paths(
    store: ManifestStore,
    app_id: str,
    mode: InstallMode,
    icon_suffix: str | None,
) -> tuple[Path, ...]:
    paths = [
        store.paths.wrapper_path(app_id),
        store.paths.desktop_entry_path(app_id),
    ]
    if mode is InstallMode.MANAGED:
        paths.append(store.paths.managed_app_dir(app_id))
    if icon_suffix is not None:
        paths.append(store.paths.managed_icon_path(app_id, icon_suffix))
    return tuple(paths)


def _select_id(
    store: ManifestStore,
    name: str,
    explicit_id: str | None,
    mode: InstallMode,
    icon_suffix: str | None,
) -> str:
    if explicit_id is not None:
        store.manifest_path(explicit_id)
        if explicit_id in store.list_ids() or not paths_are_available(
            _reserved_paths(store, explicit_id, mode, icon_suffix)
        ):
            raise RegistrationError(
                f"application ID or managed path already exists: {explicit_id}"
            )
        return explicit_id

    occupied = set(store.list_ids())
    while True:
        candidate = generate_app_id(name, occupied)
        if paths_are_available(_reserved_paths(store, candidate, mode, icon_suffix)):
            return candidate
        occupied.add(candidate)


def register_file(
    store: ManifestStore,
    source: str | Path,
    *,
    mode: str = "linked",
    name: str | None = None,
    app_id: str | None = None,
    kind: str = "auto",
    arguments: Sequence[str] = (),
    working_directory: str | Path | None = None,
    terminal: bool = False,
    icon: str | Path | None = None,
    categories: Sequence[str] = ("Utility",),
    startup_notify: bool = True,
    mime_types: Sequence[str] = (),
    desktop_argument: str | None = None,
) -> AppManifest:
    source_path = validate_executable_source(source)
    app_kind = detect_file_kind(source_path, kind)
    try:
        install_mode = InstallMode(mode)
    except ValueError as exc:
        raise RegistrationError(f"unsupported install mode: {mode}") from exc
    display_name = (
        _default_name(source_path, app_kind) if name is None else name.strip()
    )
    if not display_name:
        raise SourceValidationError("application name must not be empty")
    icon_source = _validate_icon(icon)
    suffix = _icon_suffix(icon_source) if icon_source is not None else None
    selected_id = _select_id(store, display_name, app_id, install_mode, suffix)
    working_path = (
        validate_working_directory(working_directory)
        if working_directory is not None
        else None
    )

    with CreationTransaction() as transaction:
        if install_mode is InstallMode.MANAGED:
            app_directory = store.paths.managed_app_dir(selected_id)
            app_directory.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            ensure_private_directory(app_directory, transaction)
            executable_path = app_directory / source_path.name
            source_mode = source_path.stat().st_mode & 0o777
            atomic_copy(
                source_path,
                executable_path,
                mode=source_mode | 0o100,
                transaction=transaction,
            )
            installed_path: Path | None = executable_path
        else:
            executable_path = source_path
            installed_path = None

        icon_path: Path | None = None
        if icon_source is not None and suffix is not None:
            icon_path = store.paths.managed_icon_path(selected_id, suffix)
            atomic_copy(icon_source, icon_path, mode=0o644, transaction=transaction)

        command = (str(executable_path), *tuple(arguments))
        wrapper_path = store.paths.wrapper_path(selected_id)
        atomic_write_text(
            wrapper_path,
            build_wrapper(command),
            mode=0o755,
            transaction=transaction,
        )
        desktop_path = store.paths.desktop_entry_path(selected_id)
        atomic_write_text(
            desktop_path,
            build_desktop_entry(
                name=display_name,
                wrapper_path=wrapper_path,
                icon_path=icon_path,
                terminal=terminal,
                categories=categories,
                startup_notify=startup_notify,
                mime_types=mime_types,
                desktop_argument=desktop_argument,
            ),
            mode=0o644,
            transaction=transaction,
        )

        external_paths = [str(source_path)]
        if icon_source is not None and str(icon_source) not in external_paths:
            external_paths.append(str(icon_source))
        if working_path is not None and str(working_path) not in external_paths:
            external_paths.append(str(working_path))
        try:
            manifest = AppManifest(
                app_id=selected_id,
                name=display_name,
                kind=app_kind,
                install_mode=install_mode,
                source_path=str(source_path),
                installed_path=str(installed_path)
                if installed_path is not None
                else None,
                command=command,
                icon_path=str(icon_path) if icon_path is not None else None,
                desktop_entry_path=str(desktop_path),
                managed_files=tuple(str(path) for path in transaction.created_paths),
                managed_file_hashes=managed_hashes(transaction.created_paths),
                external_paths=tuple(external_paths),
                working_directory=str(working_path)
                if working_path is not None
                else None,
                terminal=terminal,
                categories=tuple(categories),
                startup_notify=startup_notify,
                mime_types=tuple(mime_types),
                desktop_argument=desktop_argument,
            )
        except ManifestValidationError as exc:
            raise RegistrationError(str(exc)) from exc
        store.save(manifest)
        transaction.commit()
        return manifest
