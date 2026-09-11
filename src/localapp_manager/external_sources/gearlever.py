"""Read-only discovery of applications tracked by Gear Lever."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
import shlex
import shutil

from ..models import AppKind


@dataclass(frozen=True, slots=True)
class GearLeverCandidate:
    name: str
    source: Path
    kind: AppKind
    command: tuple[str, ...]
    desktop_entry: Path | None
    icon: Path | None
    terminal: bool
    categories: tuple[str, ...]
    startup_notify: bool


def _desktop_for(
    name: str, applications_dir: Path, configured_source: Path
) -> Path | None:
    normalized = "".join(char.lower() for char in name if char.isalnum())
    matches: list[tuple[int, Path]] = []
    for path in applications_dir.glob("*.desktop"):
        score = 0
        candidate = "".join(char.lower() for char in path.stem if char.isalnum())
        if candidate == normalized:
            score += 100
        elif candidate in normalized or normalized in candidate:
            score += 20
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if f"TryExec={configured_source}" in text or str(configured_source) in text:
            score += 200
        for line in text.splitlines():
            if line.startswith("Name="):
                desktop_name = "".join(
                    char.lower() for char in line[5:] if char.isalnum()
                )
                if desktop_name == normalized:
                    score += 80
                break
        if score:
            matches.append((score, path))
    return (
        sorted(matches, key=lambda item: (-item[0], str(item[1])))[0][1]
        if matches
        else None
    )


def _parse_desktop(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
        entry = parser["Desktop Entry"]
    except (OSError, KeyError, configparser.Error):
        return {}
    argv = shlex.split(entry.get("Exec", ""))
    argv = [item for item in argv if not (item.startswith("%") and len(item) == 2)]
    if argv and argv[0] == "env":
        argv[0] = shutil.which("env") or "/usr/bin/env"
    icon_value = entry.get("Icon")
    icon = (
        Path(icon_value).expanduser()
        if icon_value and icon_value.startswith("/")
        else None
    )
    categories = tuple(
        value for value in entry.get("Categories", "Utility;").split(";") if value
    )
    return {
        "command": tuple(argv),
        "icon": icon,
        "terminal": entry.getboolean("Terminal", fallback=False),
        "categories": categories or ("Utility",),
        "startup_notify": entry.getboolean("StartupNotify", fallback=True),
        "try_exec": entry.get("TryExec"),
    }


def discover_gearlever(
    *,
    config_path: Path | None = None,
    applications_dir: Path | None = None,
) -> tuple[GearLeverCandidate, ...]:
    config_path = (
        config_path
        or Path.home() / ".var/app/it.mijorus.gearlever/config/gearlever.conf"
    )
    applications_dir = applications_dir or Path.home() / ".local/share/applications"
    parser = configparser.ConfigParser(interpolation=None)
    if not parser.read(config_path, encoding="utf-8"):
        return ()
    results: list[GearLeverCandidate] = []
    for section in parser.sections():
        if not section.startswith("app."):
            continue
        name = parser.get(section, "name", fallback="").strip()
        configured_source = Path(
            parser.get(section, "file_path", fallback="")
        ).expanduser()
        desktop = _desktop_for(name, applications_dir, configured_source)
        metadata = _parse_desktop(desktop)
        try_exec = metadata.get("try_exec")
        source = configured_source
        if not source.exists() and isinstance(try_exec, str) and try_exec:
            source = Path(try_exec).expanduser()
        command = metadata.get("command")
        if not isinstance(command, tuple) or not command:
            command = (str(source),)
        if not name or not source.exists():
            continue
        kind = (
            AppKind.APPIMAGE
            if source.name.lower().endswith(".appimage")
            else AppKind.EXECUTABLE
        )
        results.append(
            GearLeverCandidate(
                name=name,
                source=source.absolute(),
                kind=kind,
                command=command,
                desktop_entry=desktop,
                icon=metadata.get("icon")
                if isinstance(metadata.get("icon"), Path)
                else None,
                terminal=bool(metadata.get("terminal", False)),
                categories=metadata.get("categories", ("Utility",)),
                startup_notify=bool(metadata.get("startup_notify", True)),
            )
        )
    return tuple(sorted(results, key=lambda item: item.name.casefold()))
