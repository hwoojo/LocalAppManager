from pathlib import Path
import shutil
import subprocess

import pytest

from localapp_manager.desktop import build_desktop_entry, build_wrapper


def test_wrapper_quotes_stored_command_and_forwards_runtime_arguments() -> None:
    wrapper = build_wrapper(("/home/user/My Apps/tool", "value with spaces", "$(literal)"))
    assert wrapper == (
        "#!/bin/sh\n"
        "exec '/home/user/My Apps/tool' 'value with spaces' '$(literal)' \"$@\"\n"
    )


def test_desktop_entry_contains_supported_fields_and_safe_exec_path() -> None:
    entry = build_desktop_entry(
        name="My Tool",
        wrapper_path=Path("/home/user name/.local/bin/my-tool"),
        icon_path=Path("/home/user name/.local/share/icons/my tool.png"),
        terminal=True,
        categories=("Utility", "Development"),
        startup_notify=False,
    )
    assert entry == (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=My Tool\n"
        'Exec="/home/user name/.local/bin/my-tool"\n'
        "Icon=/home/user name/.local/share/icons/my tool.png\n"
        "Terminal=true\n"
        "Categories=Utility;Development;\n"
        "StartupNotify=false\n"
    )


def test_generated_entry_passes_desktop_file_validate(tmp_path: Path) -> None:
    validator = shutil.which("desktop-file-validate")
    if validator is None:
        pytest.skip("desktop-file-validate is not installed")
    entry_path = tmp_path / "sample.desktop"
    entry_path.write_text(
        build_desktop_entry(
            name="Sample Tool",
            wrapper_path=Path("/home/user/.local/bin/sample-tool"),
            icon_path=Path("/home/user/.local/share/icons/sample-tool.png"),
            terminal=False,
            categories=("Utility",),
            startup_notify=True,
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [validator, str(entry_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
