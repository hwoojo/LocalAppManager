from __future__ import annotations

import os
from pathlib import Path

import pytest

from localapp_manager.importers import inspect_portable_folder, register_portable_folder
from localapp_manager.importers.portable import PortableRegistrationError
from localapp_manager.models import AppKind, InstallMode
from localapp_manager.paths import AppPaths
from localapp_manager.storage import ManifestStore
from localapp_manager.fileops import FileCreationError


def executable(path: Path, content: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o700)
    return path


@pytest.fixture
def store(tmp_path: Path) -> ManifestStore:
    return ManifestStore(
        AppPaths.from_environment(
            {"XDG_DATA_HOME": str(tmp_path / "data")}, home=tmp_path / "home"
        )
    )


def test_inspection_ranks_bin_name_and_desktop_references(tmp_path: Path) -> None:
    root = tmp_path / "Cool Tool"
    main = executable(root / "bin" / "cool-tool")
    executable(root / "helper")
    (root / "cool.desktop").write_text(
        "[Desktop Entry]\nExec=bin/cool-tool --start\n", encoding="utf-8"
    )
    (root / "cool.png").write_bytes(b"icon")
    inspection = inspect_portable_folder(root)
    assert inspection.executables[0].relative_path == str(main.relative_to(root))
    assert "inside bin" in inspection.executables[0].reasons
    assert "referenced by desktop entry" in inspection.executables[0].reasons
    assert inspection.desktop_files == ("cool.desktop",)
    assert inspection.icons == ("cool.png",)


def test_ambiguous_candidates_require_explicit_selection(
    store: ManifestStore, tmp_path: Path
) -> None:
    root = tmp_path / "Portable"
    executable(root / "one")
    executable(root / "two")
    with pytest.raises(PortableRegistrationError, match="--executable"):
        register_portable_folder(store, root)


def test_linked_portable_registration_preserves_folder(
    store: ManifestStore, tmp_path: Path
) -> None:
    root = tmp_path / "Portable Tool"
    selected = executable(root / "bin" / "launch")
    manifest = register_portable_folder(store, root, executable="bin/launch")
    assert manifest.kind is AppKind.PORTABLE_FOLDER
    assert manifest.install_mode is InstallMode.LINKED
    assert manifest.command[0] == str(selected)
    assert manifest.working_directory == str(root)
    assert manifest.external_paths == (str(root),)
    assert root.exists()


def test_managed_portable_copies_tree_and_uses_managed_working_directory(
    store: ManifestStore, tmp_path: Path
) -> None:
    root = tmp_path / "Portable Tool"
    executable(root / "bin" / "launch")
    (root / "assets").mkdir()
    (root / "assets" / "data.txt").write_text("asset", encoding="utf-8")
    (root / "icon.svg").write_text("<svg/>", encoding="utf-8")
    os.symlink("../assets/data.txt", root / "bin" / "data-link")

    manifest = register_portable_folder(
        store, root, mode="managed", executable="bin/launch"
    )
    managed_root = store.paths.managed_app_dir(manifest.app_id)
    assert manifest.install_mode is InstallMode.MANAGED
    assert manifest.installed_path == str(managed_root)
    assert manifest.command[0] == str(managed_root / "bin" / "launch")
    assert manifest.working_directory == str(managed_root)
    assert (managed_root / "assets" / "data.txt").read_text() == "asset"
    assert (managed_root / "bin" / "data-link").is_symlink()
    assert os.readlink(managed_root / "bin" / "data-link") == "../assets/data.txt"
    assert manifest.icon_path == str(store.paths.managed_icon_path(manifest.app_id, ".svg"))


def test_managed_portable_rejects_symlink_escaping_source_and_rolls_back(
    store: ManifestStore, tmp_path: Path
) -> None:
    root = tmp_path / "Unsafe Portable"
    executable(root / "launch")
    outside = tmp_path / "outside.txt"
    outside.write_text("external", encoding="utf-8")
    os.symlink("../outside.txt", root / "escape")
    with pytest.raises(FileCreationError, match="escapes portable folder"):
        register_portable_folder(store, root, mode="managed")
    assert outside.read_text() == "external"
    assert not store.paths.managed_app_dir("unsafe-portable").exists()


def test_executable_selection_cannot_escape_folder(store: ManifestStore, tmp_path: Path) -> None:
    root = tmp_path / "Portable"
    root.mkdir()
    outside = executable(tmp_path / "outside")
    with pytest.raises(PortableRegistrationError, match="inside"):
        register_portable_folder(store, root, executable="../outside")
    assert outside.exists()
