from __future__ import annotations

import json
from pathlib import Path

from localapp_manager.doctor import diagnose, repair
from localapp_manager.importers import register_file
from localapp_manager.paths import AppPaths
from localapp_manager.storage import ManifestStore


def executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path


def store_for(tmp_path: Path) -> ManifestStore:
    return ManifestStore(
        AppPaths.from_environment(
            {"XDG_DATA_HOME": str(tmp_path / "data")}, home=tmp_path / "home"
        )
    )


def test_doctor_reports_missing_and_mismatched_paths(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    source = executable(tmp_path / "Tool")
    manifest = register_file(store, source)
    source.unlink()
    store.paths.wrapper_path(manifest.app_id).write_text("modified", encoding="utf-8")
    store.paths.desktop_entry_path(manifest.app_id).unlink()
    codes = {issue.code for issue in diagnose(store).issues}
    assert "executable-missing" in codes
    assert "external-path-missing" in codes
    assert "wrapper-mismatch" in codes
    assert "desktop-missing" in codes
    assert "managed-path-missing" in codes


def test_doctor_continues_after_corrupt_manifest(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    register_file(store, executable(tmp_path / "Healthy"))
    (store.paths.manifest_dir / "broken.json").write_text("{broken", encoding="utf-8")
    report = diagnose(store)
    assert set(report.checked) == {"broken", "healthy"}
    assert any(issue.code == "corrupt-manifest" for issue in report.issues)


def test_doctor_repair_recreates_integration_and_persists_migration(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    manifest = register_file(store, executable(tmp_path / "Tool"))
    manifest_path = store.manifest_path(manifest.app_id)
    raw = json.loads(manifest_path.read_text())
    raw["schema_version"] = 1
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    store.paths.wrapper_path(manifest.app_id).unlink()
    store.paths.desktop_entry_path(manifest.app_id).unlink()

    repaired, failures = repair(store)
    assert repaired == (manifest.app_id,)
    assert failures == ()
    assert store.paths.wrapper_path(manifest.app_id).exists()
    assert store.paths.desktop_entry_path(manifest.app_id).exists()
    assert json.loads(manifest_path.read_text())["schema_version"] == 2
    assert diagnose(store).issues == ()


def test_doctor_detects_duplicate_embedded_ids(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    manifest = register_file(store, executable(tmp_path / "Tool"))
    raw = json.loads(store.manifest_path(manifest.app_id).read_text())
    (store.paths.manifest_dir / "copy.json").write_text(json.dumps(raw), encoding="utf-8")
    report = diagnose(store)
    assert any(issue.code == "duplicate-id" for issue in report.issues)


def test_doctor_detects_manually_modified_managed_binary(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    source = executable(tmp_path / "Managed")
    manifest = register_file(store, source, mode="managed")
    installed = Path(manifest.installed_path)
    installed.write_text("modified after registration", encoding="utf-8")
    codes = {issue.code for issue in diagnose(store, manifest.app_id).issues}
    assert "managed-file-modified" in codes
    repaired, failures = repair(store, manifest.app_id)
    assert repaired == (manifest.app_id,)
    assert failures == ()
    repaired_codes = {issue.code for issue in diagnose(store, manifest.app_id).issues}
    assert "managed-file-modified" in repaired_codes
