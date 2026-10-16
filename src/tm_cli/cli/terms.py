"""tm term — Term CRUDL + search + reverse-junction subgroup."""

from __future__ import annotations

from typing import Any

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
    TermCreate,
    TermRepository,
    TermUpdate,
    connect,
)


@click.group(name="term")
def term_group() -> None:
    """Manage glossary terms."""


@term_group.command(name="list")
@list_options
@json_fields_option
@click.pass_context
def list_terms(ctx, *, limit, offset, sort_field, order, json_fields) -> None:
    """List all terms."""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = TermRepository(conn).list(limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@term_group.command(name="get")
@click.argument("term_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_term(ctx, term_id, *, json_fields) -> None:
    """Fetch a term by id."""
    with connect() as conn:
        row = TermRepository(conn).get(term_id)
    if row is None:
        raise NotFoundError(f"Term id={term_id} not found", id=str(term_id))
    fields = parse_json_fields(json_fields)
    payload = project_fields(row.model_dump(mode="json"), fields)
    emit(ctx, payload)


@term_group.command(name="create")
@click.option("--term", "term_value", default=None)
@click.option("--definition", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option(
    "--if-not-exists",
    "if_not_exists",
    is_flag=True,
    default=False,
    help="Use natural-key lookup (term) for idempotent create.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_term(
    ctx, *, term_value, definition, use_stdin, if_not_exists, dry_run
) -> None:
    """Create a term, optionally idempotent on the ``term`` natural key."""
    enforce_stdin_exclusive(use_stdin, {"term": term_value, "definition": definition})

    if use_stdin:
        body = read_json_stdin()
    else:
        if term_value is None or definition is None:
            msg = "--term and --definition are required (or use --stdin)"
            raise click.UsageError(msg)
        body = {"term": term_value, "definition": definition}

    if isinstance(body, list):
        return _create_batch(ctx, body, if_not_exists=if_not_exists, dry_run=dry_run)

    model = TermCreate.model_validate(body)
    if if_not_exists:
        with connect() as conn:
            existing = TermRepository(conn).get_by_term(model.term)
        if existing is not None:
            payload = {"created": False, **existing.model_dump(mode="json")}
            if dry_run:
                payload = {"dry_run": True, "would_create": False, "existing": payload}
            emit(ctx, payload)
            return

    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return

    with connect() as conn:
        created = TermRepository(conn).create(model)
    if if_not_exists:
        payload = {"created": True, **created.model_dump(mode="json")}
    else:
        payload = created.model_dump(mode="json")
    emit(ctx, payload)


def _create_batch(
    ctx, body: list[dict[str, Any]], *, if_not_exists: bool, dry_run: bool
) -> None:
    models: list[TermCreate] = []
    for index, item in enumerate(body):
        try:
            models.append(TermCreate.model_validate(item))
        except ValidationError as e:
            raise map_exception(e, input_payload={"index": index, "item": item}) from e

    if dry_run:
        models_dumped = [m.model_dump(mode="json") for m in models]
        emit(ctx, {"dry_run": True, "would_create": models_dumped})
        return

    with connect() as conn:
        repo = TermRepository(conn)
        out: list[dict[str, Any]] = []
        for m in models:
            existing = repo.get_by_term(m.term) if if_not_exists else None
            if existing is not None:
                out.append({"created": False, **existing.model_dump(mode="json")})
            else:
                created = repo.create(m)
                if if_not_exists:
                    out.append({"created": True, **created.model_dump(mode="json")})
                else:
                    out.append(created.model_dump(mode="json"))
    emit(ctx, out)


@term_group.command(name="update")
@click.argument("term_id", type=click.INT)
@click.option("--term", "term_value", default=None)
@click.option("--definition", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_term(ctx, term_id, *, term_value, definition, use_stdin, dry_run) -> None:
    """Apply a partial update to a term."""
    enforce_stdin_exclusive(use_stdin, {"term": term_value, "definition": definition})

    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body = {
            k: v
            for k, v in {"term": term_value, "definition": definition}.items()
            if v is not None
        }
        if not body:
            msg = "No update fields provided (and --stdin not used)"
            raise click.UsageError(msg)

    patch = TermUpdate.model_validate(body)
    if dry_run:
        patch_data = patch.model_dump(mode="json", exclude_none=True)
        would_update = {"id": str(term_id), "patch": patch_data}
        emit(ctx, {"dry_run": True, "would_update": would_update})
        return

    with connect() as conn:
        updated = TermRepository(conn).update(term_id, patch)
    if updated is None:
        raise NotFoundError(f"Term id={term_id} not found", id=str(term_id))
    emit(ctx, updated.model_dump(mode="json"))


@term_group.command(name="delete")
@click.argument("term_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_term(ctx, term_id, *, yes, dry_run) -> None:
    """Delete a term (idempotent)."""
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(term_id)})
        return
    with connect() as conn:
        existed = TermRepository(conn).delete(term_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(term_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(term_id), "reason": "not_found"})


@term_group.command(name="search")
@click.argument("text", nargs=1)
@list_options
@json_fields_option
@click.pass_context
def search_terms(ctx, text, *, limit, offset, sort_field, order, json_fields) -> None:
    """Full-text search across term and definition."""
    if not text.strip():
        raise click.UsageError("search requires a non-empty TEXT argument")
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = TermRepository(conn).search(text=text, limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@term_group.command(name="list-documents")
@click.argument("term_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_documents_for_term(
    ctx, term_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List documents linked to a term."""
    with connect() as conn:
        repo = TermRepository(conn)
        if repo.get(term_id) is None:
            raise NotFoundError(f"Term id={term_id} not found", id=str(term_id))
        rows = repo.documents_for_term(term_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
