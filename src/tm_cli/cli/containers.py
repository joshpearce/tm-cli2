"""tm container — Container (polymorphic) CRUDL + search + membership subgroup."""

from __future__ import annotations

from typing import Any, get_args

import click

from tm_cli.cli._errors import NotFoundError, UserError
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
    ContainerType,
    ContainerVariantCreate,
    ContainerVariantUpdate,
    EntityDocumentRepository,
    EntityObservationRepository,
    PrivilegeLevel,
    TrustBoundaryCreate,
    TrustBoundaryUpdate,
    connect,
)

_CONTAINER_TYPE_CHOICES = list(get_args(ContainerType))
_PRIVILEGE_LEVEL_CHOICES = list(get_args(PrivilegeLevel))

# Mapping from database type literal to Click subcommand name
_TYPE_TO_SUBCOMMAND = {
    "trust_boundary": "trust-boundary",
    "container": "container",
}


@click.group(name="container")
def container_group() -> None:
    """Manage DFD containers (trust_boundary, container)."""


@container_group.command(name="list")
@list_options
@dfd_diagram_id_option
@click.option(
    "--type",
    "container_type",
    type=click.Choice(_CONTAINER_TYPE_CHOICES),
    default=None,
    help="Filter to a single container variant.",
)
@json_fields_option
@click.pass_context
def list_containers(
    ctx,
    *,
    limit,
    offset,
    sort_field,
    order,
    diagram_id,
    container_type,
    json_fields,
) -> None:
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = ContainerRepository(conn).list(
            resolved, type=container_type, limit=limit, offset=offset
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@container_group.command(name="get")
@click.argument("container_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_container(ctx, container_id, *, json_fields) -> None:
    with connect() as conn:
        row = ContainerRepository(conn).get(container_id)
    if row is None:
        raise NotFoundError(
            f"Container id={container_id} not found", id=str(container_id)
        )
    payload = project_fields(
        row.model_dump(mode="json"), parse_json_fields(json_fields)
    )
    emit(ctx, payload)


@container_group.command(name="delete")
@click.argument("container_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_container(ctx, container_id, *, yes, dry_run) -> None:
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(container_id)})
        return
    with connect() as conn:
        existed = ContainerRepository(conn).delete(container_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(container_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(container_id), "reason": "not_found"})


@container_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@dfd_diagram_id_option
@click.option(
    "--type",
    "container_type",
    type=click.Choice(_CONTAINER_TYPE_CHOICES),
    default=None,
)
@json_fields_option
@click.pass_context
def search_containers(
    ctx,
    text,
    *,
    limit,
    offset,
    sort_field,
    order,
    diagram_id,
    container_type,
    json_fields,
) -> None:
    text_str = " ".join(text).strip() if text else ""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = ContainerRepository(conn).search(
            resolved,
            text=text_str if text_str else None,
            type=container_type,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


# ============================================================================
# CREATE subcommand group with variant subcommands
# ============================================================================


@container_group.group(name="create")
def create_container_group() -> None:
    """Create a container of a specific variant."""


def _create_container(ctx, diagram_id, model, dry_run) -> None:
    """Shared write path for the variant subcommands."""
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        assert resolved is not None
        created = ContainerRepository(conn).create(resolved, model)
    emit(ctx, {"diagram_id": str(resolved), **created.model_dump(mode="json")})


def _create_container_batch(ctx, diagram_id, models, dry_run) -> None:
    """Shared batch write path for --stdin with a JSON array."""
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
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        assert resolved is not None
        repo = ContainerRepository(conn)
        created = [repo.create(resolved, m) for m in models]
    results = [
        {"diagram_id": str(resolved), **c.model_dump(mode="json")} for c in created
    ]
    emit(ctx, results)


@create_container_group.command(name="trust-boundary")
@dfd_diagram_id_option
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option(
    "--privilege-level",
    "privilege_level",
    type=click.Choice(_PRIVILEGE_LEVEL_CHOICES),
    default=None,
)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option(
    "--if-not-exists",
    "if_not_exists",
    is_flag=True,
    default=False,
    help="No-op for Container (no natural key); kept for command-shape consistency.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_trust_boundary(
    ctx,
    *,
    diagram_id,
    name,
    description,
    privilege_level,
    use_stdin,
    if_not_exists,
    dry_run,
) -> None:
    """Create a trust boundary."""
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "description": description,
            "privilege_level": privilege_level,
        },
    )
    if use_stdin:
        body = read_json_stdin()
        if isinstance(body, dict):
            body.setdefault("type", "trust_boundary")
        elif isinstance(body, list):
            for item in body:
                if isinstance(item, dict):
                    item.setdefault("type", "trust_boundary")
    else:
        if name is None or description is None or privilege_level is None:
            msg = (
                "--name, --description, and --privilege-level are required "
                "(or use --stdin)"
            )
            raise click.UsageError(msg)
        body = {
            "type": "trust_boundary",
            "name": name,
            "description": description,
            "privilege_level": privilege_level,
        }

    if isinstance(body, list):
        models = [TrustBoundaryCreate.model_validate(item) for item in body]
        _create_container_batch(ctx, diagram_id, models, dry_run)
        return

    model = TrustBoundaryCreate.model_validate(body)
    _create_container(ctx, diagram_id, model, dry_run)


@create_container_group.command(name="container")
@dfd_diagram_id_option
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option(
    "--if-not-exists",
    "if_not_exists",
    is_flag=True,
    default=False,
    help="No-op for Container (no natural key); kept for command-shape consistency.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_container_variant(
    ctx,
    *,
    diagram_id,
    name,
    description,
    use_stdin,
    if_not_exists,
    dry_run,
) -> None:
    """Create a generic container."""
    enforce_stdin_exclusive(use_stdin, {"name": name, "description": description})
    if use_stdin:
        body = read_json_stdin()
        if isinstance(body, dict):
            body.setdefault("type", "container")
        elif isinstance(body, list):
            for item in body:
                if isinstance(item, dict):
                    item.setdefault("type", "container")
    else:
        if name is None or description is None:
            raise click.UsageError(
                "--name and --description are required (or use --stdin)"
            )
        body = {"type": "container", "name": name, "description": description}

    if isinstance(body, list):
        models = [ContainerVariantCreate.model_validate(item) for item in body]
        _create_container_batch(ctx, diagram_id, models, dry_run)
        return

    model = ContainerVariantCreate.model_validate(body)
    _create_container(ctx, diagram_id, model, dry_run)


# ============================================================================
# UPDATE subcommand group with variant subcommands
# ============================================================================


@container_group.group(name="update")
def update_container_group() -> None:
    """Update a container of a specific variant.

    The variant must match the row's existing type."""


def _ensure_container_variant(container_id: int, expected_type: str) -> None:
    """Pre-flight: confirm the row exists and matches the expected variant."""
    with connect() as conn:
        row = ContainerRepository(conn).get(container_id)
    if row is None:
        raise NotFoundError(
            f"Container id={container_id} not found", id=str(container_id)
        )
    if row.type != expected_type:
        msg = (
            f"Type mismatch: row id={container_id} is {row.type}, but the "
            f"{expected_type} variant subcommand was used."
        )
        actual_subcommand = _TYPE_TO_SUBCOMMAND[row.type]
        hint = f"Use 'tm container update {actual_subcommand} {container_id}' instead."
        raise UserError(msg, hint=hint)


def _apply_container_update(ctx, container_id, patch, dry_run) -> None:
    if dry_run:
        emit(
            ctx,
            {
                "dry_run": True,
                "would_update": {
                    "id": str(container_id),
                    "patch": patch.model_dump(mode="json", exclude_none=True),
                },
            },
        )
        return
    with connect() as conn:
        updated = ContainerRepository(conn).update(container_id, patch)
    if updated is None:
        # Should not happen because _ensure_container_variant pre-checked,
        # but be defensive.
        raise NotFoundError(
            f"Container id={container_id} not found", id=str(container_id)
        )
    emit(ctx, updated.model_dump(mode="json"))


@update_container_group.command(name="trust-boundary")
@click.argument("container_id", type=click.INT)
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option(
    "--privilege-level",
    "privilege_level",
    type=click.Choice(_PRIVILEGE_LEVEL_CHOICES),
    default=None,
)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_trust_boundary(
    ctx,
    container_id,
    *,
    name,
    description,
    privilege_level,
    use_stdin,
    dry_run,
) -> None:
    """Update a trust boundary."""
    _ensure_container_variant(container_id, "trust_boundary")
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "description": description,
            "privilege_level": privilege_level,
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
        if privilege_level is not None:
            body["privilege_level"] = privilege_level
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = TrustBoundaryUpdate.model_validate(body)
    _apply_container_update(ctx, container_id, patch, dry_run)


@update_container_group.command(name="container")
@click.argument("container_id", type=click.INT)
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_container_variant(
    ctx,
    container_id,
    *,
    name,
    description,
    use_stdin,
    dry_run,
) -> None:
    """Update a generic container."""
    _ensure_container_variant(container_id, "container")
    enforce_stdin_exclusive(use_stdin, {"name": name, "description": description})
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
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = ContainerVariantUpdate.model_validate(body)
    _apply_container_update(ctx, container_id, patch, dry_run)


# ============================================================================
# MEMBERSHIP commands: set-parent / clear-parent / parent-of / list-children
# ============================================================================


@container_group.command(name="set-parent")
@click.argument("container_id", type=click.INT)
@click.argument("parent_id", type=click.INT)
@click.pass_context
def container_set_parent(ctx, container_id: int, parent_id: int) -> None:
    """Place ``container_id`` inside the container ``parent_id``."""
    with connect() as conn:
        try:
            ContainerRepository(conn).set_parent(container_id, parent_id)
        except ValueError as e:
            raise UserError(str(e), hint=str(e))
    emit(ctx, {"child_id": str(container_id), "parent_id": str(parent_id)})


@container_group.command(name="clear-parent")
@click.argument("container_id", type=click.INT)
@click.pass_context
def container_clear_parent(ctx, container_id: int) -> None:
    """Clear the parent of ``container_id``."""
    with connect() as conn:
        existed = ContainerRepository(conn).clear_parent(container_id)
    emit(ctx, {"cleared": existed, "id": str(container_id)})


@container_group.command(name="parent-of")
@click.argument("container_id", type=click.INT)
@json_fields_option
@click.pass_context
def container_parent_of(ctx, container_id: int, *, json_fields) -> None:
    """Get the parent container of ``container_id``."""
    with connect() as conn:
        parent = ContainerRepository(conn).parent_of(container_id)
    if parent is None:
        emit(ctx, {"id": str(container_id), "parent": None})
        return
    payload = project_fields(
        parent.model_dump(mode="json"), parse_json_fields(json_fields)
    )
    emit(ctx, {"id": str(container_id), "parent": payload})


@container_group.command(name="list-children")
@click.argument("container_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_children(
    ctx, container_id: int, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List Nodes and Containers under ``container_id`` (heterogeneous output)."""
    with connect() as conn:
        # Pre-check that the container exists; gives a friendlier error than
        # an empty list.
        if ContainerRepository(conn).get(container_id) is None:
            raise NotFoundError(
                f"Container id={container_id} not found", id=str(container_id)
            )
        rows = ContainerRepository(conn).children_of(container_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@container_group.command(name="link-document")
@click.argument("container_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def container_link_document(ctx, container_id: int, doc_id: int) -> None:
    """Link a document to this container. Idempotent."""
    with connect() as conn:
        repo = EntityDocumentRepository(conn)
        existing_ids = {d.id for d in repo.documents_for_entity(container_id)}
        already = doc_id in existing_ids
        repo.link(container_id, doc_id)
    payload = {
        "linked": not already,
        "container_id": str(container_id),
        "document_id": str(doc_id),
    }
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@container_group.command(name="unlink-document")
@click.argument("container_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def container_unlink_document(ctx, container_id: int, doc_id: int) -> None:
    """Remove a document↔container link. Idempotent."""
    with connect() as conn:
        existed = EntityDocumentRepository(conn).unlink(container_id, doc_id)
    payload = {
        "unlinked": existed,
        "container_id": str(container_id),
        "document_id": str(doc_id),
    }
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@container_group.command(name="list-documents")
@click.argument("container_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def container_list_documents(
    ctx, container_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List documents linked to this container."""
    with connect() as conn:
        if ContainerRepository(conn).get(container_id) is None:
            raise NotFoundError(
                f"Container id={container_id} not found",
                id=str(container_id),
            )
        rows = EntityDocumentRepository(conn).documents_for_entity(container_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@container_group.command(name="link-observation")
@click.argument("container_id", type=click.INT)
@click.argument("obs_id", type=click.INT)
@click.pass_context
def container_link_observation(ctx, container_id: int, obs_id: int) -> None:
    """Link an observation to this container. Idempotent."""
    with connect() as conn:
        repo = EntityObservationRepository(conn)
        already = repo.is_linked(container_id, obs_id)
        repo.link(container_id, obs_id)
    payload = {
        "linked": not already,
        "container_id": str(container_id),
        "observation_id": str(obs_id),
    }
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@container_group.command(name="unlink-observation")
@click.argument("container_id", type=click.INT)
@click.argument("obs_id", type=click.INT)
@click.pass_context
def container_unlink_observation(ctx, container_id: int, obs_id: int) -> None:
    """Remove an observation↔container link. Idempotent."""
    with connect() as conn:
        existed = EntityObservationRepository(conn).unlink(container_id, obs_id)
    payload = {
        "unlinked": existed,
        "container_id": str(container_id),
        "observation_id": str(obs_id),
    }
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@container_group.command(name="list-observations")
@click.argument("container_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def container_list_observations(
    ctx, container_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List observations linked to this container."""
    with connect() as conn:
        if ContainerRepository(conn).get(container_id) is None:
            raise NotFoundError(
                f"Container id={container_id} not found",
                id=str(container_id),
            )
        rows = EntityObservationRepository(conn).observations_for_entity(container_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    if limit is not None:
        sliced = sorted_rows[offset : offset + limit]
    else:
        sliced = sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
