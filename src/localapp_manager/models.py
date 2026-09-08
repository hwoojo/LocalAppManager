"""Versioned data model for one registered local application."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import re
from typing import Any, ClassVar, Mapping


class ManifestValidationError(ValueError):
    """Raised when manifest data violates the supported schema."""


class AppKind(StrEnum):
    APPIMAGE = "appimage"
    PORTABLE_FOLDER = "portable-folder"
    EXECUTABLE = "executable"
    PYTHON_PROJECT = "python-project"


class InstallMode(StrEnum):
    MANAGED = "managed"
    LINKED = "linked"


_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _require_string(value: Any, field_name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise ManifestValidationError(f"{field_name} must be a non-empty string")
    return value


def _string_tuple(value: Any, field_name: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ManifestValidationError(f"{field_name} must be a list of strings")
    result = tuple(value)
    if nonempty and not result:
        raise ManifestValidationError(f"{field_name} must not be empty")
    if any(not isinstance(item, str) or not item for item in result):
        raise ManifestValidationError(f"{field_name} must contain only non-empty strings")
    return result


def _hash_tuple(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise ManifestValidationError("managed_file_hashes must be an object")
    result: list[tuple[str, str]] = []
    for path, digest in value.items():
        if not isinstance(path, str) or not path:
            raise ManifestValidationError("managed file hash paths must be non-empty strings")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ManifestValidationError("managed file hashes must be SHA-256 hex strings")
        result.append((path, digest))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class AppManifest:
    """The complete persisted registration record for one application.

    Commands are stored as an argv tuple so callers never need ``shell=True``.
    Managed and external paths are intentionally distinct safety domains.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = 2

    app_id: str
    name: str
    kind: AppKind
    install_mode: InstallMode
    source_path: str
    command: tuple[str, ...]
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    installed_path: str | None = None
    icon_path: str | None = None
    desktop_entry_path: str | None = None
    managed_files: tuple[str, ...] = ()
    external_paths: tuple[str, ...] = ()
    working_directory: str | None = None
    terminal: bool = False
    categories: tuple[str, ...] = ("Utility",)
    startup_notify: bool = True
    python_interpreter: str | None = None
    python_entry_type: str | None = None
    python_entrypoint: str | None = None
    managed_file_hashes: tuple[tuple[str, str], ...] = ()
    integration_managed: bool = True
    mime_types: tuple[str, ...] = ()
    desktop_argument: str | None = None
    schema_version: int = CURRENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.app_id, str) or not _ID_PATTERN.fullmatch(self.app_id):
            raise ManifestValidationError(
                "app_id must contain lowercase ASCII letters, digits, and single hyphens"
            )
        for field_name in ("name", "source_path"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ManifestValidationError(f"{field_name} must be a non-empty string")
        for field_name in (
            "installed_path",
            "icon_path",
            "desktop_entry_path",
            "working_directory",
            "python_interpreter",
            "python_entry_type",
            "python_entrypoint",
            "desktop_argument",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ManifestValidationError(
                    f"{field_name} must be null or a non-empty string"
                )
        if not isinstance(self.kind, AppKind):
            raise ManifestValidationError("kind must be an AppKind")
        if not isinstance(self.install_mode, InstallMode):
            raise ManifestValidationError("install_mode must be an InstallMode")
        if (
            not isinstance(self.command, tuple)
            or not self.command
            or any(not isinstance(item, str) or not item for item in self.command)
        ):
            raise ManifestValidationError("command must contain at least one non-empty argument")
        if type(self.schema_version) is not int or self.schema_version != self.CURRENT_SCHEMA_VERSION:
            raise ManifestValidationError(
                f"unsupported schema version {self.schema_version}; "
                f"expected {self.CURRENT_SCHEMA_VERSION}"
            )
        if not isinstance(self.registered_at, datetime) or self.registered_at.tzinfo is None:
            raise ManifestValidationError("registered_at must include a timezone")
        for field_name in ("terminal", "startup_notify", "integration_managed"):
            if type(getattr(self, field_name)) is not bool:
                raise ManifestValidationError(f"{field_name} must be a boolean")
        for field_name in ("managed_files", "external_paths", "categories", "mime_types"):
            values = getattr(self, field_name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, str) or not item for item in values
            ):
                raise ManifestValidationError(
                    f"{field_name} must be a tuple of non-empty strings"
                )
            if len(values) != len(set(values)):
                raise ManifestValidationError(f"{field_name} must not contain duplicates")
        if self.desktop_argument not in {None, "%f", "%F", "%u", "%U"}:
            raise ManifestValidationError("desktop_argument must be %f, %F, %u, or %U")
        if any(";" in value or any(ord(char) < 32 for char in value) for value in self.mime_types):
            raise ManifestValidationError("mime_types contain an invalid value")
        for category in self.categories:
            if not all(char.isalnum() or char == "-" for char in category):
                raise ManifestValidationError(
                    "categories may contain only letters, digits, and hyphens"
                )
        overlap = set(self.managed_files).intersection(self.external_paths)
        if overlap:
            raise ManifestValidationError(
                "a path cannot be both managed and external: " + ", ".join(sorted(overlap))
            )
        python_fields = (
            self.python_interpreter,
            self.python_entry_type,
            self.python_entrypoint,
        )
        if self.kind is AppKind.PYTHON_PROJECT:
            if any(value is None for value in python_fields):
                raise ManifestValidationError(
                    "python projects require interpreter, entry type, and entrypoint"
                )
            if self.python_entry_type not in {"script", "module"}:
                raise ManifestValidationError("python_entry_type must be script or module")
        elif any(value is not None for value in python_fields):
            raise ManifestValidationError(
                "python execution fields are only valid for python projects"
            )
        hash_paths: set[str] = set()
        for path, digest in self.managed_file_hashes:
            if path in hash_paths or path not in self.managed_files:
                raise ManifestValidationError(
                    "managed file hashes must uniquely reference managed_files"
                )
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ManifestValidationError("managed file hashes must be SHA-256 hex strings")
            hash_paths.add(path)
        object.__setattr__(
            self, "managed_file_hashes", tuple(sorted(self.managed_file_hashes))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "name": self.name,
            "kind": self.kind.value,
            "install_mode": self.install_mode.value,
            "source_path": self.source_path,
            "installed_path": self.installed_path,
            "command": list(self.command),
            "icon_path": self.icon_path,
            "desktop_entry_path": self.desktop_entry_path,
            "registered_at": self.registered_at.isoformat(),
            "managed_files": list(self.managed_files),
            "external_paths": list(self.external_paths),
            "working_directory": self.working_directory,
            "terminal": self.terminal,
            "categories": list(self.categories),
            "startup_notify": self.startup_notify,
            "python_interpreter": self.python_interpreter,
            "python_entry_type": self.python_entry_type,
            "python_entrypoint": self.python_entrypoint,
            "managed_file_hashes": dict(self.managed_file_hashes),
            "integration_managed": self.integration_managed,
            "mime_types": list(self.mime_types),
            "desktop_argument": self.desktop_argument,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AppManifest":
        if not isinstance(data, Mapping):
            raise ManifestValidationError("manifest root must be an object")
        try:
            schema_version = data["schema_version"]
            kind = AppKind(data["kind"])
            install_mode = InstallMode(data["install_mode"])
            registered_at_raw = _require_string(data["registered_at"], "registered_at")
            registered_at = datetime.fromisoformat(registered_at_raw)
        except KeyError as exc:
            raise ManifestValidationError(f"missing required field: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise ManifestValidationError(f"invalid manifest value: {exc}") from exc

        if type(schema_version) is not int:
            raise ManifestValidationError("schema_version must be an integer")
        terminal = data.get("terminal", False)
        if type(terminal) is not bool:
            raise ManifestValidationError("terminal must be a boolean")
        startup_notify = data.get("startup_notify", True)
        if type(startup_notify) is not bool:
            raise ManifestValidationError("startup_notify must be a boolean")
        integration_managed = data.get("integration_managed", True)
        if type(integration_managed) is not bool:
            raise ManifestValidationError("integration_managed must be a boolean")

        return cls(
            app_id=_require_string(data.get("app_id"), "app_id"),
            name=_require_string(data.get("name"), "name"),
            kind=kind,
            install_mode=install_mode,
            source_path=_require_string(data.get("source_path"), "source_path"),
            installed_path=_require_string(
                data.get("installed_path"), "installed_path", optional=True
            ),
            command=_string_tuple(data.get("command"), "command", nonempty=True),
            icon_path=_require_string(data.get("icon_path"), "icon_path", optional=True),
            desktop_entry_path=_require_string(
                data.get("desktop_entry_path"), "desktop_entry_path", optional=True
            ),
            registered_at=registered_at,
            managed_files=_string_tuple(data.get("managed_files", []), "managed_files"),
            external_paths=_string_tuple(data.get("external_paths", []), "external_paths"),
            working_directory=_require_string(
                data.get("working_directory"), "working_directory", optional=True
            ),
            terminal=terminal,
            categories=_string_tuple(data.get("categories", ["Utility"]), "categories"),
            startup_notify=startup_notify,
            python_interpreter=_require_string(
                data.get("python_interpreter"), "python_interpreter", optional=True
            ),
            python_entry_type=_require_string(
                data.get("python_entry_type"), "python_entry_type", optional=True
            ),
            python_entrypoint=_require_string(
                data.get("python_entrypoint"), "python_entrypoint", optional=True
            ),
            managed_file_hashes=_hash_tuple(data.get("managed_file_hashes", {})),
            integration_managed=integration_managed,
            mime_types=_string_tuple(data.get("mime_types", []), "mime_types"),
            desktop_argument=_require_string(
                data.get("desktop_argument"), "desktop_argument", optional=True
            ),
            schema_version=schema_version,
        )
