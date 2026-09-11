from __future__ import annotations

from pathlib import Path

from localapp_manager.external_sources import discover_gearlever
from localapp_manager.importers import register_external_integration
from localapp_manager.models import AppKind
from localapp_manager.paths import AppPaths
from localapp_manager.removal import build_removal_plan, execute_removal
from localapp_manager.storage import ManifestStore


def test_discover_and_register_gearlever_without_duplicating_desktop(
    tmp_path: Path,
) -> None:
    appimage = tmp_path / "apps" / "Example.AppImage"
    appimage.parent.mkdir()
    appimage.write_bytes(b"app")
    appimage.chmod(0o700)
    icon = tmp_path / "example.png"
    icon.write_bytes(b"icon")
    applications = tmp_path / "applications"
    applications.mkdir()
    desktop = applications / "example.desktop"
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\nName=Example\n"
        f"Exec=env DESKTOPINTEGRATION=1 {appimage} %U\n"
        f"TryExec={appimage}\nIcon={icon}\n"
        "Terminal=false\nCategories=Utility;\nStartupNotify=true\n",
        encoding="utf-8",
    )
    config = tmp_path / "gearlever.conf"
    config.write_text(
        f"[app.123]\nname = Example\nfile_path = {appimage}\n",
        encoding="utf-8",
    )
    candidates = discover_gearlever(config_path=config, applications_dir=applications)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind is AppKind.APPIMAGE
    assert candidate.command[0].endswith("env")
    assert "%U" not in candidate.command

    store = ManifestStore(
        AppPaths.from_environment(
            {"XDG_DATA_HOME": str(tmp_path / "data")}, home=tmp_path / "home"
        )
    )
    manifest = register_external_integration(
        store,
        candidate.source,
        name=candidate.name,
        kind=candidate.kind,
        command=candidate.command,
        desktop_entry=candidate.desktop_entry,
        icon=candidate.icon,
        terminal=candidate.terminal,
        categories=candidate.categories,
        startup_notify=candidate.startup_notify,
    )
    assert manifest.app_id == "example"
    assert manifest.integration_managed is False
    assert manifest.managed_files == ()
    assert desktop.exists()
    result = execute_removal(store, build_removal_plan(store, manifest.app_id))
    assert result.manifest_removed
    assert appimage.exists()
    assert desktop.exists()
    assert icon.exists()
