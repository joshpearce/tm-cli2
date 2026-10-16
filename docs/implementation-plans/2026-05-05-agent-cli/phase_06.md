# Agent CLI — Phase 6: Container (polymorphic, 2 variants) + container_membership reverse

**Goal:** Apply the Phase 5 polymorphic pattern to Container (two variants instead of three), and add the parent-side membership verbs that Phase 5 only covered from the child side. Specifically: `tm container set-parent`, `clear-parent`, `parent-of`, `list-children` (with heterogeneous Node|Container output). This phase also closes out the membership failure paths (cross-diagram, cycle) since multi-diagram tests are easier to author with containers as the test scaffolding.

**Architecture:** Mirrors Phase 5's `nodes.py`. The two variants (`trust_boundary`, `container`) share `name`/`description`; trust boundaries additionally take `privilege_level`. The `list-children` command returns a mixed list of Pydantic nodes and containers — each row already carries its own `type` discriminator field, so consumers can route on it client-side without any extra envelope. The repo's `children_of()` returns `list[Node | Container]`; the CLI emits each row's `model_dump(mode="json")` directly. Membership pre-checks (cycle, cross-diagram, kind restriction) live in `ContainerRepository.set_parent` and surface as `ValueError` → `UserError` (exit 1) with the repo's message as the user-facing hint.

**Tech Stack:** Same as previous phases.

**Scope:** Phase 6 of 8 from `docs/design-plans/2026-05-05-agent-cli.md`.

**Codebase verified:** 2026-05-05.
- `ContainerRepository`: `create(diagram_id, ContainerCreate)`, `get(container_id)`, `update(container_id, ContainerUpdate)` (raises `ValueError` on type mismatch), `delete(container_id)`, `list(diagram_id, *, type=None, limit, offset)`, `search(diagram_id, text=None, *, type=None, limit, offset)`, plus `set_parent`, `clear_parent`, `parent_of`, `children_of`.
- `ContainerCreate = Annotated[TrustBoundaryCreate | ContainerVariantCreate, Field(discriminator="type")]`. `ContainerUpdate = TrustBoundaryUpdate | ContainerVariantUpdate` (no `Annotated` — same as Node, callers pass a specific variant).
- Variant fields:
  - `TrustBoundaryCreate`: `name`, `description`, `privilege_level: PrivilegeLevel` (`internet|dmz|corporate|restricted`).
  - `ContainerVariantCreate`: `name`, `description` (no extra fields).
- `set_parent` errors:
  - Self-parent: `"A container cannot be its own parent"`.
  - Unknown child: `"Unknown child entity id: {id}"`.
  - Wrong child kind (flow / item): `"Container children must be nodes or containers; got kind=..."`.
  - Unknown parent: `"Unknown container id: {id}"`.
  - Cross-diagram: `"Child and parent must belong to the same diagram"`.
  - Cycle: `"Setting this parent would introduce a container hierarchy cycle"`.
  - These map to `UserError` (exit 1); the repo message is the `hint` payload.
- `children_of()` returns rows in stable order (the repo orders by `entity.id` ascending). Each row is a fully realized Pydantic `Node` or `Container` discriminated-union value.

**External dependencies verified:** none new.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### agent-cli.AC1: Standard CRUDL behaviors (universal across entities)
- **agent-cli.AC1.1 Success** [Container]
- **agent-cli.AC1.2 Success** [Container]
- **agent-cli.AC1.3 Success** [Container]
- **agent-cli.AC1.4 Success** [Container]
- **agent-cli.AC1.5 Failure** [Container]
- **agent-cli.AC1.6 Failure** [Container]

### agent-cli.AC3: Junctions
- **agent-cli.AC3.4 Success:** `tm container set-parent` followed by `tm container parent-of` round-trips; `tm container list-children` includes the new child with a `type` discriminator.
- **agent-cli.AC3.5 Failure:** `set-parent` across diagrams exits 1 with a hint naming the cross-diagram constraint.
- **agent-cli.AC3.6 Failure:** `set-parent` that would create a cycle exits 1 with a cycle-detected hint.

### agent-cli.AC8: Polymorphism
- **agent-cli.AC8.1 Success** [Container variants]
- **agent-cli.AC8.4 Success:** `tm container create trust-boundary|container` dispatches correctly; matching `update` subcommands enforce the type-match rule.
- **agent-cli.AC8.5 Success** [Container `--type` filter]

---

## Required reading for the executor

- `/Users/josh/code/tm-cli/src/tm_cli/db/dfd_models.py` (TrustBoundary*, ContainerVariant*).
- `/Users/josh/code/tm-cli/src/tm_cli/db/dfd_containers.py` (ContainerRepository — exact `set_parent` error messages).
- Phase 5 deliverable `src/tm_cli/cli/nodes.py` as the template.

---

<!-- START_TASK_1 -->
### Task 1: `tm container` non-variant commands (list / get / delete / search with `--type` filter)

**Type:** Functionality (tests in Task 5).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/containers.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/main.py` (register `container_group`).

**Implementation:**

Mirror `nodes.py` Task 1 byte-for-byte, swapping `Node` for `Container` and `NodeType` for `ContainerType`. The `--type` filter is `click.Choice(get_args(ContainerType))` = `["trust_boundary", "container"]`.

Skeleton:

```python
"""tm container — Container (polymorphic) CRUDL + search + membership subgroup."""

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
    ContainerType,
    ContainerVariantCreate,
    ContainerVariantUpdate,
    PrivilegeLevel,
    TrustBoundaryCreate,
    TrustBoundaryUpdate,
    connect,
)


_CONTAINER_TYPE_CHOICES = list(get_args(ContainerType))
_PRIVILEGE_LEVEL_CHOICES = list(get_args(PrivilegeLevel))


@click.group(name="container")
def container_group() -> None:
    """Manage DFD containers (trust_boundary, container)."""

# list, get, delete, search — copy from nodes.py with substitutions.
```

Implement `list`, `get`, `delete`, `search` with the same flag stack as `tm node`. Register the group in `main.py`.

**Verification:**

Run: `uv run tm container --help`
Expected: lists `list`, `get`, `delete`, `search` (variant create/update added in Tasks 2–3).

**Commit:** `feat(cli): add tm container list/get/delete/search with --type filter`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `tm container create` variant subcommands

**Type:** Functionality (tests in Task 6).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/containers.py`.

**Implementation:**

```python
@container_group.group(name="create")
def create_container_group() -> None:
    """Create a container of a specific variant."""


def _create_container(ctx, diagram_id, model, dry_run) -> None:
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        assert resolved is not None
        created = ContainerRepository(conn).create(resolved, model)
    emit(ctx, {"diagram_id": str(resolved), **created.model_dump(mode="json")})


@create_container_group.command(name="trust-boundary")
@dfd_diagram_id_option
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--privilege-level", "privilege_level", type=click.Choice(_PRIVILEGE_LEVEL_CHOICES), default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_trust_boundary(ctx, *, diagram_id, name, description, privilege_level, use_stdin, if_not_exists, dry_run) -> None:
    """Create a trust boundary."""
    enforce_stdin_exclusive(use_stdin, {
        "name": name, "description": description, "privilege_level": privilege_level,
    })
    if use_stdin:
        body = read_json_stdin()
        if isinstance(body, dict):
            body.setdefault("type", "trust_boundary")
    else:
        if name is None or description is None or privilege_level is None:
            raise click.UsageError("--name, --description, and --privilege-level are required (or use --stdin)")
        body = {
            "type": "trust_boundary", "name": name, "description": description,
            "privilege_level": privilege_level,
        }
    model = TrustBoundaryCreate.model_validate(body)
    _create_container(ctx, diagram_id, model, dry_run)


@create_container_group.command(name="container")
@dfd_diagram_id_option
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_container_variant(ctx, *, diagram_id, name, description, use_stdin, if_not_exists, dry_run) -> None:
    """Create a generic container."""
    enforce_stdin_exclusive(use_stdin, {"name": name, "description": description})
    if use_stdin:
        body = read_json_stdin()
        if isinstance(body, dict):
            body.setdefault("type", "container")
    else:
        if name is None or description is None:
            raise click.UsageError("--name and --description are required (or use --stdin)")
        body = {"type": "container", "name": name, "description": description}
    model = ContainerVariantCreate.model_validate(body)
    _create_container(ctx, diagram_id, model, dry_run)
```

Add a batch-stdin path (list of dicts) to each variant — copy the pattern from `nodes.py:create_process`. Optional for v1 but design's `--stdin` array contract requires it.

**Verification:**

Run: `uv run tm container create --help`
Expected: lists `trust-boundary`, `container`.

Run: `uv run tm container create trust-boundary --help`
Expected: shows `--privilege-level`. Run: `uv run tm container create container --help` shows no `--privilege-level`.

**Commit:** `feat(cli): add tm container create variant subcommands (trust-boundary|container)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `tm container update` variant subcommands (with type-match enforcement)

**Type:** Functionality (tests in Task 6).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/containers.py`.

**Implementation:**

Same pattern as `tm node update`:

```python
@container_group.group(name="update")
def update_container_group() -> None:
    """Update a container of a specific variant."""


def _ensure_container_variant(container_id: int, expected_type: str) -> None:
    with connect() as conn:
        row = ContainerRepository(conn).get(container_id)
    if row is None:
        raise NotFoundError(f"Container id={container_id} not found", id=str(container_id))
    if row.type != expected_type:
        raise UserError(
            f"Type mismatch: row id={container_id} is {row.type}, but the {expected_type} variant subcommand was used.",
            hint=f"Use 'tm container update {row.type.replace('_', '-')} {container_id}' instead.",
        )


def _apply_container_update(ctx, container_id, patch, dry_run) -> None:
    if dry_run:
        emit(ctx, {"dry_run": True, "would_update": {"id": str(container_id), "patch": patch.model_dump(mode="json", exclude_none=True)}})
        return
    with connect() as conn:
        updated = ContainerRepository(conn).update(container_id, patch)
    if updated is None:
        raise NotFoundError(f"Container id={container_id} not found", id=str(container_id))
    emit(ctx, updated.model_dump(mode="json"))


@update_container_group.command(name="trust-boundary")
@click.argument("container_id", type=click.INT)
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--privilege-level", "privilege_level", type=click.Choice(_PRIVILEGE_LEVEL_CHOICES), default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_trust_boundary(ctx, container_id, *, name, description, privilege_level, use_stdin, dry_run) -> None:
    _ensure_container_variant(container_id, "trust_boundary")
    enforce_stdin_exclusive(use_stdin, {
        "name": name, "description": description, "privilege_level": privilege_level,
    })
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body: dict[str, Any] = {}
        if name is not None: body["name"] = name
        if description is not None: body["description"] = description
        if privilege_level is not None: body["privilege_level"] = privilege_level
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = TrustBoundaryUpdate.model_validate(body)
    _apply_container_update(ctx, container_id, patch, dry_run)


@update_container_group.command(name="container")
@click.argument("container_id", type=click.INT)
@click.option("--name", default=None)
@click.option("--description", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_container_variant(ctx, container_id, *, name, description, use_stdin, dry_run) -> None:
    _ensure_container_variant(container_id, "container")
    enforce_stdin_exclusive(use_stdin, {"name": name, "description": description})
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
    else:
        body: dict[str, Any] = {}
        if name is not None: body["name"] = name
        if description is not None: body["description"] = description
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = ContainerVariantUpdate.model_validate(body)
    _apply_container_update(ctx, container_id, patch, dry_run)
```

**Verification:**

Run: `uv run tm container update --help`
Expected: lists `trust-boundary`, `container`.

**Commit:** `feat(cli): add tm container update variant subcommands with type-match preflight`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Container-side membership commands (set-parent / clear-parent / parent-of / list-children)

**Type:** Functionality (tests in Task 7).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/containers.py`.

**Implementation:**

```python
@container_group.command(name="set-parent")
@click.argument("container_id", type=click.INT)
@click.argument("parent_id", type=click.INT)
@click.pass_context
def container_set_parent(ctx, container_id: int, parent_id: int) -> None:
    """Place ``container_id`` inside the container ``parent_id``."""
    with connect() as conn:
        ContainerRepository(conn).set_parent(container_id, parent_id)
    emit(ctx, {"child_id": str(container_id), "parent_id": str(parent_id)})


@container_group.command(name="clear-parent")
@click.argument("container_id", type=click.INT)
@click.pass_context
def container_clear_parent(ctx, container_id: int) -> None:
    with connect() as conn:
        existed = ContainerRepository(conn).clear_parent(container_id)
    emit(ctx, {"cleared": existed, "id": str(container_id)})


@container_group.command(name="parent-of")
@click.argument("container_id", type=click.INT)
@json_fields_option
@click.pass_context
def container_parent_of(ctx, container_id: int, *, json_fields) -> None:
    with connect() as conn:
        parent = ContainerRepository(conn).parent_of(container_id)
    if parent is None:
        emit(ctx, {"id": str(container_id), "parent": None})
        return
    payload = project_fields(parent.model_dump(mode="json"), parse_json_fields(json_fields))
    emit(ctx, {"id": str(container_id), "parent": payload})


@container_group.command(name="list-children")
@click.argument("container_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_children(ctx, container_id: int, *, limit, offset, sort_field, order, json_fields) -> None:
    """List Nodes and Containers whose parent is ``container_id`` (heterogeneous output)."""
    with connect() as conn:
        # Pre-check that the container exists; gives a friendlier error than an empty list.
        if ContainerRepository(conn).get(container_id) is None:
            raise NotFoundError(f"Container id={container_id} not found", id=str(container_id))
        rows = ContainerRepository(conn).children_of(container_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
```

`list-children` paginates client-side because `children_of()` doesn't accept limit/offset. Cardinality is small (a container holds tens of children, not thousands), so this is acceptable.

**Verification:**

Run: `uv run tm container set-parent --help`
Expected: shows two positional args.

Run: `uv run tm container list-children --help`
Expected: standard list flags.

**Commit:** `feat(cli): add tm container set-parent/clear-parent/parent-of/list-children`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Tests for `tm container` non-variant commands

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.1`, `agent-cli.AC1.2`, `agent-cli.AC1.5`, `agent-cli.AC8.5`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_containers.py`.
- Create: `/Users/josh/code/tm-cli/tests/cli/test_containers_help.py`.

**Implementation:**

Use `db_with_seed` (one container variant + one trust boundary in the seeded diagram). Tests:

| Test | AC | Action |
|---|---|---|
| `test_list_returns_two_seeded_containers` | AC1.1 | seed; `tm container list --diagram-id=<id>` returns 2 |
| `test_list_filtered_by_type_trust_boundary` | AC8.5 | seed; `--type=trust_boundary` returns 1 |
| `test_list_filtered_by_type_container` | AC8.5 | seed; `--type=container` returns 1 |
| `test_get_trust_boundary_returns_typed` | AC1.2 | `tm container get <trust_boundary_id>` → `type == "trust_boundary"`, `privilege_level == "corporate"` |
| `test_get_container_returns_typed` | AC1.2 | `tm container get <container_id>` → `type == "container"`, no `privilege_level` field |
| `test_search_text_matches_seeded_names` | AC2.1 | `tm container search seed --diagram-id=<id>` returns 2 |
| `test_get_missing_id_exits_2` | AC1.5 | `tm container get 99999` |

`tests/cli/test_containers_help.py` snapshots help for the group plus every leaf command in the `container` subgroup (~12 snapshots once Tasks 2–4 are merged).

**Commit:** `test(cli): tm container non-variant CRUDL coverage`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Tests for variant create / update + type-mismatch failure

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.3`, `agent-cli.AC1.4`, `agent-cli.AC8.1`, `agent-cli.AC8.4`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_container_variants.py`.

**Implementation:**

| Test | AC | Action |
|---|---|---|
| `test_create_trust_boundary_returns_trust_boundary` | AC1.3, AC8.1, AC8.4 | `tm container create trust-boundary --name=tb --description=d --privilege-level=corporate` → JSON `{type: "trust_boundary", privilege_level: "corporate", ...}` |
| `test_create_container_returns_container` | AC1.3, AC8.1, AC8.4 | `tm container create container --name=c --description=d` → JSON `{type: "container", ...}` (no `privilege_level`) |
| `test_create_with_invalid_privilege_level_exits_1` | AC1.7 | `--privilege-level=bogus` → exit 1 |
| `test_update_trust_boundary` | AC1.4, AC8.4 | seed; `tm container update trust-boundary <id> --privilege-level=restricted` |
| `test_update_container` | AC1.4, AC8.4 | seed; `tm container update container <id> --description="new"` |
| `test_update_trust_boundary_against_container_exits_1` | AC8.4 (mismatch) | seed; `tm container update trust-boundary <container-id> --privilege-level=corporate` → exit 1, hint mentions `tm container update container <id>` |
| `test_update_missing_id_exits_2` | AC1.6 | `tm container update container 99999 --name=x` |

**Commit:** `test(cli): polymorphic container create/update with type-mismatch hint`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Tests for container-side membership (round-trip + cross-diagram + cycle + list-children)

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC3.4`, `agent-cli.AC3.5`, `agent-cli.AC3.6`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_container_membership.py`.

**Implementation:**

| Test | AC | Action |
|---|---|---|
| `test_set_parent_then_parent_of_round_trips` | AC3.4 | seed; create a child container in same diagram; `tm container set-parent <child> <parent>`; `tm container parent-of <child>` returns the parent's container row |
| `test_list_children_includes_node_and_container` | AC3.4 | seed; set process node's parent to seeded container; set another container's parent to it; `tm container list-children <container_id>` returns both rows; each carries `type` discriminator (`process` and `container`) |
| `test_clear_parent_then_list_children_excludes_child` | AC3.4 | seed + parented; `tm container clear-parent <child_id>`; `list-children` no longer includes it |
| `test_set_parent_cross_diagram_exits_1_with_hint` | AC3.5 | create a second diagram; create a container in it; attempt `tm container set-parent <child-from-diagram-A> <parent-from-diagram-B>` → exit 1, `error.code == "user_error"`, message mentions `same diagram` (or hint copied verbatim from the repo) |
| `test_set_parent_self_exits_1` | AC3.4 | `tm container set-parent <id> <id>` → exit 1, message mentions `cannot be its own parent` |
| `test_set_parent_creates_cycle_exits_1_with_hint` | AC3.6 | seed; create container A and container B; `tm container set-parent B A`; `tm container set-parent A B` (would be a cycle) → exit 1, message mentions `cycle` |
| `test_list_children_missing_container_exits_2` | AC1.5 | `tm container list-children 99999` → exit 2 |
| `test_set_parent_unknown_parent_exits_1` | AC5.1 | `tm container set-parent <child> 99999` → exit 1 |

The cross-diagram and cycle tests need helper utilities to construct multi-diagram, multi-container fixtures inline:

```python
def _create_diagram_with_containers(runner, name: str, n: int) -> tuple[str, list[str]]:
    diagram = runner.invoke(cli, ["diagram", "create", "--name", name])
    diag_id = json.loads(diagram.stdout)["id"]
    container_ids = []
    for i in range(n):
        result = runner.invoke(cli, [
            "container", "create", "container",
            "--diagram-id", diag_id,
            "--name", f"{name}-c{i}",
            "--description", "test",
        ])
        container_ids.append(json.loads(result.stdout)["id"])
    return diag_id, container_ids
```

(Full test code shows the cycle and cross-diagram setups; the executor implements them per the table.)

**Commit:** `test(cli): tm container membership round-trip + cross-diagram + cycle failures`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Final operational verification

**Type:** Infrastructure (verification only).

**Files:** none.

**Verification:**

Run: `make lint`, `make test`. Expected: clean.

End-to-end smoke:

```bash
DI=$(uv run tm diagram create --name=phase6 | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
TB=$(uv run tm container create trust-boundary --diagram-id "$DI" --name=tb --description=d --privilege-level=corporate | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
C=$(uv run tm container create container --diagram-id "$DI" --name=c --description=d | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
uv run tm container set-parent "$C" "$TB"
uv run tm container parent-of "$C"
uv run tm container list-children "$TB"
uv run tm container set-parent "$TB" "$C" 2>&1 1>/dev/null    # cycle
```

Expected: every step exits 0 except the last (cycle), which exits 1 with `user_error` and mentions cycle.

**Commit:** none.
<!-- END_TASK_8 -->

---

## Phase 6 — Done When

- `tm container` non-variant CRUDL is in place.
- `tm container create trust-boundary|container` and `tm container update <variant> <id>` work; type-mismatch returns a friendly hint.
- `tm container set-parent / clear-parent / parent-of / list-children` work end-to-end.
- Cross-diagram and cycle failures exit 1 with messages matching the repo's verbatim text.
- All Phase 6 tests green.
- `make lint` clean.
