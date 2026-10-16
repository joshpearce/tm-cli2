"""Syrupy extension that masks volatile fields for stable golden snapshots.

Masks ids and ISO-8601 datetimes to allow snapshot testing of dynamic data.
"""

from __future__ import annotations

import re
from typing import Any

from syrupy.extensions.amber import AmberSnapshotExtension

# YYYY-MM-DDTHH:MM:SS(.ffffff)?(+HH:MM|Z)? — covers Python's datetime.isoformat() output
_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?$",
)

_ID_KEY_EXACT = frozenset({"id"})
_ID_SUFFIX = "_id"


def _is_id_key(key: str) -> bool:
    return key in _ID_KEY_EXACT or key.endswith(_ID_SUFFIX)


def mask(value: Any) -> Any:
    """Recursively mask ids and ISO datetimes in dicts, lists, and strings."""
    if isinstance(value, dict):
        return {
            k: ("<INT>" if (_is_id_key(k) and isinstance(v, int)) else mask(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [mask(item) for item in value]
    if isinstance(value, str) and _ISO_DATETIME_RE.match(value):
        return "<DATETIME>"
    return value


class MaskingSnapshotExtension(AmberSnapshotExtension):
    """Syrupy extension that masks volatile fields before snapshotting."""

    def serialize(self, data: Any, **kwargs: Any) -> str:  # type: ignore[override]
        return super().serialize(mask(_to_plain(data)), **kwargs)


def _to_plain(data: Any) -> Any:
    """Convert Pydantic models to plain dicts so the mask can walk them."""
    if hasattr(data, "model_dump"):
        return data.model_dump(mode="json")
    if isinstance(data, list):
        return [_to_plain(item) for item in data]
    if isinstance(data, dict):
        return {k: _to_plain(v) for k, v in data.items()}
    return data
