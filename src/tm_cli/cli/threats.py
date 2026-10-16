"""tm threat — Threat CRUDL + observation/entity linking."""

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
    ThreatCreate,
    ThreatRating,
    ThreatRepository,
    ThreatUpdate,
    connect,
)

_RATING_CHOICES = list(get_args(ThreatRating))


@click.group(name="threat")
def threat_group() -> None:
    """Manage threat assessment records."""


@threat_group.command(name="list")
@list_options
@click.option(
    "--rating",
    type=click.Choice(_RATING_CHOICES),
    default=None,
    help="Filter by threat rating.",
)
@json_fields_option
@click.pass_context
def list_threats(ctx, *, limit, offset, sort_field, order, rating, json_fields) -> None:
    """List threats."""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = ThreatRepository(conn).list(rating=rating, limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@threat_group.command(name="get")
@click.argument("threat_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_threat(ctx, threat_id, *, json_fields) -> None:
    """Fetch a threat by id."""
    with connect() as conn:
        row = ThreatRepository(conn).get(threat_id)
    if row is None:
        raise NotFoundError(f"Threat id={threat_id} not found", id=str(threat_id))
    fields = parse_json_fields(json_fields)
    payload = project_fields(row.model_dump(mode="json"), fields)
    emit(ctx, payload)


@threat_group.command(name="create")
@click.option("--title", default=None)
@click.option("--scenario", default=None)
@click.option("--rating", type=click.Choice(_RATING_CHOICES), default=None)
@click.option("--description", default=None)
@click.option("--mitre-reference", "mitre_reference", default=None)
@click.option("--observed-mitigations", "observed_mitigations", default=None)
@click.option("--recommendations", default=None)
@click.option("--threat-catalog-id", "threat_catalog_id", type=click.INT, default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_threat(
    ctx,
    *,
    title,
    scenario,
    rating,
    description,
    mitre_reference,
    observed_mitigations,
    recommendations,
    threat_catalog_id,
    use_stdin,
    dry_run,
) -> None:
    """Create a threat record."""
    named = {
        "title": title,
        "scenario": scenario,
        "rating": rating,
        "description": description,
        "mitre_reference": mitre_reference,
        "observed_mitigations": observed_mitigations,
        "recommendations": recommendations,
        "threat_catalog_id": threat_catalog_id,
    }
    enforce_stdin_exclusive(use_stdin, named)

    if use_stdin:
        body = read_json_stdin()
    else:
        required = (
            "title",
            "scenario",
            "rating",
            "description",
            "mitre_reference",
            "observed_mitigations",
            "recommendations",
        )
        missing = [k for k in required if named[k] is None]
        if missing:
            flags = ", ".join("--" + k.replace("_", "-") for k in missing)
            msg = f"Missing required options: {flags} (or use --stdin)"
            raise click.UsageError(msg)
        body = {k: v for k, v in named.items() if v is not None}

    if isinstance(body, list):
        models = _validate_create_batch(body)
        if dry_run:
            dumped = [m.model_dump(mode="json") for m in models]
            emit(ctx, {"dry_run": True, "would_create": dumped})
            return
        with connect() as conn:
            repo = ThreatRepository(conn)
            created = [repo.create(m) for m in models]
        emit(ctx, [c.model_dump(mode="json") for c in created])
        return

    model = ThreatCreate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        created_threat = ThreatRepository(conn).create(model)
    emit(ctx, created_threat.model_dump(mode="json"))


def _validate_create_batch(body: list[dict[str, Any]]) -> list[ThreatCreate]:
    out: list[ThreatCreate] = []
    for index, item in enumerate(body):
        try:
            out.append(ThreatCreate.model_validate(item))
        except ValidationError as e:
            raise map_exception(e, input_payload={"index": index, "item": item}) from e
    return out


@threat_group.command(name="update")
@click.argument("threat_id", type=click.INT)
@click.option("--title", default=None)
@click.option("--scenario", default=None)
@click.option("--rating", type=click.Choice(_RATING_CHOICES), default=None)
@click.option("--description", default=None)
@click.option("--mitre-reference", "mitre_reference", default=None)
@click.option("--observed-mitigations", "observed_mitigations", default=None)
@click.option("--recommendations", default=None)
@click.option("--threat-catalog-id", "threat_catalog_id", type=click.INT, default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_threat(
    ctx,
    threat_id,
    *,
    title,
    scenario,
    rating,
    description,
    mitre_reference,
    observed_mitigations,
    recommendations,
    threat_catalog_id,
    use_stdin,
    dry_run,
) -> None:
    """Apply a partial update to a threat."""
    named = {
        "title": title,
        "scenario": scenario,
        "rating": rating,
        "description": description,
        "mitre_reference": mitre_reference,
        "observed_mitigations": observed_mitigations,
        "recommendations": recommendations,
        "threat_catalog_id": threat_catalog_id,
    }
    enforce_stdin_exclusive(use_stdin, named)

    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body = {k: v for k, v in named.items() if v is not None}
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")

    patch = ThreatUpdate.model_validate(body)
    if dry_run:
        patch_data = patch.model_dump(mode="json", exclude_none=True)
        would_update = {"id": str(threat_id), "patch": patch_data}
        emit(ctx, {"dry_run": True, "would_update": would_update})
        return
    with connect() as conn:
        updated = ThreatRepository(conn).update(threat_id, patch)
    if updated is None:
        raise NotFoundError(f"Threat id={threat_id} not found", id=str(threat_id))
    emit(ctx, updated.model_dump(mode="json"))


@threat_group.command(name="delete")
@click.argument("threat_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_threat(ctx, threat_id, *, yes, dry_run) -> None:
    """Delete a threat (idempotent)."""
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(threat_id)})
        return
    with connect() as conn:
        existed = ThreatRepository(conn).delete(threat_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(threat_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(threat_id), "reason": "not_found"})


@threat_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@click.option(
    "--rating",
    type=click.Choice(_RATING_CHOICES),
    default=None,
    help="Filter by threat rating.",
)
@json_fields_option
@click.pass_context
def search_threats(
    ctx, text, *, limit, offset, sort_field, order, rating, json_fields
) -> None:
    """Search threats by text; combine with rating filter."""
    text_str = " ".join(text).strip() if text else ""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = ThreatRepository(conn).search(
            text=text_str if text_str else None,
            rating=rating,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@threat_group.command(name="link-observation")
@click.argument("threat_id", type=click.INT)
@click.argument("observation_id", type=click.INT)
@click.pass_context
def link_observation(ctx, threat_id, observation_id) -> None:
    """Link a threat to an observation (idempotent)."""
    with connect() as conn:
        repo = ThreatRepository(conn)
        if not repo.exists(threat_id):
            raise NotFoundError(f"Threat id={threat_id} not found", id=str(threat_id))
        repo.link_observation(threat_id, observation_id)
    emit(
        ctx,
        {
            "linked": True,
            "threat_id": str(threat_id),
            "observation_id": str(observation_id),
        },
    )


@threat_group.command(name="unlink-observation")
@click.argument("threat_id", type=click.INT)
@click.argument("observation_id", type=click.INT)
@click.pass_context
def unlink_observation(ctx, threat_id, observation_id) -> None:
    """Unlink a threat from an observation."""
    with connect() as conn:
        removed = ThreatRepository(conn).unlink_observation(threat_id, observation_id)
    emit(
        ctx,
        {
            "unlinked": removed,
            "threat_id": str(threat_id),
            "observation_id": str(observation_id),
        },
    )


@threat_group.command(name="link-entity")
@click.argument("threat_id", type=click.INT)
@click.argument("entity_id", type=click.INT)
@click.pass_context
def link_entity(ctx, threat_id, entity_id) -> None:
    """Link a threat to a DFD entity (idempotent)."""
    with connect() as conn:
        repo = ThreatRepository(conn)
        if not repo.exists(threat_id):
            raise NotFoundError(
                f"Threat id={threat_id} not found",
                id=str(threat_id),
            )
        repo.link_entity(threat_id, entity_id)
    emit(
        ctx,
        {
            "linked": True,
            "threat_id": str(threat_id),
            "entity_id": str(entity_id),
        },
    )


@threat_group.command(name="unlink-entity")
@click.argument("threat_id", type=click.INT)
@click.argument("entity_id", type=click.INT)
@click.pass_context
def unlink_entity(ctx, threat_id, entity_id) -> None:
    """Unlink a threat from a DFD entity."""
    with connect() as conn:
        removed = ThreatRepository(conn).unlink_entity(threat_id, entity_id)
    emit(
        ctx,
        {
            "unlinked": removed,
            "threat_id": str(threat_id),
            "entity_id": str(entity_id),
        },
    )
