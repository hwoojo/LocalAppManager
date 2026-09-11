from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from localapp_manager.models import AppManifest
from localapp_manager.paths import AppPaths
from localapp_manager.storage import (
    CorruptManifestError,
    DuplicateManifestError,
    ManifestNotFoundError,
    ManifestStore,
)


@pytest.fixture
def store(tmp_path: Path) -> ManifestStore:
    paths = AppPaths.from_environment(
        {"XDG_DATA_HOME": str(tmp_path / "xdg-data")},
        home=tmp_path,
    )
    return ManifestStore(paths)


def test_save_load_list_and_delete(
    store: ManifestStore, sample_manifest: AppManifest
) -> None:
    path = store.save(sample_manifest)
    assert path.name == "sample-app.json"
    assert store.load("sample-app") == sample_manifest
    assert store.list_ids() == ("sample-app",)
    assert store.list_manifests() == (sample_manifest,)

    store.delete_manifest("sample-app")
    assert store.list_ids() == ()
    with pytest.raises(ManifestNotFoundError):
        store.load("sample-app")


def test_duplicate_create_preserves_original(
    store: ManifestStore, sample_manifest: AppManifest
) -> None:
    store.save(sample_manifest)
    changed = replace(sample_manifest, name="Changed")
    with pytest.raises(DuplicateManifestError):
        store.save(changed)
    assert store.load(sample_manifest.app_id).name == "Sample App"


def test_explicit_overwrite_replaces_manifest(
    store: ManifestStore, sample_manifest: AppManifest
) -> None:
    store.save(sample_manifest)
    changed = replace(sample_manifest, name="Changed")
    store.save(changed, overwrite=True)
    assert store.load(sample_manifest.app_id).name == "Changed"


def test_no_temporary_file_remains_after_save(
    store: ManifestStore, sample_manifest: AppManifest
) -> None:
    store.save(sample_manifest)
    assert [path.name for path in store.paths.manifest_dir.iterdir()] == [
        "sample-app.json"
    ]


def test_create_failure_after_publish_removes_incomplete_registration(
    store: ManifestStore, sample_manifest: AppManifest, monkeypatch
) -> None:
    def fail_fsync(directory):
        raise OSError("simulated directory sync failure")

    monkeypatch.setattr(store, "_fsync_directory", fail_fsync)
    with pytest.raises(OSError, match="simulated directory sync failure"):
        store.save(sample_manifest)
    assert not store.manifest_path(sample_manifest.app_id).exists()
    assert list(store.paths.manifest_dir.iterdir()) == []


def test_corrupt_json_has_specific_error(store: ManifestStore) -> None:
    directory = store.paths.ensure_manifest_dir()
    (directory / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CorruptManifestError, match="invalid manifest"):
        store.load("broken")


def test_filename_and_embedded_id_mismatch_is_corrupt(
    store: ManifestStore, sample_manifest: AppManifest
) -> None:
    store.save(sample_manifest)
    sample_path = store.manifest_path(sample_manifest.app_id)
    other_path = store.manifest_path("other")
    sample_path.rename(other_path)
    with pytest.raises(CorruptManifestError, match="does not match filename"):
        store.load("other")


def test_invalid_id_cannot_escape_manifest_directory(store: ManifestStore) -> None:
    with pytest.raises(ValueError, match="invalid application ID"):
        store.manifest_path("../outside")
