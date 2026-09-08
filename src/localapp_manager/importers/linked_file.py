"""Compatibility entry point for linked file registration."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..models import AppManifest
from ..storage import ManifestStore
from .file import register_file


def register_linked_file(
    store: ManifestStore,
    source: str | Path,
    *,
    name: str | None = None,
    app_id: str | None = None,
    kind: str = "auto",
    arguments: Sequence[str] = (),
    working_directory: str | Path | None = None,
    terminal: bool = False,
) -> AppManifest:
    return register_file(
        store,
        source,
        mode="linked",
        name=name,
        app_id=app_id,
        kind=kind,
        arguments=arguments,
        working_directory=working_directory,
        terminal=terminal,
    )
