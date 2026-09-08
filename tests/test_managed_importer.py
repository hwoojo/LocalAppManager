from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from localapp_manager.importers import register_file
from localapp_manager.models import AppKind, InstallMode
from localapp_manager.paths import AppPaths
from localapp_manager.storage import ManifestStore


def make_executable(path: Path, content: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o700)
    return path


@pytest.fixture
def store(tmp_path: Path) -> ManifestStore:
    return ManifestStore(
        AppPaths.from_environment(
            {"XDG_DATA_HOME": str(tmp_path / "xdg data")}, home=tmp_path / "home space"
        )
    )


def test_managed_registration_copies_binary_icon_wrapper_and_desktop(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "sources" / "Demo.AppImage", "app image bytes")
    icon = tmp_path / "sources" / "demo icon.PNG"
    icon.write_bytes(b"png bytes")

    manifest = register_file(
        store,
        source,
        mode="managed",
        icon=icon,
        arguments=("--safe value",),
        terminal=True,
        categories=("Utility", "Development"),
        startup_notify=False,
    )

    installed = store.paths.managed_app_dir("demo") / "Demo.AppImage"
    managed_icon = store.paths.managed_icon_path("demo", ".png")
    wrapper = store.paths.wrapper_path("demo")
    desktop = store.paths.desktop_entry_path("demo")
    assert manifest.kind is AppKind.APPIMAGE
    assert manifest.install_mode is InstallMode.MANAGED
    assert manifest.installed_path == str(installed)
    assert manifest.command == (str(installed), "--safe value")
    assert installed.read_bytes() == source.read_bytes()
    assert os.access(installed, os.X_OK)
    assert managed_icon.read_bytes() == icon.read_bytes()
    assert os.access(wrapper, os.X_OK)
    assert "exec " in wrapper.read_text(encoding="utf-8")
    desktop_text = desktop.read_text(encoding="utf-8")
    assert f'Exec="{wrapper}"' in desktop_text
    assert f"Icon={managed_icon}" in desktop_text
    assert "Terminal=true" in desktop_text
    assert "Categories=Utility;Development;" in desktop_text
    assert "StartupNotify=false" in desktop_text
    assert manifest.managed_files == (
        str(store.paths.managed_app_dir("demo")),
        str(installed),
        str(managed_icon),
        str(wrapper),
        str(desktop),
    )
    assert manifest.external_paths == (str(source.absolute()), str(icon.absolute()))


def test_managed_run_uses_copy_after_original_disappears(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "original-tool")
    manifest = register_file(store, source, mode="managed")
    source.unlink()
    assert Path(manifest.command[0]).exists()


def test_generated_wrapper_executes_stored_and_runtime_argv_without_shell(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(
        tmp_path / "argument-recorder",
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))\n",
    )
    output = tmp_path / "recorded.json"
    shell_target = tmp_path / "must-not-be-created"
    shell_like = f"$(touch {shell_target})"
    manifest = register_file(
        store,
        source,
        mode="managed",
        arguments=(str(output), "stored value"),
    )

    completed = subprocess.run(
        [store.paths.wrapper_path(manifest.app_id), shell_like, "runtime value"],
        check=False,
        shell=False,
    )
    assert completed.returncode == 0
    assert json.loads(output.read_text()) == ["stored value", shell_like, "runtime value"]
    assert not shell_target.exists()


def test_linked_registration_creates_integration_but_no_app_copy(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "linked-tool")
    manifest = register_file(store, source, mode="linked")
    assert manifest.installed_path is None
    assert manifest.command[0] == str(source.absolute())
    assert not store.paths.managed_app_dir("linked-tool").exists()
    assert store.paths.wrapper_path("linked-tool").exists()
    assert store.paths.desktop_entry_path("linked-tool").exists()


def test_generated_id_skips_unmanaged_target_collision(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "Tool")
    collision = store.paths.wrapper_path("tool")
    collision.parent.mkdir(parents=True)
    collision.write_text("user-owned", encoding="utf-8")
    manifest = register_file(store, source)
    assert manifest.app_id == "tool-2"
    assert collision.read_text(encoding="utf-8") == "user-owned"


def test_registration_failure_rolls_back_only_new_managed_paths(
    store: ManifestStore, tmp_path: Path, monkeypatch
) -> None:
    source = make_executable(tmp_path / "Rollback Tool")
    preexisting = store.paths.bin_dir / "keep-me"
    preexisting.parent.mkdir(parents=True)
    preexisting.write_text("preserve", encoding="utf-8")

    def fail_save(manifest):
        raise RuntimeError("simulated manifest failure")

    monkeypatch.setattr(store, "save", fail_save)
    with pytest.raises(RuntimeError, match="simulated manifest failure"):
        register_file(store, source, mode="managed")

    assert source.exists()
    assert preexisting.read_text(encoding="utf-8") == "preserve"
    assert not store.paths.managed_app_dir("rollback-tool").exists()
    assert not store.paths.wrapper_path("rollback-tool").exists()
    assert not store.paths.desktop_entry_path("rollback-tool").exists()
