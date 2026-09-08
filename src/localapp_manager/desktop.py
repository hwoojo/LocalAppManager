"""Generation of freedesktop.org desktop entries and execution wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import shlex


def build_wrapper(command: Sequence[str]) -> str:
    """Create a POSIX shell wrapper with each stored argv item safely quoted."""

    return "#!/bin/sh\nexec " + shlex.join(command) + ' "$@"\n'


def _desktop_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _desktop_exec_path(path: Path) -> str:
    escaped = str(path).replace("%", "%%")
    escaped = escaped.replace("\\", "\\\\")
    escaped = escaped.replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def build_desktop_entry(
    *,
    name: str,
    wrapper_path: Path,
    icon_path: Path | None,
    terminal: bool,
    categories: Sequence[str],
    startup_notify: bool,
    mime_types: Sequence[str] = (),
    desktop_argument: str | None = None,
) -> str:
    exec_value = _desktop_exec_path(wrapper_path)
    if desktop_argument is not None:
        exec_value += f" {desktop_argument}"
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={_desktop_string(name)}",
        f"Exec={exec_value}",
    ]
    if icon_path is not None:
        lines.append(f"Icon={_desktop_string(str(icon_path))}")
    lines.extend(
        [
            f"Terminal={'true' if terminal else 'false'}",
            "Categories=" + ";".join(categories) + ";",
            f"StartupNotify={'true' if startup_notify else 'false'}",
        ]
    )
    if mime_types:
        lines.append("MimeType=" + ";".join(mime_types) + ";")
    return "\n".join(lines) + "\n"
