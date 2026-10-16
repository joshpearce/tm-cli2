"""tm observation — Observation CRUDL + search subgroup."""

from __future__ import annotations

from typing import Any, get_args

import click
from pydantic import ValidationError

from tm_cli.cli._errors import NotFoundError, map_exception
from tm_cli.cli._options import (
    apply_sort,
    json_fields_option,
    list_options,
    parse_json_fields,
)
from tm_cli.cli._output import emit, project_fields
from tm_cli.cli._stdin import enforce_stdin_exclusive, read_json_stdin
from tm_cli.db import (
    EntityObservationRepository,
    ObservationCreate,
    ObservationRepository,
    ObservationStatus,
    ObservationType,
    ObservationUpdate,
    connect,
)

_OBS_TYPE_CHOICES = list(get_args(ObservationType))
_OBS_STATUS_CHOICES = list(get_args(ObservationStatus))


def _filter_options(f):
    f = click.option(
        "--observation-type",
        "observation_type",
        type=click.Choice(_OBS_TYPE_CHOICES),
        default=None,
        help="Filter by observation type.",
    )(f)
    f = click.option(
        "--status",
        "status",
        type=click.Choice(_OBS_STATUS_CHOICES),
        default=None,
        help="Filter by status.",
    )(f)
    return f


@click.group(name="observation")
def observation_group() -> None:
    """Manage threat-model observations (todos, questions, threats)."""


@observation_group.command(name="list")
@list_options
@_filter_options
@json_fields_option
@click.pass_context
def list_observations(
    ctx,
    *,
    limit,
    offset,
    sort_field,
    order,
    observation_type,
    status,
    json_fields,
) -> None:
    """List observations."""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = ObservationRepository(conn).list(
            observation_type=observation_type,
            status=status,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@observation_group.command(name="get")
@click.argument("obs_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_observation(ctx, obs_id, *, json_fields) -> None:
    """Fetch an observation by id."""
    with connect() as conn:
        row = ObservationRepository(conn).get(obs_id)
    if row is None:
        raise NotFoundError(f"Observation id={obs_id} not found", id=str(obs_id))
    fields = parse_json_fields(json_fields)
    payload = project_fields(row.model_dump(mode="json"), fields)
    emit(ctx, payload)


@observation_group.command(name="create")
@click.option("--content", default=None)
@click.option(
    "--observation-type",
    "observation_type",
    type=click.Choice(_OBS_TYPE_CHOICES),
    default=None,
)
@click.option("--status", type=click.Choice(_OBS_STATUS_CHOICES), default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option(
    "--if-not-exists",
    "if_not_exists",
    is_flag=True,
    default=False,
    help="No-op for Observation (no natural key); kept for command-shape consistency.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_observation(
    ctx, *, content, observation_type, status, use_stdin, if_not_exists, dry_run
) -> None:
    """Create an observation."""
    enforce_stdin_exclusive(
        use_stdin,
        {"content": content, "observation_type": observation_type, "status": status},
    )
    if use_stdin:
        body = read_json_stdin()
    else:
        if content is None or observation_type is None:
            msg = "--content and --observation-type are required (or use --stdin)"
            raise click.UsageError(msg)
        body = {"content": content, "observation_type": observation_type}
        if status is not None:
            body["status"] = status

    if isinstance(body, list):
        models = _validate_create_batch(body)
        if dry_run:
            models_dumped = [m.model_dump(mode="json") for m in models]
            emit(ctx, {"dry_run": True, "would_create": models_dumped})
            return
        with connect() as conn:
            repo = ObservationRepository(conn)
            created = [repo.create(m) for m in models]
        emit(ctx, [c.model_dump(mode="json") for c in created])
        return

    model = ObservationCreate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        created_obs = ObservationRepository(conn).create(model)
    emit(ctx, created_obs.model_dump(mode="json"))


def _validate_create_batch(body: list[dict[str, Any]]) -> list[ObservationCreate]:
    out: list[ObservationCreate] = []
    for index, item in enumerate(body):
        try:
            out.append(ObservationCreate.model_validate(item))
        except ValidationError as e:
            raise map_exception(e, input_payload={"index": index, "item": item}) from e
    return out


@observation_group.command(name="update")
@click.argument("obs_id", type=click.INT)
@click.option("--content", default=None)
@click.option(
    "--observation-type",
    "observation_type",
    type=click.Choice(_OBS_TYPE_CHOICES),
    default=None,
)
@click.option("--status", type=click.Choice(_OBS_STATUS_CHOICES), default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_observation(
    ctx, obs_id, *, content, observation_type, status, use_stdin, dry_run
) -> None:
    """Apply a partial update to an observation."""
    enforce_stdin_exclusive(
        use_stdin,
        {"content": content, "observation_type": observation_type, "status": status},
    )
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body = {
            k: v
            for k, v in {
                "content": content,
                "observation_type": observation_type,
                "status": status,
            }.items()
            if v is not None
        }
        if not body:
            msg = "No update fields provided (and --stdin not used)"
            raise click.UsageError(msg)

    patch = ObservationUpdate.model_validate(body)
    if dry_run:
        patch_data = patch.model_dump(mode="json", exclude_none=True)
        would_update = {"id": str(obs_id), "patch": patch_data}
        emit(ctx, {"dry_run": True, "would_update": would_update})
        return
    with connect() as conn:
        updated = ObservationRepository(conn).update(obs_id, patch)
    if updated is None:
        raise NotFoundError(f"Observation id={obs_id} not found", id=str(obs_id))
    emit(ctx, updated.model_dump(mode="json"))


@observation_group.command(name="delete")
@click.argument("obs_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_observation(ctx, obs_id, *, yes, dry_run) -> None:
    """Delete an observation (idempotent)."""
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(obs_id)})
        return
    with connect() as conn:
        existed = ObservationRepository(conn).delete(obs_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(obs_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(obs_id), "reason": "not_found"})


@observation_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@_filter_options
@json_fields_option
@click.pass_context
def search_observations(
    ctx,
    text,
    *,
    limit,
    offset,
    sort_field,
    order,
    observation_type,
    status,
    json_fields,
) -> None:
    """Full-text search over content; combine with type/status filters."""
    text_str = " ".join(text).strip() if text else ""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = ObservationRepository(conn).search(
            text=text_str if text_str else None,
            observation_type=observation_type,
            status=status,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


# The four list-* commands below intentionally mirror documents.py's four
# list_*_for_doc commands rather than table-driving them. Click decorator
# stacking and per-command docstrings require explicit function definitions;
# a loop-based approach would have to rebind ``query`` per iteration and would
# obscure the help text and ``tm commands`` JSON introspection output.
def _list_for_observation(
    ctx, obs_id, *, limit, offset, sort_field, order, json_fields, query
):
    """Shared body for the four reverse-listing commands."""
    with connect() as conn:
        if not ObservationRepository(conn).exists(obs_id):
            raise NotFoundError(f"Observation id={obs_id} not found", id=str(obs_id))
        rows = query(EntityObservationRepository(conn), obs_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    if limit is not None:
        sliced = sorted_rows[offset : offset + limit]
    else:
        sliced = sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@observation_group.command(name="list-nodes")
@click.argument("obs_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_nodes_for_observation(
    ctx, obs_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List nodes linked to an observation."""
    _list_for_observation(
        ctx,
        obs_id,
        limit=limit,
        offset=offset,
        sort_field=sort_field,
        order=order,
        json_fields=json_fields,
        query=lambda repo, oid: repo.nodes_for_observation(oid),
    )


@observation_group.command(name="list-containers")
@click.argument("obs_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_containers_for_observation(
    ctx, obs_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List containers linked to an observation."""
    _list_for_observation(
        ctx,
        obs_id,
        limit=limit,
        offset=offset,
        sort_field=sort_field,
        order=order,
        json_fields=json_fields,
        query=lambda repo, oid: repo.containers_for_observation(oid),
    )


@observation_group.command(name="list-flows")
@click.argument("obs_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_flows_for_observation(
    ctx, obs_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List flows linked to an observation."""
    _list_for_observation(
        ctx,
        obs_id,
        limit=limit,
        offset=offset,
        sort_field=sort_field,
        order=order,
        json_fields=json_fields,
        query=lambda repo, oid: repo.flows_for_observation(oid),
    )


@observation_group.command(name="list-items")
@click.argument("obs_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_items_for_observation(
    ctx, obs_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List data items linked to an observation."""
    _list_for_observation(
        ctx,
        obs_id,
        limit=limit,
        offset=offset,
        sort_field=sort_field,
        order=order,
        json_fields=json_fields,
        query=lambda repo, oid: repo.items_for_observation(oid),
    )
