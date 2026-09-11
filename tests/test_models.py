from __future__ import annotations

from dataclasses import replace

import pytest

from localapp_manager.models import AppManifest, ManifestValidationError


def test_manifest_round_trip(sample_manifest: AppManifest) -> None:
    assert AppManifest.from_dict(sample_manifest.to_dict()) == sample_manifest


def test_command_preserves_arguments_and_spaces(sample_manifest: AppManifest) -> None:
    restored = AppManifest.from_dict(sample_manifest.to_dict())
    assert restored.command == ("/home/user/My Apps/sample", "--safe argument")


def test_managed_and_external_paths_must_not_overlap(
    sample_manifest: AppManifest,
) -> None:
    with pytest.raises(ManifestValidationError, match="both managed and external"):
        replace(
            sample_manifest,
            external_paths=sample_manifest.managed_files,
        )


def test_naive_registration_timestamp_is_rejected(sample_manifest: AppManifest) -> None:
    with pytest.raises(ManifestValidationError, match="timezone"):
        replace(
            sample_manifest,
            registered_at=sample_manifest.registered_at.replace(tzinfo=None),
        )


def test_unknown_schema_version_is_rejected(sample_manifest: AppManifest) -> None:
    data = sample_manifest.to_dict()
    data["schema_version"] = 999
    with pytest.raises(ManifestValidationError, match="unsupported schema"):
        AppManifest.from_dict(data)


def test_direct_construction_validates_runtime_types(
    sample_manifest: AppManifest,
) -> None:
    with pytest.raises(ManifestValidationError, match="terminal must be a boolean"):
        replace(sample_manifest, terminal="no")

    with pytest.raises(ManifestValidationError, match="kind must be an AppKind"):
        replace(sample_manifest, kind="executable")

    with pytest.raises(ManifestValidationError, match="categories may contain"):
        replace(sample_manifest, categories=("Utility;Bad",))
