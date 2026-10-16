"""tm process-component — ProcessComponent CRUDL + search subgroup."""

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
    ComponentType,
    EntityDocumentRepository,
    EntityObservationRepository,
    ProcessComponentCreate,
    ProcessComponentRepository,
    ProcessComponentUpdate,
    connect,
)

_COMPONENT_TYPE_CHOICES = list(get_args(ComponentType))


def _parse_parent_process_filter(value: str | None) -> int | None:
    """Parse ``--parent-process-id`` filter for list/search (always integer-or-none)."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as e:
        msg = f"--parent-process-id filter must be integer: {value!r}"
        raise click.UsageError(msg) from e


@click.group(name="process-component")
def process_component_group() -> None:
    """Manage process components."""


@process_component_group.command(name="list")
@list_options
@dfd_diagram_id_option
@click.option(
    "--parent-process-id",
    "parent_process_id_raw",
    default=None,
    help="Filter to process components whose parent_process_id equals this integer.",
)
@click.option(
    "--component-type",
    type=click.Choice(_COMPONENT_TYPE_CHOICES),
    default=None,
    help="Filter to process components with this component type.",
)
@json_fields_option
@click.pass_context
def list_components(
    ctx,
    *,
    limit,
    offset,
    sort_field,
    order,
    diagram_id,
    parent_process_id_raw,
    component_type,
    json_fields,
) -> None:
    """List process components in a diagram (defaults to the 'default' diagram)."""
    parent_process_id = _parse_parent_process_filter(parent_process_id_raw)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = ProcessComponentRepository(conn).search(
            resolved,
            text=None,
            parent_process_id=parent_process_id,
            component_type=component_type,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@process_component_group.command(name="get")
@click.argument("component_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_component(ctx, component_id, *, json_fields) -> None:
    """Get a process component by id."""
    with connect() as conn:
        row = ProcessComponentRepository(conn).get(component_id)
    if row is None:
        raise NotFoundError(
            f"ProcessComponent id={component_id} not found", id=str(component_id)
        )
    fields = parse_json_fields(json_fields)
    payload = project_fields(row.model_dump(mode="json"), fields)
    emit(ctx, payload)


@process_component_group.command(name="create")
@dfd_diagram_id_option
@click.option("--name", default=None, help="Process component name.")
@click.option("--description", default=None, help="Process component description.")
@click.option(
    "--component-type",
    type=click.Choice(_COMPONENT_TYPE_CHOICES),
    default=None,
    help="Process component type.",
)
@click.option(
    "--parent-process-id",
    "parent_process_id",
    type=click.INT,
    default=None,
    help="Parent process node id (required).",
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
    help="No-op for ProcessComponent; kept for consistency.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Dry-run.")
@click.pass_context
def create_component(
    ctx,
    *,
    diagram_id,
    name,
    description,
    component_type,
    parent_process_id,
    use_stdin,
    if_not_exists,
    dry_run,
) -> None:
    """Create a process component. Use named flags or --stdin."""
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "description": description,
            "component_type": component_type,
            "parent_process_id": parent_process_id,
        },
    )
    if use_stdin:
        body = read_json_stdin()
    else:
        if (
            name is None
            or description is None
            or component_type is None
            or parent_process_id is None
        ):
            raise click.UsageError(
                "--name, --description, --component-type, --parent-process-id required "
                "(or use --stdin)"
            )
        body = {
            "name": name,
            "description": description,
            "component_type": component_type,
            "parent_process_id": parent_process_id,
        }

    if isinstance(body, list):
        models: list[ProcessComponentCreate] = []
        for index, item in enumerate(body):
            try:
                models.append(ProcessComponentCreate.model_validate(item))
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
            repo = ProcessComponentRepository(conn)
            created = [repo.create(resolved, m) for m in models]
        results = [
            {"diagram_id": str(resolved), **c.model_dump(mode="json")} for c in created
        ]
        emit(ctx, results)
        return

    model = ProcessComponentCreate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        assert resolved is not None
        created_component = ProcessComponentRepository(conn).create(resolved, model)
    result = {"diagram_id": str(resolved), **created_component.model_dump(mode="json")}
    emit(ctx, result)


@process_component_group.command(name="update")
@click.argument("component_id", type=click.INT)
@click.option("--name", default=None, help="Process component name.")
@click.option("--description", default=None, help="Process component description.")
@click.option(
    "--component-type",
    type=click.Choice(_COMPONENT_TYPE_CHOICES),
    default=None,
    help="Process component type.",
)
@click.option(
    "--parent-process-id",
    "parent_process_id",
    type=click.INT,
    default=None,
    help="Set parent process node id (integer; cannot be cleared).",
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
def update_component(
    ctx,
    component_id,
    *,
    name,
    description,
    component_type,
    parent_process_id,
    use_stdin,
    dry_run,
) -> None:
    """Update a process component."""
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "description": description,
            "component_type": component_type,
            "parent_process_id": parent_process_id,
        },
    )
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if component_type is not None:
            body["component_type"] = component_type
        if parent_process_id is not None:
            body["parent_process_id"] = parent_process_id
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")

    patch = ProcessComponentUpdate.model_validate(body)
    if dry_run:
        patch_dump = patch.model_dump(mode="json")
        emit(
            ctx,
            {
                "dry_run": True,
                "would_update": {"id": str(component_id), "patch": patch_dump},
            },
        )
        return
    with connect() as conn:
        updated = ProcessComponentRepository(conn).update(component_id, patch)
    if updated is None:
        raise NotFoundError(
            f"ProcessComponent id={component_id} not found", id=str(component_id)
        )
    emit(ctx, updated.model_dump(mode="json"))


@process_component_group.command(name="delete")
@click.argument("component_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Dry-run.")
@click.pass_context
def delete_component(ctx, component_id, *, yes, dry_run) -> None:
    """Delete a process component."""
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(component_id)})
        return
    with connect() as conn:
        existed = ProcessComponentRepository(conn).delete(component_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(component_id)})
    else:
        emit(
            ctx,
            {"deleted": False, "id": str(component_id), "reason": "not_found"},
        )


@process_component_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@dfd_diagram_id_option
@click.option(
    "--parent-process-id",
    "parent_process_id_raw",
    default=None,
    help="Filter to process components whose parent_process_id equals this integer.",
)
@click.option(
    "--component-type",
    type=click.Choice(_COMPONENT_TYPE_CHOICES),
    default=None,
    help="Filter to process components with this component type.",
)
@json_fields_option
@click.pass_context
def search_components(
    ctx,
    text,
    *,
    limit,
    offset,
    sort_field,
    order,
    diagram_id,
    parent_process_id_raw,
    component_type,
    json_fields,
) -> None:
    """Search process components by name or description."""
    text_str = " ".join(text).strip() if text else ""
    parent_process_id = _parse_parent_process_filter(parent_process_id_raw)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = ProcessComponentRepository(conn).search(
            resolved,
            text=text_str if text_str else None,
            parent_process_id=parent_process_id,
            component_type=component_type,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@process_component_group.command(name="link-document")
@click.argument("component_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def component_link_document(ctx, component_id: int, doc_id: int) -> None:
    """Link a document to this process component. Idempotent."""
    with connect() as conn:
        repo = EntityDocumentRepository(conn)
        existing_ids = {d.id for d in repo.documents_for_entity(component_id)}
        already = doc_id in existing_ids
        repo.link(component_id, doc_id)
    payload = {
        "linked": not already,
        "component_id": str(component_id),
        "document_id": str(doc_id),
    }
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@process_component_group.command(name="unlink-document")
@click.argument("component_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def component_unlink_document(ctx, component_id: int, doc_id: int) -> None:
    """Remove a document↔process-component link. Idempotent."""
    with connect() as conn:
        existed = EntityDocumentRepository(conn).unlink(component_id, doc_id)
    payload = {
        "unlinked": existed,
        "component_id": str(component_id),
        "document_id": str(doc_id),
    }
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@process_component_group.command(name="list-documents")
@click.argument("component_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def component_list_documents(
    ctx, component_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List documents linked to this process component."""
    with connect() as conn:
        if ProcessComponentRepository(conn).get(component_id) is None:
            raise NotFoundError(
                f"ProcessComponent id={component_id} not found", id=str(component_id)
            )
        rows = EntityDocumentRepository(conn).documents_for_entity(component_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@process_component_group.command(name="link-observation")
@click.argument("component_id", type=click.INT)
@click.argument("obs_id", type=click.INT)
@click.pass_context
def component_link_observation(ctx, component_id: int, obs_id: int) -> None:
    """Link an observation to this process component. Idempotent."""
    with connect() as conn:
        repo = EntityObservationRepository(conn)
        already = repo.is_linked(component_id, obs_id)
        repo.link(component_id, obs_id)
    payload = {
        "linked": not already,
        "component_id": str(component_id),
        "observation_id": str(obs_id),
    }
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@process_component_group.command(name="unlink-observation")
@click.argument("component_id", type=click.INT)
@click.argument("obs_id", type=click.INT)
@click.pass_context
def component_unlink_observation(ctx, component_id: int, obs_id: int) -> None:
    """Remove an observation↔process-component link. Idempotent."""
    with connect() as conn:
        existed = EntityObservationRepository(conn).unlink(component_id, obs_id)
    payload = {
        "unlinked": existed,
        "component_id": str(component_id),
        "observation_id": str(obs_id),
    }
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@process_component_group.command(name="list-observations")
@click.argument("component_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def component_list_observations(
    ctx, component_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List observations linked to this process component."""
    with connect() as conn:
        if ProcessComponentRepository(conn).get(component_id) is None:
            raise NotFoundError(
                f"ProcessComponent id={component_id} not found", id=str(component_id)
            )
        rows = EntityObservationRepository(conn).observations_for_entity(component_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    if limit is not None:
        sliced = sorted_rows[offset : offset + limit]
    else:
        sliced = sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@process_component_group.command(name="set-parent")
@click.argument("component_id", type=click.INT)
@click.argument("process_node_id", type=click.INT)
@click.pass_context
def set_parent(ctx, component_id, process_node_id):
    """Reassign a process component to a different process node."""
    with connect() as conn:
        repo = ProcessComponentRepository(conn)
        patch = ProcessComponentUpdate(parent_process_id=process_node_id)
        updated = repo.update(component_id, patch)
    if updated is None:
        raise NotFoundError(
            f"ProcessComponent id={component_id} not found", id=str(component_id)
        )
    emit(ctx, updated.model_dump(mode="json"))
