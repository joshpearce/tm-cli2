"""Shared Click option decorators for the tm CLI.

These decorators are stacked onto entity commands in subsequent phases.
The default-diagram resolver function lands in Phase 4.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

import click

from tm_cli.cli._errors import NotFoundError, UserError

F = TypeVar("F", bound=Callable[..., Any])


def list_options(f: F) -> F:
    """Standard pagination + sort options for ``list`` and ``search`` commands."""
    f = click.option(
        "--limit",
        type=click.IntRange(min=1, max=10_000),
        default=50,
        show_default=True,
        help="Maximum rows to return.",
    )(f)
    f = click.option(
        "--offset",
        type=click.IntRange(min=0),
        default=0,
        show_default=True,
        help="Rows to skip from the start.",
    )(f)
    f = click.option(
        "--sort",
        "sort_field",
        default="id",
        show_default=True,
        metavar="FIELD",
        help="Column to sort by.",
    )(f)
    f = click.option(
        "--order",
        type=click.Choice(["asc", "desc"]),
        default="asc",
        show_default=True,
        help="Sort direction.",
    )(f)
    return f


def json_fields_option(f: F) -> F:
    """``--json FIELDS`` projects the listed comma-separated fields on output."""
    return click.option(
        "--json",
        "json_fields",
        metavar="FIELDS",
        default=None,
        help="Comma-separated field names to include in output.",
    )(f)


def dfd_diagram_id_option(f: F) -> F:
    """Hidden ``--diagram-id`` option for DFD entity commands.

    The resolver function (``resolve_default_diagram_id``) lands in Phase 4;
    this decorator only attaches the option so the option is in scope when
    Phase 4 wires it up.
    """
    return click.option(
        "--diagram-id",
        "diagram_id",
        type=click.INT,
        default=None,
        hidden=True,
        help="Diagram id (defaults to looking up or creating a 'default' diagram).",
    )(f)


def apply_sort(rows: Iterable[Any], *, sort_field: str, order: str) -> list[Any]:
    """Sort ``rows`` by ``sort_field`` (Pydantic model attribute) in given ``order``.

    Rows whose attribute is missing are placed at the end (stable).
    """

    rows_list = list(rows)
    if not sort_field:
        return rows_list
    reverse = order == "desc"
    sentinel = object()

    def key(row: Any) -> tuple[int, Any]:
        value = getattr(row, sort_field, sentinel)
        if value is sentinel:
            return (1, 0)
        return (0, value)

    return sorted(rows_list, key=key, reverse=reverse)


def parse_json_fields(value: str | None) -> list[str] | None:
    """Parse a ``--json FIELDS`` value into a list, or ``None`` if not specified."""
    if value is None:
        return None
    return [f.strip() for f in value.split(",") if f.strip()]


def resolve_default_diagram_id(
    conn: sqlite3.Connection,
    explicit_id: int | None,
    *,
    create_if_missing: bool,
) -> int | None:
    """Resolve the ``--diagram-id`` for a DFD command.

    Resolution order:
    - If ``explicit_id`` is set, verify the diagram exists; raise NotFoundError if not.
    - Else if ``$TM_DIAGRAM_ID`` is set, parse it as an int (UserError on non-int),
      verify the diagram exists (NotFoundError if missing), and return its id.
    - Otherwise scan for a diagram named ``default`` (lowest id wins on tie).
    - If none found:
        - ``create_if_missing=True``: create one with ``DiagramCreate(name="default")``.
        - ``create_if_missing=False``: return ``None`` (caller emits empty list).
    """
    # Imports are local to avoid a circular import at module load time
    # (``_options`` is imported by every entity module; the db package is heavy).
    from tm_cli.db import DiagramCreate, DiagramRepository

    repo = DiagramRepository(conn)

    if explicit_id is not None:
        existing = repo.get(explicit_id)
        if existing is None:
            raise NotFoundError(
                f"Diagram id={explicit_id} not found",
                id=str(explicit_id),
            )
        return existing.id

    # Consult $TM_DIAGRAM_ID when no explicit --diagram-id was provided.
    env_value = os.environ.get("TM_DIAGRAM_ID")
    if env_value:
        # Falsy env_value (None or "") falls through to the default-scan,
        # matching how shell / .env files conventionally express "unset".
        try:
            # int() permissively strips whitespace and accepts a leading sign;
            # this matches shell-conventional env-var parsing. Strict callers
            # should pre-validate before exporting.
            env_id = int(env_value)
        except ValueError:
            raise UserError(
                f"TM_DIAGRAM_ID must be an integer; got {env_value!r}",
                hint="Unset TM_DIAGRAM_ID or set it to a numeric diagram id.",
            ) from None
        existing = repo.get(env_id)
        if existing is None:
            raise NotFoundError(
                f"Diagram id={env_id} not found (from $TM_DIAGRAM_ID)",
                id=str(env_id),
            )
        return existing.id

    # Scan all diagrams for the lowest-id one named "default".
    # ``list()`` returns rows ordered by id ascending, so the first match wins.
    for diagram in repo.list():
        if diagram.name == "default":
            return diagram.id

    if not create_if_missing:
        return None

    new_diagram = repo.create(DiagramCreate(name="default"))
    return new_diagram.id
