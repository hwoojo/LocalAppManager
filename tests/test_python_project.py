from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from localapp_manager.importers import register_python_project
from localapp_manager.importers.python_project import PythonRegistrationError
from localapp_manager.models import AppKind, InstallMode
from localapp_manager.paths import AppPaths
from localapp_manager.runners import run_app
from localapp_manager.storage import ManifestStore


@pytest.fixture
def store(tmp_path: Path) -> ManifestStore:
    return ManifestStore(
        AppPaths.from_environment(
            {"XDG_DATA_HOME": str(tmp_path / "data")}, home=tmp_path / "home"
        )
    )


def test_register_and_run_existing_python_script(
    store: ManifestStore, tmp_path: Path
) -> None:
    project = tmp_path / "Script Project"
    project.mkdir()
    output = tmp_path / "script-output.json"
    (project / "main.py").write_text(
        "import json, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))\n",
        encoding="utf-8",
    )
    manifest = register_python_project(
        store,
        project,
        interpreter=sys.executable,
        script="main.py",
        arguments=(str(output), "stored value"),
    )
    assert manifest.kind is AppKind.PYTHON_PROJECT
    assert manifest.install_mode is InstallMode.LINKED
    assert manifest.python_interpreter == sys.executable
    assert manifest.python_entry_type == "script"
    assert manifest.python_entrypoint == "main.py"
    assert manifest.command == (
        sys.executable,
        str(project / "main.py"),
        str(output),
        "stored value",
    )
    assert run_app(manifest, ("runtime value",)) == 0
    assert json.loads(output.read_text()) == ["stored value", "runtime value"]


def test_register_and_run_python_module(store: ManifestStore, tmp_path: Path) -> None:
    project = tmp_path / "Module Project"
    package = project / "demo"
    package.mkdir(parents=True)
    output = tmp_path / "module-output.txt"
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('module ran')\n",
        encoding="utf-8",
    )
    manifest = register_python_project(
        store,
        project,
        interpreter=sys.executable,
        module="demo",
        arguments=(str(output),),
    )
    assert manifest.python_entry_type == "module"
    assert manifest.python_entrypoint == "demo"
    assert run_app(manifest) == 0
    assert output.read_text() == "module ran"


def test_python_registration_rejects_unsafe_or_ambiguous_entry(
    store: ManifestStore, tmp_path: Path
) -> None:
    project = tmp_path / "Project"
    project.mkdir()
    with pytest.raises(PythonRegistrationError, match="exactly one"):
        register_python_project(store, project, interpreter=sys.executable)
    with pytest.raises(PythonRegistrationError, match="inside"):
        register_python_project(
            store, project, interpreter=sys.executable, script="../outside.py"
        )
    with pytest.raises(PythonRegistrationError, match="invalid Python module"):
        register_python_project(
            store, project, interpreter=sys.executable, module="bad-module"
        )


def test_python_registration_does_not_create_or_modify_environment(
    store: ManifestStore, tmp_path: Path
) -> None:
    project = tmp_path / "Existing Project"
    project.mkdir()
    script = project / "app.py"
    script.write_text("pass\n", encoding="utf-8")
    before = {
        path.relative_to(project): path.read_bytes() for path in project.rglob("*")
    }
    manifest = register_python_project(
        store, project, interpreter=sys.executable, script="app.py"
    )
    after = {
        path.relative_to(project): path.read_bytes() for path in project.rglob("*")
    }
    assert before == after
    assert manifest.external_paths[0] == str(project)


def test_managed_mode_is_explicitly_rejected(
    store: ManifestStore, tmp_path: Path
) -> None:
    project = tmp_path / "Project"
    project.mkdir()
    (project / "app.py").write_text("pass\n", encoding="utf-8")
    with pytest.raises(PythonRegistrationError, match="linked mode only"):
        register_python_project(
            store,
            project,
            interpreter=sys.executable,
            script="app.py",
            mode="managed",
        )
