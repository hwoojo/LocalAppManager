"""Pure manifest-data migrations between supported schema versions."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .models import ManifestValidationError


def migrate_manifest_data(
    data: Mapping[str, Any], *, target_version: int
) -> tuple[dict[str, Any], bool]:
    if not isinstance(data, Mapping):
        raise ManifestValidationError("manifest root must be an object")
    migrated = deepcopy(dict(data))
    version = migrated.get("schema_version")
    if type(version) is not int:
        raise ManifestValidationError("schema_version must be an integer")
    if version > target_version:
        raise ManifestValidationError(
            f"manifest schema {version} is newer than supported schema {target_version}"
        )
    changed = False
    if version == 1:
        migrated.setdefault("categories", ["Utility"])
        migrated.setdefault("startup_notify", True)
        migrated.setdefault("python_interpreter", None)
        migrated.setdefault("python_entry_type", None)
        migrated.setdefault("python_entrypoint", None)
        migrated.setdefault("managed_file_hashes", {})
        migrated.setdefault("integration_managed", True)
        migrated.setdefault("mime_types", [])
        migrated.setdefault("desktop_argument", None)
        if migrated.get("kind") == "python-project" and not migrated["python_interpreter"]:
            command = migrated.get("command", [])
            source = Path(migrated.get("source_path", "."))
            if len(command) >= 3 and command[1] == "-m":
                migrated["python_interpreter"] = command[0]
                migrated["python_entry_type"] = "module"
                migrated["python_entrypoint"] = command[2]
            elif len(command) >= 2:
                migrated["python_interpreter"] = command[0]
                migrated["python_entry_type"] = "script"
                try:
                    migrated["python_entrypoint"] = str(Path(command[1]).relative_to(source))
                except ValueError:
                    migrated["python_entrypoint"] = command[1]
        migrated["schema_version"] = 2
        version = 2
        changed = True
    if version != target_version:
        raise ManifestValidationError(
            f"no migration path from schema {version} to {target_version}"
        )
    return migrated, changed
