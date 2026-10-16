"""Output helpers — ``emit()`` is the single write path for all command results."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

import click

_ID_FIELD_EXACT = frozenset({"id"})
_ID_SUFFIX = "_id"
_IDS_SUFFIX = "_ids"


def _is_int_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _stringify_ids(obj: Any) -> Any:
    # The _id / _ids suffix match is greedy by design (e.g., user_id, node_ids).
    # Field-name collisions are the entity author's responsibility.
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if k in _ID_FIELD_EXACT or k.endswith(_ID_SUFFIX):
                # Scalar id field — stringify int, recurse otherwise.
                result[k] = str(v) if _is_int_id(v) else _stringify_ids(v)
            elif k.endswith(_IDS_SUFFIX) and isinstance(v, list):
                # Plural ids list — stringify each int element.
                result[k] = [
                    str(item) if _is_int_id(item) else _stringify_ids(item)
                    for item in v
                ]
            else:
                result[k] = _stringify_ids(v)
        return result
    if isinstance(obj, list):
        return [_stringify_ids(item) for item in obj]
    return obj


class _IsoEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:  # noqa: D401
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        return super().default(o)


def _to_jsonable(payload: Any) -> Any:
    # Pydantic's model_dump(mode="json") handles nested-model recursion natively,
    # so we deliberately don't re-walk after the initial conversion.
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return _stringify_ids(payload)


def _id_only_value(payload: Any) -> str | None:
    """Return the bare id string for an id-bearing dict, or None if not id-bearing.

    - Prefers a bare ``id`` key.
    - Falls back to the first ``*_id``-suffixed key in insertion order
      (so ``tm diagram push`` returns ``diagram_id`` — the local id, not ``remote_id``,
      because ``diagram_id`` appears first in the payload).
    - Returns None for non-dict payloads or dicts without any id-bearing key.

    Note: this runs AFTER ``_to_jsonable`` (so ids are already stringified),
    and the returned value is the post-stringification string.
    """
    if not isinstance(payload, dict):
        return None
    # Prefer bare "id" first.
    if "id" in payload:
        return str(payload["id"])
    # Fall back to the first *_id-suffixed key in insertion order.
    for key in payload:
        if key.endswith(_ID_SUFFIX):
            return str(payload[key])
    return None


def _json_mode(ctx: click.Context) -> bool:
    obj = ctx.obj if ctx.obj is not None else {}
    return bool(obj.get("json", True))


def project_fields(payload: Any, fields: list[str] | None) -> Any:
    """Return ``payload`` projected to only the named ``fields``.

    Walks dicts and lists. Missing keys are silently dropped.
    """

    if fields is None:
        return payload
    if isinstance(payload, dict):
        return {k: payload[k] for k in fields if k in payload}
    if isinstance(payload, list):
        return [project_fields(item, fields) for item in payload]
    return payload


def emit(
    ctx: click.Context,
    payload: object,
    *,
    list_mode: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> None:
    """Emit ``payload`` to stdout.

    list_mode=True writes NDJSON, one row per line, with an optional
    ``_pagination`` footer when ``len(rows) == limit``.
    """

    json_mode = _json_mode(ctx)
    indent = None if json_mode else 2
    id_only = bool((ctx.obj or {}).get("id_only", False))

    if list_mode and id_only:
        rows: list[Any] = list(payload) if isinstance(payload, Iterable) else [payload]
        for row in rows:
            row_jsonable = _to_jsonable(row)
            value = _id_only_value(row_jsonable)
            if value is not None:
                click.echo(value)
        # NOTE: the _pagination footer is intentionally suppressed under --id-only.
        return

    if list_mode:
        rows = list(payload) if isinstance(payload, Iterable) else [payload]
        for row in rows:
            click.echo(json.dumps(_to_jsonable(row), cls=_IsoEncoder))
        if limit is not None and len(rows) == limit:
            footer = {
                "_pagination": {
                    "next_offset": offset + limit,
                    "returned": len(rows),
                },
            }
            click.echo(json.dumps(footer, cls=_IsoEncoder))
        return

    if id_only:
        jsonable = _to_jsonable(payload)
        value = _id_only_value(jsonable)
        if value is not None:
            click.echo(value)
            return
        # Fall through to normal JSON for non-id-bearing payloads (e.g. schema).

    click.echo(json.dumps(_to_jsonable(payload), cls=_IsoEncoder, indent=indent))
