"""Portable application folder inspection and registration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import shlex

from ..desktop import build_desktop_entry, build_wrapper
from ..errors import LocalAppError
from ..fileops import (
    CreationTransaction,
    FileCreationError,
    atomic_copy,
    atomic_write_text,
    create_symlink,
    ensure_private_directory,
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


class PortableRegistrationError(LocalAppError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutableCandidate:
    relative_path: str
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PortableInspection:
    executables: tuple[ExecutableCandidate, ...]
    desktop_files: tuple[str, ...]
    icons: tuple[str, ...]


def _normalized_name(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def inspect_portable_folder(source: str | Path) -> PortableInspection:
    root = absolute_user_path(source)
    if not root.is_dir():
        raise SourceValidationError(f"portable source is not a directory: {root}")
    desktop_files: list[Path] = []
    icons: list[Path] = []
    executable_paths: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        if path.is_file():
            suffix = path.suffix.lower()
            if suffix == ".desktop":
                desktop_files.append(path)
            if suffix in {".png", ".svg", ".svgz", ".xpm", ".ico"}:
                icons.append(path)
            if os.access(path, os.X_OK):
                executable_paths.append(path)

    desktop_exec_names: set[str] = set()
    for desktop in desktop_files:
        try:
            for line in desktop.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                if line.startswith("Exec="):
                    argv = shlex.split(line[5:])
                    if argv:
                        desktop_exec_names.add(Path(argv[0]).name)
        except ValueError:
            continue

    root_name = _normalized_name(root.name)
    candidates: list[ExecutableCandidate] = []
    for path in executable_paths:
        relative = path.relative_to(root)
        reasons = ["executable"]
        score = 10
        if "bin" in relative.parts[:-1]:
            score += 30
            reasons.append("inside bin")
        candidate_name = _normalized_name(path.stem)
        if candidate_name and candidate_name == root_name:
            score += 40
            reasons.append("matches folder name")
        elif candidate_name and (
            candidate_name in root_name or root_name in candidate_name
        ):
            score += 20
            reasons.append("similar to folder name")
        if path.name in desktop_exec_names:
            score += 50
            reasons.append("referenced by desktop entry")
        if ".so" in path.name:
            score -= 30
            reasons.append("shared-library-like name")
        score -= max(0, len(relative.parts) - 1)
        candidates.append(ExecutableCandidate(str(relative), score, tuple(reasons)))
    candidates.sort(key=lambda item: (-item.score, item.relative_path))
    return PortableInspection(
        executables=tuple(candidates),
        desktop_files=tuple(str(path.relative_to(root)) for path in desktop_files),
        icons=tuple(str(path.relative_to(root)) for path in icons),
    )


def _select_executable(
    root: Path, inspection: PortableInspection, selected: str | Path | None
) -> Path:
    if selected is None:
        if not inspection.executables:
            raise PortableRegistrationError("no executable candidates found")
        if len(inspection.executables) != 1:
            choices = ", ".join(
                candidate.relative_path for candidate in inspection.executables
            )
            raise PortableRegistrationError(
                "multiple executable candidates; choose one with --executable: "
                + choices
            )
        selected = inspection.executables[0].relative_path
    relative = Path(selected)
    if relative.is_absolute() or ".." in relative.parts:
        raise PortableRegistrationError(
            "--executable must be a path inside the portable folder"
        )
    executable = root / relative
    if (
        executable.is_symlink()
        or not executable.is_file()
        or not os.access(executable, os.X_OK)
    ):
        raise PortableRegistrationError(
            f"selected path is not an executable file: {relative}"
        )
    return executable


def _copy_portable_tree(
    source: Path,
    destination: Path,
    transaction: CreationTransaction,
    *,
    source_root: Path | None = None,
) -> None:
    root = source if source_root is None else source_root
    for child in sorted(source.iterdir(), key=lambda path: path.name):
        target = destination / child.name
        if child.is_symlink():
            link_target = os.readlink(child)
            if os.path.isabs(link_target):
                raise FileCreationError(f"absolute symlink is not allowed: {child}")
            resolved_target = Path(os.path.abspath(child.parent / link_target))
            if not (resolved_target == root or root in resolved_target.parents):
                raise FileCreationError(f"symlink escapes portable folder: {child}")
            create_symlink(target, link_target, transaction=transaction)
        elif child.is_dir():
            ensure_private_directory(target, transaction)
            _copy_portable_tree(child, target, transaction, source_root=root)
        elif child.is_file():
            atomic_copy(
                child,
                target,
                mode=child.stat().st_mode & 0o777,
                transaction=transaction,
            )
        else:
            raise FileCreationError(f"special files are not supported: {child}")


def register_portable_folder(
    store: ManifestStore,
    source: str | Path,
    *,
    mode: str = "linked",
    executable: str | Path | None = None,
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
    root = absolute_user_path(source)
    if not root.is_dir():
        raise SourceValidationError(f"portable source is not a directory: {root}")
    inspection = inspect_portable_folder(root)
    selected_executable = _select_executable(root, inspection, executable)
    relative_executable = selected_executable.relative_to(root)
    try:
        install_mode = InstallMode(mode)
    except ValueError as exc:
        raise PortableRegistrationError(f"unsupported install mode: {mode}") from exc
    display_name = root.name if name is None else name.strip()
    if not display_name:
        raise SourceValidationError("application name must not be empty")

    auto_icon: Path | None = None
    if icon is None and len(inspection.icons) == 1:
        auto_icon = root / inspection.icons[0]
    icon_source = _validate_icon(icon) if icon is not None else auto_icon
    suffix = _icon_suffix(icon_source) if icon_source is not None else None
    selected_id = _select_id(store, display_name, app_id, install_mode, suffix)
    explicit_working = (
        validate_working_directory(working_directory)
        if working_directory is not None
        else None
    )

    with CreationTransaction() as transaction:
        if install_mode is InstallMode.MANAGED:
            app_root = store.paths.managed_app_dir(selected_id)
            app_root.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            ensure_private_directory(app_root, transaction)
            _copy_portable_tree(root, app_root, transaction)
            executable_path = app_root / relative_executable
            installed_path: Path | None = app_root
            default_working = app_root
        else:
            executable_path = selected_executable
            installed_path = None
            default_working = root

        icon_path: Path | None = None
        if icon_source is not None and suffix is not None:
            icon_path = store.paths.managed_icon_path(selected_id, suffix)
            atomic_copy(icon_source, icon_path, mode=0o644, transaction=transaction)
        command = (str(executable_path), *tuple(arguments))
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
        if icon_source is not None and not (
            icon_source == root or root in icon_source.parents
        ):
            external_paths.append(str(icon_source))
        if explicit_working is not None and str(explicit_working) not in external_paths:
            external_paths.append(str(explicit_working))
        try:
            manifest = AppManifest(
                app_id=selected_id,
                name=display_name,
                kind=AppKind.PORTABLE_FOLDER,
                install_mode=install_mode,
                source_path=str(root),
                installed_path=str(installed_path)
                if installed_path is not None
                else None,
                command=command,
                icon_path=str(icon_path) if icon_path is not None else None,
                desktop_entry_path=str(desktop_path),
                managed_files=tuple(str(path) for path in transaction.created_paths),
                managed_file_hashes=managed_hashes(transaction.created_paths),
                external_paths=tuple(external_paths),
                working_directory=str(explicit_working or default_working),
                terminal=terminal,
                categories=tuple(categories),
                startup_notify=startup_notify,
                mime_types=tuple(mime_types),
                desktop_argument=desktop_argument,
            )
        except ManifestValidationError as exc:
            raise PortableRegistrationError(str(exc)) from exc
        store.save(manifest)
        transaction.commit()
        return manifest
