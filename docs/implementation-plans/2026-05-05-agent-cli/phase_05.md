# Agent CLI — Phase 5: Node (polymorphic, 3 variants)

**Goal:** Establish the polymorphic-create/update pattern with explicit-type subcommands. Add the container-side parent verbs (`set-parent`, `clear-parent`, `parent-of`) on `tm node` so any node can be placed in (or removed from) a container.

**Architecture:** `tm node` ships hand-written variant subcommands rather than a single generic command — the Click `Choice` for `--type` would only validate the discriminator at parse time, not the per-variant required field set. Each variant subcommand exposes only the flags that belong to its variant (e.g., `tm node create process` does not show `--storage-type`, and `tm node create data-store` does not show `--trust-level`). On `update`, the variant subcommand is also explicit, and the repo enforces the type match: `NodeRepository.update` raises `ValueError("type mismatch: row is data_store, patch is process")` when the variant doesn't align — `map_exception` translates this to a `UserError` (exit 1) with a hint extracted from the message. Container-membership commands on `tm node` call `ContainerRepository`'s `set_parent`/`clear_parent`/`parent_of` methods directly because membership is a property of the parent table. List/get/delete/search remain non-variant and return polymorphic Pydantic models (each row carries its own `type` discriminator).

**Intentional deviation from the design's "small builder":** the design plan sketches "a small builder in nodes.py (or _options.py if reused) that takes a Pydantic model class and returns a list of Click options derived from `model_fields`." Phase 5 hand-codes the six variant subcommands (3 Node × 2 verbs) instead. Reasoning: at this scale (Phase 6 adds 4 more in Container) the builder abstraction adds indirection that obscures what each subcommand accepts and complicates `tm commands --json` output, while the per-variant idioms differ enough to require special-casing anyway (`--assumption` is `multiple=True` on Process, but `--out-of-scope/--no-out-of-scope` is a paired bool on ExternalEntity, and `--contains-pii` / `--encryption-at-rest` on DataStore are required paired bools). Hand-coding is more readable for both the executor following this plan AND for agents introspecting the CLI tree.

**Tech Stack:** Same as previous phases.

**Scope:** Phase 5 of 8 from `docs/design-plans/2026-05-05-agent-cli.md`.

**Codebase verified:** 2026-05-05.
- `NodeRepository`: `create(diagram_id, NodeCreate)`, `get(node_id) -> Node | None`, `update(node_id, NodeUpdate) -> Node | None` (raises `ValueError` on type mismatch), `delete(node_id)`, `list(diagram_id, *, type=None, limit, offset)`, `search(diagram_id, text=None, *, type=None, limit, offset)`.
- `NodeCreate = Annotated[ProcessNodeCreate | ExternalEntityNodeCreate | DataStoreNodeCreate, Field(discriminator="type")]`. Each Create class has `type: Literal[...]` with a default value, so callers can omit `type` only when constructing a specific variant; the CLI sets it explicitly to match the subcommand.
- `NodeUpdate = ProcessNodeUpdate | ExternalEntityNodeUpdate | DataStoreNodeUpdate` — **NOT** wrapped in `Annotated` with a discriminator. Callers pass one of the three Update classes directly. The repo dispatches on the row's existing `type` and rejects mismatches.
- Variant fields:
  - `ProcessNodeCreate`: `name`, `description`, `trust_level: TrustLevel`, `assumptions: list[str]` (default `[]`).
  - `ExternalEntityNodeCreate`: `name`, `description`, `entity_type: ExternalEntityType`, `out_of_scope: bool` (default `False`).
  - `DataStoreNodeCreate`: `name`, `description`, `storage_type: StorageType`, `contains_pii: bool` (required), `encryption_at_rest: bool` (required).
- `ContainerRepository.set_parent(child_id, parent_container_id)` validates: same diagram, acyclicity (walks ancestor chain), child-kind restriction (nodes and containers only). Raises `ValueError` with descriptive messages on each violation. `clear_parent(child_id) -> bool`, `parent_of(child_id) -> Container | None`.

**External dependencies verified:** none new. Pydantic v2's `model_fields` introspection is reused indirectly (each variant's fields are mapped to Click options by hand for clarity).

---

## Acceptance Criteria Coverage

This phase implements and tests:

### agent-cli.AC1: Standard CRUDL behaviors (universal across entities)
- **agent-cli.AC1.1 Success** [Node]
- **agent-cli.AC1.2 Success** [Node]
- **agent-cli.AC1.3 Success** [Node — exercised on every variant]
- **agent-cli.AC1.4 Success** [Node]
- **agent-cli.AC1.5 Failure** [Node]
- **agent-cli.AC1.6 Failure** [Node]
- **agent-cli.AC1.7 Failure** [Node — invalid `trust_level` / `entity_type` / `storage_type` enum value rejected by Click `Choice`]

### agent-cli.AC2: Search
- **agent-cli.AC2.4 Success:** `tm node search "..." --type=process` filters results to the named variant.

### agent-cli.AC3: Junctions
- **agent-cli.AC3.4 Success:** `tm container set-parent` followed by `tm container parent-of` round-trips. (Phase 5 covers the **node-side** half: `tm node set-parent` + `tm node parent-of`; the symmetric container-side commands land in Phase 6.)

### agent-cli.AC8: Polymorphism (Node, Container)
- **agent-cli.AC8.1 Success:** `tm node create process|external-entity|data-store` dispatches to the correct variant; each subcommand exposes only its variant's fields as flags.
- **agent-cli.AC8.2 Success:** `tm node update process <id>` against a process row updates the row and returns the updated process node.
- **agent-cli.AC8.3 Failure:** `tm node update process <data-store-id>` exits 1 with `error.code = "user_error"` and a hint identifying the actual row type.
- **agent-cli.AC8.5 Success:** `--type` filter on `list` and `search` restricts results to the named variant.

**Deferred (per design):**
- `agent-cli.AC3.5` (cross-diagram set-parent) and `agent-cli.AC3.6` (cycle) — Phase 6 (Container) provides the test scaffolding (multiple containers across multiple diagrams) needed to exercise both. We surface them on `tm node` here but Phase 6 owns the failure-path tests because containers are needed to construct the setups.
- `agent-cli.AC8.4` (Container variants) — Phase 6.

---

## Required reading for the executor

- `/Users/josh/code/tm-cli/src/tm_cli/db/CLAUDE.md` (DFD subdomain: discriminated unions, type-match invariant on update).
- `/Users/josh/code/tm-cli/src/tm_cli/db/dfd_models.py` (variant model fields and literals).
- `/Users/josh/code/tm-cli/src/tm_cli/db/dfd_nodes.py` (NodeRepository — exact `update` error message).
- `/Users/josh/code/tm-cli/src/tm_cli/db/dfd_containers.py` (ContainerRepository.set_parent/clear_parent/parent_of).
- Phase 4 deliverable `src/tm_cli/cli/items.py` as the template for DFD entity commands with the resolver.

The executor should activate these skills if relevant in their session:
- `house-style:writing-good-tests`
- `ed3d-plan-and-execute:test-driven-development`
- `ed3d-plan-and-execute:verification-before-completion`

---

<!-- START_TASK_1 -->
### Task 1: `tm node` non-variant commands (list / get / delete / search with `--type` filter)

**Type:** Functionality (tests in Task 5).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/nodes.py` (with the non-variant commands and the group). Variant commands and membership commands are added in Tasks 2–4 to keep diffs reviewable.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/main.py` (register `node_group`).

**Implementation:**

Pattern matches `items.py`. The `--type` filter accepts `NodeType` literal values via `click.Choice`.

```python
"""tm node — Node (polymorphic) CRUDL + search + container membership subgroup."""

from __future__ import annotations

from typing import Any, get_args

import click

from tm_cli.cli._errors import NotFoundError
from tm_cli.cli._options import (
    apply_sort,
    dfd_diagram_id_option,
    json_fields_option,
    list_options,
    parse_json_fields,
    resolve_default_diagram_id,
)
from tm_cli.cli._output import emit, project_fields
from tm_cli.db import NodeRepository, NodeType, connect

_NODE_TYPE_CHOICES = list(get_args(NodeType))


@click.group(name="node")
def node_group() -> None:
    """Manage DFD nodes (process, external_entity, data_store)."""


@node_group.command(name="list")
@list_options
@dfd_diagram_id_option
@click.option("--type", "node_type", type=click.Choice(_NODE_TYPE_CHOICES), default=None,
              help="Filter to a single node variant.")
@json_fields_option
@click.pass_context
def list_nodes(ctx, *, limit, offset, sort_field, order, diagram_id, node_type, json_fields) -> None:
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = NodeRepository(conn).list(resolved, type=node_type, limit=limit, offset=offset)
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
    payload = project_fields(row.model_dump(mode="json"), parse_json_fields(json_fields))
    emit(ctx, payload)


@node_group.command(name="delete")
@click.argument("node_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False)
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
@click.option("--type", "node_type", type=click.Choice(_NODE_TYPE_CHOICES), default=None)
@json_fields_option
@click.pass_context
def search_nodes(ctx, text, *, limit, offset, sort_field, order, diagram_id, node_type, json_fields) -> None:
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
```

Register the group in `main.py`.

**Verification:**

Run: `uv run tm node --help`
Expected: lists `list`, `get`, `delete`, `search` (the variant create/update commands are added later in this phase but won't appear yet).

**Commit:** `feat(cli): add tm node list/get/delete/search with --type filter`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `tm node create` variant subcommands

**Type:** Functionality (tests in Task 6).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/nodes.py` (add the `create` subgroup with three subcommands).

**Implementation:**

`tm node create` is itself a `click.Group` so that variant subcommands hang off it (`tm node create process`, `tm node create external-entity`, `tm node create data-store`). Each subcommand:

1. Accepts only its variant's fields (plus the universal `--stdin`, `--if-not-exists`, `--dry-run`, hidden `--diagram-id`).
2. Builds the variant's `*Create` Pydantic model.
3. Calls `NodeRepository.create(resolved_diagram_id, model)`.
4. Emits the resulting row including `diagram_id` in the envelope.

`--assumption` for ProcessNode is `multiple=True` (zero-or-many).

```python
from tm_cli.db import (
    DataStoreNodeCreate,
    ExternalEntityNodeCreate,
    ExternalEntityType,
    ProcessNodeCreate,
    StorageType,
    TrustLevel,
)
from tm_cli.cli._stdin import enforce_stdin_exclusive, read_json_stdin

_TRUST_LEVEL_CHOICES = list(get_args(TrustLevel))
_EXTERNAL_ENTITY_TYPE_CHOICES = list(get_args(ExternalEntityType))
_STORAGE_TYPE_CHOICES = list(get_args(StorageType))


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


@create_node_group.command(name="process")
@dfd_diagram_id_option
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--trust-level", "trust_level", type=click.Choice(_TRUST_LEVEL_CHOICES), default=None)
@click.option("--assumption", "assumptions", multiple=True, default=(),
              help="Repeatable. Each --assumption adds one item to the assumptions list.")
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False,
              help="No-op for Node (no natural key); kept for command-shape consistency.")
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_process(ctx, *, diagram_id, name, description, trust_level, assumptions, use_stdin, if_not_exists, dry_run) -> None:
    """Create a process node."""
    enforce_stdin_exclusive(use_stdin, {
        "name": name, "description": description, "trust_level": trust_level,
        "assumptions": list(assumptions) if assumptions else None,
    })
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
            raise click.UsageError("--name, --description, and --trust-level are required (or use --stdin)")
        body = {
            "type": "process",
            "name": name,
            "description": description,
            "trust_level": trust_level,
            "assumptions": list(assumptions),
        }

    if isinstance(body, list):
        models = [ProcessNodeCreate.model_validate(item) for item in body]
        if dry_run:
            emit(ctx, {"dry_run": True, "would_create": [m.model_dump(mode="json") for m in models]})
            return
        with connect() as conn:
            resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
            assert resolved is not None
            repo = NodeRepository(conn)
            created = [repo.create(resolved, m) for m in models]
        emit(ctx, [{"diagram_id": str(resolved), **c.model_dump(mode="json")} for c in created])
        return

    model = ProcessNodeCreate.model_validate(body)
    _create_variant(ctx, diagram_id, model, dry_run)


@create_node_group.command(name="external-entity")
@dfd_diagram_id_option
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--entity-type", "entity_type", type=click.Choice(_EXTERNAL_ENTITY_TYPE_CHOICES), default=None)
@click.option("--out-of-scope/--no-out-of-scope", "out_of_scope", default=None,
              help="Set the out_of_scope flag (default False if neither flag given).")
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_external_entity(ctx, *, diagram_id, name, description, entity_type, out_of_scope, use_stdin, if_not_exists, dry_run) -> None:
    """Create an external entity node."""
    enforce_stdin_exclusive(use_stdin, {
        "name": name, "description": description, "entity_type": entity_type, "out_of_scope": out_of_scope,
    })
    if use_stdin:
        body = read_json_stdin()
        if isinstance(body, dict):
            body.setdefault("type", "external_entity")
    else:
        if name is None or description is None or entity_type is None:
            raise click.UsageError("--name, --description, and --entity-type are required (or use --stdin)")
        body = {
            "type": "external_entity",
            "name": name,
            "description": description,
            "entity_type": entity_type,
            "out_of_scope": bool(out_of_scope) if out_of_scope is not None else False,
        }

    model = ExternalEntityNodeCreate.model_validate(body)
    _create_variant(ctx, diagram_id, model, dry_run)


@create_node_group.command(name="data-store")
@dfd_diagram_id_option
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--storage-type", "storage_type", type=click.Choice(_STORAGE_TYPE_CHOICES), default=None)
@click.option("--contains-pii/--no-contains-pii", "contains_pii", default=None)
@click.option("--encryption-at-rest/--no-encryption-at-rest", "encryption_at_rest", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_data_store(ctx, *, diagram_id, name, description, storage_type, contains_pii, encryption_at_rest, use_stdin, if_not_exists, dry_run) -> None:
    """Create a data store node."""
    enforce_stdin_exclusive(use_stdin, {
        "name": name, "description": description, "storage_type": storage_type,
        "contains_pii": contains_pii, "encryption_at_rest": encryption_at_rest,
    })
    if use_stdin:
        body = read_json_stdin()
        if isinstance(body, dict):
            body.setdefault("type", "data_store")
    else:
        if name is None or description is None or storage_type is None or contains_pii is None or encryption_at_rest is None:
            raise click.UsageError(
                "--name, --description, --storage-type, --contains-pii/--no-contains-pii, "
                "and --encryption-at-rest/--no-encryption-at-rest are required (or use --stdin)"
            )
        body = {
            "type": "data_store",
            "name": name,
            "description": description,
            "storage_type": storage_type,
            "contains_pii": contains_pii,
            "encryption_at_rest": encryption_at_rest,
        }

    model = DataStoreNodeCreate.model_validate(body)
    _create_variant(ctx, diagram_id, model, dry_run)
```

**Batch-stdin paths for ExternalEntity and DataStore.** The pattern mirrors `create_process`'s `isinstance(body, list)` branch verbatim — only the `*Create` class differs. The executor MUST implement all three. Stubs:

```python
# In create_external_entity, between the body-construction and `model = ExternalEntityNodeCreate.model_validate(body)`:
    if isinstance(body, list):
        models = []
        for index, item in enumerate(body):
            if isinstance(item, dict):
                item.setdefault("type", "external_entity")
            try:
                models.append(ExternalEntityNodeCreate.model_validate(item))
            except ValidationError as e:
                raise map_exception(e, input_payload={"index": index, "item": item}) from e
        if dry_run:
            emit(ctx, {"dry_run": True, "would_create": [m.model_dump(mode="json") for m in models]})
            return
        with connect() as conn:
            resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
            assert resolved is not None
            repo = NodeRepository(conn)
            created = [repo.create(resolved, m) for m in models]
        emit(ctx, [{"diagram_id": str(resolved), **c.model_dump(mode="json")} for c in created])
        return

# In create_data_store, the equivalent block uses DataStoreNodeCreate and `item.setdefault("type", "data_store")`.
```

These blocks belong inside their respective variant functions, immediately after the body-construction logic and before the single-object `model_validate` call. Without them, `--stdin` with a JSON array on `tm node create external-entity` or `tm node create data-store` would either fail or silently process only the first element.

**Verification:**

Run: `uv run tm node create --help`
Expected: lists `process`, `external-entity`, `data-store`.

Run: `uv run tm node create process --help`
Expected: shows `--name`, `--description`, `--trust-level`, `--assumption`, `--stdin`, `--if-not-exists`, `--dry-run`. Does NOT show `--storage-type`, `--entity-type`.

Run: `uv run tm node create data-store --help`
Expected: shows `--storage-type`, `--contains-pii/--no-contains-pii`, `--encryption-at-rest/--no-encryption-at-rest`. Does NOT show `--trust-level`, `--assumption`.

**Commit:** `feat(cli): add tm node create variant subcommands (process|external-entity|data-store)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `tm node update` variant subcommands (with type-match enforcement)

**Type:** Functionality (tests in Task 6).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/nodes.py`.

**Implementation:**

Same pattern as create: a `tm node update` group with three subcommands, each accepting only its variant's optional fields. The repo's `update` raises `ValueError` on type mismatch; `map_exception` translates to `UserError`.

To make the error message more useful (per AC8.3 — "exits 1 with a hint identifying the actual row type"), the CLI:
1. Calls `repo.get(node_id)` first.
2. If the row exists but `row.type != expected_type`, raises `UserError` directly with a hint: `"Type mismatch: row id={id} is {actual_type}, but the {expected_type} variant subcommand was used. Use 'tm node update {actual_type} {id}' instead."`
3. If the row exists and types match, dispatches to `repo.update(node_id, patch)`.
4. If the row doesn't exist, raises `NotFoundError`.

This mirrors the repo's behavior (the repo would also reject) but produces a friendlier message and avoids a second DB write attempt.

```python
from tm_cli.cli._errors import UserError
from tm_cli.db import (
    DataStoreNodeUpdate,
    ExternalEntityNodeUpdate,
    ProcessNodeUpdate,
)


@node_group.group(name="update")
def update_node_group() -> None:
    """Update a node of a specific variant. The variant must match the row's existing type."""


def _ensure_variant(node_id: int, expected_type: str) -> None:
    """Pre-flight: confirm the row exists and matches the expected variant."""
    with connect() as conn:
        row = NodeRepository(conn).get(node_id)
    if row is None:
        raise NotFoundError(f"Node id={node_id} not found", id=str(node_id))
    if row.type != expected_type:
        raise UserError(
            f"Type mismatch: row id={node_id} is {row.type}, but the {expected_type} variant subcommand was used.",
            hint=f"Use 'tm node update {row.type} {node_id}' instead.",
        )


def _apply_variant_update(ctx, node_id, patch, dry_run) -> None:
    if dry_run:
        emit(ctx, {"dry_run": True, "would_update": {"id": str(node_id), "patch": patch.model_dump(mode="json", exclude_none=True)}})
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
@click.option("--trust-level", "trust_level", type=click.Choice(_TRUST_LEVEL_CHOICES), default=None)
@click.option("--assumption", "assumptions", multiple=True, default=None,
              help="Repeatable. Pass to replace the assumptions list. Omit to leave unchanged.")
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_process(ctx, node_id, *, name, description, trust_level, assumptions, use_stdin, dry_run) -> None:
    """Update a process node."""
    _ensure_variant(node_id, "process")
    enforce_stdin_exclusive(use_stdin, {
        "name": name, "description": description, "trust_level": trust_level,
        "assumptions": list(assumptions) if assumptions else None,
    })
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body: dict[str, Any] = {}
        if name is not None: body["name"] = name
        if description is not None: body["description"] = description
        if trust_level is not None: body["trust_level"] = trust_level
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
@click.option("--entity-type", "entity_type", type=click.Choice(_EXTERNAL_ENTITY_TYPE_CHOICES), default=None)
@click.option("--out-of-scope/--no-out-of-scope", "out_of_scope", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_external_entity(ctx, node_id, *, name, description, entity_type, out_of_scope, use_stdin, dry_run) -> None:
    """Update an external entity node."""
    _ensure_variant(node_id, "external_entity")
    enforce_stdin_exclusive(use_stdin, {
        "name": name, "description": description,
        "entity_type": entity_type, "out_of_scope": out_of_scope,
    })
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body: dict[str, Any] = {}
        if name is not None: body["name"] = name
        if description is not None: body["description"] = description
        if entity_type is not None: body["entity_type"] = entity_type
        if out_of_scope is not None: body["out_of_scope"] = out_of_scope
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = ExternalEntityNodeUpdate.model_validate(body)
    _apply_variant_update(ctx, node_id, patch, dry_run)


@update_node_group.command(name="data-store")
@click.argument("node_id", type=click.INT)
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--storage-type", "storage_type", type=click.Choice(_STORAGE_TYPE_CHOICES), default=None)
@click.option("--contains-pii/--no-contains-pii", "contains_pii", default=None)
@click.option("--encryption-at-rest/--no-encryption-at-rest", "encryption_at_rest", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_data_store(ctx, node_id, *, name, description, storage_type, contains_pii, encryption_at_rest, use_stdin, dry_run) -> None:
    """Update a data store node."""
    _ensure_variant(node_id, "data_store")
    enforce_stdin_exclusive(use_stdin, {
        "name": name, "description": description, "storage_type": storage_type,
        "contains_pii": contains_pii, "encryption_at_rest": encryption_at_rest,
    })
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body: dict[str, Any] = {}
        if name is not None: body["name"] = name
        if description is not None: body["description"] = description
        if storage_type is not None: body["storage_type"] = storage_type
        if contains_pii is not None: body["contains_pii"] = contains_pii
        if encryption_at_rest is not None: body["encryption_at_rest"] = encryption_at_rest
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = DataStoreNodeUpdate.model_validate(body)
    _apply_variant_update(ctx, node_id, patch, dry_run)
```

**Verification:**

Run: `uv run tm node update --help`
Expected: lists `process`, `external-entity`, `data-store`.

**Commit:** `feat(cli): add tm node update variant subcommands with type-match preflight`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Container-membership commands on `tm node` (set-parent / clear-parent / parent-of)

**Type:** Functionality (tests in Task 7).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/nodes.py`.

**Implementation:**

Three commands. They open a connection, dispatch to `ContainerRepository`, and emit a small envelope.

```python
from tm_cli.db import ContainerRepository


@node_group.command(name="set-parent")
@click.argument("node_id", type=click.INT)
@click.argument("container_id", type=click.INT)
@click.pass_context
def set_parent(ctx, node_id: int, container_id: int) -> None:
    """Place ``node_id`` inside the container ``container_id`` (same diagram, no cycle)."""
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
    payload = project_fields(parent.model_dump(mode="json"), parse_json_fields(json_fields))
    emit(ctx, {"id": str(node_id), "parent": payload})
```

`set-parent` does not pre-check the node exists — the repo raises `ValueError("Unknown child entity id: ...")` which `map_exception` routes to `UserError` (exit 1). The repo's error message is sufficient as the user-facing hint.

`clear-parent` is idempotent: if the node had no parent, `cleared=False`; otherwise `cleared=True`.

**Verification:**

Run: `uv run tm node set-parent --help`
Expected: shows two positional args `NODE_ID` and `CONTAINER_ID`.

**Commit:** `feat(cli): add container-membership commands on tm node (set-parent/clear-parent/parent-of)`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Tests for `tm node` non-variant commands

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.1`, `agent-cli.AC1.2`, `agent-cli.AC1.5`, `agent-cli.AC2.4`, `agent-cli.AC8.5`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_nodes.py`.
- Create: `/Users/josh/code/tm-cli/tests/cli/test_nodes_help.py`.

**Implementation:**

Use `db_with_seed` (one process, one external_entity, one data_store seeded). Use explicit `--diagram-id <seed.diagram_id>` so the default-diagram resolver doesn't engage; this isolates Phase 5 tests from default-diagram concerns (already tested in Phase 4).

| Test | AC | Action |
|---|---|---|
| `test_list_returns_three_seeded_node_variants` | AC1.1 | seed; `tm node list --diagram-id=<id>` returns 3 (mixed types) |
| `test_get_returns_typed_node` | AC1.2 | `tm node get <process_id>` → JSON has `type=="process"` |
| `test_list_filtered_by_type_process` | AC2.4, AC8.5 | `tm node list --diagram-id=<id> --type=process` → 1 row |
| `test_list_filtered_by_type_data_store` | AC2.4, AC8.5 | `tm node list --diagram-id=<id> --type=data_store` → 1 row |
| `test_search_filtered_by_type` | AC2.4, AC8.5 | `tm node search seed --diagram-id=<id> --type=process` → 1 row |
| `test_search_text_only_returns_all_matching` | AC2.1 | `tm node search seed --diagram-id=<id>` → 3 rows |
| `test_get_missing_id_exits_2` | AC1.5 | `tm node get 99999` |
| `test_invalid_type_filter_value_exits_1` | AC1.7 | `tm node list --diagram-id=<id> --type=bogus` → exit 1, `error.code == "user_error"` |

`tests/cli/test_nodes_help.py` snapshots `tm node`, `tm node list/get/delete/search`, `tm node create`, `tm node create process|external-entity|data-store`, `tm node update`, `tm node update process|external-entity|data-store`, `tm node set-parent`, `tm node clear-parent`, `tm node parent-of` `--help` output (16 snapshots total once Tasks 2–4 are merged).

**Verification:**

Run: `uv run pytest tests/cli/test_nodes.py tests/cli/test_nodes_help.py -v`
Expected: every test passes.

**Commit:** `test(cli): tm node CRUDL + filter coverage`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Tests for variant create / update + type-mismatch failure

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.3`, `agent-cli.AC1.4`, `agent-cli.AC1.6`, `agent-cli.AC1.7`, `agent-cli.AC8.1`, `agent-cli.AC8.2`, `agent-cli.AC8.3`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_node_variants.py`.

**Implementation:**

Tests cover each variant for create, each for update, plus the cross-variant error path.

| Test | AC | Action |
|---|---|---|
| `test_create_process_returns_process_node` | AC1.3, AC8.1 | `tm node create process --name=p --description=d --trust-level=admin --assumption a1 --assumption a2 --diagram-id=<id>` → JSON `{type: "process", name: "p", trust_level: "admin", assumptions: ["a1", "a2"], ...}` |
| `test_create_external_entity_returns_external_entity_node` | AC1.3, AC8.1 | `tm node create external-entity --name=e --description=d --entity-type=user --out-of-scope --diagram-id=<id>` → JSON `{type: "external_entity", entity_type: "user", out_of_scope: true, ...}` |
| `test_create_data_store_returns_data_store_node` | AC1.3, AC8.1 | `tm node create data-store --name=ds --description=d --storage-type=database --contains-pii --no-encryption-at-rest --diagram-id=<id>` → JSON `{type: "data_store", contains_pii: true, encryption_at_rest: false, ...}` |
| `test_create_with_invalid_trust_level_exits_1` | AC1.7 | `tm node create process --trust-level=bogus ...` → exit 1, `error.code == "user_error"` |
| `test_create_data_store_missing_required_bool_exits_1` | AC5.1 | `tm node create data-store --name=x --description=y --storage-type=cache --contains-pii ...` (omit `--encryption-at-rest`) → exit 1 |
| `test_update_process_returns_updated_process_node` | AC1.4, AC8.2 | seed; `tm node update process <process_id> --trust-level=system` → JSON `{type: "process", trust_level: "system", ...}` |
| `test_update_external_entity` | AC1.4, AC8.2 | seed; `tm node update external-entity <id> --out-of-scope` |
| `test_update_data_store` | AC1.4, AC8.2 | seed; `tm node update data-store <id> --no-contains-pii` |
| `test_update_process_against_data_store_exits_1_with_hint` | AC8.3 | seed; `tm node update process <data_store_id> --trust-level=system` → exit 1; stderr `error.code == "user_error"`; `error.hint` mentions `tm node update data-store <id>` |
| `test_update_missing_id_exits_2` | AC1.6 | `tm node update process 99999 --trust-level=admin` |
| `test_update_no_fields_exits_1` | (edge) | `tm node update process <id>` (no flags, no --stdin) → exit 1 |

A representative test:

```python
import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_create_process_returns_process_node(db_with_seed) -> None:
    db_path, seed_ids = db_with_seed
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, [
        "node", "create", "process",
        "--diagram-id", str(seed_ids.diagram_id),
        "--name", "Worker",
        "--description", "background process",
        "--trust-level", "admin",
        "--assumption", "always-up",
        "--assumption", "ipv4-only",
    ])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["type"] == "process"
    assert payload["trust_level"] == "admin"
    assert payload["assumptions"] == ["always-up", "ipv4-only"]


def test_update_process_against_data_store_exits_1_with_hint(db_with_seed) -> None:
    _, seed_ids = db_with_seed
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, [
        "node", "update", "process", str(seed_ids.data_store_node_id),
        "--trust-level", "system",
    ])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    hint = payload["error"].get("hint", "")
    assert "tm node update data-store" in hint
```

**Verification:**

Run: `uv run pytest tests/cli/test_node_variants.py -v`
Expected: every test passes.

**Commit:** `test(cli): polymorphic node create/update + type-mismatch hint`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Tests for container-membership commands on `tm node`

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC3.4` (node-side half).

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_node_membership.py`.

**Implementation:**

The seeded fixture includes one container in the same diagram as the process node. Tests:

| Test | AC | Action |
|---|---|---|
| `test_set_parent_then_parent_of_round_trips` | AC3.4 | seed; `tm node set-parent <process_id> <container_id>` → `{"child_id": "<process>", "parent_id": "<container>"}`; `tm node parent-of <process_id>` → `{id, parent: {<container row>}}` |
| `test_clear_parent_removes_membership` | AC3.4 | seed; set-parent then clear-parent then parent-of → `{id, parent: null}` |
| `test_clear_parent_idempotent_when_unmembered` | AC3.4 | seed; clear-parent without set-parent → `{cleared: false, id: ...}`, exit 0 |
| `test_set_parent_unknown_child_exits_1` | AC5.1 | seed; `tm node set-parent 99999 <container>` → exit 1, `error.code == "user_error"` |
| `test_set_parent_unknown_parent_exits_1` | AC5.1 | seed; `tm node set-parent <process_id> 99999` → exit 1 |

(Cross-diagram and cycle tests are deferred to Phase 6; they require multi-diagram setups that are owned by the Container subcommand suite.)

**Verification:**

Run: `uv run pytest tests/cli/test_node_membership.py -v`
Expected: every test passes.

**Commit:** `test(cli): tm node set-parent/clear-parent/parent-of round-trips and validation`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Final operational verification

**Type:** Infrastructure (verification only).

**Files:** none.

**Verification:**

Run: `make lint`
Expected: clean.

Run: `make test`
Expected: every Phase 1–5 test passes.

End-to-end smoke (against `TM_DB_PATH`):

```bash
DI=$(uv run tm diagram create --name=phase5-smoke | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
PI=$(uv run tm node create process --diagram-id "$DI" --name=p --description=d --trust-level=admin | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
DS=$(uv run tm node create data-store --diagram-id "$DI" --name=ds --description=d --storage-type=cache --contains-pii --encryption-at-rest | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
uv run tm node list --diagram-id "$DI" --type=process
uv run tm node update process "$PI" --trust-level=system
uv run tm node update process "$DS" 2>&1 1>/dev/null     # type mismatch
```

Expected: each step exits 0 except the last one, which exits 1 with `error.code == "user_error"` and a hint pointing at `tm node update data-store`.

**Commit:** none. Use `chore(cli): phase 5 verification fix-ups` for any fix-ups.
<!-- END_TASK_8 -->

---

## Phase 5 — Done When

- `tm node list/get/delete/search` work with `--type` filtering.
- `tm node create process|external-entity|data-store` accept exactly the variant's fields.
- `tm node update process|external-entity|data-store <id>` enforces type match before dispatching to the repo, with a friendly hint on mismatch.
- `tm node set-parent / clear-parent / parent-of` work end-to-end (positive paths).
- Every test file in this phase is green.
- `make lint` clean.
- The pattern in `nodes.py` is the template for `containers.py` in Phase 6.
