from __future__ import annotations

import json
from pathlib import Path

from localapp_manager.models import AppManifest
from localapp_manager.paths import AppPaths
from localapp_manager.storage import ManifestStore


def test_store_loads_v1_manifest_as_current_without_mutating_file(
    tmp_path: Path, sample_manifest: AppManifest
) -> None:
    store = ManifestStore(
        AppPaths.from_environment(
            {"XDG_DATA_HOME": str(tmp_path / "data")}, home=tmp_path
        )
    )
    data = sample_manifest.to_dict()
    data["schema_version"] = 1
    data.pop("categories")
    data.pop("startup_notify")
    data.pop("python_interpreter")
    data.pop("python_entry_type")
    data.pop("python_entrypoint")
    data.pop("managed_file_hashes")
    path = store.paths.ensure_manifest_dir() / "sample-app.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = store.load("sample-app")
    assert loaded.schema_version == AppManifest.CURRENT_SCHEMA_VERSION
    assert loaded.categories == ("Utility",)
    assert json.loads(path.read_text())["schema_version"] == 1
