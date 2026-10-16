"""tm diagram — Diagram CRUDL + search subgroup."""

# pattern: Imperative Shell

from __future__ import annotations

import os

import click
from pydantic import ValidationError

from tm_cli.cli._dfd_editor_client import DfdEditorError, post_diagram, put_diagram
from tm_cli.cli._errors import (
    NotFoundError,
    UserError,
    map_exception,
)
from tm_cli.cli._errors import (
    SystemError as CliSystemError,  # noqa: A001 – shadows builtin intentionally
)
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
    ContainerRepository,
    DataFlowRepository,
    DataItemRepository,
    DiagramCreate,
    DiagramRepository,
    DiagramUpdate,
    NodeRepository,
    ValidationFindingRepository,
    connect,
)
from tm_cli.db.dfd_export import to_dfd_editor_dict


def _load_container_parents(conn, diagram_id: int) -> dict[int, int]:
    """Return ``{child_id: parent_id}`` for every membership in ``diagram_id``.

    ``container_membership`` is keyed on ``child_id`` so the dict is naturally
    well-formed (one parent per child). Joining through ``entity`` restricts to
    the requested diagram.
    """
    rows = conn.execute(
        "SELECT cm.child_id AS child_id, cm.parent_id AS parent_id "
        "FROM container_membership cm "
        "JOIN entity e ON e.id = cm.child_id "
        "WHERE e.diagram_id = ?",
        (diagram_id,),
    ).fetchall()
    return {row["child_id"]: row["parent_id"] for row in rows}


def _map_dfd_editor_error(exc: DfdEditorError, server: str):
    """Translate ``DfdEditorError`` into the CLI's structured ``SystemError``.

    ``CliSystemError`` is ``tm_cli.cli._errors.SystemError`` (aliased to dodge
    the builtin shadow). Exit code 4; ``status`` and ``server`` flow into the
    error envelope via ``TmError(**extra)`` → ``to_payload()``.
    """
    return CliSystemError(
        str(exc),
        status=exc.status,
        server=server,
    )


@click.group(name="diagram")
def diagram_group() -> None:
    """Manage DFD diagrams."""


@diagram_group.command(name="list")
@list_options
@json_fields_option
@click.pass_context
def list_diagrams(ctx, *, limit, offset, sort_field, order, json_fields) -> None:
    """List diagrams."""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = DiagramRepository(conn).list(limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@diagram_group.command(name="get")
@click.argument("diagram_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_diagram(ctx, diagram_id, *, json_fields) -> None:
    """Get a diagram by id."""
    with connect() as conn:
        row = DiagramRepository(conn).get(diagram_id)
    if row is None:
        raise NotFoundError(f"Diagram id={diagram_id} not found", id=str(diagram_id))
    fields = parse_json_fields(json_fields)
    payload = project_fields(row.model_dump(mode="json"), fields)
    emit(ctx, payload)


@diagram_group.command(name="create")
@click.option("--name", default=None, help="Diagram name.")
@click.option("--description", default=None, help="Diagram description.")
@click.option("--author", default=None, help="Diagram author.")
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
    help="No-op for Diagram (no natural key); kept for consistency.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Dry-run mode.")
@click.pass_context
def create_diagram(
    ctx, *, name, description, author, use_stdin, if_not_exists, dry_run
) -> None:
    """Create a diagram. Use named flags or --stdin."""
    enforce_stdin_exclusive(
        use_stdin, {"name": name, "description": description, "author": author}
    )
    if use_stdin:
        body = read_json_stdin()
    else:
        body = {
            k: v
            for k, v in {
                "name": name,
                "description": description,
                "author": author,
            }.items()
            if v is not None
        }
        # All fields optional, so empty body is permitted.

    if isinstance(body, list):
        models = []
        for index, item in enumerate(body):
            try:
                models.append(DiagramCreate.model_validate(item))
            except ValidationError as e:
                raise map_exception(
                    e, input_payload={"index": index, "item": item}
                ) from e
        if dry_run:
            would_create = [m.model_dump(mode="json") for m in models]
            emit(ctx, {"dry_run": True, "would_create": would_create})
            return
        with connect() as conn:
            repo = DiagramRepository(conn)
            created = [repo.create(m) for m in models]
        emit(ctx, [c.model_dump(mode="json") for c in created])
        return

    model = DiagramCreate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        created_diagram = DiagramRepository(conn).create(model)
    emit(ctx, created_diagram.model_dump(mode="json"))


@diagram_group.command(name="update")
@click.argument("diagram_id", type=click.INT)
@click.option("--name", default=None, help="Diagram name.")
@click.option("--description", default=None, help="Diagram description.")
@click.option("--author", default=None, help="Diagram author.")
@click.option(
    "--stdin",
    "use_stdin",
    is_flag=True,
    default=False,
    help="Read JSON object from stdin instead of named flags.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Dry-run mode.")
@click.pass_context
def update_diagram(
    ctx, diagram_id, *, name, description, author, use_stdin, dry_run
) -> None:
    """Update a diagram."""
    enforce_stdin_exclusive(
        use_stdin, {"name": name, "description": description, "author": author}
    )
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body = {
            k: v
            for k, v in {
                "name": name,
                "description": description,
                "author": author,
            }.items()
            if v is not None
        }
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = DiagramUpdate.model_validate(body)
    if dry_run:
        dump = patch.model_dump(mode="json", exclude_none=True)
        emit(
            ctx,
            {
                "dry_run": True,
                "would_update": {"id": str(diagram_id), "patch": dump},
            },
        )
        return
    with connect() as conn:
        updated = DiagramRepository(conn).update(diagram_id, patch)
    if updated is None:
        raise NotFoundError(f"Diagram id={diagram_id} not found", id=str(diagram_id))
    emit(ctx, updated.model_dump(mode="json"))


@diagram_group.command(name="delete")
@click.argument("diagram_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Dry-run mode.")
@click.pass_context
def delete_diagram(ctx, diagram_id, *, yes, dry_run) -> None:
    """Delete a diagram."""
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(diagram_id)})
        return
    with connect() as conn:
        existed = DiagramRepository(conn).delete(diagram_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(diagram_id)})
    else:
        emit(
            ctx,
            {"deleted": False, "id": str(diagram_id), "reason": "not_found"},
        )


@diagram_group.command(name="search")
@click.argument("text", nargs=1)
@list_options
@json_fields_option
@click.pass_context
def search_diagrams(
    ctx, text, *, limit, offset, sort_field, order, json_fields
) -> None:
    """Search diagrams by name, description, or author."""
    if not text.strip():
        raise click.UsageError("search requires a non-empty TEXT argument")
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = DiagramRepository(conn).search(text=text, limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@diagram_group.command(name="push")
@dfd_diagram_id_option
@click.option(
    "--server",
    "server",
    default=None,
    help="dfd_editor server URL (overrides $DFD_EDITOR_URL).",
)
@click.pass_context
def push_diagram(ctx, *, diagram_id, server) -> None:
    """Push the diagram to a running dfd_editor server.

    Creates remotely on first push (storing the server-minted UUID locally),
    updates remotely on subsequent pushes via that UUID. Element UUIDs are
    deterministic — re-pushing preserves dfd_editor-side layout.
    """
    resolved_server = server or os.environ.get("DFD_EDITOR_URL")
    if not resolved_server:
        raise UserError(
            "No dfd_editor server URL provided",
            hint="Pass --server URL or set DFD_EDITOR_URL in your environment.",
        )

    with connect() as conn:
        target_id = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        if target_id is None:
            # ``create_if_missing=True`` only returns None on a logic bug in
            # the resolver.
            raise CliSystemError("Failed to resolve a target diagram")
        diagram_repo = DiagramRepository(conn)
        diagram = diagram_repo.get(target_id)
        if diagram is None:
            raise CliSystemError(f"Diagram id={target_id} disappeared mid-flight")

        node_repo = NodeRepository(conn)
        container_repo = ContainerRepository(conn)
        flow_repo = DataFlowRepository(conn)
        item_repo = DataItemRepository(conn)

        # Load all entities for this diagram. ``limit=None`` returns everything;
        # the CLI's standard pagination is for agent reads, not internal exports.
        nodes = node_repo.list(target_id, limit=None)
        containers = container_repo.list(target_id, limit=None)
        flows = flow_repo.list(target_id, limit=None)
        items = item_repo.list(target_id, limit=None)

        # Container parent map: child_id -> parent_id, for every child that has one.
        container_parents = _load_container_parents(conn, target_id)

        # Payload refs (per flow, per endpoint) — without these, every flow
        # ships to dfd_editor with empty src_data_item_refs and the renderer
        # has no direction information to draw arrows from.
        payloads_by_flow = flow_repo.payloads_for_diagram(target_id)

        # Load validation findings for this diagram.
        finding_repo = ValidationFindingRepository(conn)
        findings = finding_repo.for_diagram(target_id)

        # Build entity_id → kind mapping for GUID resolution in export.
        entity_kinds: dict[int, str] = {}
        for n in nodes:
            entity_kinds[n.id] = "node"
        for c in containers:
            entity_kinds[c.id] = "container"
        for f in flows:
            entity_kinds[f.id] = "data_flow"
        for i in items:
            entity_kinds[i.id] = "data_item"

        body = to_dfd_editor_dict(
            diagram,
            nodes,
            containers,
            container_parents,
            flows,
            items,
            payloads_by_flow,
            findings=findings,
            entity_kinds=entity_kinds,
        )

        if diagram.dfd_editor_diagram_id is None:
            try:
                remote_id = post_diagram(resolved_server, body)
            except DfdEditorError as e:
                raise _map_dfd_editor_error(e, resolved_server) from e
            diagram_repo.set_remote_id(target_id, remote_id)
            operation = "created"
        else:
            remote_id = diagram.dfd_editor_diagram_id
            try:
                put_diagram(resolved_server, remote_id, body)
            except DfdEditorError as e:
                raise _map_dfd_editor_error(e, resolved_server) from e
            operation = "updated"

    # Deliberately outside the ``with`` block: commit must precede emit so the
    # server-minted UUID is durable before any non-essential work runs.
    error_count = sum(1 for vf in findings if vf.severity == "error")
    warning_count = sum(1 for vf in findings if vf.severity == "warning")

    emit(
        ctx,
        {
            "diagram_id": target_id,
            "remote_id": remote_id,
            "operation": operation,
            "server": resolved_server,
            "error_count": error_count,
            "warning_count": warning_count,
        },
    )
