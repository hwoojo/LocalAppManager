"""Centralized XDG and LocalAppManager path calculation."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_home: Path
    config_home: Path
    state_home: Path
    managed_apps: Path
    bin_dir: Path

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        home: Path | None = None,
    ) -> "AppPaths":
        env = os.environ if environ is None else environ
        resolved_home = (
            Path(env.get("HOME", str(Path.home()))) if home is None else home
        )

        def xdg_path(variable: str, fallback: Path) -> Path:
            configured = env.get(variable)
            candidate = Path(configured).expanduser() if configured else fallback
            return candidate if candidate.is_absolute() else fallback

        data_home = xdg_path("XDG_DATA_HOME", resolved_home / ".local" / "share")
        config_home = xdg_path("XDG_CONFIG_HOME", resolved_home / ".config")
        state_home = xdg_path("XDG_STATE_HOME", resolved_home / ".local" / "state")
        return cls(
            data_home=data_home,
            config_home=config_home,
            state_home=state_home,
            managed_apps=resolved_home / ".local" / "opt",
            bin_dir=resolved_home / ".local" / "bin",
        )

    @property
    def app_data_dir(self) -> Path:
        return self.data_home / "localapp-manager"

    @property
    def manifest_dir(self) -> Path:
        return self.app_data_dir / "manifests"

    @property
    def app_config_dir(self) -> Path:
        return self.config_home / "localapp-manager"

    @property
    def app_state_dir(self) -> Path:
        return self.state_home / "localapp-manager"

    @property
    def desktop_entry_dir(self) -> Path:
        return self.data_home / "applications"

    @property
    def icon_dir(self) -> Path:
        return self.data_home / "icons"

    def ensure_manifest_dir(self) -> Path:
        self.manifest_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        return self.manifest_dir

    def managed_app_dir(self, app_id: str) -> Path:
        return self.managed_apps / app_id

    def wrapper_path(self, app_id: str) -> Path:
        return self.bin_dir / app_id

    def desktop_entry_path(self, app_id: str) -> Path:
        return self.desktop_entry_dir / f"{app_id}.desktop"

    def managed_icon_path(self, app_id: str, suffix: str) -> Path:
        return self.icon_dir / "localapp-manager" / f"{app_id}{suffix}"
