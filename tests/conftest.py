from __future__ import annotations

from datetime import UTC, datetime

import pytest

from localapp_manager.models import AppKind, AppManifest, InstallMode


@pytest.fixture
def sample_manifest() -> AppManifest:
    return AppManifest(
        app_id="sample-app",
        name="Sample App",
        kind=AppKind.EXECUTABLE,
        install_mode=InstallMode.LINKED,
        source_path="/home/user/My Apps/sample",
        command=("/home/user/My Apps/sample", "--safe argument"),
        registered_at=datetime(2026, 7, 18, 6, 0, tzinfo=UTC),
        icon_path="/home/user/icons/sample.png",
        managed_files=("/home/user/.local/share/applications/sample-app.desktop",),
        external_paths=("/home/user/My Apps/sample",),
    )

