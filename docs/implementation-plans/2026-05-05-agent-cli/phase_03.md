# Agent CLI — Phase 3: Term + Observation + document_terms junction

**Goal:** Close out the legacy (non-DFD) domain. Apply the Phase 2 pattern to two more entities, add the `--if-not-exists` natural-key idempotency path on Term, expose the document↔term junction in both directions, and surface enum-filtered list/search on Observation.

**Architecture:** Two new entity modules (`terms.py`, `observations.py`) follow the Phase 2 Document template byte-for-byte for the six core verbs. Term adds two unique behaviors: `--if-not-exists` short-circuits via `TermRepository.get_by_term()` (natural-key lookup), and a `tm term list-documents <term-id>` subcommand surfaces `documents_for_term`. Observation adds `--observation-type` and `--status` filters that pass through to the repository's `list()`/`search()` filter kwargs. The document↔term junction lives on `tm document link-term/unlink-term/list-terms` (per design — `documents.py` is the natural subject for forward links) plus the reverse `tm term list-documents`. All link verbs are idempotent at the repository (`INSERT OR IGNORE`); the CLI checks pre-existence via `terms_for_document` to populate the `linked: true|false` envelope.

**Tech Stack:** Same as Phase 2.

**Scope:** Phase 3 of 8 from `docs/design-plans/2026-05-05-agent-cli.md`.

**Codebase verified:** 2026-05-05.
- `TermRepository` exposes `create`, `get`, `get_by_term`, `update`, `delete`, `list`, `search`, plus the junction methods `link`, `unlink`, `documents_for_term`, `terms_for_document`. `link()` returns `None` (uses `INSERT OR IGNORE`). FK violations raise `sqlite3.IntegrityError` with the `FOREIGN KEY constraint failed` prefix.
- `terms.term` has a UNIQUE constraint; `TermRepository.create` raises `sqlite3.IntegrityError` with the `UNIQUE constraint failed: terms.term` prefix on duplicates.
- `ObservationRepository.list()` and `.search()` both accept `observation_type` and `status` filter kwargs (typed as the Literals `ObservationType` and `ObservationStatus`).
- Pydantic `Literal` rejects invalid enum values BEFORE the SQL CHECK fires, so CHECK violations are not reachable through the CLI. AC5.5 (CHECK constraint exit code 3) is structurally unreachable end-to-end and remains covered only by Phase 1's `map_exception` unit test. This is documented and intentional.
- `link()` does not raise on duplicate links (idempotent), but DOES raise `sqlite3.IntegrityError` (FK) when the document_id or term_id doesn't exist.

**External dependencies verified:** none new; this phase reuses Phase 1/2 infrastructure.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### agent-cli.AC1: Standard CRUDL behaviors (universal across entities)
- **agent-cli.AC1.1 Success:** `list` returns all rows for an entity as NDJSON when stdout is piped (one JSON object per line). [Term, Observation]
- **agent-cli.AC1.2 Success:** `get` returns the full model for an existing id (including server-set fields like `last_imported`). [Term, Observation]
- **agent-cli.AC1.3 Success:** `create` with valid flags returns the new row, including the synthesized id (string-quoted) and any server-managed timestamps. [Term, Observation]
- **agent-cli.AC1.4 Success:** `update` with a valid patch returns the resulting row (full object, not `{"ok": true}`). [Term, Observation]
- **agent-cli.AC1.5 Failure:** `get` of a missing id exits 2 with `error.code = "not_found"`. [Term, Observation]
- **agent-cli.AC1.6 Failure:** `update` of a missing id exits 2 with `error.code = "not_found"`. [Term, Observation]
- **agent-cli.AC1.7 Failure:** `create` with an invalid enum value (e.g., `--observation-type=bogus`) exits 1 at the Click parser with a Choice error. [Observation]

### agent-cli.AC2: Search
- **agent-cli.AC2.1 Success:** `search "X"` matches case-insensitively across all searchable text columns for the entity (per the repo's `search()` columns). [Term, Observation]
- **agent-cli.AC2.2 Success:** Multi-token text (`search "foo bar"`) AND-combines tokens; each token must match at least one searchable column. [Term, Observation]
- **agent-cli.AC2.3 Success:** `tm observation search "todo" --observation-type=todo --status=open` AND-combines text and filters.
- **agent-cli.AC2.7 Edge:** `search` with empty text plus filters returns the same shape as `list` with those filters. [Observation]

### agent-cli.AC3: Junctions
- **agent-cli.AC3.1 Success:** `tm document link-term <doc-id> <term-id>` creates the link; subsequent `tm document list-terms <doc-id>` includes the term.
- **agent-cli.AC3.2 Success:** Re-linking the same pair returns `{"linked": false, "reason": "already_linked"}` and exits 0.
- **agent-cli.AC3.3 Success:** `tm document unlink-term` removes the link; the term no longer appears in `list-terms`.

### agent-cli.AC5: Errors and exit codes
- **agent-cli.AC5.3 Success:** UNIQUE constraint violation (e.g., duplicate `Term.term`) → exit 3, `error.constraint = "unique"`.
- **agent-cli.AC5.4 Success:** FOREIGN KEY violation → exit 3, `error.constraint = "foreign_key"`.

### agent-cli.AC6: Idempotency and --dry-run
- **agent-cli.AC6.1 Success:** `tm term create --if-not-exists --term foo --definition bar` with `foo` already present returns the existing row with `{"created": false, ...}` and exits 0.

**Not reachable through CLI (intentional):**
- `agent-cli.AC5.5` (CHECK violation): Pydantic `Literal` validation rejects invalid enum values before the SQL CHECK fires. Already covered by Phase 1's `map_exception` unit test. Not retested in this phase.

---

## Required reading for the executor

- `/Users/josh/code/tm-cli/src/tm_cli/db/CLAUDE.md` (db domain contracts).
- `/Users/josh/code/tm-cli/src/tm_cli/db/terms.py` (TermRepository).
- `/Users/josh/code/tm-cli/src/tm_cli/db/observations.py` (ObservationRepository — verify the actual `list()`/`search()` filter kwarg names match what's used in the CLI commands here).
- `/Users/josh/code/tm-cli/src/tm_cli/db/models.py` (Term, TermCreate, TermUpdate, Observation, ObservationCreate, ObservationUpdate, ObservationType, ObservationStatus).
- Phase 2 deliverables (`src/tm_cli/cli/documents.py`) as the template.

The executor should activate these skills if relevant in their session:
- `house-style:writing-good-tests`
- `ed3d-plan-and-execute:test-driven-development`
- `ed3d-plan-and-execute:verification-before-completion`

---

<!-- START_TASK_1 -->
### Task 1: `tm term` command surface

**Type:** Functionality (tests in Task 5).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/terms.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/main.py` (register the `term` subgroup).

**Implementation:**

Mirror `documents.py` for the six core verbs, with two adjustments:

1. **`--if-not-exists` on create**: when set, the command first calls `TermRepository.get_by_term(term)`. If a row matches, return `{"created": false, **existing_row}`. Otherwise call `repo.create()` and return `{"created": true, **new_row}`. The envelope's `created` key is added by the CLI; the repository is unchanged.

2. **`tm term list-documents <term-id>`**: a seventh subcommand that returns `repo.documents_for_term(term_id)` as NDJSON, honoring `--limit/--offset/--sort/--order/--json` like `list`. Pre-checks the term exists; if not, raises `NotFoundError` (exit 2).

Term's `--if-not-exists` is the only entity using this idempotency path in v1. Other entities accept the flag but no-op (Document already does this).

`/Users/josh/code/tm-cli/src/tm_cli/cli/terms.py`:

```python
"""tm term — Term CRUDL + search + reverse-junction subgroup."""

from __future__ import annotations

from typing import Any

import click
from pydantic import ValidationError

from tm_cli.cli._errors import NotFoundError, map_exception
from tm_cli.cli._options import apply_sort, json_fields_option, list_options, parse_json_fields
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
    payload = project_fields(row.model_dump(mode="json"), parse_json_fields(json_fields))
    emit(ctx, payload)


@term_group.command(name="create")
@click.option("--term", "term_value", default=None)
@click.option("--definition", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False,
              help="Use natural-key lookup (term) for idempotent create.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_term(ctx, *, term_value, definition, use_stdin, if_not_exists, dry_run) -> None:
    """Create a term, optionally idempotent on the ``term`` natural key."""
    enforce_stdin_exclusive(use_stdin, {"term": term_value, "definition": definition})

    if use_stdin:
        body = read_json_stdin()
    else:
        if term_value is None or definition is None:
            raise click.UsageError("--term and --definition are required (or use --stdin)")
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
    payload = {"created": True, **created.model_dump(mode="json")} if if_not_exists else created.model_dump(mode="json")
    emit(ctx, payload)


def _create_batch(ctx, body: list[dict[str, Any]], *, if_not_exists: bool, dry_run: bool) -> None:
    models: list[TermCreate] = []
    for index, item in enumerate(body):
        try:
            models.append(TermCreate.model_validate(item))
        except ValidationError as e:
            raise map_exception(e, input_payload={"index": index, "item": item}) from e

    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": [m.model_dump(mode="json") for m in models]})
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
                out.append({"created": True, **created.model_dump(mode="json")} if if_not_exists else created.model_dump(mode="json"))
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
        body = {k: v for k, v in {"term": term_value, "definition": definition}.items() if v is not None}
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")

    patch = TermUpdate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_update": {"id": str(term_id), "patch": patch.model_dump(mode="json", exclude_none=True)}})
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
def list_documents_for_term(ctx, term_id, *, limit, offset, sort_field, order, json_fields) -> None:
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
```

Note the `list-documents` subcommand applies `--limit`/`--offset` client-side (the repo method doesn't paginate). This is acceptable — the document↔term cardinality per term is low.

Update `src/tm_cli/main.py`: add `from tm_cli.cli.terms import term_group` and `cli.add_command(term_group)`.

**Verification:**

Run: `uv run tm term --help`
Expected: lists `list`, `get`, `create`, `update`, `delete`, `search`, `list-documents`.

Run: `uv run tm term create --term foo --definition "first attempt"`
Expected: prints a Term JSON with `id` as a string.

Run: `uv run tm term create --if-not-exists --term foo --definition "second attempt"`
Expected: prints `{"created": false, ...}` envelope with the original definition (not "second attempt").

**Commit:** `feat(cli): add tm term command surface with --if-not-exists idempotency`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `tm observation` command surface

**Type:** Functionality (tests in Task 6).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/observations.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/main.py` (register the `observation` subgroup).

**Implementation:**

Mirror `terms.py` for the six core verbs, plus filter flags `--observation-type` and `--status` on both `list` and `search`. The Click `Choice` is constructed from the literal values of `ObservationType` and `ObservationStatus` typing literals — extract them via `typing.get_args()`.

```python
"""tm observation — Observation CRUDL + search subgroup."""

from __future__ import annotations

from typing import Any, get_args

import click
from pydantic import ValidationError

from tm_cli.cli._errors import NotFoundError, map_exception
from tm_cli.cli._options import apply_sort, json_fields_option, list_options, parse_json_fields
from tm_cli.cli._output import emit, project_fields
from tm_cli.cli._stdin import enforce_stdin_exclusive, read_json_stdin
from tm_cli.db import (
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
    f = click.option("--observation-type", "observation_type",
                     type=click.Choice(_OBS_TYPE_CHOICES), default=None,
                     help="Filter by observation type.")(f)
    f = click.option("--status", "status",
                     type=click.Choice(_OBS_STATUS_CHOICES), default=None,
                     help="Filter by status.")(f)
    return f


@click.group(name="observation")
def observation_group() -> None:
    """Manage threat-model observations (todos, questions, threats)."""


@observation_group.command(name="list")
@list_options
@_filter_options
@json_fields_option
@click.pass_context
def list_observations(ctx, *, limit, offset, sort_field, order, observation_type, status, json_fields) -> None:
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
    with connect() as conn:
        row = ObservationRepository(conn).get(obs_id)
    if row is None:
        raise NotFoundError(f"Observation id={obs_id} not found", id=str(obs_id))
    payload = project_fields(row.model_dump(mode="json"), parse_json_fields(json_fields))
    emit(ctx, payload)


@observation_group.command(name="create")
@click.option("--content", default=None)
@click.option("--observation-type", "observation_type",
              type=click.Choice(_OBS_TYPE_CHOICES), default=None)
@click.option("--status", type=click.Choice(_OBS_STATUS_CHOICES), default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False,
              help="No-op for Observation (no natural key); kept for command-shape consistency.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_observation(ctx, *, content, observation_type, status, use_stdin, if_not_exists, dry_run) -> None:
    enforce_stdin_exclusive(
        use_stdin,
        {"content": content, "observation_type": observation_type, "status": status},
    )
    if use_stdin:
        body = read_json_stdin()
    else:
        if content is None or observation_type is None:
            raise click.UsageError("--content and --observation-type are required (or use --stdin)")
        body = {"content": content, "observation_type": observation_type}
        if status is not None:
            body["status"] = status

    if isinstance(body, list):
        models = _validate_create_batch(body)
        if dry_run:
            emit(ctx, {"dry_run": True, "would_create": [m.model_dump(mode="json") for m in models]})
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
@click.option("--observation-type", "observation_type",
              type=click.Choice(_OBS_TYPE_CHOICES), default=None)
@click.option("--status", type=click.Choice(_OBS_STATUS_CHOICES), default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_observation(ctx, obs_id, *, content, observation_type, status, use_stdin, dry_run) -> None:
    enforce_stdin_exclusive(
        use_stdin,
        {"content": content, "observation_type": observation_type, "status": status},
    )
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body = {k: v for k, v in {
            "content": content,
            "observation_type": observation_type,
            "status": status,
        }.items() if v is not None}
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")

    patch = ObservationUpdate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_update": {"id": str(obs_id), "patch": patch.model_dump(mode="json", exclude_none=True)}})
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
def search_observations(ctx, text, *, limit, offset, sort_field, order, observation_type, status, json_fields) -> None:
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
```

**Note on `search` text vs. AC2.7:** AC2.7 says "search with empty text plus filters returns the same shape as `list` with those filters". Observation's `search` accepts `text` as `nargs=-1` (zero-or-more), so `tm observation search --status=open` works with no text. The repo treats `text=None` as a no-op text clause and applies filters. This is the design's intended behavior.

`Term`'s `search` requires text (per Phase 2 pattern); AC2.7 is verified on Observation only. This is consistent: Term has no filter flags, so an empty-text search would be redundant with `list`.

Update `src/tm_cli/main.py`: add `from tm_cli.cli.observations import observation_group` and `cli.add_command(observation_group)`.

**Verification:**

Run: `uv run tm observation --help`
Expected: lists six commands.

Run: `uv run tm observation create --help`
Expected: shows `--observation-type` with `[potential_threat|incomplete_information|question|todo]` choice and `--status` with `[open|closed]`.

Run: `uv run tm observation create --observation-type=bogus --content=x 2>&1 1>/dev/null`
Expected: stderr contains a JSON object with `error.code == "user_error"` and exit code 1 (Choice rejection mapped through `map_exception`).

**Commit:** `feat(cli): add tm observation command surface with type/status filters`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: document↔term junction commands

**Type:** Functionality (tests in Task 7).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/documents.py` (add three subcommands).

**Implementation:**

Add three subcommands to the existing `document_group`:

- `tm document link-term <doc-id> <term-id>` — calls `repo.link()` (idempotent at the repo). The CLI checks pre-existence via a `terms_for_document(doc_id)` lookup so it can return the documented `linked: true | false` envelope.
- `tm document unlink-term <doc-id> <term-id>` — calls `repo.unlink()` (returns bool).
- `tm document list-terms <doc-id>` — calls `repo.terms_for_document()`; shape mirrors `tm term list-documents`.

The pre-existence check is two queries per `link` call. Acceptable for v1.

Add to `src/tm_cli/cli/documents.py`:

```python
from tm_cli.db import TermRepository  # add to imports if not already


@document_group.command(name="link-term")
@click.argument("doc_id", type=click.INT)
@click.argument("term_id", type=click.INT)
@click.pass_context
def link_term(ctx, doc_id: int, term_id: int) -> None:
    """Link a term to a document. Idempotent: returns linked=false if already linked."""
    with connect() as conn:
        repo = TermRepository(conn)
        existing_term_ids = {t.id for t in repo.terms_for_document(doc_id)}
        if term_id in existing_term_ids:
            emit(ctx, {"linked": False, "doc_id": str(doc_id), "term_id": str(term_id), "reason": "already_linked"})
            return
        repo.link(doc_id, term_id)
    emit(ctx, {"linked": True, "doc_id": str(doc_id), "term_id": str(term_id)})


@document_group.command(name="unlink-term")
@click.argument("doc_id", type=click.INT)
@click.argument("term_id", type=click.INT)
@click.pass_context
def unlink_term(ctx, doc_id: int, term_id: int) -> None:
    """Remove a document↔term link. Idempotent: returns unlinked=false if not linked."""
    with connect() as conn:
        existed = TermRepository(conn).unlink(doc_id, term_id)
    if existed:
        emit(ctx, {"unlinked": True, "doc_id": str(doc_id), "term_id": str(term_id)})
    else:
        emit(ctx, {"unlinked": False, "doc_id": str(doc_id), "term_id": str(term_id), "reason": "not_linked"})


@document_group.command(name="list-terms")
@click.argument("doc_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_terms_for_doc(ctx, doc_id: int, *, limit, offset, sort_field, order, json_fields) -> None:
    """List terms linked to a document."""
    with connect() as conn:
        from tm_cli.db import DocumentRepository  # local import; avoids cycles
        if DocumentRepository(conn).get(doc_id) is None:
            raise NotFoundError(f"Document id={doc_id} not found", id=str(doc_id))
        rows = TermRepository(conn).terms_for_document(doc_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
```

**Verification:**

Run: `uv run tm document link-term --help`
Expected: shows two positional arguments `DOC_ID` and `TERM_ID`.

(Behavioral verification in Task 7.)

**Commit:** `feat(cli): add document↔term junction commands (link-term/unlink-term/list-terms)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Tests for `tm term` (CRUDL + `--if-not-exists` + reverse junction)

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.1`–`agent-cli.AC1.6` (Term), `agent-cli.AC2.1`, `agent-cli.AC2.2` (Term), `agent-cli.AC5.3` (UNIQUE), `agent-cli.AC6.1`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_terms.py`.
- Create: `/Users/josh/code/tm-cli/tests/cli/test_terms_help.py`.

**Implementation:**

Use `db_with_seed` (seeded with three terms `seed-term-1/2/3`) and an empty `db_path` for create cases. Mirror the test layout from `tests/cli/test_documents.py`.

Tests to write:

| Test | AC | Action |
|---|---|---|
| `test_list_returns_seeded_terms_as_ndjson` | AC1.1 | `tm term list` → 3 NDJSON lines |
| `test_get_returns_full_term` | AC1.2 | `tm term get <id>` with seed id |
| `test_create_with_named_flags_returns_new_row` | AC1.3 | `tm term create --term=fresh --definition="..."` |
| `test_update_returns_updated_row` | AC1.4 | `tm term update <id> --definition="new"` |
| `test_get_missing_id_exits_2` | AC1.5 | `tm term get 9999` |
| `test_update_missing_id_exits_2` | AC1.6 | `tm term update 9999 --term=x` |
| `test_search_case_insensitive` | AC2.1 | seed has `seed-term-1/2/3`; `tm term search SEED` returns all three |
| `test_search_multi_token_and` | AC2.2 | seed; `tm term search "seed 1"` returns only `seed-term-1` (AND across `term` and `definition`) |
| `test_create_duplicate_term_exits_3_unique` | AC5.3 | seed; `tm term create --term=seed-term-1 --definition=...` → exit 3, `error.constraint == "unique"` |
| `test_if_not_exists_returns_existing_with_created_false` | AC6.1 | seed; `tm term create --if-not-exists --term=seed-term-1 --definition=different` → `{"created": false, ..., "definition": "<original>"}` |
| `test_if_not_exists_creates_when_absent` | AC6.1 | empty; `tm term create --if-not-exists --term=fresh --definition=new` → `{"created": true, ...}` |
| `test_list_documents_for_term_returns_linked_docs` | (junction reverse) | seed; create a link; `tm term list-documents <term-id>` returns the doc summary |
| `test_list_documents_for_missing_term_exits_2` | AC1.5 | `tm term list-documents 9999` → exit 2 |

Bless snapshots: `uv run pytest tests/cli/test_terms.py --snapshot-update`.

`tests/cli/test_terms_help.py` snapshots `tm term --help` and the seven leaf commands' help (mirroring Phase 2's pattern).

**Verification:**

Run: `uv run pytest tests/cli/test_terms.py tests/cli/test_terms_help.py -v`
Expected: every test passes.

**Commit:** `test(cli): coverage for tm term verbs, --if-not-exists, and unique-constraint path`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Tests for `tm observation` (CRUDL + filters + invalid enum)

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.1`–`agent-cli.AC1.7` (Observation), `agent-cli.AC2.1`, `agent-cli.AC2.2`, `agent-cli.AC2.3`, `agent-cli.AC2.7`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_observations.py`.
- Create: `/Users/josh/code/tm-cli/tests/cli/test_observations_help.py`.

**Implementation:**

Tests:

| Test | AC | Action |
|---|---|---|
| `test_list_returns_all_seeded_observations` | AC1.1 | seed (2 todos); `tm observation list` |
| `test_list_filtered_by_type_returns_subset` | AC1.1 | create one `todo` and one `question`; `tm observation list --observation-type=todo` returns only the todo |
| `test_list_filtered_by_status` | AC1.1 | seed (2 open todos); `tm observation list --status=open` returns 2 |
| `test_get_returns_full_observation` | AC1.2 | seed; `tm observation get <id>` |
| `test_create_with_named_flags` | AC1.3 | empty; `tm observation create --content=x --observation-type=todo` |
| `test_update_returns_full_row` | AC1.4 | seed; `tm observation update <id> --status=closed` |
| `test_get_missing_id_exits_2` | AC1.5 | `tm observation get 9999` |
| `test_update_missing_id_exits_2` | AC1.6 | `tm observation update 9999 --status=closed` |
| `test_invalid_enum_value_exits_1` | AC1.7 | `tm observation create --observation-type=bogus --content=x` → exit 1, `error.code == "user_error"`; stderr message mentions `bogus` and the choices |
| `test_search_case_insensitive` | AC2.1 | seed (`Seed observation 1/2`); `tm observation search SEED` returns 2 |
| `test_search_multi_token_and` | AC2.2 | seed; `tm observation search "seed 1"` returns 1 |
| `test_search_text_plus_filters_and_combined` | AC2.3 | create one open todo "todo X" and one closed todo "todo Y"; `tm observation search "todo" --observation-type=todo --status=open` returns only "todo X" |
| `test_search_empty_text_with_filters_matches_list_shape` | AC2.7 | seed; `tm observation search --status=open` returns same rows as `tm observation list --status=open` |

Bless snapshots and run.

**Verification:**

Run: `uv run pytest tests/cli/test_observations.py tests/cli/test_observations_help.py -v`
Expected: every test passes.

**Commit:** `test(cli): coverage for tm observation verbs, filters, and enum rejection`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Tests for document↔term junction commands

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC3.1`, `agent-cli.AC3.2`, `agent-cli.AC3.3`, `agent-cli.AC5.4`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_document_terms.py`.

**Implementation:**

Tests:

| Test | AC | Action |
|---|---|---|
| `test_link_term_creates_link` | AC3.1 | seed; `tm document link-term <doc-id> <term-id>` returns `{"linked": true, ...}`; subsequent `tm document list-terms <doc-id>` includes the term |
| `test_relink_returns_already_linked` | AC3.2 | seed + link once; second `link-term` returns `{"linked": false, ..., "reason": "already_linked"}`, exit 0 |
| `test_unlink_term_removes_link` | AC3.3 | seed + link; `tm document unlink-term ...` returns `{"unlinked": true, ...}`; subsequent `list-terms` no longer includes the term |
| `test_unlink_nonexistent_link_returns_not_linked` | (extension) | seed; `tm document unlink-term <doc> <term>` (never linked) returns `{"unlinked": false, ...}`, exit 0 |
| `test_link_term_unknown_doc_id_exits_3_fk` | AC5.4 | `tm document link-term 9999 <real-term-id>` → exit 3, `error.constraint == "foreign_key"` |
| `test_link_term_unknown_term_id_exits_3_fk` | AC5.4 | `tm document link-term <real-doc-id> 9999` → exit 3, `error.constraint == "foreign_key"` |
| `test_list_terms_returns_ndjson` | AC3.1 | seed + link; `tm document list-terms <doc-id>` returns NDJSON of Term rows |
| `test_list_terms_for_missing_doc_exits_2` | AC1.5 | `tm document list-terms 9999` → exit 2 (mirrors `tm term list-documents 9999` in Task 4) |

Note the FK pre-existence check is bypassed for `link-term` (we only check whether the term is already linked to *that* doc). When FK violation hits, it's at the `INSERT OR IGNORE` step, which still raises for FK errors (only `OR IGNORE` ignores constraint resolutions, not FK enforcement under `PRAGMA foreign_keys = ON`).

Bless snapshots and run.

**Verification:**

Run: `uv run pytest tests/cli/test_document_terms.py -v`
Expected: every test passes.

**Commit:** `test(cli): junction tests for document↔term link/unlink/list with FK violation`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Final operational verification

**Type:** Infrastructure (verification only).

**Files:** none.

**Verification:**

Run: `make lint`
Expected: clean.

Run: `make test`
Expected: all tests pass — Phase 1, 2, 3.

Run: `uv run tm --help`
Expected: lists `document`, `term`, `observation` (no other subgroups yet).

End-to-end smoke:

```bash
DOC_ID=$(uv run tm document create --title=t --author=a --content=c | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
TERM_ID=$(uv run tm term create --term=alpha --definition=def | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
uv run tm document link-term "$DOC_ID" "$TERM_ID"
uv run tm document list-terms "$DOC_ID"
uv run tm term list-documents "$TERM_ID"
uv run tm document link-term "$DOC_ID" "$TERM_ID"   # idempotent: linked=false
uv run tm document unlink-term "$DOC_ID" "$TERM_ID"
uv run tm document link-term "$DOC_ID" 99999 2>&1 1>/dev/null   # FK violation
```

Expected: each step produces parseable JSON; the FK violation step prints a JSON error with `error.constraint == "foreign_key"` and exits 3; everything else exits 0.

**Commit:** none. Use `chore(cli): phase 3 verification fix-ups` for any fix-ups.
<!-- END_TASK_7 -->

---

## Phase 3 — Done When

- `tests/cli/test_terms.py`, `test_observations.py`, `test_document_terms.py` (and their `*_help.py` siblings) are green.
- `make lint`, `make test` clean.
- `tm term`, `tm observation` subgroups are wired into the root group.
- `tm document link-term/unlink-term/list-terms` are present.
- `--if-not-exists` works on Term but is a documented no-op on Document/Observation.
- UNIQUE violation on duplicate term and FK violation on link-term both exit 3 with the right `constraint` value in stderr JSON.
