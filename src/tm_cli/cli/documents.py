"""tm document — Document CRUDL + search subgroup."""

from __future__ import annotations

from datetime import UTC, datetime
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
    DocumentCreate,
    DocumentRepository,
    DocumentUpdate,
    EntityDocumentRepository,
    TermRepository,
    connect,
)


@click.group(name="document")
def document_group() -> None:
    """Manage documents (source artifacts: threat-model reports, design docs)."""


@document_group.command(name="list")
@list_options
@json_fields_option
@click.pass_context
def list_documents(
    ctx: click.Context,
    *,
    limit: int,
    offset: int,
    sort_field: str,
    order: str,
    json_fields: str | None,
) -> None:
    """List documents (without ``content`` blobs)."""

    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = DocumentRepository(conn).list(limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@document_group.command(name="get")
@click.argument("doc_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_document(ctx: click.Context, doc_id: int, *, json_fields: str | None) -> None:
    """Fetch a single document by id (returns full content)."""

    with connect() as conn:
        row = DocumentRepository(conn).get(doc_id)
    if row is None:
        raise NotFoundError(f"Document id={doc_id} not found", id=str(doc_id))
    fields = parse_json_fields(json_fields)
    payload = project_fields(row.model_dump(mode="json"), fields)
    emit(ctx, payload)


@document_group.command(name="create")
@click.option(
    "--last-updated",
    "last_updated",
    type=click.DateTime(),
    default=None,
    help="ISO-8601 datetime of source author's last update. Defaults to now.",
)
@click.option("--title", default=None, help="Document title.")
@click.option("--author", default=None, help="Document author.")
@click.option("--content", default=None, help="Full document body.")
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
    help="No-op for Document (no natural key); kept for consistency.",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Validate inputs, do not write.",
)
@click.pass_context
def create_document(
    ctx: click.Context,
    *,
    last_updated: datetime | None,
    title: str | None,
    author: str | None,
    content: str | None,
    use_stdin: bool,
    if_not_exists: bool,
    dry_run: bool,
) -> None:
    """Create a document. Use named flags or ``--stdin``."""

    named_values = {
        "last_updated": last_updated,
        "title": title,
        "author": author,
        "content": content,
    }
    enforce_stdin_exclusive(use_stdin, named_values)

    if use_stdin:
        body = read_json_stdin()
    else:
        if title is None or author is None or content is None:
            msg = "--title, --author, and --content are required (or use --stdin)"
            raise click.UsageError(msg)
        body = {
            "last_updated": (last_updated or datetime.now(UTC)).isoformat(),
            "title": title,
            "author": author,
            "content": content,
        }

    if isinstance(body, list):
        models = _validate_create_batch(body)
        if dry_run:
            created_models = [m.model_dump(mode="json") for m in models]
            emit(ctx, {"dry_run": True, "would_create": created_models})
            return
        with connect() as conn:
            repo = DocumentRepository(conn)
            created = [repo.create(m) for m in models]
        emit(ctx, [c.model_dump(mode="json") for c in created])
        return

    model = _validate_create_single(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        created_doc = DocumentRepository(conn).create(model)
    emit(ctx, created_doc.model_dump(mode="json"))


def _validate_create_single(body: dict[str, Any]) -> DocumentCreate:
    return DocumentCreate.model_validate(body)


def _validate_create_batch(body: list[dict[str, Any]]) -> list[DocumentCreate]:
    out: list[DocumentCreate] = []
    for index, item in enumerate(body):
        try:
            out.append(DocumentCreate.model_validate(item))
        except ValidationError as e:
            mapped = map_exception(e, input_payload={"index": index, "item": item})
            raise mapped from e
    return out


@document_group.command(name="update")
@click.argument("doc_id", type=click.INT)
@click.option("--last-updated", "last_updated", type=click.DateTime(), default=None)
@click.option("--title", default=None)
@click.option("--author", default=None)
@click.option("--content", default=None)
@click.option(
    "--stdin",
    "use_stdin",
    is_flag=True,
    default=False,
    help="Read a JSON object from stdin with the patch fields.",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_document(
    ctx: click.Context,
    doc_id: int,
    *,
    last_updated: datetime | None,
    title: str | None,
    author: str | None,
    content: str | None,
    use_stdin: bool,
    dry_run: bool,
) -> None:
    """Apply a partial update to a document."""

    named_values = {
        "last_updated": last_updated,
        "title": title,
        "author": author,
        "content": content,
    }
    enforce_stdin_exclusive(use_stdin, named_values)

    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body = {
            k: v
            for k, v in {
                "last_updated": last_updated.isoformat() if last_updated else None,
                "title": title,
                "author": author,
                "content": content,
            }.items()
            if v is not None
        }
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")

    patch = DocumentUpdate.model_validate(body)
    if dry_run:
        patch_data = patch.model_dump(mode="json", exclude_none=True)
        would_update = {"id": str(doc_id), "patch": patch_data}
        emit(ctx, {"dry_run": True, "would_update": would_update})
        return

    with connect() as conn:
        updated = DocumentRepository(conn).update(doc_id, patch)
    if updated is None:
        raise NotFoundError(f"Document id={doc_id} not found", id=str(doc_id))
    emit(ctx, updated.model_dump(mode="json"))


@document_group.command(name="delete")
@click.argument("doc_id", type=click.INT)
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Required to confirm deletion (matches design contract).",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_document(
    ctx: click.Context, doc_id: int, *, yes: bool, dry_run: bool
) -> None:
    """Delete a document (idempotent: missing id returns ``deleted=false``)."""

    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(doc_id)})
        return

    with connect() as conn:
        existed = DocumentRepository(conn).delete(doc_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(doc_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(doc_id), "reason": "not_found"})


@document_group.command(name="search")
@click.argument("text", nargs=1)
@list_options
@json_fields_option
@click.pass_context
def search_documents(
    ctx: click.Context,
    text: str,
    *,
    limit: int,
    offset: int,
    sort_field: str,
    order: str,
    json_fields: str | None,
) -> None:
    """Full-text search across title, author, and content."""

    if not text.strip():
        msg = (
            "search requires a non-empty TEXT argument; "
            "use 'tm document list' for unfiltered output"
        )
        raise click.UsageError(msg)
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = DocumentRepository(conn).search(text=text, limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@document_group.command(name="link-term")
@click.argument("doc_id", type=click.INT)
@click.argument("term_id", type=click.INT)
@click.pass_context
def link_term(ctx: click.Context, doc_id: int, term_id: int) -> None:
    """Link a term to a document. Idempotent: returns linked=false if already linked."""
    with connect() as conn:
        repo = TermRepository(conn)
        existing_term_ids = {t.id for t in repo.terms_for_document(doc_id)}
        if term_id in existing_term_ids:
            payload = {
                "linked": False,
                "doc_id": str(doc_id),
                "term_id": str(term_id),
                "reason": "already_linked",
            }
            emit(ctx, payload)
            return
        repo.link(doc_id, term_id)
    emit(ctx, {"linked": True, "doc_id": str(doc_id), "term_id": str(term_id)})


@document_group.command(name="unlink-term")
@click.argument("doc_id", type=click.INT)
@click.argument("term_id", type=click.INT)
@click.pass_context
def unlink_term(ctx: click.Context, doc_id: int, term_id: int) -> None:
    """Remove a document↔term link. Idempotent: returns unlinked=false if not linked."""
    with connect() as conn:
        existed = TermRepository(conn).unlink(doc_id, term_id)
    if existed:
        emit(ctx, {"unlinked": True, "doc_id": str(doc_id), "term_id": str(term_id)})
    else:
        payload = {
            "unlinked": False,
            "doc_id": str(doc_id),
            "term_id": str(term_id),
            "reason": "not_linked",
        }
        emit(ctx, payload)


@document_group.command(name="list-terms")
@click.argument("doc_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_terms_for_doc(
    ctx: click.Context,
    doc_id: int,
    *,
    limit: int,
    offset: int,
    sort_field: str,
    order: str,
    json_fields: str | None,
) -> None:
    """List terms linked to a document."""
    with connect() as conn:
        if DocumentRepository(conn).get(doc_id) is None:
            raise NotFoundError(f"Document id={doc_id} not found", id=str(doc_id))
        rows = TermRepository(conn).terms_for_document(doc_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


def _list_for_document(
    ctx, doc_id, *, limit, offset, sort_field, order, json_fields, query
):
    """Shared body for the four reverse-listing commands."""
    with connect() as conn:
        if DocumentRepository(conn).get(doc_id) is None:
            raise NotFoundError(f"Document id={doc_id} not found", id=str(doc_id))
        rows = query(EntityDocumentRepository(conn), doc_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@document_group.command(name="list-nodes")
@click.argument("doc_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_nodes_for_doc(
    ctx, doc_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List nodes linked to a document."""
    _list_for_document(
        ctx,
        doc_id,
        limit=limit,
        offset=offset,
        sort_field=sort_field,
        order=order,
        json_fields=json_fields,
        query=lambda repo, did: repo.nodes_for_document(did),
    )


@document_group.command(name="list-containers")
@click.argument("doc_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_containers_for_doc(
    ctx, doc_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List containers linked to a document."""
    _list_for_document(
        ctx,
        doc_id,
        limit=limit,
        offset=offset,
        sort_field=sort_field,
        order=order,
        json_fields=json_fields,
        query=lambda repo, did: repo.containers_for_document(did),
    )


@document_group.command(name="list-flows")
@click.argument("doc_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_flows_for_doc(
    ctx, doc_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List flows linked to a document."""
    _list_for_document(
        ctx,
        doc_id,
        limit=limit,
        offset=offset,
        sort_field=sort_field,
        order=order,
        json_fields=json_fields,
        query=lambda repo, did: repo.flows_for_document(did),
    )


@document_group.command(name="list-items")
@click.argument("doc_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_items_for_doc(
    ctx, doc_id, *, limit, offset, sort_field, order, json_fields
) -> None:
    """List data items linked to a document."""
    _list_for_document(
        ctx,
        doc_id,
        limit=limit,
        offset=offset,
        sort_field=sort_field,
        order=order,
        json_fields=json_fields,
        query=lambda repo, did: repo.items_for_document(did),
    )
