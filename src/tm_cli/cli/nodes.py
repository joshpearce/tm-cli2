"""tm node — Node (polymorphic) CRUDL + search + container membership subgroup."""

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
    DataStoreNodeCreate,
    DataStoreNodeUpdate,
    EntityDocumentRepository,
    EntityObservationRepository,
    ExternalEntityNodeCreate,
    ExternalEntityNodeUpdate,
    ExternalEntityType,
    NodeRepository,
    NodeType,
    ProcessNodeCreate,
    ProcessNodeUpdate,
    StorageType,
    TrustLevel,
    connect,
)

_NODE_TYPE_CHOICES = list(get_args(NodeType))
_TRUST_LEVEL_CHOICES = list(get_args(TrustLevel))
_EXTERNAL_ENTITY_TYPE_CHOICES = list(get_args(ExternalEntityType))
_STORAGE_TYPE_CHOICES = list(get_args(StorageType))

# Mapping from database type literal to Click subcommand name
_TYPE_TO_SUBCOMMAND = {
    "process": "process",
    "external_entity": "external-entity",
    "data_store": "data-store",
}


@click.group(name="node")
def node_group() -> None:
    """Manage DFD nodes (process, external_entity, data_store)."""


@node_group.command(name="list")
@list_options
@dfd_diagram_id_option
@click.option(
    "--type",
    "node_type",
    type=click.Choice(_NODE_TYPE_CHOICES),
    default=None,
    help="Filter to a single node variant.",
)
@json_fields_option
@click.pass_context
def list_nodes(
    ctx,
    *,
    limit,
    offset,
    sort_field,
    order,
    diagram_id,
    node_type,
    json_fields,
) -> None:
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = NodeRepository(conn).list(
            resolved, type=node_type, limit=limit, offset=offset
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@node_group.command(name="get")
@click.argument("node_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_node(ctx, node_id, *, json_fields) -> None:
    with connect() as conn:
        row = NodeRepository(conn).get(node_id)
    if row is None:
        raise NotFoundError(f"Node id={node_id} not found", id=str(node_id))
    payload = project_fields(
        row.model_dump(mode="json"), parse_json_fields(json_fields)
    )
    emit(ctx, payload)


@node_group.command(name="delete")
@click.argument("node_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_node(ctx, node_id, *, yes, dry_run) -> None:
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(node_id)})
        return
    with connect() as conn:
        existed = NodeRepository(conn).delete(node_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(node_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(node_id), "reason": "not_found"})


@node_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@dfd_diagram_id_option
@click.option(
    "--type",
    "node_type",
    type=click.Choice(_NODE_TYPE_CHOICES),
    default=None,
)
@json_fields_option
@click.pass_context
def search_nodes(
    ctx,
    text,
    *,
    limit,
    offset,
    sort_field,
    order,
    diagram_id,
    node_type,
    json_fields,
) -> None:
    text_str = " ".join(text).strip() if text else ""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = NodeRepository(conn).search(
            resolved,
            text=text_str if text_str else None,
            type=node_type,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


# ============================================================================
# CREATE subcommand group with variant subcommands
# ============================================================================


@node_group.group(name="create")
def create_node_group() -> None:
    """Create a node of a specific variant."""


def _create_variant(ctx, diagram_id, model, dry_run) -> None:
    """Shared write path for the three variant subcommands."""
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        assert resolved is not None
        created = NodeRepository(conn).create(resolved, model)
    emit(ctx, {"diagram_id": str(resolved), **created.model_dump(mode="json")})


def _create_variant_batch(ctx, diagram_id, models, dry_run) -> None:
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
        repo = NodeRepository(conn)
        created = [repo.create(resolved, m) for m in models]
    results = [
        {"diagram_id": str(resolved), **c.model_dump(mode="json")} for c in created
    ]
    emit(ctx, results)


@create_node_group.command(name="process")
@dfd_diagram_id_option
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option(
    "--trust-level",
    "trust_level",
    type=click.Choice(_TRUST_LEVEL_CHOICES),
    default=None,
)
@click.option(
    "--assumption",
    "assumptions",
    multiple=True,
    default=(),
    help="Repeatable. Each --assumption adds one item to the assumptions list.",
)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option(
    "--if-not-exists",
    "if_not_exists",
    is_flag=True,
    default=False,
    help="No-op for Node (no natural key); kept for command-shape consistency.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_process(
    ctx,
    *,
    diagram_id,
    name,
    description,
    trust_level,
    assumptions,
    use_stdin,
    if_not_exists,
    dry_run,
) -> None:
    """Create a process node."""
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "description": description,
            "trust_level": trust_level,
            "assumptions": list(assumptions) if assumptions else None,
        },
    )
    if use_stdin:
        body = read_json_stdin()
        if isinstance(body, dict):
            body.setdefault("type", "process")
        elif isinstance(body, list):
            for item in body:
                if isinstance(item, dict):
                    item.setdefault("type", "process")
    else:
        if name is None or description is None or trust_level is None:
            raise click.UsageError(
                "--name, --description, and --trust-level are required (or use --stdin)"
            )
        body = {
            "type": "process",
            "name": name,
            "description": description,
            "trust_level": trust_level,
            "assumptions": list(assumptions),
        }

    if isinstance(body, list):
        models = [ProcessNodeCreate.model_validate(item) for item in body]
        _create_variant_batch(ctx, diagram_id, models, dry_run)
        return

    model = ProcessNodeCreate.model_validate(body)
    _create_variant(ctx, diagram_id, model, dry_run)


@create_node_group.command(name="external-entity")
@dfd_diagram_id_option
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option(
    "--entity-type",
    "entity_type",
    type=click.Choice(_EXTERNAL_ENTITY_TYPE_CHOICES),
    default=None,
)
@click.option(
    "--out-of-scope/--no-out-of-scope",
    "out_of_scope",
    default=None,
    help="Set the out_of_scope flag (default False if neither flag given).",
)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_external_entity(
    ctx,
    *,
    diagram_id,
    name,
    description,
    entity_type,
    out_of_scope,
    use_stdin,
    if_not_exists,
    dry_run,
) -> None:
    """Create an external entity node."""
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "description": description,
            "entity_type": entity_type,
            "out_of_scope": out_of_scope,
        },
    )
    if use_stdin:
        body = read_json_stdin()
        if isinstance(body, dict):
            body.setdefault("type", "external_entity")
        elif isinstance(body, list):
            for item in body:
                if isinstance(item, dict):
                    item.setdefault("type", "external_entity")
    else:
        if name is None or description is None or entity_type is None:
            raise click.UsageError(
                "--name, --description, and --entity-type are required (or use --stdin)"
            )
        body = {
            "type": "external_entity",
            "name": name,
            "description": description,
            "entity_type": entity_type,
            "out_of_scope": bool(out_of_scope) if out_of_scope is not None else False,
        }

    if isinstance(body, list):
        models = [ExternalEntityNodeCreate.model_validate(item) for item in body]
        _create_variant_batch(ctx, diagram_id, models, dry_run)
        return

    model = ExternalEntityNodeCreate.model_validate(body)
    _create_variant(ctx, diagram_id, model, dry_run)


@create_node_group.command(name="data-store")
@dfd_diagram_id_option
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option(
    "--storage-type",
    "storage_type",
    type=click.Choice(_STORAGE_TYPE_CHOICES),
    default=None,
)
@click.option("--contains-pii/--no-contains-pii", "contains_pii", default=None)
@click.option(
    "--encryption-at-rest/--no-encryption-at-rest",
    "encryption_at_rest",
    default=None,
)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_data_store(
    ctx,
    *,
    diagram_id,
    name,
    description,
    storage_type,
    contains_pii,
    encryption_at_rest,
    use_stdin,
    if_not_exists,
    dry_run,
) -> None:
    """Create a data store node."""
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "description": description,
            "storage_type": storage_type,
            "contains_pii": contains_pii,
            "encryption_at_rest": encryption_at_rest,
        },
    )
    if use_stdin:
        body = read_json_stdin()
        if isinstance(body, dict):
            body.setdefault("type", "data_store")
        elif isinstance(body, list):
            for item in body:
                if isinstance(item, dict):
                    item.setdefault("type", "data_store")
    else:
        if (
            name is None
            or description is None
            or storage_type is None
            or contains_pii is None
            or encryption_at_rest is None
        ):
            msg = (
                "--name, --description, --storage-type, "
                "--contains-pii/--no-contains-pii, and "
                "--encryption-at-rest/--no-encryption-at-rest are required "
                "(or use --stdin)"
            )
            raise click.UsageError(msg)
        body = {
            "type": "data_store",
            "name": name,
            "description": description,
            "storage_type": storage_type,
            "contains_pii": contains_pii,
            "encryption_at_rest": encryption_at_rest,
        }

    if isinstance(body, list):
        models = [DataStoreNodeCreate.model_validate(item) for item in body]
        _create_variant_batch(ctx, diagram_id, models, dry_run)
        return

    model = DataStoreNodeCreate.model_validate(body)
    _create_variant(ctx, diagram_id, model, dry_run)


# ============================================================================
# UPDATE subcommand group with variant subcommands
# ============================================================================


@node_group.group(name="update")
def update_node_group() -> None:
    """Update a node of a specific variant.

    The variant must match the row's existing type."""


def _ensure_variant(node_id: int, expected_type: str) -> None:
    """Pre-flight: confirm the row exists and matches the expected variant."""
    with connect() as conn:
        row = NodeRepository(conn).get(node_id)
    if row is None:
        raise NotFoundError(f"Node id={node_id} not found", id=str(node_id))
    if row.type != expected_type:
        msg = (
            f"Type mismatch: row id={node_id} is {row.type}, but the "
            f"{expected_type} variant subcommand was used."
        )
        actual_subcommand = _TYPE_TO_SUBCOMMAND[row.type]
        hint = f"Use 'tm node update {actual_subcommand} {node_id}' instead."
        raise UserError(msg, hint=hint)


def _apply_variant_update(ctx, node_id, patch, dry_run) -> None:
    if dry_run:
        emit(
            ctx,
            {
                "dry_run": True,
                "would_update": {
                    "id": str(node_id),
                    "patch": patch.model_dump(mode="json", exclude_none=True),
                },
            },
        )
        return
    with connect() as conn:
        updated = NodeRepository(conn).update(node_id, patch)
    if updated is None:
        # Should not happen because _ensure_variant pre-checked, but be defensive.
        raise NotFoundError(f"Node id={node_id} not found", id=str(node_id))
    emit(ctx, updated.model_dump(mode="json"))


@update_node_group.command(name="process")
@click.argument("node_id", type=click.INT)
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option(
    "--trust-level",
    "trust_level",
    type=click.Choice(_TRUST_LEVEL_CHOICES),
    default=None,
)
@click.option(
    "--assumption",
    "assumptions",
    multiple=True,
    default=None,
    help="Repeatable. Pass to replace the assumptions list. Omit to leave unchanged.",
)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_process(
    ctx,
    node_id,
    *,
    name,
    description,
    trust_level,
    assumptions,
    use_stdin,
    dry_run,
) -> None:
    """Update a process node."""
    _ensure_variant(node_id, "process")
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "description": description,
            "trust_level": trust_level,
            "assumptions": list(assumptions) if assumptions else None,
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
        if trust_level is not None:
            body["trust_level"] = trust_level
        if assumptions is not None and len(assumptions) > 0:
            body["assumptions"] = list(assumptions)
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = ProcessNodeUpdate.model_validate(body)
    _apply_variant_update(ctx, node_id, patch, dry_run)


@update_node_group.command(name="external-entity")
@click.argument("node_id", type=click.INT)
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option(
    "--entity-type",
    "entity_type",
    type=click.Choice(_EXTERNAL_ENTITY_TYPE_CHOICES),
    default=None,
)
@click.option("--out-of-scope/--no-out-of-scope", "out_of_scope", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_external_entity(
    ctx,
    node_id,
    *,
    name,
    description,
    entity_type,
    out_of_scope,
    use_stdin,
    dry_run,
) -> None:
    """Update an external entity node."""
    _ensure_variant(node_id, "external_entity")
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "description": description,
            "entity_type": entity_type,
            "out_of_scope": out_of_scope,
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
        if entity_type is not None:
            body["entity_type"] = entity_type
        if out_of_scope is not None:
            body["out_of_scope"] = out_of_scope
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = ExternalEntityNodeUpdate.model_validate(body)
    _apply_variant_update(ctx, node_id, patch, dry_run)


@update_node_group.command(name="data-store")
@click.argument("node_id", type=click.INT)
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option(
    "--storage-type",
    "storage_type",
    type=click.Choice(_STORAGE_TYPE_CHOICES),
    default=None,
)
@click.option("--contains-pii/--no-contains-pii", "contains_pii", default=None)
@click.option(
    "--encryption-at-rest/--no-encryption-at-rest",
    "encryption_at_rest",
    default=None,
)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_data_store(
    ctx,
    node_id,
    *,
    name,
    description,
    storage_type,
    contains_pii,
    encryption_at_rest,
    use_stdin,
    dry_run,
) -> None:
    """Update a data store node."""
    _ensure_variant(node_id, "data_store")
    enforce_stdin_exclusive(
        use_stdin,
        {
            "name": name,
            "description": description,
            "storage_type": storage_type,
            "contains_pii": contains_pii,
            "encryption_at_rest": encryption_at_rest,
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
        if storage_type is not None:
            body["storage_type"] = storage_type
        if contains_pii is not None:
            body["contains_pii"] = contains_pii
        if encryption_at_rest is not None:
            body["encryption_at_rest"] = encryption_at_rest
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = DataStoreNodeUpdate.model_validate(body)
    _apply_variant_update(ctx, node_id, patch, dry_run)


# ============================================================================
# Container membership commands
# ============================================================================


@node_group.command(name="set-parent")
@click.argument("node_id", type=click.INT)
@click.argument("container_id", type=click.INT)
@click.pass_context
def set_parent(ctx, node_id: int, container_id: int) -> None:
    """Place ``node_id`` inside the container ``container_id``.

    Same diagram, no cycle."""
    with connect() as conn:
        ContainerRepository(conn).set_parent(node_id, container_id)
    emit(ctx, {"child_id": str(node_id), "parent_id": str(container_id)})


@node_group.command(name="clear-parent")
@click.argument("node_id", type=click.INT)
@click.pass_context
def clear_parent(ctx, node_id: int) -> None:
    """Remove ``node_id`` from any container."""
    with connect() as conn:
        existed = ContainerRepository(conn).clear_parent(node_id)
    emit(ctx, {"cleared": existed, "id": str(node_id)})


@node_group.command(name="parent-of")
@click.argument("node_id", type=click.INT)
@json_fields_option
@click.pass_context
def parent_of(ctx, node_id: int, *, json_fields) -> None:
    """Get the container that holds ``node_id``, if any."""
    with connect() as conn:
        parent = ContainerRepository(conn).parent_of(node_id)
    if parent is None:
        emit(ctx, {"id": str(node_id), "parent": None})
        return
    payload = project_fields(
        parent.model_dump(mode="json"), parse_json_fields(json_fields)
    )
    emit(ctx, {"id": str(node_id), "parent": payload})


@node_group.command(name="link-document")
@click.argument("node_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def node_link_document(ctx, node_id: int, doc_id: int) -> None:
    """Link a document to this node. Idempotent."""
    with connect() as conn:
        repo = EntityDocumentRepository(conn)
        existing_ids = {d.id for d in repo.documents_for_entity(node_id)}
        already = doc_id in existing_ids
        repo.link(node_id, doc_id)
    payload = {
        "linked": not already,
        "node_id": str(node_id),
        "document_id": str(doc_id),
    }
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@node_group.command(name="unlink-document")
@click.argument("node_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def node_unlink_document(ctx, node_id: int, doc_id: int) -> None:
    """Remove a document↔node link. Idempotent."""
    with connect() as conn:
        existed = EntityDocumentRepository(conn).unlink(node_id, doc_id)
    payload = {
        "unlinked": existed,
        "node_id": str(node_id),
        "document_id": str(doc_id),
    }
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@node_group.command(name="list-documents")
@click.argument("node_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def node_list_documents(
    ctx, node_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List documents linked to this node."""
    with connect() as conn:
        if NodeRepository(conn).get(node_id) is None:
            raise NotFoundError(f"Node id={node_id} not found", id=str(node_id))
        rows = EntityDocumentRepository(conn).documents_for_entity(node_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@node_group.command(name="link-observation")
@click.argument("node_id", type=click.INT)
@click.argument("obs_id", type=click.INT)
@click.pass_context
def node_link_observation(ctx, node_id: int, obs_id: int) -> None:
    """Link an observation to this node. Idempotent."""
    with connect() as conn:
        repo = EntityObservationRepository(conn)
        already = repo.is_linked(node_id, obs_id)
        repo.link(node_id, obs_id)
    payload = {
        "linked": not already,
        "node_id": str(node_id),
        "observation_id": str(obs_id),
    }
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@node_group.command(name="unlink-observation")
@click.argument("node_id", type=click.INT)
@click.argument("obs_id", type=click.INT)
@click.pass_context
def node_unlink_observation(ctx, node_id: int, obs_id: int) -> None:
    """Remove an observation↔node link. Idempotent."""
    with connect() as conn:
        existed = EntityObservationRepository(conn).unlink(node_id, obs_id)
    payload = {
        "unlinked": existed,
        "node_id": str(node_id),
        "observation_id": str(obs_id),
    }
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@node_group.command(name="list-observations")
@click.argument("node_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def node_list_observations(
    ctx, node_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List observations linked to this node."""
    with connect() as conn:
        if NodeRepository(conn).get(node_id) is None:
            raise NotFoundError(f"Node id={node_id} not found", id=str(node_id))
        rows = EntityObservationRepository(conn).observations_for_entity(node_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    if limit is not None:
        sliced = sorted_rows[offset : offset + limit]
    else:
        sliced = sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
