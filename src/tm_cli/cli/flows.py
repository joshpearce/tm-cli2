"""tm flow — DataFlow CRUDL + search + payload junction subgroup."""

# pattern: Imperative Shell

from __future__ import annotations

from typing import TYPE_CHECKING

import click
from pydantic import ValidationError

from tm_cli.cli._errors import NotFoundError, UserError, map_exception
from tm_cli.cli._options import (
    apply_sort,
    dfd_diagram_id_option,
    json_fields_option,
    list_options,
    parse_json_fields,
    resolve_default_diagram_id,
)
from tm_cli.cli._output import emit, project_fields
from tm_cli.cli._stdin import enforce_stdin_exclusive, read_json_stdin
from tm_cli.db import (
    DataFlow,
    DataFlowCreate,
    DataFlowRepository,
    DataFlowUpdate,
    EntityDocumentRepository,
    EntityObservationRepository,
    connect,
)

if TYPE_CHECKING:
    import sqlite3


@click.group(name="flow")
def flow_group() -> None:
    """Manage DFD data flows."""


@flow_group.command(name="list")
@list_options
@dfd_diagram_id_option
@json_fields_option
@click.pass_context
def list_flows(
    ctx, *, limit, offset, sort_field, order, diagram_id, json_fields
) -> None:
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = DataFlowRepository(conn).list(resolved, limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@flow_group.command(name="get")
@click.argument("flow_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_flow(ctx, flow_id, *, json_fields) -> None:
    with connect() as conn:
        row = DataFlowRepository(conn).get(flow_id)
    if row is None:
        raise NotFoundError(f"DataFlow id={flow_id} not found", id=str(flow_id))
    fields = parse_json_fields(json_fields)
    payload = project_fields(row.model_dump(mode="json"), fields)
    emit(ctx, payload)


@flow_group.command(name="create")
@dfd_diagram_id_option
@click.option("--node1-id", "node1_id", type=click.INT, default=None)
@click.option("--node2-id", "node2_id", type=click.INT, default=None)
@click.option("--name", default=None)
@click.option("--protocol", default=None)
@click.option("--authenticated/--no-authenticated", "authenticated", default=None)
@click.option("--encrypted/--no-encrypted", "encrypted", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_flow(
    ctx,
    *,
    diagram_id,
    node1_id,
    node2_id,
    name,
    protocol,
    authenticated,
    encrypted,
    use_stdin,
    if_not_exists,
    dry_run,
) -> None:
    """Create a data flow. Endpoints are canonicalized (lower id first)."""
    enforce_stdin_exclusive(
        use_stdin,
        {
            "node1_id": node1_id,
            "node2_id": node2_id,
            "name": name,
            "protocol": protocol,
            "authenticated": authenticated,
            "encrypted": encrypted,
        },
    )
    if use_stdin:
        body = read_json_stdin()
    else:
        if (
            node1_id is None
            or node2_id is None
            or name is None
            or protocol is None
            or authenticated is None
            or encrypted is None
        ):
            raise click.UsageError(
                "--node1-id, --node2-id, --name, --protocol, "
                "--authenticated/--no-authenticated, and "
                "--encrypted/--no-encrypted are required (or use --stdin)"
            )
        body = {
            "node1_id": node1_id,
            "node2_id": node2_id,
            "name": name,
            "protocol": protocol,
            "authenticated": authenticated,
            "encrypted": encrypted,
        }

    if isinstance(body, list):
        models = []
        for index, item in enumerate(body):
            try:
                models.append(DataFlowCreate.model_validate(item))
            except ValidationError as e:
                raise map_exception(
                    e, input_payload={"index": index, "item": item}
                ) from e
        if dry_run:
            emit(
                ctx,
                {
                    "dry_run": True,
                    "would_create": [m.model_dump(mode="json") for m in models],
                },
            )
            return
        with connect() as conn:
            resolved = resolve_default_diagram_id(
                conn, diagram_id, create_if_missing=True
            )
            assert resolved is not None
            repo = DataFlowRepository(conn)
            created = [repo.create(resolved, m) for m in models]
        emit(
            ctx,
            [
                {"diagram_id": str(resolved), **c.model_dump(mode="json")}
                for c in created
            ],
        )
        return

    model = DataFlowCreate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        assert resolved is not None
        created_flow = DataFlowRepository(conn).create(resolved, model)
    emit(ctx, {"diagram_id": str(resolved), **created_flow.model_dump(mode="json")})


@flow_group.command(name="update")
@click.argument("flow_id", type=click.INT)
@click.option("--name", default=None)
@click.option("--protocol", default=None)
@click.option("--authenticated/--no-authenticated", "authenticated", default=None)
@click.option("--encrypted/--no-encrypted", "encrypted", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_flow(
    ctx, flow_id, *, name, protocol, authenticated, encrypted, use_stdin, dry_run
) -> None:
    """Update a data flow's metadata.

    Endpoints (node1_id/node2_id) are immutable. Delete and recreate to change
    them.
    """
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "protocol": protocol,
            "authenticated": authenticated,
            "encrypted": encrypted,
        },
    )
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
        # Reject smuggled endpoint fields with a friendly hint.
        if "node1_id" in body or "node2_id" in body:
            raise click.UsageError(
                "Endpoints are immutable on DataFlow. Delete and recreate "
                "to swap node1_id/node2_id."
            )
    else:
        body = {
            k: v
            for k, v in {
                "name": name,
                "protocol": protocol,
                "authenticated": authenticated,
                "encrypted": encrypted,
            }.items()
            if v is not None
        }
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = DataFlowUpdate.model_validate(body)
    if dry_run:
        emit(
            ctx,
            {
                "dry_run": True,
                "would_update": {
                    "id": str(flow_id),
                    "patch": patch.model_dump(mode="json", exclude_none=True),
                },
            },
        )
        return
    with connect() as conn:
        updated = DataFlowRepository(conn).update(flow_id, patch)
    if updated is None:
        raise NotFoundError(f"DataFlow id={flow_id} not found", id=str(flow_id))
    emit(ctx, updated.model_dump(mode="json"))


@flow_group.command(name="delete")
@click.argument("flow_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_flow(ctx, flow_id, *, yes, dry_run) -> None:
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(flow_id)})
        return
    with connect() as conn:
        existed = DataFlowRepository(conn).delete(flow_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(flow_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(flow_id), "reason": "not_found"})


@flow_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@dfd_diagram_id_option
@json_fields_option
@click.pass_context
def search_flows(
    ctx, text, *, limit, offset, sort_field, order, diagram_id, json_fields
) -> None:
    """Full-text search across DataFlow name and protocol."""
    text_str = " ".join(text).strip() if text else ""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = DataFlowRepository(conn).search(
            resolved,
            text=text_str if text_str else None,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


def _endpoint_callback(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> int | None:
    if value is None:
        return None
    return int(value)


def _resolve_source_endpoint(
    conn: sqlite3.Connection, flow_id: int, from_node_id: int
) -> tuple[int, DataFlow]:
    """Translate ``--from <node_id>`` to a flow's ``source_endpoint`` (1 or 2).

    Raises ``NotFoundError`` if the flow doesn't exist; ``UserError`` if
    ``from_node_id`` is neither endpoint of the flow. The hint exposes both
    real endpoint ids so the agent can correct mismatches without a separate
    ``flow get`` call.

    Returns the resolved (endpoint, flow) so callers can reuse the loaded
    row without a second ``.get(flow_id)``.
    """
    flow = DataFlowRepository(conn).get(flow_id)
    if flow is None:
        raise NotFoundError(f"Flow id={flow_id} not found", id=str(flow_id))
    # Self-loops are rejected at flow create (node1_id != node2_id),
    # so endpoint 1 vs 2 is unambiguous.
    if from_node_id == flow.node1_id:
        return 1, flow
    if from_node_id == flow.node2_id:
        return 2, flow
    raise UserError(
        f"Node id={from_node_id} is not an endpoint of flow id={flow_id}",
        flow_id=str(flow_id),
        from_node_id=str(from_node_id),
        node1_id=str(flow.node1_id),
        node2_id=str(flow.node2_id),
        hint=f"Pass --from {flow.node1_id} or --from {flow.node2_id}.",
    )


@flow_group.command(name="add-payload")
@click.argument("flow_id", type=click.INT)
@click.option(
    "--data-item",
    "data_item_id",
    type=click.INT,
    required=True,
    help="DataItem id to attach as a payload.",
)
@click.option(
    "--from",
    "from_node_id",
    type=click.INT,
    required=True,
    help="Node id this data item is sourced at (must be node1 or node2 of the flow).",
)
@click.pass_context
def add_payload(ctx, flow_id, *, data_item_id, from_node_id) -> None:
    """Attach a data item to a flow as sourced at a specific node."""
    with connect() as conn:
        repo = DataFlowRepository(conn)
        source_endpoint, _ = _resolve_source_endpoint(conn, flow_id, from_node_id)
        # Pre-check: was this exact triple already attached?
        existing = repo.payload_for_flow(flow_id, source_endpoint=source_endpoint)
        already_present = any(item.id == data_item_id for item in existing)
        repo.add_payload(flow_id, data_item_id, source_endpoint)
    emit(
        ctx,
        {
            "linked": not already_present,
            "flow_id": str(flow_id),
            "data_item_id": str(data_item_id),
            "from_node_id": str(from_node_id),
            "endpoint": source_endpoint,
            **({"reason": "already_linked"} if already_present else {}),
        },
    )


@flow_group.command(name="remove-payload")
@click.argument("flow_id", type=click.INT)
@click.option("--data-item", "data_item_id", type=click.INT, required=True)
@click.option(
    "--from",
    "from_node_id",
    type=click.INT,
    required=True,
    help="Node id this data item is sourced at (must be node1 or node2 of the flow).",
)
@click.pass_context
def remove_payload(ctx, flow_id, *, data_item_id, from_node_id) -> None:
    """Detach a data item from a flow at a specific source node."""
    with connect() as conn:
        repo = DataFlowRepository(conn)
        source_endpoint, _ = _resolve_source_endpoint(conn, flow_id, from_node_id)
        existed = repo.remove_payload(flow_id, data_item_id, source_endpoint)
    emit(
        ctx,
        {
            "unlinked": existed,
            "flow_id": str(flow_id),
            "data_item_id": str(data_item_id),
            "from_node_id": str(from_node_id),
            "endpoint": source_endpoint,
            **({"reason": "not_linked"} if not existed else {}),
        },
    )


@flow_group.command(name="list-payloads")
@click.argument("flow_id", type=click.INT)
@click.option(
    "--endpoint",
    "source_endpoint",
    type=click.Choice(["1", "2"]),
    default=None,
    callback=_endpoint_callback,
    help="Filter to payloads on a specific endpoint.",
)
@list_options
@json_fields_option
@click.pass_context
def list_payloads(
    ctx, flow_id, *, source_endpoint, limit, offset, sort_field, order, json_fields
) -> None:
    """List data items attached to a flow."""
    with connect() as conn:
        if DataFlowRepository(conn).get(flow_id) is None:
            raise NotFoundError(f"DataFlow id={flow_id} not found", id=str(flow_id))
        rows = DataFlowRepository(conn).payload_for_flow(
            flow_id, source_endpoint=source_endpoint
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@flow_group.command(name="link-document")
@click.argument("flow_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def flow_link_document(ctx, flow_id: int, doc_id: int) -> None:
    """Link a document to this flow. Idempotent."""
    with connect() as conn:
        repo = EntityDocumentRepository(conn)
        existing_ids = {d.id for d in repo.documents_for_entity(flow_id)}
        already = doc_id in existing_ids
        repo.link(flow_id, doc_id)
    payload = {
        "linked": not already,
        "flow_id": str(flow_id),
        "document_id": str(doc_id),
    }
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@flow_group.command(name="unlink-document")
@click.argument("flow_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def flow_unlink_document(ctx, flow_id: int, doc_id: int) -> None:
    """Remove a document↔flow link. Idempotent."""
    with connect() as conn:
        existed = EntityDocumentRepository(conn).unlink(flow_id, doc_id)
    payload = {
        "unlinked": existed,
        "flow_id": str(flow_id),
        "document_id": str(doc_id),
    }
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@flow_group.command(name="list-documents")
@click.argument("flow_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def flow_list_documents(
    ctx, flow_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List documents linked to this flow."""
    with connect() as conn:
        if DataFlowRepository(conn).get(flow_id) is None:
            raise NotFoundError(f"DataFlow id={flow_id} not found", id=str(flow_id))
        rows = EntityDocumentRepository(conn).documents_for_entity(flow_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@flow_group.command(name="link-observation")
@click.argument("flow_id", type=click.INT)
@click.argument("obs_id", type=click.INT)
@click.pass_context
def flow_link_observation(ctx, flow_id: int, obs_id: int) -> None:
    """Link an observation to this flow. Idempotent."""
    with connect() as conn:
        repo = EntityObservationRepository(conn)
        already = repo.is_linked(flow_id, obs_id)
        repo.link(flow_id, obs_id)
    payload = {
        "linked": not already,
        "flow_id": str(flow_id),
        "observation_id": str(obs_id),
    }
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@flow_group.command(name="unlink-observation")
@click.argument("flow_id", type=click.INT)
@click.argument("obs_id", type=click.INT)
@click.pass_context
def flow_unlink_observation(ctx, flow_id: int, obs_id: int) -> None:
    """Remove an observation↔flow link. Idempotent."""
    with connect() as conn:
        existed = EntityObservationRepository(conn).unlink(flow_id, obs_id)
    payload = {
        "unlinked": existed,
        "flow_id": str(flow_id),
        "observation_id": str(obs_id),
    }
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@flow_group.command(name="list-observations")
@click.argument("flow_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def flow_list_observations(
    ctx, flow_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List observations linked to this flow."""
    with connect() as conn:
        if DataFlowRepository(conn).get(flow_id) is None:
            raise NotFoundError(f"DataFlow id={flow_id} not found", id=str(flow_id))
        rows = EntityObservationRepository(conn).observations_for_entity(flow_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    if limit is not None:
        sliced = sorted_rows[offset : offset + limit]
    else:
        sliced = sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
