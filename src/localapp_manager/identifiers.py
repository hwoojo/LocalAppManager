"""Safe, human-readable application ID generation."""

from __future__ import annotations

from collections.abc import Collection
import re
import unicodedata


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or "app"


def generate_app_id(name: str, existing_ids: Collection[str] = ()) -> str:
    """Return a slug, adding the first available numeric suffix on collision."""

    base = slugify(name)
    if base not in existing_ids:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing_ids:
        suffix += 1
    return f"{base}-{suffix}"
