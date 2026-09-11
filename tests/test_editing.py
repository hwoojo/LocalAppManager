from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from localapp_manager.desktop import build_wrapper
from localapp_manager.editing import EditError, edit_app
from localapp_manager.importers import register_file
from localapp_manager.paths import AppPaths
from localapp_manager.storage import ManifestStore


def executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path


@pytest.fixture
def store(tmp_path: Path) -> ManifestStore:
    return ManifestStore(
        AppPaths.from_environment(
            {"XDG_DATA_HOME": str(tmp_path / "data")}, home=tmp_path / "home"
        )
    )


def test_edit_updates_manifest_wrapper_and_desktop_together(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = executable(tmp_path / "Tool")
    manifest = register_file(store, source, arguments=("old",))
    updated = edit_app(
        store,
        manifest.app_id,
        name="New Name",
        arguments=("value with spaces", "$(literal)"),
        terminal=True,
        categories=("Development",),
        startup_notify=False,
    )
    assert store.load(manifest.app_id) == updated
    assert updated.command == (str(source), "value with spaces", "$(literal)")
    assert store.paths.wrapper_path(manifest.app_id).read_text() == build_wrapper(
        updated.command
    )
    desktop = store.paths.desktop_entry_path(manifest.app_id).read_text()
    assert "Name=New Name" in desktop
    assert "Terminal=true" in desktop
    assert "Categories=Development;" in desktop
    assert "StartupNotify=false" in desktop


def test_edit_recreates_tracked_missing_integration(
    store: ManifestStore, tmp_path: Path
) -> None:
    manifest = register_file(store, executable(tmp_path / "Tool"))
    store.paths.wrapper_path(manifest.app_id).unlink()
    store.paths.desktop_entry_path(manifest.app_id).unlink()
    edit_app(store, manifest.app_id)
    assert store.paths.wrapper_path(manifest.app_id).exists()
    assert store.paths.desktop_entry_path(manifest.app_id).exists()


def test_edit_refuses_untracked_collision(store: ManifestStore, tmp_path: Path) -> None:
    manifest = register_file(store, executable(tmp_path / "Tool"))
    wrapper = store.paths.wrapper_path(manifest.app_id)
    wrapper.write_text("user replacement", encoding="utf-8")
    untracked = tuple(path for path in manifest.managed_files if path != str(wrapper))
    untracked_hashes = tuple(
        item for item in manifest.managed_file_hashes if item[0] != str(wrapper)
    )
    store.save(
        replace(
            manifest,
            managed_files=untracked,
            managed_file_hashes=untracked_hashes,
        ),
        overwrite=True,
    )
    with pytest.raises(EditError, match="untracked"):
        edit_app(store, manifest.app_id, name="Blocked")
    assert wrapper.read_text() == "user replacement"
