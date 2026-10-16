"""tm data-item — DataItem CRUDL + search subgroup with default-diagram fallback."""

from __future__ import annotations

from typing import Any, get_args

import click
from pydantic import ValidationError

from tm_cli.cli._errors import NotFoundError, map_exception
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
    Classification,
    DataFlowRepository,
    DataItemCreate,
    DataItemRepository,
    DataItemUpdate,
    EntityDocumentRepository,
    EntityObservationRepository,
    connect,
)

_CLASSIFICATION_CHOICES = list(get_args(Classification))

# Sentinel for "user explicitly cleared the parent_node_id" on update.
_CLEAR_PARENT = object()


def _parse_parent_node_id(value: str | None) -> int | None | object:
    """Parse ``--parent-node-id`` for update.

    Three distinct return values:
    - ``None`` — Click flag was NOT supplied (default). The caller leaves the
      field untouched in the patch (omit from ``DataItemUpdate`` body).
    - ``_CLEAR_PARENT`` (sentinel) — flag was supplied with ``""`` / ``"none"`` /
      ``"null"``. The caller sets ``parent_node_id=None`` in the patch (DFD
      repos honor explicit ``None`` to clear the column).
    - ``int`` — flag was supplied with an integer string. Set to that id.

    The distinction between "flag absent" (``None``) and "flag explicitly
    cleared" (``_CLEAR_PARENT``) matters because ``DataItemUpdate`` uses
    ``model_dump(exclude_unset=True)`` and the repo's nullable-field handling
    differentiates the two states. Tests in Task 6 cover both branches.
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in ("", "none", "null"):
        return _CLEAR_PARENT
    try:
        return int(value)
    except ValueError as e:
        msg = f"--parent-node-id must be integer, 'none', or empty: {value!r}"
        raise click.UsageError(msg) from e


def _parse_parent_node_filter(value: str | None) -> int | None:
    """Parse ``--parent-node-id`` filter for list/search (always integer-or-none)."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as e:
        msg = f"--parent-node-id filter must be integer: {value!r}"
        raise click.UsageError(msg) from e


@click.group(name="data-item")
def data_item_group() -> None:
    """Manage DFD data items."""


@data_item_group.command(name="list")
@list_options
@dfd_diagram_id_option
@click.option(
    "--classification",
    type=click.Choice(_CLASSIFICATION_CHOICES),
    default=None,
    help="Filter to data items with this classification.",
)
@click.option(
    "--parent-node-id",
    "parent_node_id_raw",
    default=None,
    help="Filter to data items whose parent_node_id equals this integer.",
)
@json_fields_option
@click.pass_context
def list_items(
    ctx,
    *,
    limit,
    offset,
    sort_field,
    order,
    diagram_id,
    classification,
    parent_node_id_raw,
    json_fields,
) -> None:
    """List data items in a diagram (defaults to the 'default' diagram)."""
    parent_node_id = _parse_parent_node_filter(parent_node_id_raw)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = DataItemRepository(conn).search(
            resolved,
            text=None,
            classification=classification,
            parent_node_id=parent_node_id,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@data_item_group.command(name="get")
@click.argument("item_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_item(ctx, item_id, *, json_fields) -> None:
    """Get a data item by id."""
    with connect() as conn:
        row = DataItemRepository(conn).get(item_id)
    if row is None:
        raise NotFoundError(f"DataItem id={item_id} not found", id=str(item_id))
    fields = parse_json_fields(json_fields)
    payload = project_fields(row.model_dump(mode="json"), fields)
    emit(ctx, payload)


@data_item_group.command(name="create")
@dfd_diagram_id_option
@click.option("--identifier", default=None, help="Data item identifier.")
@click.option("--name", default=None, help="Data item name.")
@click.option("--description", default=None, help="Data item description.")
@click.option(
    "--classification",
    type=click.Choice(_CLASSIFICATION_CHOICES),
    default=None,
    help="Data item classification.",
)
@click.option(
    "--parent-node-id",
    "parent_node_id",
    type=click.INT,
    default=None,
    help="Parent node id (optional).",
)
@click.option(
    "--stdin",
    "use_stdin",
    is_flag=True,
    default=False,
    help="Read JSON object or array from stdin instead of named flags.",
)
@click.option(
    "--if-not-exists",
    "if_not_exists",
    is_flag=True,
    default=False,
    help="No-op for DataItem (identifier not unique); kept for consistency.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Dry-run.")
@click.pass_context
def create_item(
    ctx,
    *,
    diagram_id,
    identifier,
    name,
    description,
    classification,
    parent_node_id,
    use_stdin,
    if_not_exists,
    dry_run,
) -> None:
    """Create a data item. Use named flags or --stdin."""
    enforce_stdin_exclusive(
        use_stdin,
        {
            "identifier": identifier,
            "name": name,
            "description": description,
            "classification": classification,
            "parent_node_id": parent_node_id,
        },
    )
    if use_stdin:
        body = read_json_stdin()
    else:
        if identifier is None or name is None or description is None:
            raise click.UsageError(
                "--identifier, --name, --description required (or use --stdin)"
            )
        body = {"identifier": identifier, "name": name, "description": description}
        if classification is not None:
            body["classification"] = classification
        if parent_node_id is not None:
            body["parent_node_id"] = parent_node_id

    if isinstance(body, list):
        models: list[DataItemCreate] = []
        for index, item in enumerate(body):
            try:
                models.append(DataItemCreate.model_validate(item))
            except ValidationError as e:
                raise map_exception(
                    e, input_payload={"index": index, "item": item}
                ) from e
        if dry_run:
            would_create = [m.model_dump(mode="json") for m in models]
            emit(ctx, {"dry_run": True, "would_create": would_create})
            return
        with connect() as conn:
            resolved = resolve_default_diagram_id(
                conn, diagram_id, create_if_missing=True
            )
            assert resolved is not None
            repo = DataItemRepository(conn)
            created = [repo.create(resolved, m) for m in models]
        results = [
            {"diagram_id": str(resolved), **c.model_dump(mode="json")} for c in created
        ]
        emit(ctx, results)
        return

    model = DataItemCreate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        assert resolved is not None
        created_item = DataItemRepository(conn).create(resolved, model)
    emit(ctx, {"diagram_id": str(resolved), **created_item.model_dump(mode="json")})


@data_item_group.command(name="update")
@click.argument("item_id", type=click.INT)
@click.option("--identifier", default=None, help="Data item identifier.")
@click.option("--name", default=None, help="Data item name.")
@click.option("--description", default=None, help="Data item description.")
@click.option(
    "--classification",
    type=click.Choice(_CLASSIFICATION_CHOICES),
    default=None,
    help="Data item classification.",
)
@click.option(
    "--parent-node-id",
    "parent_node_id_raw",
    default=None,
    help="Set parent node id, or 'none'/'' to clear (NULL).",
)
@click.option(
    "--stdin",
    "use_stdin",
    is_flag=True,
    default=False,
    help="Read JSON object from stdin instead of named flags.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Dry-run.")
@click.pass_context
def update_item(
    ctx,
    item_id,
    *,
    identifier,
    name,
    description,
    classification,
    parent_node_id_raw,
    use_stdin,
    dry_run,
) -> None:
    """Update a data item."""
    parsed_parent = _parse_parent_node_id(parent_node_id_raw)
    enforce_stdin_exclusive(
        use_stdin,
        {
            "identifier": identifier,
            "name": name,
            "description": description,
            "classification": classification,
            "parent_node_id": (None if parsed_parent is None else parsed_parent),
        },
    )
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body: dict[str, Any] = {}
        if identifier is not None:
            body["identifier"] = identifier
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if classification is not None:
            body["classification"] = classification
        if parsed_parent is _CLEAR_PARENT:
            body["parent_node_id"] = None
        elif parsed_parent is not None:
            body["parent_node_id"] = parsed_parent
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")

    patch = DataItemUpdate.model_validate(body)
    if dry_run:
        patch_dump = patch.model_dump(mode="json")
        emit(
            ctx,
            {
                "dry_run": True,
                "would_update": {"id": str(item_id), "patch": patch_dump},
            },
        )
        return
    with connect() as conn:
        updated = DataItemRepository(conn).update(item_id, patch)
    if updated is None:
        raise NotFoundError(f"DataItem id={item_id} not found", id=str(item_id))
    emit(ctx, updated.model_dump(mode="json"))


@data_item_group.command(name="delete")
@click.argument("item_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Dry-run.")
@click.pass_context
def delete_item(ctx, item_id, *, yes, dry_run) -> None:
    """Delete a data item."""
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(item_id)})
        return
    with connect() as conn:
        existed = DataItemRepository(conn).delete(item_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(item_id)})
    else:
        emit(
            ctx,
            {"deleted": False, "id": str(item_id), "reason": "not_found"},
        )


@data_item_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@dfd_diagram_id_option
@click.option(
    "--classification",
    type=click.Choice(_CLASSIFICATION_CHOICES),
    default=None,
    help="Filter to data items with this classification.",
)
@click.option(
    "--parent-node-id",
    "parent_node_id_raw",
    default=None,
    help="Filter to data items whose parent_node_id equals this integer.",
)
@json_fields_option
@click.pass_context
def search_items(
    ctx,
    text,
    *,
    limit,
    offset,
    sort_field,
    order,
    diagram_id,
    classification,
    parent_node_id_raw,
    json_fields,
) -> None:
    """Search data items by identifier, name, or description."""
    text_str = " ".join(text).strip() if text else ""
    parent_node_id = _parse_parent_node_filter(parent_node_id_raw)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = DataItemRepository(conn).search(
            resolved,
            text=text_str if text_str else None,
            classification=classification,
            parent_node_id=parent_node_id,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@data_item_group.command(name="list-flows")
@click.argument("item_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_flows_for_item(
    ctx, item_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List flows that carry this data item (on either endpoint)."""
    with connect() as conn:
        if DataItemRepository(conn).get(item_id) is None:
            raise NotFoundError(f"DataItem id={item_id} not found", id=str(item_id))
        rows = DataFlowRepository(conn).flows_for_data_item(item_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@data_item_group.command(name="link-document")
@click.argument("item_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def item_link_document(ctx, item_id: int, doc_id: int) -> None:
    """Link a document to this data item. Idempotent."""
    with connect() as conn:
        repo = EntityDocumentRepository(conn)
        existing_ids = {d.id for d in repo.documents_for_entity(item_id)}
        already = doc_id in existing_ids
        repo.link(item_id, doc_id)
    payload = {
        "linked": not already,
        "item_id": str(item_id),
        "document_id": str(doc_id),
    }
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@data_item_group.command(name="unlink-document")
@click.argument("item_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def item_unlink_document(ctx, item_id: int, doc_id: int) -> None:
    """Remove a document↔data-item link. Idempotent."""
    with connect() as conn:
        existed = EntityDocumentRepository(conn).unlink(item_id, doc_id)
    payload = {
        "unlinked": existed,
        "item_id": str(item_id),
        "document_id": str(doc_id),
    }
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@data_item_group.command(name="list-documents")
@click.argument("item_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def item_list_documents(
    ctx, item_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List documents linked to this data item."""
    with connect() as conn:
        if DataItemRepository(conn).get(item_id) is None:
            raise NotFoundError(f"DataItem id={item_id} not found", id=str(item_id))
        rows = EntityDocumentRepository(conn).documents_for_entity(item_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@data_item_group.command(name="link-observation")
@click.argument("item_id", type=click.INT)
@click.argument("obs_id", type=click.INT)
@click.pass_context
def item_link_observation(ctx, item_id: int, obs_id: int) -> None:
    """Link an observation to this data item. Idempotent."""
    with connect() as conn:
        repo = EntityObservationRepository(conn)
        already = repo.is_linked(item_id, obs_id)
        repo.link(item_id, obs_id)
    payload = {
        "linked": not already,
        "item_id": str(item_id),
        "observation_id": str(obs_id),
    }
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@data_item_group.command(name="unlink-observation")
@click.argument("item_id", type=click.INT)
@click.argument("obs_id", type=click.INT)
@click.pass_context
def item_unlink_observation(ctx, item_id: int, obs_id: int) -> None:
    """Remove an observation↔data-item link. Idempotent."""
    with connect() as conn:
        existed = EntityObservationRepository(conn).unlink(item_id, obs_id)
    payload = {
        "unlinked": existed,
        "item_id": str(item_id),
        "observation_id": str(obs_id),
    }
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@data_item_group.command(name="list-observations")
@click.argument("item_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def item_list_observations(
    ctx, item_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List observations linked to this data item."""
    with connect() as conn:
        if DataItemRepository(conn).get(item_id) is None:
            raise NotFoundError(f"DataItem id={item_id} not found", id=str(item_id))
        rows = EntityObservationRepository(conn).observations_for_entity(item_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    if limit is not None:
        sliced = sorted_rows[offset : offset + limit]
    else:
        sliced = sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
