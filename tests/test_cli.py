from __future__ import annotations

import json
from pathlib import Path
import sys

from localapp_manager.cli import main


def make_executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path


def make_argument_recorder(path: Path) -> Path:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "pathlib.Path('cli-arguments.json').write_text(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    path.chmod(0o700)
    return path


def configure_isolated_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)


def test_add_list_and_show_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    configure_isolated_home(monkeypatch, tmp_path)
    source = make_executable(tmp_path / "My CLI Tool")

    assert main(["add", str(source), "--name", "Friendly Tool"]) == 0
    assert "Registered friendly-tool" in capsys.readouterr().out

    assert main(["list"]) == 0
    listing = capsys.readouterr().out
    assert "friendly-tool\tFriendly Tool\texecutable\tlinked" in listing

    assert main(["show", "friendly-tool"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["command"] == [str(source.absolute())]
    assert shown["managed_files"] == [
        str(tmp_path / ".local" / "bin" / "friendly-tool"),
        str(tmp_path / "data" / "applications" / "friendly-tool.desktop"),
    ]
    assert shown["external_paths"] == [str(source.absolute())]


def test_cli_reports_expected_errors(monkeypatch, tmp_path: Path, capsys) -> None:
    configure_isolated_home(monkeypatch, tmp_path)
    assert main(["show", "missing"]) == 2
    assert "application not found: missing" in capsys.readouterr().err


def test_run_command_forwards_arguments_after_separator(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    configure_isolated_home(monkeypatch, tmp_path)
    source = make_argument_recorder(tmp_path / "argument recorder")
    working_directory = tmp_path / "run-here"
    working_directory.mkdir()

    assert (
        main(
            [
                "add",
                str(source),
                "--working-directory",
                str(working_directory),
                "--arg=stored value",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["run", "argument-recorder", "--", "--flag", "extra value"]) == 0
    recorded = json.loads((working_directory / "cli-arguments.json").read_text())
    assert recorded == ["stored value", "--flag", "extra value"]


def test_cli_managed_mode_copies_source_and_icon(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    configure_isolated_home(monkeypatch, tmp_path)
    source = make_executable(tmp_path / "Managed Tool")
    icon = tmp_path / "tool.svg"
    icon.write_text("<svg/>", encoding="utf-8")

    assert (
        main(
            [
                "add",
                str(source),
                "--mode",
                "managed",
                "--icon",
                str(icon),
                "--category",
                "Development",
                "--no-startup-notify",
            ]
        )
        == 0
    )
    assert "(executable, managed)" in capsys.readouterr().out

    assert main(["show", "managed-tool"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["installed_path"] == str(
        tmp_path / ".local" / "opt" / "managed-tool" / "Managed Tool"
    )
    assert shown["icon_path"] == str(
        tmp_path / "data" / "icons" / "localapp-manager" / "managed-tool.svg"
    )
    assert shown["categories"] == ["Development"]
    assert shown["startup_notify"] is False


def test_remove_requires_preview_then_explicit_confirmation(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    configure_isolated_home(monkeypatch, tmp_path)
    source = make_executable(tmp_path / "Remove Me")
    assert main(["add", str(source)]) == 0
    capsys.readouterr()

    assert main(["remove", "remove-me"]) == 0
    preview = capsys.readouterr().out
    assert "Preview only" in preview
    assert "preserve [external]" in preview
    assert source.exists()

    assert main(["remove", "remove-me", "--yes"]) == 0
    assert "Removed remove-me registration" in capsys.readouterr().out
    assert source.exists()


def test_cli_adds_portable_folder_with_selected_executable(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    configure_isolated_home(monkeypatch, tmp_path)
    root = tmp_path / "Portable CLI"
    root.mkdir()
    source = make_executable(root / "launch")
    assert (
        main(["add", str(root), "--kind", "portable-folder", "--executable", "launch"])
        == 0
    )
    assert "(portable-folder, linked)" in capsys.readouterr().out
    assert main(["show", "portable-cli"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["command"][0] == str(source.absolute())


def test_cli_registers_python_module(monkeypatch, tmp_path: Path, capsys) -> None:
    configure_isolated_home(monkeypatch, tmp_path)
    project = tmp_path / "Python CLI"
    project.mkdir()
    assert (
        main(
            [
                "add",
                str(project),
                "--kind",
                "python-project",
                "--python",
                sys.executable,
                "--module",
                "demo.app",
            ]
        )
        == 0
    )
    assert "(python-project, linked)" in capsys.readouterr().out
    assert main(["show", "python-cli"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["python_entry_type"] == "module"
    assert shown["python_entrypoint"] == "demo.app"


def test_cli_edit_and_doctor(monkeypatch, tmp_path: Path, capsys) -> None:
    configure_isolated_home(monkeypatch, tmp_path)
    source = make_executable(tmp_path / "Editable")
    assert main(["add", str(source)]) == 0
    capsys.readouterr()
    assert (
        main(["edit", "editable", "--name", "Edited", "--arg=new value", "--terminal"])
        == 0
    )
    assert "Updated editable" in capsys.readouterr().out
    assert main(["doctor", "editable"]) == 0
    assert "OK: checked 1" in capsys.readouterr().out
