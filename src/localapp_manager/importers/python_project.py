"""Linked registration for existing Python projects and environments."""

from __future__ import annotations

from collections.abc import Sequence
import os
from pathlib import Path
import re

from ..desktop import build_desktop_entry, build_wrapper
from ..errors import LocalAppError
from ..fileops import (
    CreationTransaction,
    atomic_copy,
    atomic_write_text,
    managed_hashes,
)
from ..models import AppKind, AppManifest, InstallMode, ManifestValidationError
from ..storage import ManifestStore
from ..validation import (
    SourceValidationError,
    absolute_user_path,
    validate_working_directory,
)
from .file import _icon_suffix, _select_id, _validate_icon


class PythonRegistrationError(LocalAppError):
    pass


_MODULE_PATTERN = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def register_python_project(
    store: ManifestStore,
    project: str | Path,
    *,
    interpreter: str | Path,
    script: str | Path | None = None,
    module: str | None = None,
    mode: str = "linked",
    name: str | None = None,
    app_id: str | None = None,
    arguments: Sequence[str] = (),
    working_directory: str | Path | None = None,
    terminal: bool = False,
    icon: str | Path | None = None,
    categories: Sequence[str] = ("Utility",),
    startup_notify: bool = True,
    mime_types: Sequence[str] = (),
    desktop_argument: str | None = None,
) -> AppManifest:
    root = absolute_user_path(project)
    if not root.is_dir():
        raise SourceValidationError(f"Python project is not a directory: {root}")
    if mode != "linked":
        raise PythonRegistrationError(
            "Python projects currently support linked mode only"
        )
    python = absolute_user_path(interpreter)
    if not python.is_file() or not os.access(python, os.X_OK):
        raise PythonRegistrationError(f"Python interpreter is not executable: {python}")
    if (script is None) == (module is None):
        raise PythonRegistrationError("choose exactly one of --script or --module")

    if script is not None:
        relative_script = Path(script)
        if relative_script.is_absolute() or ".." in relative_script.parts:
            raise PythonRegistrationError("--script must be a path inside the project")
        entry_script = root / relative_script
        if not entry_script.is_file() or entry_script.is_symlink():
            raise PythonRegistrationError(
                f"entry script does not exist: {relative_script}"
            )
        entry_type = "script"
        entrypoint = str(relative_script)
        command = (str(python), str(entry_script), *tuple(arguments))
    else:
        assert module is not None
        if not _MODULE_PATTERN.fullmatch(module):
            raise PythonRegistrationError(f"invalid Python module name: {module}")
        entry_type = "module"
        entrypoint = module
        command = (str(python), "-m", module, *tuple(arguments))

    display_name = root.name if name is None else name.strip()
    if not display_name:
        raise SourceValidationError("application name must not be empty")
    working_path = (
        validate_working_directory(working_directory)
        if working_directory is not None
        else root
    )
    icon_source = _validate_icon(icon)
    suffix = _icon_suffix(icon_source) if icon_source is not None else None
    selected_id = _select_id(store, display_name, app_id, InstallMode.LINKED, suffix)

    with CreationTransaction() as transaction:
        icon_path: Path | None = None
        if icon_source is not None and suffix is not None:
            icon_path = store.paths.managed_icon_path(selected_id, suffix)
            atomic_copy(icon_source, icon_path, mode=0o644, transaction=transaction)
        wrapper_path = store.paths.wrapper_path(selected_id)
        atomic_write_text(
            wrapper_path, build_wrapper(command), mode=0o755, transaction=transaction
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
        external_paths = [str(root)]
        if not _inside(python, root):
            external_paths.append(str(python))
        if icon_source is not None and not _inside(icon_source, root):
            external_paths.append(str(icon_source))
        if not _inside(working_path, root) and str(working_path) not in external_paths:
            external_paths.append(str(working_path))
        try:
            manifest = AppManifest(
                app_id=selected_id,
                name=display_name,
                kind=AppKind.PYTHON_PROJECT,
                install_mode=InstallMode.LINKED,
                source_path=str(root),
                installed_path=None,
                command=command,
                icon_path=str(icon_path) if icon_path is not None else None,
                desktop_entry_path=str(desktop_path),
                managed_files=tuple(str(path) for path in transaction.created_paths),
                managed_file_hashes=managed_hashes(transaction.created_paths),
                external_paths=tuple(external_paths),
                working_directory=str(working_path),
                terminal=terminal,
                categories=tuple(categories),
                startup_notify=startup_notify,
                mime_types=tuple(mime_types),
                desktop_argument=desktop_argument,
                python_interpreter=str(python),
                python_entry_type=entry_type,
                python_entrypoint=entrypoint,
            )
        except ManifestValidationError as exc:
            raise PythonRegistrationError(str(exc)) from exc
        store.save(manifest)
        transaction.commit()
        return manifest
