from __future__ import annotations

import os
from pathlib import Path

import pytest

from localapp_manager.importers import register_linked_file
from localapp_manager.models import AppKind, InstallMode
from localapp_manager.paths import AppPaths
from localapp_manager.storage import ManifestStore
from localapp_manager.validation import SourceValidationError


@pytest.fixture
def store(tmp_path: Path) -> ManifestStore:
    return ManifestStore(
        AppPaths.from_environment(
            {"XDG_DATA_HOME": str(tmp_path / "data")}, home=tmp_path
        )
    )


def make_executable(path: Path, content: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)
    return path


def test_register_appimage_in_linked_mode_without_changing_source(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "Original Apps" / "Demo.AppImage", "original")
    original_bytes = source.read_bytes()
    original_mode = source.stat().st_mode

    manifest = register_linked_file(store, source)

    assert manifest.app_id == "demo"
    assert manifest.name == "Demo"
    assert manifest.kind is AppKind.APPIMAGE
    assert manifest.install_mode is InstallMode.LINKED
    assert manifest.installed_path is None
    assert manifest.managed_files == (
        str(store.paths.wrapper_path("demo")),
        str(store.paths.desktop_entry_path("demo")),
    )
    assert manifest.external_paths == (str(source.absolute()),)
    assert source.read_bytes() == original_bytes
    assert source.stat().st_mode == original_mode
    assert tuple(store.paths.manifest_dir.iterdir()) == (store.manifest_path("demo"),)


def test_register_executable_preserves_each_command_argument(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "tools" / "my tool")
    manifest = register_linked_file(
        store,
        source,
        arguments=("--label", "value with spaces", "$(not-a-shell)"),
    )
    assert manifest.kind is AppKind.EXECUTABLE
    assert manifest.command == (
        str(source.absolute()),
        "--label",
        "value with spaces",
        "$(not-a-shell)",
    )


def test_duplicate_names_receive_incrementing_ids(
    store: ManifestStore, tmp_path: Path
) -> None:
    first = make_executable(tmp_path / "one" / "Tool")
    second = make_executable(tmp_path / "two" / "Tool")
    assert register_linked_file(store, first).app_id == "tool"
    assert register_linked_file(store, second).app_id == "tool-2"


def test_working_directory_is_validated_and_recorded_as_external(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "tool")
    working_directory = tmp_path / "project files"
    working_directory.mkdir()
    manifest = register_linked_file(
        store, source, working_directory=working_directory
    )
    assert manifest.working_directory == str(working_directory.absolute())
    assert str(working_directory.absolute()) in manifest.external_paths


def test_missing_or_non_executable_source_is_rejected(
    store: ManifestStore, tmp_path: Path
) -> None:
    with pytest.raises(SourceValidationError, match="does not exist"):
        register_linked_file(store, tmp_path / "missing")

    source = tmp_path / "not-executable"
    source.write_text("data", encoding="utf-8")
    source.chmod(0o600)
    assert not os.access(source, os.X_OK)
    with pytest.raises(SourceValidationError, match="not executable"):
        register_linked_file(store, source)
