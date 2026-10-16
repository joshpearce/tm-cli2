"""tm finding — ValidationFinding CRUDL + search + clear subgroup."""

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
    FindingSeverity,
    ValidationFindingCreate,
    ValidationFindingRepository,
    ValidationFindingUpdate,
    connect,
)

_SEVERITY_CHOICES = list(get_args(FindingSeverity))

# Sentinel for "user explicitly cleared the code field" on update.
_CLEAR_CODE = object()


def _parse_code_value(value: str | None) -> str | None | object:
    """Parse ``--code`` for update.

    Three distinct return values:
    - ``None`` — Click flag was NOT supplied (default). The caller leaves the
      field untouched in the patch.
    - ``_CLEAR_CODE`` (sentinel) — flag was supplied with ``""`` / ``"none"`` /
      ``"null"``. The caller sets ``code=None`` in the patch (clears the column).
    - ``str`` — flag was supplied with a non-empty value. Set to that string.
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in ("", "none", "null"):
        return _CLEAR_CODE
    return value


@click.group(name="finding")
def finding_group() -> None:
    """Manage validation findings."""


@finding_group.command(name="create")
@dfd_diagram_id_option
@click.option(
    "--severity",
    type=click.Choice(_SEVERITY_CHOICES),
    default=None,
    help="Finding severity (error or warning).",
)
@click.option("--message", default=None, help="Finding message.")
@click.option("--source", default=None, help="Finding source (e.g. validator name).")
@click.option(
    "--entity-id",
    "entity_id",
    type=click.INT,
    default=None,
    help="Optional DFD entity id this finding relates to.",
)
@click.option("--code", default=None, help="Optional finding code.")
@click.option(
    "--stdin",
    "use_stdin",
    is_flag=True,
    default=False,
    help="Read JSON object or array from stdin instead of named flags.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Dry-run.")
@click.pass_context
def create_finding(
    ctx,
    *,
    diagram_id,
    severity,
    message,
    source,
    entity_id,
    code,
    use_stdin,
    dry_run,
) -> None:
    """Create a validation finding. Use named flags or --stdin."""
    enforce_stdin_exclusive(
        use_stdin,
        {
            "severity": severity,
            "message": message,
            "source": source,
            "entity_id": entity_id,
            "code": code,
        },
    )
    if use_stdin:
        body = read_json_stdin()
    else:
        if severity is None or message is None or source is None:
            raise click.UsageError(
                "--severity, --message, --source required (or use --stdin)"
            )
        body: dict[str, Any] = {
            "severity": severity,
            "message": message,
            "source": source,
        }
        if entity_id is not None:
            body["entity_id"] = entity_id
        if code is not None:
            body["code"] = code

    if isinstance(body, list):
        models: list[ValidationFindingCreate] = []
        for index, item in enumerate(body):
            try:
                models.append(ValidationFindingCreate.model_validate(item))
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
            repo = ValidationFindingRepository(conn)
            created = [repo.create(resolved, m) for m in models]
        results = [
            {"diagram_id": str(resolved), **c.model_dump(mode="json")} for c in created
        ]
        emit(ctx, results)
        return

    try:
        model = ValidationFindingCreate.model_validate(body)
    except ValidationError as e:
        raise map_exception(e, input_payload=body) from e
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        assert resolved is not None
        created_finding = ValidationFindingRepository(conn).create(resolved, model)
    emit(ctx, {"diagram_id": str(resolved), **created_finding.model_dump(mode="json")})


@finding_group.command(name="get")
@click.argument("finding_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_finding(ctx, finding_id, *, json_fields) -> None:
    """Get a validation finding by id."""
    with connect() as conn:
        row = ValidationFindingRepository(conn).get(finding_id)
    if row is None:
        raise NotFoundError(
            f"ValidationFinding id={finding_id} not found", id=str(finding_id)
        )
    fields = parse_json_fields(json_fields)
    payload = project_fields(row.model_dump(mode="json"), fields)
    emit(ctx, payload)


@finding_group.command(name="update")
@click.argument("finding_id", type=click.INT)
@click.option(
    "--severity",
    type=click.Choice(_SEVERITY_CHOICES),
    default=None,
    help="Finding severity (error or warning).",
)
@click.option("--message", default=None, help="Finding message.")
@click.option("--source", default=None, help="Finding source.")
@click.option(
    "--code",
    "code_raw",
    default=None,
    help="Finding code, or 'none'/'' to clear.",
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
def update_finding(
    ctx,
    finding_id,
    *,
    severity,
    message,
    source,
    code_raw,
    use_stdin,
    dry_run,
) -> None:
    """Apply a partial update to a validation finding."""
    parsed_code = _parse_code_value(code_raw)
    enforce_stdin_exclusive(
        use_stdin,
        {
            "severity": severity,
            "message": message,
            "source": source,
            "code": (None if parsed_code is None else parsed_code),
        },
    )
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body = {}
        if severity is not None:
            body["severity"] = severity
        if message is not None:
            body["message"] = message
        if source is not None:
            body["source"] = source
        if parsed_code is _CLEAR_CODE:
            body["code"] = None
        elif parsed_code is not None:
            body["code"] = parsed_code
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")

    try:
        patch = ValidationFindingUpdate.model_validate(body)
    except ValidationError as e:
        raise map_exception(e, input_payload=body) from e
    if dry_run:
        patch_dump = patch.model_dump(mode="json")
        emit(
            ctx,
            {
                "dry_run": True,
                "would_update": {"id": str(finding_id), "patch": patch_dump},
            },
        )
        return
    with connect() as conn:
        updated = ValidationFindingRepository(conn).update(finding_id, patch)
    if updated is None:
        raise NotFoundError(
            f"ValidationFinding id={finding_id} not found", id=str(finding_id)
        )
    emit(ctx, updated.model_dump(mode="json"))


@finding_group.command(name="delete")
@click.argument("finding_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Dry-run.")
@click.pass_context
def delete_finding(ctx, finding_id, *, yes, dry_run) -> None:
    """Delete a validation finding."""
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(finding_id)})
        return
    with connect() as conn:
        existed = ValidationFindingRepository(conn).delete(finding_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(finding_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(finding_id), "reason": "not_found"})


@finding_group.command(name="list")
@list_options
@dfd_diagram_id_option
@click.option(
    "--severity",
    type=click.Choice(_SEVERITY_CHOICES),
    default=None,
    help="Filter to findings with this severity.",
)
@click.option(
    "--source",
    default=None,
    help="Filter to findings from this source.",
)
@json_fields_option
@click.pass_context
def list_findings(
    ctx,
    *,
    limit,
    offset,
    sort_field,
    order,
    diagram_id,
    severity,
    source,
    json_fields,
) -> None:
    """List validation findings in a diagram (defaults to the 'default' diagram)."""
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = ValidationFindingRepository(conn).search(
            resolved,
            text=None,
            severity=severity,
            source=source,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@finding_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@dfd_diagram_id_option
@click.option(
    "--severity",
    type=click.Choice(_SEVERITY_CHOICES),
    default=None,
    help="Filter to findings with this severity.",
)
@click.option(
    "--source",
    default=None,
    help="Filter to findings from this source.",
)
@json_fields_option
@click.pass_context
def search_findings(
    ctx,
    text,
    *,
    limit,
    offset,
    sort_field,
    order,
    diagram_id,
    severity,
    source,
    json_fields,
) -> None:
    """Search validation findings by message or code."""
    text_str = " ".join(text).strip() if text else ""
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = ValidationFindingRepository(conn).search(
            resolved,
            text=text_str if text_str else None,
            severity=severity,
            source=source,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@finding_group.command(name="clear")
@dfd_diagram_id_option
@click.option(
    "--source",
    default=None,
    help="Limit clearing to findings from this source only.",
)
@click.pass_context
def clear_findings(ctx, *, diagram_id, source) -> None:
    """Bulk-delete validation findings for a diagram (optionally filtered by source)."""
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, {"cleared": 0})
            return
        count = ValidationFindingRepository(conn).clear(resolved, source=source)
    emit(ctx, {"cleared": count, "diagram_id": str(resolved)})
