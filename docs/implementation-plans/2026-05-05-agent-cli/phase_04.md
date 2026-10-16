# Agent CLI — Phase 4: Diagram + DataItem + default-diagram resolver

**Goal:** Foundational DFD support. Add diagram management plus the data-item entity, and ship the `resolve_default_diagram_id` helper so subsequent DFD phases (Node, Container, Flow) can call into it.

**Architecture:** `tm diagram` is a vanilla entity subgroup — diagrams own themselves and never inherit the hidden `--diagram-id` flag. `tm data-item` is the first DFD entity in the build, so it introduces the default-diagram behavior: on **create** without `--diagram-id`, the resolver looks up a diagram named `default` (lowest id wins on tie) and, if none exists, creates one with `DiagramCreate(name="default")` and uses its id. On **list** / **search** without `--diagram-id`, the resolver returns `None` and the command emits an empty NDJSON list — read paths never implicitly create a diagram. The `--diagram-id` option is registered on every DFD command via the Phase 1 decorator with `hidden=True`, so it doesn't appear in `--help` but is fully functional and will be surfaced in `tm commands --json` in Phase 8. The resolver is exercised by per-command tests and a dedicated unit test that covers all four branches.

**Tech Stack:** Same as previous phases.

**Scope:** Phase 4 of 8 from `docs/design-plans/2026-05-05-agent-cli.md`.

**Codebase verified:** 2026-05-05.
- `DiagramRepository` exposes the standard `create`/`get`/`update`/`delete`/`list`/`search`. `Diagram` has fields `id`, `name`, `description`, `author`, `created`. `DiagramCreate` has all-optional `name`/`description`/`author`. `Diagram.search()` matches against `name`/`description`/`author` (NULL-safe via `IFNULL(col, '')`).
- `DataItemRepository.list(diagram_id, *, limit, offset)` is unfiltered. `DataItemRepository.search(diagram_id, text=None, *, classification, parent_node_id, limit, offset)` accepts both filters. The CLI's `tm data-item list` routes through `repo.search(text=None, **filters)` to support `--classification` and `--parent-node-id` on `list` (per design).
- `DataItemUpdate` accepts `parent_node_id=None` to clear the column (the DFD repos drop the `is not None` guard for nullable fields per the db CLAUDE.md). The CLI's update command must pass `parent_node_id=None` explicitly when the user clears it; an empty string from the command line is not the same as omission.
- `DiagramCreate(name="default")` works (name is optional, defaults to `None`; passing `"default"` is fine).

**External dependencies verified:** none new.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### agent-cli.AC1: Standard CRUDL behaviors (universal across entities)
- **agent-cli.AC1.1 Success** [Diagram, DataItem]
- **agent-cli.AC1.2 Success** [Diagram, DataItem]
- **agent-cli.AC1.3 Success** [Diagram, DataItem]
- **agent-cli.AC1.4 Success** [Diagram, DataItem]
- **agent-cli.AC1.5 Failure** [Diagram, DataItem]
- **agent-cli.AC1.6 Failure** [Diagram, DataItem]
- **agent-cli.AC1.8 Edge** [Diagram, DataItem]

### agent-cli.AC2: Search
- **agent-cli.AC2.5 Success:** `tm data-item search` with `--classification` and `--parent-node-id` filters returns the AND of those constraints.

### agent-cli.AC9: Default-diagram fallback
- **agent-cli.AC9.1 Success:** A DFD `create` command without `--diagram-id` creates a diagram named "default" when none exists, then creates the entity in it; the response includes the resolved `diagram_id`.
- **agent-cli.AC9.2 Success:** DFD `list` / `search` without `--diagram-id` and no default diagram in the DB returns empty NDJSON (no implicit creation on read).
- **agent-cli.AC9.3 Success:** DFD `list` / `search` without `--diagram-id` uses the default diagram's id when one exists.
- **agent-cli.AC9.4 Success:** `--diagram-id` does not appear in any DFD command's `--help` output.
- **agent-cli.AC9.5 Success:** *(deferred to Phase 8 where `tm commands --json` is implemented; this phase verifies the option is registered with `hidden=True` via inspection of `Command.params`.)*

### agent-cli.AC11: Entity-specific invariants
- **agent-cli.AC11.4 Success:** `tm data-item update <id> --parent-node-id ""` (or the equivalent stdin-cleared form) sets the row's `parent_node_id` to NULL.

**Deferred (per codebase verification, not testable in this phase):**
- `agent-cli.AC2.6` — Flow search columns; lands in Phase 7 (DataFlow).
- `agent-cli.AC9.5` — full machine-readable inspection; verified structurally here, exercised end-to-end in Phase 8.

---

## Required reading for the executor

- `/Users/josh/code/tm-cli/src/tm_cli/db/CLAUDE.md` (DFD subdomain section).
- `/Users/josh/code/tm-cli/src/tm_cli/db/diagrams.py` (DiagramRepository, `_mint_entity_id` helper).
- `/Users/josh/code/tm-cli/src/tm_cli/db/dfd_items.py` (DataItemRepository).
- `/Users/josh/code/tm-cli/src/tm_cli/db/dfd_models.py` (Diagram*, DataItem*, Classification literal).
- Phase 1 deliverable: `src/tm_cli/cli/_options.py` (where `resolve_default_diagram_id` lands).
- Phase 2/3 deliverables (Document, Term, Observation modules) as templates.

The executor should activate these skills if relevant in their session:
- `house-style:writing-good-tests`
- `ed3d-plan-and-execute:test-driven-development`
- `ed3d-plan-and-execute:verification-before-completion`

---

<!-- START_TASK_1 -->
### Task 1: `resolve_default_diagram_id` resolver

**Type:** Functionality (with full unit-test coverage in Task 2).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/_options.py` (add the resolver function).

**Implementation:**

The resolver takes an open SQLite connection and the user's optional explicit id. It returns:

- The explicit id if provided (after existence check; raises `NotFoundError` if absent).
- The id of the diagram named `default` if one exists (lowest id on tie).
- A newly created diagram's id if `create_if_missing=True` and none exists.
- `None` if `create_if_missing=False` and none exists (caller emits empty list on read paths).

Add to `src/tm_cli/cli/_options.py`:

```python
import sqlite3

from tm_cli.cli._errors import NotFoundError


def resolve_default_diagram_id(
    conn: "sqlite3.Connection",
    explicit_id: int | None,
    *,
    create_if_missing: bool,
) -> int | None:
    """Resolve the ``--diagram-id`` for a DFD command.

    - If ``explicit_id`` is set, verify the diagram exists; raise NotFoundError if not.
    - Otherwise scan for a diagram named ``default`` (lowest id wins on tie).
    - If none found:
        - ``create_if_missing=True``: create one with ``DiagramCreate(name="default")``.
        - ``create_if_missing=False``: return ``None`` (caller emits empty list).
    """
    # Imports are local to avoid a circular import at module load time
    # (``_options`` is imported by every entity module; the db package is heavy).
    from tm_cli.db import DiagramCreate, DiagramRepository

    repo = DiagramRepository(conn)

    if explicit_id is not None:
        existing = repo.get(explicit_id)
        if existing is None:
            raise NotFoundError(f"Diagram id={explicit_id} not found", id=str(explicit_id))
        return existing.id

    # Scan all diagrams for the lowest-id one named "default".
    # ``list()`` returns rows ordered by id ascending, so the first match wins.
    for diagram in repo.list():
        if diagram.name == "default":
            return diagram.id

    if not create_if_missing:
        return None

    new_diagram = repo.create(DiagramCreate(name="default"))
    return new_diagram.id
```

**Verification:**

Run: `uv run python -c "from tm_cli.cli._options import resolve_default_diagram_id; print('ok')"`
Expected: prints `ok`.

(Behavioral verification in Task 2.)

**Commit:** `feat(cli): add resolve_default_diagram_id resolver`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit tests for `resolve_default_diagram_id`

**Type:** Functionality (tests).

**Verifies:** structural coverage for AC9.1–AC9.3 via the resolver primitive (commands exercise it end-to-end in Tasks 4–5).

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_resolve_default_diagram_id.py`.

**Implementation:**

Tests:

| Test | Scenario | Assertion |
|---|---|---|
| `test_explicit_id_returns_id_when_exists` | create a diagram with id=K; call with `explicit_id=K, create_if_missing=False` | returns K |
| `test_explicit_id_raises_not_found_when_missing` | empty diagrams; call with `explicit_id=999, create_if_missing=False` | raises `NotFoundError` |
| `test_no_explicit_no_default_no_create_returns_none` | empty diagrams; call with `explicit_id=None, create_if_missing=False` | returns `None` |
| `test_no_explicit_no_default_with_create_creates_and_returns_id` | empty; call with `explicit_id=None, create_if_missing=True` | a new diagram named "default" exists; the call returns its id |
| `test_no_explicit_default_exists_returns_default_id` | create one diagram with name="default"; call with `explicit_id=None` (either create flag) | returns the default's id |
| `test_two_default_diagrams_lowest_id_wins` | create two diagrams both named "default" (back-to-back); call → returns the smaller id |
| `test_no_explicit_only_other_named_diagrams_no_create` | create one diagram named "non-default"; call with `create_if_missing=False` | returns `None` |
| `test_no_explicit_only_other_named_diagrams_with_create` | create one diagram named "non-default"; call with `create_if_missing=True` | a NEW diagram named "default" is created and its id is returned (not the "non-default" one) |

Use the `db_path` fixture (gives a fresh DB), open a connection with `connect(db_path)`, populate test data via `DiagramRepository(conn).create(...)`, then call `resolve_default_diagram_id` with the same connection.

```python
import pytest

from tm_cli.cli._errors import NotFoundError
from tm_cli.cli._options import resolve_default_diagram_id
from tm_cli.db import DiagramCreate, DiagramRepository, connect


def test_no_explicit_no_default_no_create_returns_none(db_path) -> None:
    with connect(db_path) as conn:
        result = resolve_default_diagram_id(conn, None, create_if_missing=False)
    assert result is None


def test_no_explicit_no_default_with_create_creates_and_returns_id(db_path) -> None:
    with connect(db_path) as conn:
        created_id = resolve_default_diagram_id(conn, None, create_if_missing=True)
        assert created_id is not None
        diagram = DiagramRepository(conn).get(created_id)
    assert diagram is not None
    assert diagram.name == "default"


def test_two_default_diagrams_lowest_id_wins(db_path) -> None:
    with connect(db_path) as conn:
        repo = DiagramRepository(conn)
        first = repo.create(DiagramCreate(name="default"))
        repo.create(DiagramCreate(name="default"))
        result = resolve_default_diagram_id(conn, None, create_if_missing=False)
    assert result == first.id


def test_explicit_id_raises_not_found_when_missing(db_path) -> None:
    with connect(db_path) as conn:
        with pytest.raises(NotFoundError):
            resolve_default_diagram_id(conn, 999, create_if_missing=False)
```

(Implement all eight tests — the table above is the contract.)

**Verification:**

Run: `uv run pytest tests/cli/test_resolve_default_diagram_id.py -v`
Expected: 8 tests pass.

**Commit:** `test(cli): cover resolve_default_diagram_id branches and edge cases`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `tm diagram` command surface

**Type:** Functionality (tests in Task 6).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/diagrams.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/main.py` (register the `diagram` subgroup).

**Implementation:**

Mirror `documents.py` precisely. No hidden `--diagram-id` flag — diagrams own themselves. All fields on `DiagramCreate` are optional (`name`, `description`, `author`); the CLI defaults to passing whatever the user provided. `--if-not-exists` is accepted but no-op (no natural key on diagrams; design says agents should use explicit naming when they care).

```python
"""tm diagram — Diagram CRUDL + search subgroup."""

from __future__ import annotations

from typing import Any

import click
from pydantic import ValidationError

from tm_cli.cli._errors import NotFoundError, map_exception
from tm_cli.cli._options import apply_sort, json_fields_option, list_options, parse_json_fields
from tm_cli.cli._output import emit, project_fields
from tm_cli.cli._stdin import enforce_stdin_exclusive, read_json_stdin
from tm_cli.db import (
    DiagramCreate,
    DiagramRepository,
    DiagramUpdate,
    connect,
)


@click.group(name="diagram")
def diagram_group() -> None:
    """Manage DFD diagrams."""


@diagram_group.command(name="list")
@list_options
@json_fields_option
@click.pass_context
def list_diagrams(ctx, *, limit, offset, sort_field, order, json_fields) -> None:
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
    with connect() as conn:
        row = DiagramRepository(conn).get(diagram_id)
    if row is None:
        raise NotFoundError(f"Diagram id={diagram_id} not found", id=str(diagram_id))
    payload = project_fields(row.model_dump(mode="json"), parse_json_fields(json_fields))
    emit(ctx, payload)


@diagram_group.command(name="create")
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--author", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False,
              help="No-op for Diagram (no natural key); kept for command-shape consistency.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_diagram(ctx, *, name, description, author, use_stdin, if_not_exists, dry_run) -> None:
    enforce_stdin_exclusive(use_stdin, {"name": name, "description": description, "author": author})
    if use_stdin:
        body = read_json_stdin()
    else:
        body = {k: v for k, v in {"name": name, "description": description, "author": author}.items() if v is not None}
        # All fields optional, so empty body is permitted.

    if isinstance(body, list):
        models = []
        for index, item in enumerate(body):
            try:
                models.append(DiagramCreate.model_validate(item))
            except ValidationError as e:
                raise map_exception(e, input_payload={"index": index, "item": item}) from e
        if dry_run:
            emit(ctx, {"dry_run": True, "would_create": [m.model_dump(mode="json") for m in models]})
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
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--author", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_diagram(ctx, diagram_id, *, name, description, author, use_stdin, dry_run) -> None:
    enforce_stdin_exclusive(use_stdin, {"name": name, "description": description, "author": author})
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body = {k: v for k, v in {"name": name, "description": description, "author": author}.items() if v is not None}
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = DiagramUpdate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_update": {"id": str(diagram_id), "patch": patch.model_dump(mode="json", exclude_none=True)}})
        return
    with connect() as conn:
        updated = DiagramRepository(conn).update(diagram_id, patch)
    if updated is None:
        raise NotFoundError(f"Diagram id={diagram_id} not found", id=str(diagram_id))
    emit(ctx, updated.model_dump(mode="json"))


@diagram_group.command(name="delete")
@click.argument("diagram_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_diagram(ctx, diagram_id, *, yes, dry_run) -> None:
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(diagram_id)})
        return
    with connect() as conn:
        existed = DiagramRepository(conn).delete(diagram_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(diagram_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(diagram_id), "reason": "not_found"})


@diagram_group.command(name="search")
@click.argument("text", nargs=1)
@list_options
@json_fields_option
@click.pass_context
def search_diagrams(ctx, text, *, limit, offset, sort_field, order, json_fields) -> None:
    if not text.strip():
        raise click.UsageError("search requires a non-empty TEXT argument")
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = DiagramRepository(conn).search(text=text, limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
```

Update `src/tm_cli/main.py`: register `diagram_group`.

**Verification:**

Run: `uv run tm diagram --help`
Expected: lists six commands; no `--diagram-id` anywhere.

**Commit:** `feat(cli): add tm diagram command surface`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: `tm data-item` command surface (uses default-diagram resolver)

**Type:** Functionality (tests in Tasks 5 and 7).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/items.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/main.py` (register the `data-item` subgroup).

**Implementation:**

`tm data-item` is the first DFD entity in the build, so it's the first place the `dfd_diagram_id_option` decorator and the resolver are applied. Pattern:

1. The `--diagram-id` option is hidden via `@dfd_diagram_id_option`.
2. Inside each command, after opening `connect()`, call `resolve_default_diagram_id(conn, diagram_id, create_if_missing=<is_create>)`.
3. On read commands (`list`, `search`), if the resolver returns `None`, emit an empty list and exit immediately.
4. On `create`, the resolver creates a "default" diagram if none exists; the resolved id is included in the response object (already done because the repo's response carries `parent_node_id` etc., but the resolved diagram_id needs to be added to the envelope explicitly when not part of the model).
5. On `update`, `get`, `delete` — the entity id is sufficient; no diagram lookup needed.

`Classification` filter values come from `typing.get_args(Classification)`.

The `--parent-node-id` filter accepts an integer or `none` to match rows with NULL parent. `data-item update` accepting `--parent-node-id ""` to clear the field requires special handling: Click's default for `--parent-node-id` is `None` (= "not set"), but the user passing `""` (empty string) should be interpreted as "clear it". Trick: use a custom Click `type` that maps the string `"none"` (case-insensitive) to a sentinel meaning "set to NULL". On the command line, the sentinel is the literal `none`. This is an explicit, agent-discoverable contract.

```python
"""tm data-item — DataItem CRUDL + search subgroup with default-diagram fallback."""

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
    Classification,
    DataItemCreate,
    DataItemRepository,
    DataItemUpdate,
    connect,
)


_CLASSIFICATION_CHOICES = list(get_args(Classification))

# Sentinel for "user explicitly cleared the parent_node_id" on update.
_CLEAR_PARENT = object()


def _parse_parent_node_id(value: str | None) -> int | None | object:
    """Parse ``--parent-node-id`` for update.

    Three distinct return values:
    - ``None`` — Click flag was NOT supplied (default). The caller leaves the
      field untouched in the patch (omit from ``DataItemUpdate`` body).
    - ``_CLEAR_PARENT`` (sentinel) — flag was supplied with ``""`` / ``"none"`` /
      ``"null"``. The caller sets ``parent_node_id=None`` in the patch (DFD
      repos honor explicit ``None`` to clear the column).
    - ``int`` — flag was supplied with an integer string. Set to that id.

    The distinction between "flag absent" (``None``) and "flag explicitly
    cleared" (``_CLEAR_PARENT``) matters because ``DataItemUpdate`` uses
    ``model_dump(exclude_unset=True)`` and the repo's nullable-field handling
    differentiates the two states. Tests in Task 6 cover both branches.
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in ("", "none", "null"):
        return _CLEAR_PARENT
    try:
        return int(value)
    except ValueError as e:
        raise click.UsageError(f"--parent-node-id must be an integer, 'none', or empty: {value!r}") from e


def _parse_parent_node_filter(value: str | None) -> int | None:
    """Parse ``--parent-node-id`` filter for list/search (always integer-or-none)."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as e:
        raise click.UsageError(f"--parent-node-id filter must be an integer: {value!r}") from e


@click.group(name="data-item")
def data_item_group() -> None:
    """Manage DFD data items."""


@data_item_group.command(name="list")
@list_options
@dfd_diagram_id_option
@click.option("--classification", type=click.Choice(_CLASSIFICATION_CHOICES), default=None)
@click.option("--parent-node-id", "parent_node_id_raw", default=None,
              help="Filter to data items whose parent_node_id equals this integer.")
@json_fields_option
@click.pass_context
def list_items(ctx, *, limit, offset, sort_field, order, diagram_id, classification, parent_node_id_raw, json_fields) -> None:
    """List data items in a diagram (defaults to the 'default' diagram)."""
    parent_node_id = _parse_parent_node_filter(parent_node_id_raw)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = DataItemRepository(conn).search(
            resolved,
            text=None,
            classification=classification,
            parent_node_id=parent_node_id,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), parse_json_fields(json_fields)) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@data_item_group.command(name="get")
@click.argument("item_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_item(ctx, item_id, *, json_fields) -> None:
    with connect() as conn:
        row = DataItemRepository(conn).get(item_id)
    if row is None:
        raise NotFoundError(f"DataItem id={item_id} not found", id=str(item_id))
    payload = project_fields(row.model_dump(mode="json"), parse_json_fields(json_fields))
    emit(ctx, payload)


@data_item_group.command(name="create")
@dfd_diagram_id_option
@click.option("--identifier", default=None)
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--classification", type=click.Choice(_CLASSIFICATION_CHOICES), default=None)
@click.option("--parent-node-id", "parent_node_id", type=click.INT, default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False,
              help="No-op for DataItem (identifier is not enforced unique); kept for shape consistency.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_item(ctx, *, diagram_id, identifier, name, description, classification, parent_node_id, use_stdin, if_not_exists, dry_run) -> None:
    enforce_stdin_exclusive(use_stdin, {
        "identifier": identifier, "name": name, "description": description,
        "classification": classification, "parent_node_id": parent_node_id,
    })
    if use_stdin:
        body = read_json_stdin()
    else:
        if identifier is None or name is None or description is None:
            raise click.UsageError("--identifier, --name, and --description are required (or use --stdin)")
        body = {"identifier": identifier, "name": name, "description": description}
        if classification is not None:
            body["classification"] = classification
        if parent_node_id is not None:
            body["parent_node_id"] = parent_node_id

    if isinstance(body, list):
        models: list[DataItemCreate] = []
        for index, item in enumerate(body):
            try:
                models.append(DataItemCreate.model_validate(item))
            except ValidationError as e:
                raise map_exception(e, input_payload={"index": index, "item": item}) from e
        if dry_run:
            emit(ctx, {"dry_run": True, "would_create": [m.model_dump(mode="json") for m in models]})
            return
        with connect() as conn:
            resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
            assert resolved is not None
            repo = DataItemRepository(conn)
            created = [repo.create(resolved, m) for m in models]
        emit(ctx, [{"diagram_id": str(resolved), **c.model_dump(mode="json")} for c in created])
        return

    model = DataItemCreate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        assert resolved is not None
        created_item = DataItemRepository(conn).create(resolved, model)
    emit(ctx, {"diagram_id": str(resolved), **created_item.model_dump(mode="json")})


@data_item_group.command(name="update")
@click.argument("item_id", type=click.INT)
@click.option("--identifier", default=None)
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--classification", type=click.Choice(_CLASSIFICATION_CHOICES), default=None)
@click.option("--parent-node-id", "parent_node_id_raw", default=None,
              help="Set parent node id, or 'none'/'' to clear (NULL).")
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_item(ctx, item_id, *, identifier, name, description, classification, parent_node_id_raw, use_stdin, dry_run) -> None:
    parsed_parent = _parse_parent_node_id(parent_node_id_raw)
    enforce_stdin_exclusive(use_stdin, {
        "identifier": identifier, "name": name, "description": description,
        "classification": classification,
        "parent_node_id": (None if parsed_parent is None else parsed_parent),
    })
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body: dict[str, Any] = {}
        if identifier is not None:
            body["identifier"] = identifier
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if classification is not None:
            body["classification"] = classification
        if parsed_parent is _CLEAR_PARENT:
            body["parent_node_id"] = None
        elif parsed_parent is not None:
            body["parent_node_id"] = parsed_parent
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")

    patch = DataItemUpdate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_update": {"id": str(item_id), "patch": patch.model_dump(mode="json")}})
        return
    with connect() as conn:
        updated = DataItemRepository(conn).update(item_id, patch)
    if updated is None:
        raise NotFoundError(f"DataItem id={item_id} not found", id=str(item_id))
    emit(ctx, updated.model_dump(mode="json"))


@data_item_group.command(name="delete")
@click.argument("item_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_item(ctx, item_id, *, yes, dry_run) -> None:
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(item_id)})
        return
    with connect() as conn:
        existed = DataItemRepository(conn).delete(item_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(item_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(item_id), "reason": "not_found"})


@data_item_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@dfd_diagram_id_option
@click.option("--classification", type=click.Choice(_CLASSIFICATION_CHOICES), default=None)
@click.option("--parent-node-id", "parent_node_id_raw", default=None)
@json_fields_option
@click.pass_context
def search_items(ctx, text, *, limit, offset, sort_field, order, diagram_id, classification, parent_node_id_raw, json_fields) -> None:
    text_str = " ".join(text).strip() if text else ""
    parent_node_id = _parse_parent_node_filter(parent_node_id_raw)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = DataItemRepository(conn).search(
            resolved,
            text=text_str if text_str else None,
            classification=classification,
            parent_node_id=parent_node_id,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), parse_json_fields(json_fields)) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
```

Update `src/tm_cli/main.py`: register `data_item_group`.

**Verification:**

Run: `uv run tm data-item --help`
Expected: lists six commands. `--diagram-id` does NOT appear (hidden=True).

Run: `uv run tm data-item create --help`
Expected: shows `--identifier`, `--name`, `--description`, `--classification`, `--parent-node-id`, `--stdin`, `--if-not-exists`, `--dry-run`. No `--diagram-id`.

Run: `uv run python -c "from tm_cli.main import cli; cmd = cli.commands['data-item'].commands['create']; print([p for p in cmd.params if p.name == 'diagram_id'][0].hidden)"`
Expected: prints `True`.

**Commit:** `feat(cli): add tm data-item command surface with default-diagram fallback`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Tests for `tm diagram` (CRUDL)

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.1`–`agent-cli.AC1.6`, `agent-cli.AC1.8` (Diagram).

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_diagrams.py`.
- Create: `/Users/josh/code/tm-cli/tests/cli/test_diagrams_help.py`.

**Implementation:**

Mirror `tests/cli/test_documents.py` for the six verbs. The seed includes one diagram (`non-default`); use it as the existing-id baseline. Add help-text snapshots for the six commands.

Tests:

| Test | AC | Action |
|---|---|---|
| `test_list_returns_seeded_diagram` | AC1.1 | seed | `tm diagram list` returns 1 row |
| `test_get_returns_diagram` | AC1.2 | seed | `tm diagram get <id>` |
| `test_create_returns_new_diagram` | AC1.3 | empty | `tm diagram create --name=fresh --description=d` |
| `test_create_no_args_creates_unnamed_diagram` | AC1.3 | empty | `tm diagram create` (all-optional fields) returns a row with `name`, `description`, `author` all null |
| `test_update_returns_updated_diagram` | AC1.4 | seed | `tm diagram update <id> --description="new"` |
| `test_get_missing_id_exits_2` | AC1.5 | seed | `tm diagram get 9999` |
| `test_update_missing_id_exits_2` | AC1.6 | seed | `tm diagram update 9999 --name=x` |
| `test_list_under_limit_no_pagination_footer` | AC1.8 | seed | `tm diagram list --limit 50` has no `_pagination` line |

**Commit:** `test(cli): tm diagram CRUDL coverage`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Tests for `tm data-item` (CRUDL + filters + clear-nullable)

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.1`–`agent-cli.AC1.6` (DataItem), `agent-cli.AC2.5`, `agent-cli.AC11.4`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_data_items.py`.
- Create: `/Users/josh/code/tm-cli/tests/cli/test_data_items_help.py`.

**Implementation:**

Use `db_with_seed` (seeded with two data items, one with parent_node_id, one without). Use `db_path` for empty-DB cases.

Tests:

| Test | AC | Action |
|---|---|---|
| `test_list_returns_seeded_items` | AC1.1 | seed; `tm data-item list` returns 2 |
| `test_list_filtered_by_classification` | AC2.5 | seed (`pii`, `public`); `--classification=pii` returns the one |
| `test_list_filtered_by_parent_node_id` | AC2.5 | seed; `--parent-node-id=<process-id>` returns the one with parent |
| `test_list_filtered_by_classification_and_parent_node` | AC2.5 | seed; combining filters returns the AND |
| `test_get_returns_item` | AC1.2 | seed |
| `test_create_with_named_flags_in_seeded_diagram` | AC1.3 | seed; pass explicit `--diagram-id` (hidden but functional) |
| `test_update_returns_full_row` | AC1.4 | seed; update name |
| `test_update_clear_parent_node_id_with_empty_string` | AC11.4 | seed item with parent; `tm data-item update <id> --parent-node-id ""`; subsequent `get` shows `parent_node_id == None` |
| `test_update_clear_parent_node_id_with_none_literal` | AC11.4 | seed; `tm data-item update <id> --parent-node-id none` → same effect |
| `test_update_clear_parent_node_id_via_stdin` | AC11.4 | seed; `tm data-item update <id> --stdin` with `{"parent_node_id": null}` → cleared |
| `test_get_missing_id_exits_2` | AC1.5 | `tm data-item get 9999` |
| `test_update_missing_id_exits_2` | AC1.6 | `tm data-item update 9999 --name=x` |

**Hidden flag check** is done in Task 7's resolver/integration tests rather than here.

**Commit:** `test(cli): tm data-item CRUDL with filters and nullable parent_node_id`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Default-diagram resolver behavior end-to-end

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC9.1`, `agent-cli.AC9.2`, `agent-cli.AC9.3`, `agent-cli.AC9.4`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_default_diagram.py`.

**Implementation:**

Each test uses a fresh `db_path` (no seed), exercises a `tm data-item` command, and asserts both behavioral and structural outcomes.

| Test | AC | Action | Assertion |
|---|---|---|---|
| `test_create_without_diagram_id_creates_default_diagram` | AC9.1 | empty DB; `tm data-item create --identifier=x --name=n --description=d` | command exits 0; `tm diagram list` afterwards shows exactly one diagram with `name == "default"`; the create response includes `diagram_id` set to that diagram's id |
| `test_list_without_diagram_id_with_no_default_returns_empty` | AC9.2 | empty DB; `tm data-item list` | exit 0; stdout has no NDJSON rows; `tm diagram list` still returns zero diagrams (no implicit creation on read) |
| `test_search_without_diagram_id_with_no_default_returns_empty` | AC9.2 | empty DB; `tm data-item search foo` | same as above |
| `test_list_uses_existing_default_diagram` | AC9.3 | empty DB; create a diagram named `default`; create a data item in it (via explicit `--diagram-id`); `tm data-item list` (no flag) returns the item |
| `test_diagram_id_hidden_in_help` | AC9.4 | inspect `tm data-item create --help` output | does NOT contain the substring `--diagram-id` |
| `test_diagram_id_hidden_param_attribute` | AC9.4 (structural) | reflect on the Click command's params | the `diagram_id` param has `hidden == True` |

Representative implementation:

```python
import json
import re

from click.testing import CliRunner

from tm_cli.main import cli


def test_create_without_diagram_id_creates_default_diagram(db_path) -> None:
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(
        cli,
        ["data-item", "create", "--identifier=x", "--name=n", "--description=d"],
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "diagram_id" in payload
    assert payload["identifier"] == "x"

    # The default diagram must now exist.
    list_result = runner.invoke(cli, ["diagram", "list"])
    diagrams = [json.loads(line) for line in list_result.stdout.splitlines() if line.strip()]
    assert len(diagrams) == 1
    assert diagrams[0]["name"] == "default"


def test_diagram_id_hidden_in_help(db_path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["data-item", "create", "--help"])
    assert result.exit_code == 0
    assert "--diagram-id" not in result.output
```

**Verification:**

Run: `uv run pytest tests/cli/test_default_diagram.py -v`
Expected: every test passes.

**Commit:** `test(cli): default-diagram resolver behavior end-to-end on tm data-item`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Final operational verification

**Type:** Infrastructure (verification only).

**Files:** none.

**Verification:**

Run: `make lint`
Expected: clean.

Run: `make test`
Expected: every Phase 1/2/3/4 test passes.

End-to-end smoke (against `TM_DB_PATH`):

```bash
uv run tm diagram create --name=alpha
uv run tm data-item create --identifier=foo --name=Foo --description=bar
uv run tm data-item list
uv run tm diagram list                             # should include "default" plus "alpha"
uv run tm data-item search --classification=public
```

Expected: every step exits 0 with parseable JSON; the second command implicitly creates a "default" diagram if no `--diagram-id` was passed.

**Commit:** none. `chore(cli): phase 4 verification fix-ups` if needed.
<!-- END_TASK_8 -->

---

## Phase 4 — Done When

- `tests/cli/test_resolve_default_diagram_id.py`, `test_diagrams.py`, `test_data_items.py`, `test_default_diagram.py` all green.
- `tm diagram` and `tm data-item` are wired into the root group.
- `--diagram-id` is registered on every DFD entity command (verified for `data-item` here; subsequent phases inherit the pattern).
- `tm data-item create` with no `--diagram-id` creates a `default` diagram on first call and reuses it thereafter.
- `tm data-item list/search` with no `--diagram-id` and no `default` diagram returns an empty NDJSON stream without creating one.
- Nullable `parent_node_id` clears on update via either `--parent-node-id ""`, `--parent-node-id none`, or `--stdin {"parent_node_id": null}`.
- `make lint` clean.
