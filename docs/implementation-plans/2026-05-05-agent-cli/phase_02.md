# Agent CLI — Phase 2: Document end-to-end (pattern proof)

**Goal:** Prove the per-entity module shape on the simplest entity. The Document module becomes the template every subsequent entity copies.

**Architecture:** A new `src/tm_cli/cli/documents.py` module exposes one Click subgroup with six verbs (list, get, create, update, delete, search) plus the `--stdin` bulk variant. Every command opens `connect()`, instantiates `DocumentRepository`, calls one method, and emits the result through `_output.emit`. The mutation commands accept either named flags or `--stdin` (mutually exclusive). The root group registers the document subgroup. Test infrastructure adds golden-file JSON snapshots for every verb, golden `--help` snapshots, and explicit error-path tests asserting both stderr JSON shape and exit code.

**Tech Stack:** Python 3.11+, Click 8.x, Pydantic v2, Syrupy (golden snapshots), pytest CliRunner.

**Scope:** Phase 2 of 8 from `docs/design-plans/2026-05-05-agent-cli.md`.

**Codebase verified:** 2026-05-05.
- `DocumentRepository` (`src/tm_cli/db/documents.py`) provides `create`, `get`, `update`, `delete`, `list`, `search`. `list` and `search` return `DocumentSummary` (no `content`). `get` returns full `Document`.
- `DocumentCreate` requires `last_updated` (source author's time) — caller MUST provide it. The CLI defaults it to `datetime.now(UTC)` when neither `--last-updated` nor `--stdin` provides one.
- `last_imported` is always set by the repo; never accepted as input.
- `Document` has no UNIQUE / CHECK constraints reachable from the CLI (no enum fields). Design's Phase 2 list mentions `agent-cli.AC5.3` (UNIQUE) and `agent-cli.AC5.5` (CHECK), but those need Term and Observation respectively (Phase 3). Design also lists `agent-cli.AC2.4` (Node `--type` filter), which is Phase 5. Those three are explicitly **deferred from Phase 2** to the phases that introduce the relevant entities. This phase covers what genuinely fits Document.

**External dependencies verified:** Click 8.x has no native `mutually_exclusive`; we enforce the `--stdin` vs named-flags constraint at command entry by raising `click.UsageError` (which `map_exception` translates to `UserError`, exit 1). Click's `CliRunner` (`mix_stderr=False`) is used in tests so stdout/stderr can be asserted independently.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### agent-cli.AC1: Standard CRUDL behaviors (universal across entities)
- **agent-cli.AC1.1 Success:** `list` returns all rows for an entity as NDJSON when stdout is piped (one JSON object per line).
- **agent-cli.AC1.2 Success:** `get` returns the full model for an existing id (including server-set fields like `last_imported`).
- **agent-cli.AC1.3 Success:** `create` with valid flags returns the new row, including the synthesized id (string-quoted) and any server-managed timestamps.
- **agent-cli.AC1.4 Success:** `update` with a valid patch returns the resulting row (full object, not `{"ok": true}`).
- **agent-cli.AC1.5 Failure:** `get` of a missing id exits 2 with `error.code = "not_found"`.
- **agent-cli.AC1.6 Failure:** `update` of a missing id exits 2 with `error.code = "not_found"`.
- **agent-cli.AC1.8 Edge:** `list --limit N` where `N` exceeds the row count returns all rows with no `_pagination` footer.

### agent-cli.AC2: Search
- **agent-cli.AC2.1 Success:** `search "X"` matches case-insensitively across all searchable text columns for the entity (per the repo's `search()` columns).
- **agent-cli.AC2.2 Success:** Multi-token text (`search "foo bar"`) AND-combines tokens; each token must match at least one searchable column.

### agent-cli.AC4: Output format
- **agent-cli.AC4.1 Success:** Piped `list` and `search` output is NDJSON (no surrounding `[`/`]`); each row is one parseable JSON object.
- **agent-cli.AC4.2 Success:** Piped `get` / `create` / `update` output is a single compact JSON object on stdout.
- **agent-cli.AC4.3 Success:** When stdout is a TTY, all JSON output is indented with `indent=2`.
- **agent-cli.AC4.4 Success:** Integer id fields serialize as JSON strings (e.g., `"id": "5"`, not `5`).
- **agent-cli.AC4.5 Success:** Pagination footer `{"_pagination": {"next_offset": N, "returned": N}}` is the final NDJSON line when `len(rows) == limit`.

### agent-cli.AC5: Errors and exit codes
- **agent-cli.AC5.1 Success:** `pydantic.ValidationError` from a repo call → exit 1, `error.code = "user_error"`.
- **agent-cli.AC5.2 Success:** Repo returning `None` from `get`/`update` → exit 2, `error.code = "not_found"`.
- **agent-cli.AC5.7 Success:** Error JSON is written to stderr; stdout is either empty or remains a parseable JSON document.

### agent-cli.AC6: Idempotency and --dry-run
- **agent-cli.AC6.2 Success:** `delete <existing-id>` returns `{"deleted": true, "id": "..."}` and exits 0.
- **agent-cli.AC6.3 Success:** `delete <missing-id>` returns `{"deleted": false, "id": "...", "reason": "not_found"}` and exits 0.
- **agent-cli.AC6.4 Success:** `create --dry-run` returns `{"dry_run": true, "would_create": {...}}` and writes nothing to the DB.
- **agent-cli.AC6.5 Success:** `update --dry-run` returns `{"dry_run": true, "would_update": {...}}` and modifies nothing.

### agent-cli.AC7: Stdin bulk
- **agent-cli.AC7.1 Success:** `tm document create --stdin` with a single JSON object on stdin creates one row and returns one object.
- **agent-cli.AC7.2 Success:** `tm document create --stdin` with a JSON array creates N rows in input order and returns an array of N objects in the same order, all in a single connection.
- **agent-cli.AC7.3 Failure:** A single invalid item in an input array rolls back the whole batch; the error payload includes the failing item's array index.
- **agent-cli.AC7.4 Failure:** `--stdin` combined with any `--field` flag is rejected at the Click parser (mutually exclusive).

**Deferred (per codebase verification, not testable on Document):**
- `agent-cli.AC2.4` — Node `--type` filter; lands in Phase 5.
- `agent-cli.AC5.3` — UNIQUE violation on Term; lands in Phase 3.
- `agent-cli.AC5.5` — CHECK violation on Observation enum; lands in Phase 3.

---

## Required reading for the executor

- `/Users/josh/code/tm-cli/src/tm_cli/db/CLAUDE.md` (db domain contracts).
- `/Users/josh/code/tm-cli/src/tm_cli/db/models.py` (Document/DocumentCreate/DocumentUpdate/DocumentSummary).
- `/Users/josh/code/tm-cli/src/tm_cli/db/documents.py` (DocumentRepository — exact method signatures).
- Phase 1 deliverables (`src/tm_cli/cli/_errors.py`, `_output.py`, `_options.py`, `_stdin.py`, `tests/fixtures/seed.py`, `tests/fixtures/syrupy_ext.py`).

The executor should activate these skills if relevant in their session:
- `house-style:writing-good-tests`
- `ed3d-plan-and-execute:test-driven-development`
- `ed3d-plan-and-execute:verification-before-completion`

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Sort and projection helpers in `_options.py` and `_output.py`

**Type:** Functionality (with tests).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/_options.py` (add `apply_sort` and `parse_json_fields`).
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/_output.py` (add `project_fields`).
- Create: `/Users/josh/code/tm-cli/tests/cli/test_options_helpers.py`.

**Implementation:**

Repos do not accept sort/order kwargs. The CLI sorts the returned page client-side by calling `apply_sort(rows, sort_field=..., order=...)`. This is a v1 limitation (page-local sort, not query-level), acceptable because pagination defaults to `--sort id` which already matches DB order via the integer PK.

`--json FIELDS` is a comma-separated list. `project_fields(payload, fields)` walks a dict (or list of dicts) and returns a new structure with only the requested keys (silently dropping keys that don't exist).

Add to `_options.py`:

```python
from collections.abc import Iterable
from typing import Any


def apply_sort(rows: Iterable[Any], *, sort_field: str, order: str) -> list[Any]:
    """Sort ``rows`` by ``sort_field`` (Pydantic model attribute) in given ``order``.

    Rows whose attribute is missing are placed at the end (stable).
    """

    rows_list = list(rows)
    if not sort_field:
        return rows_list
    reverse = order == "desc"
    sentinel = object()

    def key(row: Any) -> tuple[int, Any]:
        value = getattr(row, sort_field, sentinel)
        if value is sentinel:
            return (1, 0)
        return (0, value)

    return sorted(rows_list, key=key, reverse=reverse)


def parse_json_fields(value: str | None) -> list[str] | None:
    """Parse a ``--json FIELDS`` value into a list, or ``None`` if not specified."""
    if value is None:
        return None
    return [f.strip() for f in value.split(",") if f.strip()]
```

Add to `_output.py`:

```python
from typing import Any


def project_fields(payload: Any, fields: list[str] | None) -> Any:
    """Return ``payload`` projected to only the named ``fields``.

    Walks dicts and lists. Missing keys are silently dropped.
    """

    if fields is None:
        return payload
    if isinstance(payload, dict):
        return {k: payload[k] for k in fields if k in payload}
    if isinstance(payload, list):
        return [project_fields(item, fields) for item in payload]
    return payload
```

`emit` does not auto-apply projection — the caller is responsible for passing already-projected data. Document commands call `project_fields` before `emit`.

Tests in `tests/cli/test_options_helpers.py`:

```python
from types import SimpleNamespace

from tm_cli.cli._options import apply_sort, parse_json_fields
from tm_cli.cli._output import project_fields


def test_apply_sort_default_id_ascending() -> None:
    rows = [SimpleNamespace(id=3), SimpleNamespace(id=1), SimpleNamespace(id=2)]
    assert [r.id for r in apply_sort(rows, sort_field="id", order="asc")] == [1, 2, 3]


def test_apply_sort_descending() -> None:
    rows = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    assert [r.id for r in apply_sort(rows, sort_field="id", order="desc")] == [2, 1]


def test_apply_sort_missing_field_goes_last() -> None:
    rows = [SimpleNamespace(name="b"), SimpleNamespace(other="x"), SimpleNamespace(name="a")]
    sorted_rows = apply_sort(rows, sort_field="name", order="asc")
    assert [getattr(r, "name", None) for r in sorted_rows] == ["a", "b", None]


def test_parse_json_fields_none() -> None:
    assert parse_json_fields(None) is None


def test_parse_json_fields_strips_and_splits() -> None:
    assert parse_json_fields("id, name , author") == ["id", "name", "author"]


def test_project_fields_dict() -> None:
    assert project_fields({"a": 1, "b": 2, "c": 3}, ["a", "c"]) == {"a": 1, "c": 3}


def test_project_fields_list() -> None:
    rows = [{"a": 1, "b": 2}, {"a": 10, "b": 20}]
    assert project_fields(rows, ["a"]) == [{"a": 1}, {"a": 10}]


def test_project_fields_missing_silently_dropped() -> None:
    assert project_fields({"a": 1}, ["a", "missing"]) == {"a": 1}
```

**Verification:**

Run: `uv run pytest tests/cli/test_options_helpers.py -v`
Expected: 8 tests pass.

**Commit:** `feat(cli): add apply_sort, parse_json_fields, project_fields helpers`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Stdin mutex helper

**Type:** Infrastructure (small functionality with one test).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/_stdin.py` (add `enforce_stdin_exclusive`).
- Modify: `/Users/josh/code/tm-cli/tests/cli/test_stdin.py` (add tests for the new helper).

**Implementation:**

Add to `_stdin.py`:

```python
import click


def enforce_stdin_exclusive(stdin: bool, named_values: dict[str, object]) -> None:
    """Raise ``click.UsageError`` when ``--stdin`` is combined with any named-flag value.

    ``named_values`` maps each named-flag's destination name to its value as Click
    parsed it. A flag is "set" if its value is not ``None`` and not the literal
    Click default for that flag (the caller passes only the flags that are not at
    their default — see ``documents.py`` for the convention).
    """

    if not stdin:
        return
    set_flags = [name for name, value in named_values.items() if value is not None]
    if set_flags:
        names = ", ".join(f"--{name.replace('_', '-')}" for name in set_flags)
        raise click.UsageError(f"--stdin cannot be combined with named flags: {names}")
```

Tests:

```python
import pytest
import click

from tm_cli.cli._stdin import enforce_stdin_exclusive


def test_stdin_false_is_noop() -> None:
    enforce_stdin_exclusive(False, {"title": "x"})


def test_stdin_true_with_no_named_flags_passes() -> None:
    enforce_stdin_exclusive(True, {"title": None, "author": None})


def test_stdin_true_with_named_flag_raises() -> None:
    with pytest.raises(click.UsageError, match="--title"):
        enforce_stdin_exclusive(True, {"title": "x", "author": None})


def test_message_lists_all_offending_flags() -> None:
    with pytest.raises(click.UsageError) as exc_info:
        enforce_stdin_exclusive(True, {"title": "x", "author": "y"})
    msg = str(exc_info.value)
    assert "--title" in msg and "--author" in msg
```

**Verification:**

Run: `uv run pytest tests/cli/test_stdin.py -v`
Expected: 10 tests pass (6 existing + 4 new).

**Commit:** `feat(cli): add enforce_stdin_exclusive helper for --stdin vs named flags`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `tm document` command surface

**Type:** Functionality (tests in Subcomponent B).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/documents.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/main.py` (register the document subgroup).

**Implementation:**

Create `documents.py` with one Click subgroup `@click.group(name="document")` and six commands. Use `connect()` for every command. Convert repository return values into Pydantic models, project fields if `--json FIELDS` was given, and emit through `_output.emit`.

Critical contracts:
- `create` accepts named flags `--last-updated`, `--title`, `--author`, `--content` OR `--stdin`. `--last-updated` defaults to `datetime.now(UTC)` when not provided and `--stdin` was not used. `--if-not-exists` is accepted but documented as no-op for Document (no natural key).
- `update` accepts `<id>` arg, then named patch flags or `--stdin`. Patch fields default to `None` so `DocumentUpdate(...)` only carries explicit changes.
- `delete` accepts `<id>` and returns the documented envelope. Always exits 0.
- `--dry-run` on create/update/delete short-circuits before any DB write.
- `search "<text>"` runs `repo.search(text=<text>, limit=..., offset=...)`. Empty string is rejected at parse (via `click.UsageError`) since the design says `search` requires `<text>` (use `list` for unfiltered queries).
- All list/search output goes through `emit(..., list_mode=True, limit=..., offset=...)` so the pagination footer fires when the page is full.
- Repo's `list()` and `search()` already return `DocumentSummary` for Document (no `content` field on list) — no extra work needed to enforce the design's "default-lean list output".

Full `documents.py`:

```python
"""tm document — Document CRUDL + search subgroup."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import click
from pydantic import ValidationError

from tm_cli.cli._errors import NotFoundError, map_exception
from tm_cli.cli._options import apply_sort, json_fields_option, list_options, parse_json_fields
from tm_cli.cli._output import emit, project_fields
from tm_cli.cli._stdin import enforce_stdin_exclusive, read_json_stdin
from tm_cli.db import (
    DocumentCreate,
    DocumentRepository,
    DocumentUpdate,
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
    payload = project_fields(row.model_dump(mode="json"), parse_json_fields(json_fields))
    emit(ctx, payload)


@document_group.command(name="create")
@click.option("--last-updated", "last_updated", type=click.DateTime(), default=None,
              help="ISO-8601 datetime of source author's last update. Defaults to now.")
@click.option("--title", default=None, help="Document title.")
@click.option("--author", default=None, help="Document author.")
@click.option("--content", default=None, help="Full document body.")
@click.option("--stdin", "use_stdin", is_flag=True, default=False,
              help="Read a single JSON object or array of objects from stdin instead of named flags.")
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False,
              help="No-op for Document (no natural key); kept for command-shape consistency.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False,
              help="Validate inputs, do not write.")
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

    enforce_stdin_exclusive(
        use_stdin,
        {"last_updated": last_updated, "title": title, "author": author, "content": content},
    )

    if use_stdin:
        body = read_json_stdin()
    else:
        if title is None or author is None or content is None:
            raise click.UsageError("--title, --author, and --content are required (or use --stdin)")
        body = {
            "last_updated": (last_updated or datetime.now(UTC)).isoformat(),
            "title": title,
            "author": author,
            "content": content,
        }

    if isinstance(body, list):
        models = _validate_create_batch(body)
        if dry_run:
            emit(ctx, {"dry_run": True, "would_create": [m.model_dump(mode="json") for m in models]})
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
@click.option("--stdin", "use_stdin", is_flag=True, default=False,
              help="Read a JSON object from stdin with the patch fields.")
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

    enforce_stdin_exclusive(
        use_stdin,
        {"last_updated": last_updated, "title": title, "author": author, "content": content},
    )

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
        emit(ctx, {"dry_run": True, "would_update": {"id": str(doc_id), "patch": patch.model_dump(mode="json", exclude_none=True)}})
        return

    with connect() as conn:
        updated = DocumentRepository(conn).update(doc_id, patch)
    if updated is None:
        raise NotFoundError(f"Document id={doc_id} not found", id=str(doc_id))
    emit(ctx, updated.model_dump(mode="json"))


@document_group.command(name="delete")
@click.argument("doc_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False, help="Required to confirm deletion (matches design contract).")
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_document(ctx: click.Context, doc_id: int, *, yes: bool, dry_run: bool) -> None:
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
        raise click.UsageError("search requires a non-empty TEXT argument; use 'tm document list' for unfiltered output")
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = DocumentRepository(conn).search(text=text, limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
```

`--yes` on delete is decorative for v1 (we always honor `delete <id>`). It's kept in the surface so downstream consumers can introspect the flag exists and so we don't have to add it later in a breaking way. Tests do not exercise the flag's presence/absence as a confirmation gate.

**Note on the `--stdin` mutex check:** the helper inspects the dict of named values; for create's `last_updated`, an explicitly passed value triggers exclusion correctly because Click defaults it to `None`. The default-to-now behavior is applied AFTER the mutex check, so `--stdin` plus no other flags works.

Update `src/tm_cli/main.py` (add the registration after the `cli` group definition):

```python
from tm_cli.cli.documents import document_group

cli.add_command(document_group)
```

**Verification:**

Run: `uv run tm document --help`
Expected: prints help text listing six commands (`list`, `get`, `create`, `update`, `delete`, `search`).

Run: `uv run tm document list 2>/dev/null`
Expected: emits an empty NDJSON stream (no rows in a fresh in-memory DB; assuming `TM_DB_PATH` points somewhere writable). Exit code 0.

(Behavioral verification with assertions happens in tasks 4–6.)

**Commit:** `feat(cli): add tm document command surface (list/get/create/update/delete/search)`
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-6) -->

<!-- START_TASK_4 -->
### Task 4: Golden help-text snapshots

**Type:** Functionality (tests).

**Verifies:** none directly — establishes the help-text contract (drift detection).

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_documents_help.py`.

**Implementation:**

Snapshot every leaf command's `--help` output. The masking serializer is unnecessary here (help text has no IDs/datetimes), so the test asserts against Syrupy's plain `snapshot` directly via the unmasked `SnapshotAssertion`.

```python
"""Golden snapshots for tm document --help text."""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from tm_cli.main import cli


@pytest.fixture
def plain_snapshot(snapshot_factory) -> SnapshotAssertion:
    """Bypass the masking extension — help text has no volatile fields to mask."""
    from syrupy.extensions.amber import AmberSnapshotExtension
    return snapshot_factory(extension_class=AmberSnapshotExtension)


@pytest.mark.parametrize(
    "args",
    [
        ("document", "--help"),
        ("document", "list", "--help"),
        ("document", "get", "--help"),
        ("document", "create", "--help"),
        ("document", "update", "--help"),
        ("document", "delete", "--help"),
        ("document", "search", "--help"),
    ],
    ids=["group", "list", "get", "create", "update", "delete", "search"],
)
def test_help_snapshots(args: tuple[str, ...], plain_snapshot: SnapshotAssertion) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0
    assert result.output == plain_snapshot
```

If `snapshot_factory` is not the correct fixture name for the installed Syrupy version, replace with whatever the version exposes (Syrupy 4.x: `snapshot.use_extension(...)`). The cleanest approach across versions is:

```python
@pytest.fixture
def plain_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    from syrupy.extensions.amber import AmberSnapshotExtension
    return snapshot.use_extension(AmberSnapshotExtension)
```

Use the `use_extension(...)` form (verified working with Syrupy ≥4.6).

**Verification:**

Run: `uv run pytest tests/cli/test_documents_help.py --snapshot-update`
Expected: writes `tests/cli/__snapshots__/test_documents_help.ambr` with seven snapshots; manually inspect the snapshots to confirm flag names match the design (no `--diagram-id` shown for any document command, since Document is not a DFD entity).

Run: `uv run pytest tests/cli/test_documents_help.py`
Expected: passes against the just-blessed snapshots.

**Commit:** `test(cli): golden snapshots for tm document --help text`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Golden JSON output snapshots for every verb

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.1`, `agent-cli.AC1.2`, `agent-cli.AC1.3`, `agent-cli.AC1.4`, `agent-cli.AC1.8`, `agent-cli.AC2.1`, `agent-cli.AC2.2`, `agent-cli.AC4.1`, `agent-cli.AC4.2`, `agent-cli.AC4.3`, `agent-cli.AC4.4`, `agent-cli.AC4.5`, `agent-cli.AC6.2`, `agent-cli.AC6.3`, `agent-cli.AC6.4`, `agent-cli.AC6.5`, `agent-cli.AC7.1`, `agent-cli.AC7.2`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_documents.py`.

**Implementation:**

Use `CliRunner(mix_stderr=False)` so stdout and stderr can be asserted independently. Use the `db_with_seed` fixture from Phase 1 for a deterministic baseline, and the masking `snapshot` fixture (which already replaces ids and ISO datetimes with `<INT>` and `<DATETIME>`).

For TTY behavior tests (AC4.3), invoke the CLI with `runner.invoke(cli, [...], color=False)` — Click's CliRunner pipes by default. To exercise the TTY-indented output, override `_default_json_mode` via `monkeypatch` so `--no-json` renders, OR pass `--no-json` explicitly. Use `--no-json` for clarity.

**Important: where `--no-json` actually changes output.** `emit()` in list mode (NDJSON) never indents — newline-delimited JSON with multi-line objects is malformed. So `--no-json` only affects single-object output paths (`get`, `create`, `update`, `delete`, the dry-run/error envelopes). Any indent assertion goes on `tm document get <id> --no-json`, not on `tm document list --no-json`. The test table below splits the assertions accordingly.

Key tests to write (one per AC case unless stated):

| Test | AC | Setup | Action | Assertion |
|---|---|---|---|---|
| `test_list_returns_ndjson_when_piped` | AC1.1, AC4.1 | seed | `tm document list` | `result.exit_code == 0`; each line of stdout parses as JSON; total lines == seeded doc count; stdout matches `snapshot`. |
| `test_list_no_pagination_footer_when_under_limit` | AC1.8, AC4.5 | seed (2 docs) | `tm document list --limit 50` | stdout has no `_pagination` line. |
| `test_list_emits_pagination_footer_when_full_page` | AC4.5 | seed (2 docs) | `tm document list --limit 2` | last line is `{"_pagination": {"next_offset": 2, "returned": 2}}`. |
| `test_list_no_json_remains_ndjson` | AC4.3 | seed | `tm document list --no-json` | stdout is still NDJSON (one JSON object per line, no indentation) — `--no-json` does NOT pretty-print list output (NDJSON-with-indent is malformed). |
| `test_get_returns_full_object_with_content` | AC1.2, AC4.2 | seed | `tm document get <doc_id>` | stdout is single compact JSON object including `content`, `last_imported`; matches `snapshot`. |
| `test_get_no_json_indents_two_spaces` | AC4.3 | seed | `tm document get <id> --no-json` | stdout begins with `{\n  "id":` (indent=2). |
| `test_id_fields_are_strings` | AC4.4 | seed | `tm document get <id>` | parsed JSON's `id` is a `str`. |
| `test_create_with_named_flags_returns_new_row` | AC1.3 | empty DB (use `db_path` not `db_with_seed`) | `tm document create --title T --author A --content C` | stdout is single JSON; `id` is a string; `last_imported` and `last_updated` are ISO-8601 strings; matches `snapshot`. |
| `test_create_dry_run_does_not_write` | AC6.4 | empty | `tm document create --title T --author A --content C --dry-run` | stdout is `{"dry_run": true, "would_create": {...}}`; subsequent `tm document list` is empty. |
| `test_update_returns_full_row` | AC1.4 | seed | `tm document update <id> --title NEW` | stdout is full Document JSON; `title == "NEW"`; matches `snapshot`. |
| `test_update_dry_run_does_not_modify` | AC6.5 | seed | `tm document update <id> --title NEW --dry-run` | stdout is `{"dry_run": true, "would_update": {...}}`; subsequent `get` shows the original title. |
| `test_delete_existing_returns_deleted_true` | AC6.2 | seed | `tm document delete <id>` | stdout is `{"deleted": true, "id": "<id>"}`. |
| `test_delete_missing_returns_deleted_false` | AC6.3 | seed | `tm document delete 9999` | stdout is `{"deleted": false, "id": "9999", "reason": "not_found"}`; exit 0. |
| `test_search_case_insensitive_single_token` | AC2.1 | seed (titles "Seed Doc 1", "Seed Doc 2") | `tm document search "seed"` | NDJSON contains both rows. |
| `test_search_multi_token_and` | AC2.2 | seed | `tm document search "seed 1"` | NDJSON contains only the row whose title or content contains both tokens. |
| `test_stdin_single_object_creates_one_row` | AC7.1 | empty | `tm document create --stdin` with stdin = `{"last_updated":"...","title":"x","author":"a","content":"c"}` | stdout is single Document JSON. |
| `test_stdin_array_creates_n_rows_in_order` | AC7.2 | empty | `tm document create --stdin` with stdin = `[{...}, {...}]` | stdout is JSON array of 2 objects, ids in ascending order. |
| `test_json_fields_projection_on_get` | AC4.6 (extension to design) | seed | `tm document get <id> --json id,title` | parsed JSON has only those keys. |
| `test_json_fields_projection_on_list` | AC4.6 (extension) | seed | `tm document list --json id,title` | each NDJSON row has only those keys. |

Use the `db_with_seed` fixture for cases that need data, and a fresh `db_path` for empty-DB cases.

A representative test:

```python
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_ndjson_when_piped(db_with_seed, snapshot) -> None:
    db_path, seed_ids = db_with_seed
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, ["document", "list"])
    assert result.exit_code == 0, result.stderr
    # NDJSON: every non-empty line is a parseable object.
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == len(seed_ids.document_ids)
    for line in lines:
        json.loads(line)
    assert result.stdout == snapshot
```

For the stdin test:

```python
def test_stdin_single_object_creates_one_row(db_path: Path, snapshot) -> None:
    runner = CliRunner(mix_stderr=False)
    body = json.dumps({
        "last_updated": "2026-01-02T03:04:05+00:00",
        "title": "ViaStdin",
        "author": "agent",
        "content": "...body...",
    })
    result = runner.invoke(cli, ["document", "create", "--stdin"], input=body)
    assert result.exit_code == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["title"] == "ViaStdin"
    assert isinstance(parsed["id"], str)
    assert result.stdout == snapshot
```

After all tests are written, bless snapshots:

Run: `uv run pytest tests/cli/test_documents.py --snapshot-update`

Then run without update:

Run: `uv run pytest tests/cli/test_documents.py -v`
Expected: every test passes.

**Verification:**

Run: `uv run pytest tests/cli/test_documents.py -v`
Expected: every listed test passes.

**Commit:** `test(cli): golden JSON tests for tm document verbs`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Error-path tests

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.5`, `agent-cli.AC1.6`, `agent-cli.AC5.1`, `agent-cli.AC5.2`, `agent-cli.AC5.7`, `agent-cli.AC7.3`, `agent-cli.AC7.4`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_documents_errors.py`.

**Implementation:**

Each test asserts both stdout and stderr shape, plus exit code. The masking `snapshot` is used for stderr JSON to keep error messages stable across runs.

| Test | AC | Action | Assertion |
|---|---|---|---|
| `test_get_missing_id_exits_2_not_found` | AC1.5, AC5.2, AC5.7 | `tm document get 9999` | exit 2; stdout empty; stderr is JSON with `error.code == "not_found"`. |
| `test_update_missing_id_exits_2_not_found` | AC1.6, AC5.2 | `tm document update 9999 --title X` | exit 2; stderr `error.code == "not_found"`. |
| `test_create_missing_required_field_exits_1_user_error` | AC5.1 | `tm document create --title T` (missing `--author`/`--content`) | exit 1; stderr `error.code == "user_error"`. |
| `test_stdin_invalid_item_in_array_rolls_back_batch` | AC7.3 | `tm document create --stdin` with stdin = a 2-item array where item[1] is missing `title` | exit 1; stderr `error.code == "user_error"`; stderr `error.input.index == 1`; subsequent `tm document list` is empty (rollback proven). |
| `test_stdin_combined_with_named_flag_exits_1_user_error` | AC7.4 | `tm document create --stdin --title X` (with empty stdin so no read happens) | exit 1; stderr `error.code == "user_error"`; message mentions `--stdin`. |
| `test_search_with_empty_text_exits_1` | AC5.1 | `tm document search ""` | exit 1; stderr `error.code == "user_error"`. |

Representative test:

```python
import json

import pytest
from click.testing import CliRunner

from tm_cli.main import cli


def test_get_missing_id_exits_2_not_found(db_with_seed, snapshot) -> None:
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, ["document", "get", "9999"])
    assert result.exit_code == 2
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"
    assert result.stderr == snapshot
```

For the rollback test:

```python
def test_stdin_invalid_item_in_array_rolls_back_batch(db_path, snapshot) -> None:
    runner = CliRunner(mix_stderr=False)
    body = json.dumps([
        {"last_updated": "2026-01-01T00:00:00+00:00", "title": "ok", "author": "a", "content": "c"},
        {"last_updated": "2026-01-01T00:00:00+00:00", "author": "a", "content": "c"},  # missing title
    ])
    result = runner.invoke(cli, ["document", "create", "--stdin"], input=body)
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    assert payload["error"]["input"]["index"] == 1
    # Rollback proof: an immediate list returns nothing.
    list_result = runner.invoke(cli, ["document", "list"])
    assert list_result.stdout.strip() == ""
```

Bless snapshots: `uv run pytest tests/cli/test_documents_errors.py --snapshot-update`.

**Verification:**

Run: `uv run pytest tests/cli/test_documents_errors.py -v`
Expected: every test passes.

**Commit:** `test(cli): error-path tests for tm document (not_found, validation, stdin)`
<!-- END_TASK_6 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_7 -->
### Task 7: Final operational verification

**Type:** Infrastructure (verification only).

**Files:** none.

**Verification:**

Run: `make lint`
Expected: clean.

Run: `make test`
Expected: every test passes — Phase 1 tests + new Phase 2 tests.

Run: `uv run tm document --help` and `uv run tm document create --help` (and similar for every verb)
Expected: human-readable help; flag names match the public design contract; no `--diagram-id` appears anywhere.

Run end-to-end smoke (against the configured `TM_DB_PATH`):

```bash
uv run tm document create --title smoke --author tester --content body | tee /tmp/created.json
ID=$(uv run python -c 'import json,sys; print(json.load(open("/tmp/created.json"))["id"])')
uv run tm document get "$ID"
uv run tm document update "$ID" --title smoke-2 | tee /tmp/updated.json
uv run tm document delete "$ID"
```

Expected: each command produces parseable JSON; exit code 0 for all; the final delete returns `{"deleted": true, "id": "<id>"}`.

If any step fails, fix before declaring the phase done.

**Commit:** none. Use `chore(cli): phase 2 verification fixes` for fix-ups if needed.
<!-- END_TASK_7 -->

---

## Phase 2 — Done When

- `tests/cli/test_options_helpers.py`, `test_stdin.py` (extended), `test_documents_help.py`, `test_documents.py`, `test_documents_errors.py` are green.
- All ACs in the coverage section above have at least one passing test.
- `make lint` passes.
- `tm document <verb> --help` matches the blessed snapshots.
- The end-to-end smoke sequence in Task 7 produces valid JSON for every verb.
- The Document module is the template every subsequent entity module copies (file structure, decorator stack, error-path layout).
