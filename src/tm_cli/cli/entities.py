"""tm entity — kind-agnostic id resolver."""

from __future__ import annotations

import click

from tm_cli.cli._errors import NotFoundError
from tm_cli.cli._options import json_fields_option, parse_json_fields
from tm_cli.cli._output import emit, project_fields
from tm_cli.db import (
    ContainerRepository,
    DataFlowRepository,
    DataItemRepository,
    NodeRepository,
    ProcessComponentRepository,
    connect,
)


@click.group(name="entity")
def entity_group() -> None:
    """Kind-agnostic DFD entity resolver."""


@entity_group.command(name="get")
@click.argument("entity_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_entity(ctx: click.Context, entity_id: int, *, json_fields: str | None) -> None:
    """Fetch a DFD entity (any kind) by id, with a ``kind`` discriminator."""
    with connect() as conn:
        row = conn.execute(
            "SELECT kind FROM entity WHERE id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Entity id={entity_id} not found", id=str(entity_id))
        kind = row["kind"]
        if kind == "node":
            payload = NodeRepository(conn).get(entity_id)
        elif kind == "container":
            payload = ContainerRepository(conn).get(entity_id)
        elif kind == "data_flow":
            payload = DataFlowRepository(conn).get(entity_id)
        elif kind == "data_item":
            payload = DataItemRepository(conn).get(entity_id)
        elif kind == "process_component":
            payload = ProcessComponentRepository(conn).get(entity_id)
        else:
            raise RuntimeError(
                f"Unexpected entity.kind={kind!r} for id={entity_id}; "
                "schema CHECK violated."
            )
    if payload is None:
        raise NotFoundError(f"Entity id={entity_id} not found", id=str(entity_id))
    fields = parse_json_fields(json_fields)
    body = {"kind": kind, **payload.model_dump(mode="json")}
    body = project_fields(body, fields)
    emit(ctx, body)
