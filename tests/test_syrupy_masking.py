"""Verify the masking serializer masks ids and datetimes."""

from __future__ import annotations

from datetime import UTC, datetime


def test_dict_with_id_and_datetime_is_masked(snapshot) -> None:
    payload = {
        "id": 42,
        "user_id": 7,
        "name": "static",
        "created": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC).isoformat(),
        "nested": {"item_id": 99, "label": "static"},
        "rows": [{"id": 1}, {"id": 2}],
    }
    assert payload == snapshot
