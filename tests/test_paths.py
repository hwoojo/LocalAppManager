from pathlib import Path

from localapp_manager.paths import AppPaths


def test_default_paths_follow_xdg_conventions() -> None:
    paths = AppPaths.from_environment({}, home=Path("/home/tester"))
    assert paths.app_data_dir == Path("/home/tester/.local/share/localapp-manager")
    assert paths.managed_apps == Path("/home/tester/.local/opt")
    assert paths.bin_dir == Path("/home/tester/.local/bin")
    assert paths.desktop_entry_dir == Path("/home/tester/.local/share/applications")


def test_xdg_overrides_are_centralized() -> None:
    paths = AppPaths.from_environment(
        {
            "XDG_DATA_HOME": "/tmp/data",
            "XDG_CONFIG_HOME": "/tmp/config",
            "XDG_STATE_HOME": "/tmp/state",
        },
        home=Path("/home/tester"),
    )
    assert paths.manifest_dir == Path("/tmp/data/localapp-manager/manifests")
    assert paths.app_config_dir == Path("/tmp/config/localapp-manager")
    assert paths.app_state_dir == Path("/tmp/state/localapp-manager")


def test_relative_xdg_override_is_ignored() -> None:
    paths = AppPaths.from_environment(
        {"XDG_DATA_HOME": "relative/data"}, home=Path("/home/tester")
    )
    assert paths.data_home == Path("/home/tester/.local/share")


def test_ensure_manifest_dir_only_creates_storage_directory(tmp_path: Path) -> None:
    paths = AppPaths.from_environment(
        {"XDG_DATA_HOME": str(tmp_path / "data")}, home=tmp_path
    )
    paths.ensure_manifest_dir()
    assert paths.manifest_dir.is_dir()
    assert not paths.desktop_entry_dir.exists()
    assert not paths.managed_apps.exists()
