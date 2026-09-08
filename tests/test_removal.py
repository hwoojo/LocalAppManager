from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from localapp_manager.importers import register_file
from localapp_manager.paths import AppPaths
from localapp_manager.removal import RemovalError, build_removal_plan, execute_removal
from localapp_manager.storage import ManifestStore


def make_executable(path: Path) -> Path:
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


def test_linked_removal_preserves_original_and_removes_integration(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "Linked Tool")
    manifest = register_file(store, source, mode="linked")
    plan = build_removal_plan(store, manifest.app_id)
    assert plan.preserved_external == (source.absolute(),)
    assert {target.role for target in plan.existing_targets} == {"wrapper", "desktop-entry"}

    result = execute_removal(store, plan)
    assert result.manifest_removed
    assert source.exists()
    assert not store.paths.wrapper_path(manifest.app_id).exists()
    assert not store.paths.desktop_entry_path(manifest.app_id).exists()
    assert store.list_ids() == ()


def test_managed_removal_uses_exact_manifest_paths_and_preserves_sources(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "Managed Tool")
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"icon")
    manifest = register_file(store, source, mode="managed", icon=icon)
    unrelated = store.paths.managed_apps / "unrelated"
    unrelated.mkdir(parents=True)
    (unrelated / "user.txt").write_text("keep", encoding="utf-8")

    result = execute_removal(store, build_removal_plan(store, manifest.app_id))
    assert result.manifest_removed
    assert source.exists()
    assert icon.exists()
    assert (unrelated / "user.txt").read_text() == "keep"
    assert all(not Path(path).exists() for path in manifest.managed_files)


def test_missing_managed_file_is_reported_and_skipped(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "Tool")
    manifest = register_file(store, source)
    store.paths.wrapper_path(manifest.app_id).unlink()
    plan = build_removal_plan(store, manifest.app_id)
    assert [target.role for target in plan.missing_targets] == ["wrapper"]
    result = execute_removal(store, plan)
    assert result.manifest_removed
    assert store.list_ids() == ()


def test_nonempty_managed_directory_is_never_recursively_deleted(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "Tool")
    manifest = register_file(store, source, mode="managed")
    app_directory = store.paths.managed_app_dir(manifest.app_id)
    unexpected = app_directory / "user-created.txt"
    unexpected.write_text("preserve", encoding="utf-8")
    result = execute_removal(store, build_removal_plan(store, manifest.app_id))
    assert not result.manifest_removed
    assert unexpected.read_text() == "preserve"
    assert store.load(manifest.app_id).app_id == manifest.app_id


def test_unsafe_manifest_path_blocks_removal(
    store: ManifestStore, tmp_path: Path
) -> None:
    source = make_executable(tmp_path / "Tool")
    external_document = tmp_path / "important.txt"
    external_document.write_text("never delete", encoding="utf-8")
    manifest = register_file(store, source)
    tampered = replace(
        manifest,
        managed_files=(*manifest.managed_files, str(external_document)),
    )
    store.save(tampered, overwrite=True)
    plan = build_removal_plan(store, manifest.app_id)
    assert plan.unsafe_paths == (external_document.absolute(),)
    with pytest.raises(RemovalError, match="unsafe"):
        execute_removal(store, plan)
    assert external_document.read_text() == "never delete"
    assert store.paths.wrapper_path(manifest.app_id).exists()

