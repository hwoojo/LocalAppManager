from __future__ import annotations

import json
from pathlib import Path

import pytest

from localapp_manager.importers import register_linked_file
from localapp_manager.paths import AppPaths
from localapp_manager.runners import RunError, run_app
from localapp_manager.storage import ManifestStore


def make_recorder(path: Path) -> Path:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "pathlib.Path('arguments.json').write_text(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    path.chmod(0o700)
    return path


def test_runner_uses_argv_and_working_directory(tmp_path: Path) -> None:
    store = ManifestStore(
        AppPaths.from_environment(
            {"XDG_DATA_HOME": str(tmp_path / "data")}, home=tmp_path
        )
    )
    source = make_recorder(tmp_path / "recorder with spaces")
    working_directory = tmp_path / "work"
    working_directory.mkdir()
    dangerous_path = tmp_path / "must-not-exist"
    shell_like_argument = f"$(touch {dangerous_path})"
    manifest = register_linked_file(
        store,
        source,
        arguments=("stored value",),
        working_directory=working_directory,
    )

    assert run_app(manifest, (shell_like_argument, "extra value")) == 0
    recorded = json.loads((working_directory / "arguments.json").read_text())
    assert recorded == ["stored value", shell_like_argument, "extra value"]
    assert not dangerous_path.exists()


def test_runner_reports_source_removed_after_registration(tmp_path: Path) -> None:
    store = ManifestStore(
        AppPaths.from_environment(
            {"XDG_DATA_HOME": str(tmp_path / "data")}, home=tmp_path
        )
    )
    source = make_recorder(tmp_path / "temporary")
    manifest = register_linked_file(store, source)
    source.unlink()
    with pytest.raises(RunError, match="does not exist"):
        run_app(manifest)
