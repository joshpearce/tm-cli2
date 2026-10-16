# Agent CLI — Phase 7: DataFlow + flow_payload

**Goal:** Add `tm flow` (DataFlow CRUDL + search) and the flow-payload junction commands. Cover the entity-specific invariants the design pins on flows: canonical endpoint ordering, self-loop rejection, and endpoint immutability on update.

**Architecture:** `tm flow` follows the established DFD entity pattern (hidden `--diagram-id` resolver, all six core verbs, list-output via `DocumentSummary`-equivalent — flows have no large blobs so `list()` and `search()` return full `DataFlow` rows). The repository handles canonical ordering and self-loop rejection itself; the CLI is a thin pass-through. Update intentionally omits `--node1-id` / `--node2-id` to enforce immutability at parse time. The `add-payload` / `remove-payload` / `list-payloads` commands accept `--endpoint 1|2` (`SourceEndpoint = Literal[1, 2]`) as a `click.Choice(["1", "2"])` plus a callback that converts back to int. The `--endpoint` filter on `list-payloads` is optional. `tm data-item list-flows <item-id>` is the reverse view added on the existing `data-item` group.

**Tech Stack:** Same as previous phases.

**Scope:** Phase 7 of 8 from `docs/design-plans/2026-05-05-agent-cli.md`.

**Codebase verified:** 2026-05-05.
- `DataFlowRepository`: `create(diagram_id, DataFlowCreate)` (canonicalizes `node1_id < node2_id`, rejects self-loops with `ValueError("Self-loops are not allowed")`, validates both endpoints are nodes in the same diagram), `get`, `update(flow_id, DataFlowUpdate)` (DataFlowUpdate has only `name`/`protocol`/`authenticated`/`encrypted` — endpoint fields are NOT present), `delete`, `list(diagram_id, *, limit, offset)`, `search(diagram_id, text=None, *, limit, offset)`.
- `add_payload(flow_id, data_item_id, source_endpoint)` is idempotent (`INSERT OR IGNORE`). Validates: flow exists and is a flow, item exists and is a data_item, both in the same diagram. Errors are `ValueError` with descriptive messages.
- `payload_for_flow(flow_id, *, source_endpoint=None)` filters by endpoint when provided. Returns `list[DataItem]`.
- `flows_for_data_item(data_item_id)` returns `list[DataFlow]`.
- `SourceEndpoint = Literal[1, 2]`. Click handles the int coercion via a callback.

**External dependencies verified:** none new.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### agent-cli.AC1: Standard CRUDL behaviors
- **agent-cli.AC1.1 Success** [DataFlow]
- **agent-cli.AC1.2 Success** [DataFlow]
- **agent-cli.AC1.3 Success** [DataFlow]
- **agent-cli.AC1.4 Success** [DataFlow]
- **agent-cli.AC1.5 Failure** [DataFlow]
- **agent-cli.AC1.6 Failure** [DataFlow]

### agent-cli.AC2: Search
- **agent-cli.AC2.6 Success:** `tm flow search "X"` matches against `name` and `protocol` columns.
- **agent-cli.AC2.7 Edge:** `search` with empty text plus filters returns the same shape as `list` with those filters (verified for flow: empty text is equivalent to `tm flow list`).

### agent-cli.AC3: Junctions
- **agent-cli.AC3.7 Success:** `tm flow add-payload <flow-id> --data-item ID --endpoint 1` plus a second call with `--endpoint 2` round-trips through `tm flow list-payloads`; `--endpoint` filter on list returns just the matching payloads.
- **agent-cli.AC3.8 Failure:** `tm flow add-payload --endpoint=3` rejected by Click's `Choice` at parse (exit 1).

### agent-cli.AC11: Entity-specific invariants
- **agent-cli.AC11.1 Success:** `tm flow create --node1-id 5 --node2-id 3 ...` produces a row with `node1_id=3, node2_id=5` (canonicalized transparently by the repo).
- **agent-cli.AC11.2 Failure:** `tm flow create --node1-id 5 --node2-id 5 ...` exits 1 with a self-loop hint.
- **agent-cli.AC11.3 Constraint:** `tm flow update --help` shows no `--node1-id` or `--node2-id` flags; `tm commands --json` (Phase 8) for `flow update` likewise omits them — verified structurally here.

---

## Required reading for the executor

- `/Users/josh/code/tm-cli/src/tm_cli/db/dfd_flows.py` (DataFlowRepository — exact error messages).
- `/Users/josh/code/tm-cli/src/tm_cli/db/dfd_models.py` (DataFlow*, SourceEndpoint).
- Phase 5 deliverable `src/tm_cli/cli/nodes.py` and Phase 4 `items.py` as templates for the resolver-using DFD pattern.

---

<!-- START_TASK_1 -->
### Task 1: `tm flow` core CRUDL + search

**Type:** Functionality (tests in Tasks 4–6).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/flows.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/main.py` (register `flow_group`).

**Implementation:**

```python
"""tm flow — DataFlow CRUDL + search + payload junction subgroup."""

from __future__ import annotations

from typing import Any

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
    DataFlowCreate,
    DataFlowRepository,
    DataFlowUpdate,
    DataItemRepository,
    connect,
)


@click.group(name="flow")
def flow_group() -> None:
    """Manage DFD data flows."""


@flow_group.command(name="list")
@list_options
@dfd_diagram_id_option
@json_fields_option
@click.pass_context
def list_flows(ctx, *, limit, offset, sort_field, order, diagram_id, json_fields) -> None:
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = DataFlowRepository(conn).list(resolved, limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@flow_group.command(name="get")
@click.argument("flow_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_flow(ctx, flow_id, *, json_fields) -> None:
    with connect() as conn:
        row = DataFlowRepository(conn).get(flow_id)
    if row is None:
        raise NotFoundError(f"DataFlow id={flow_id} not found", id=str(flow_id))
    payload = project_fields(row.model_dump(mode="json"), parse_json_fields(json_fields))
    emit(ctx, payload)


@flow_group.command(name="create")
@dfd_diagram_id_option
@click.option("--node1-id", "node1_id", type=click.INT, default=None)
@click.option("--node2-id", "node2_id", type=click.INT, default=None)
@click.option("--name", default=None)
@click.option("--protocol", default=None)
@click.option("--authenticated/--no-authenticated", "authenticated", default=None)
@click.option("--encrypted/--no-encrypted", "encrypted", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--if-not-exists", "if_not_exists", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def create_flow(ctx, *, diagram_id, node1_id, node2_id, name, protocol, authenticated, encrypted, use_stdin, if_not_exists, dry_run) -> None:
    """Create a data flow. Endpoints are canonicalized (lower id first)."""
    enforce_stdin_exclusive(use_stdin, {
        "node1_id": node1_id, "node2_id": node2_id, "name": name, "protocol": protocol,
        "authenticated": authenticated, "encrypted": encrypted,
    })
    if use_stdin:
        body = read_json_stdin()
    else:
        if (node1_id is None or node2_id is None or name is None or protocol is None
                or authenticated is None or encrypted is None):
            raise click.UsageError(
                "--node1-id, --node2-id, --name, --protocol, "
                "--authenticated/--no-authenticated, and --encrypted/--no-encrypted are required (or use --stdin)"
            )
        body = {
            "node1_id": node1_id, "node2_id": node2_id, "name": name, "protocol": protocol,
            "authenticated": authenticated, "encrypted": encrypted,
        }

    if isinstance(body, list):
        models = []
        for index, item in enumerate(body):
            try:
                models.append(DataFlowCreate.model_validate(item))
            except ValidationError as e:
                raise map_exception(e, input_payload={"index": index, "item": item}) from e
        if dry_run:
            emit(ctx, {"dry_run": True, "would_create": [m.model_dump(mode="json") for m in models]})
            return
        with connect() as conn:
            resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
            assert resolved is not None
            repo = DataFlowRepository(conn)
            created = [repo.create(resolved, m) for m in models]
        emit(ctx, [{"diagram_id": str(resolved), **c.model_dump(mode="json")} for c in created])
        return

    model = DataFlowCreate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_create": model.model_dump(mode="json")})
        return
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=True)
        assert resolved is not None
        created_flow = DataFlowRepository(conn).create(resolved, model)
    emit(ctx, {"diagram_id": str(resolved), **created_flow.model_dump(mode="json")})


@flow_group.command(name="update")
@click.argument("flow_id", type=click.INT)
@click.option("--name", default=None)
@click.option("--protocol", default=None)
@click.option("--authenticated/--no-authenticated", "authenticated", default=None)
@click.option("--encrypted/--no-encrypted", "encrypted", default=None)
@click.option("--stdin", "use_stdin", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def update_flow(ctx, flow_id, *, name, protocol, authenticated, encrypted, use_stdin, dry_run) -> None:
    """Update a data flow's metadata.

    Endpoints (node1_id/node2_id) are immutable. Delete and recreate to change them.
    """
    enforce_stdin_exclusive(use_stdin, {
        "name": name, "protocol": protocol, "authenticated": authenticated, "encrypted": encrypted,
    })
    if use_stdin:
        body = read_json_stdin()
        if not isinstance(body, dict):
            raise click.UsageError("--stdin update body must be a single JSON object")
        # Reject smuggled endpoint fields with a friendly hint.
        if "node1_id" in body or "node2_id" in body:
            raise click.UsageError(
                "Endpoints are immutable on DataFlow. Delete and recreate to swap node1_id/node2_id."
            )
    else:
        body = {k: v for k, v in {
            "name": name, "protocol": protocol,
            "authenticated": authenticated, "encrypted": encrypted,
        }.items() if v is not None}
        if not body:
            raise click.UsageError("No update fields provided (and --stdin not used)")
    patch = DataFlowUpdate.model_validate(body)
    if dry_run:
        emit(ctx, {"dry_run": True, "would_update": {"id": str(flow_id), "patch": patch.model_dump(mode="json", exclude_none=True)}})
        return
    with connect() as conn:
        updated = DataFlowRepository(conn).update(flow_id, patch)
    if updated is None:
        raise NotFoundError(f"DataFlow id={flow_id} not found", id=str(flow_id))
    emit(ctx, updated.model_dump(mode="json"))


@flow_group.command(name="delete")
@click.argument("flow_id", type=click.INT)
@click.option("--yes", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def delete_flow(ctx, flow_id, *, yes, dry_run) -> None:
    if dry_run:
        emit(ctx, {"dry_run": True, "would_delete": str(flow_id)})
        return
    with connect() as conn:
        existed = DataFlowRepository(conn).delete(flow_id)
    if existed:
        emit(ctx, {"deleted": True, "id": str(flow_id)})
    else:
        emit(ctx, {"deleted": False, "id": str(flow_id), "reason": "not_found"})


@flow_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@dfd_diagram_id_option
@json_fields_option
@click.pass_context
def search_flows(ctx, text, *, limit, offset, sort_field, order, diagram_id, json_fields) -> None:
    """Full-text search across DataFlow name and protocol."""
    text_str = " ".join(text).strip() if text else ""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        resolved = resolve_default_diagram_id(conn, diagram_id, create_if_missing=False)
        if resolved is None:
            emit(ctx, [], list_mode=True, limit=limit, offset=offset)
            return
        rows = DataFlowRepository(conn).search(
            resolved,
            text=text_str if text_str else None,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
```

Register the group in `main.py`.

**Note on `update`'s endpoint guard:** the `--node1-id` / `--node2-id` flags are not registered, so Click will reject them at parse time as `No such option`. We additionally check the stdin body for these keys to give a clearer message when an agent submits a JSON object with endpoint fields. This is defense in depth — `DataFlowUpdate` would also reject them via Pydantic's `extra="forbid"`, but the inline check produces a more actionable hint.

**Verification:**

Run: `uv run tm flow --help`
Expected: lists `list`, `get`, `create`, `update`, `delete`, `search`.

Run: `uv run tm flow update --help`
Expected: shows `--name`, `--protocol`, `--authenticated/--no-authenticated`, `--encrypted/--no-encrypted`, `--stdin`, `--dry-run`. Does NOT show `--node1-id` or `--node2-id`.

Run: `uv run python -c "from tm_cli.main import cli; cmd = cli.commands['flow'].commands['update']; print(sorted(p.name for p in cmd.params))"`
Expected: list does NOT include `node1_id` or `node2_id`.

**Commit:** `feat(cli): add tm flow CRUDL with endpoint-immutable update`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Flow payload commands (add-payload / remove-payload / list-payloads)

**Type:** Functionality (tests in Task 5).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/flows.py`.

**Implementation:**

```python
def _endpoint_callback(ctx: click.Context, param: click.Parameter, value: str | None) -> int | None:
    if value is None:
        return None
    return int(value)


@flow_group.command(name="add-payload")
@click.argument("flow_id", type=click.INT)
@click.option("--data-item", "data_item_id", type=click.INT, required=True,
              help="DataItem id to attach as a payload.")
@click.option("--endpoint", "source_endpoint",
              type=click.Choice(["1", "2"]), required=True, callback=_endpoint_callback,
              help="Endpoint (1 or 2) on which the data item flows.")
@click.pass_context
def add_payload(ctx, flow_id, *, data_item_id, source_endpoint) -> None:
    """Attach a data item to a flow at a specific endpoint."""
    with connect() as conn:
        # Pre-check: was this exact triple already attached?
        existing = DataFlowRepository(conn).payload_for_flow(flow_id, source_endpoint=source_endpoint)
        already_present = any(item.id == data_item_id for item in existing)
        DataFlowRepository(conn).add_payload(flow_id, data_item_id, source_endpoint)
    emit(ctx, {
        "linked": not already_present,
        "flow_id": str(flow_id),
        "data_item_id": str(data_item_id),
        "endpoint": source_endpoint,
        **({"reason": "already_linked"} if already_present else {}),
    })


@flow_group.command(name="remove-payload")
@click.argument("flow_id", type=click.INT)
@click.option("--data-item", "data_item_id", type=click.INT, required=True)
@click.option("--endpoint", "source_endpoint",
              type=click.Choice(["1", "2"]), required=True, callback=_endpoint_callback)
@click.pass_context
def remove_payload(ctx, flow_id, *, data_item_id, source_endpoint) -> None:
    """Detach a data item from a flow."""
    with connect() as conn:
        existed = DataFlowRepository(conn).remove_payload(flow_id, data_item_id, source_endpoint)
    emit(ctx, {
        "unlinked": existed,
        "flow_id": str(flow_id),
        "data_item_id": str(data_item_id),
        "endpoint": source_endpoint,
        **({"reason": "not_linked"} if not existed else {}),
    })


@flow_group.command(name="list-payloads")
@click.argument("flow_id", type=click.INT)
@click.option("--endpoint", "source_endpoint",
              type=click.Choice(["1", "2"]), default=None, callback=_endpoint_callback,
              help="Filter to payloads on a specific endpoint.")
@list_options
@json_fields_option
@click.pass_context
def list_payloads(ctx, flow_id, *, source_endpoint, limit, offset, sort_field, order, json_fields) -> None:
    """List data items attached to a flow."""
    with connect() as conn:
        if DataFlowRepository(conn).get(flow_id) is None:
            raise NotFoundError(f"DataFlow id={flow_id} not found", id=str(flow_id))
        rows = DataFlowRepository(conn).payload_for_flow(flow_id, source_endpoint=source_endpoint)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
```

The pre-existence check on `add-payload` makes the response distinguish "newly linked" from "already linked", matching the design's idempotent-junction shape (`{"linked": false, "reason": "already_linked"}` on the second call).

**Commit:** `feat(cli): add tm flow add-payload/remove-payload/list-payloads`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `tm data-item list-flows` reverse view

**Type:** Functionality (tests in Task 5).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/items.py`.

**Implementation:**

Add to the existing `data_item_group`:

```python
from tm_cli.db import DataFlowRepository  # add to imports


@data_item_group.command(name="list-flows")
@click.argument("item_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_flows_for_item(ctx, item_id, *, limit, offset, sort_field, order, json_fields) -> None:
    """List flows that carry this data item (on either endpoint)."""
    with connect() as conn:
        if DataItemRepository(conn).get(item_id) is None:
            raise NotFoundError(f"DataItem id={item_id} not found", id=str(item_id))
        rows = DataFlowRepository(conn).flows_for_data_item(item_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
```

`DataItemRepository` is already imported in `items.py`; just add `DataFlowRepository`.

**Commit:** `feat(cli): add tm data-item list-flows reverse view`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Tests for `tm flow` core CRUDL + canonicalization + self-loop + endpoint immutability

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC1.1`–`agent-cli.AC1.6`, `agent-cli.AC2.6`, `agent-cli.AC2.7`, `agent-cli.AC11.1`, `agent-cli.AC11.2`, `agent-cli.AC11.3`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_flows.py`.
- Create: `/Users/josh/code/tm-cli/tests/cli/test_flows_help.py`.

**Implementation:**

Use `db_with_seed` (one process, one external_entity, one data_store, one seeded flow between process and data_store). Tests:

| Test | AC | Action |
|---|---|---|
| `test_list_returns_seeded_flow` | AC1.1 | `tm flow list --diagram-id=<id>` returns 1 row |
| `test_get_returns_full_flow` | AC1.2 | `tm flow get <id>` |
| `test_create_canonicalizes_endpoints_when_n1_gt_n2` | AC1.3, AC11.1 | seed: process_id=A, data_store_id=B with A < B; create flow with `--node1-id=B --node2-id=A`; result has `node1_id=A, node2_id=B` |
| `test_create_self_loop_exits_1_with_hint` | AC11.2 | `--node1-id=<process> --node2-id=<process>` → exit 1; stderr message contains `Self-loops` |
| `test_create_cross_diagram_exits_1` | AC5.1 | seed; create another diagram with its own node; flow create with one endpoint from each diagram → exit 1 |
| `test_update_returns_full_row` | AC1.4 | `tm flow update <id> --no-encrypted` |
| `test_update_no_node1_or_node2_flag_present` | AC11.3 | inspect `update_flow` Click command's params; assert `{"node1_id", "node2_id"}.isdisjoint(p.name for p in cmd.params)` (using disjoint check rather than full set-equality so the test stays robust if other params are later added) |
| `test_update_stdin_with_node1_id_in_body_rejected` | AC11.3 | `tm flow update <id> --stdin` with `{"node1_id": 99}` → exit 1, message mentions `immutable` |
| `test_get_missing_id_exits_2` | AC1.5 | `tm flow get 99999` |
| `test_update_missing_id_exits_2` | AC1.6 | `tm flow update 99999 --name=x` |
| `test_search_matches_protocol` | AC2.6 | seed flow has `protocol="HTTPS"`; `tm flow search HTTPS --diagram-id=<id>` returns the row |
| `test_search_matches_name` | AC2.6 | `tm flow search seed --diagram-id=<id>` returns the row |
| `test_search_empty_text_returns_list_shape` | AC2.7 | `tm flow search --diagram-id=<id>` (no text) returns same row count as `tm flow list --diagram-id=<id>` |

Help-text snapshots cover the seven leaf commands.

**Commit:** `test(cli): tm flow CRUDL coverage with canonicalization, self-loop, endpoint-immutability`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Tests for flow payload junction + reverse view

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC3.7`, `agent-cli.AC3.8`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_flow_payloads.py`.

**Implementation:**

Tests:

| Test | AC | Action |
|---|---|---|
| `test_add_payload_endpoint_1` | AC3.7 | seed (flow + 2 data items); `tm flow add-payload <flow> --data-item <item-1> --endpoint 1` → `linked: true, endpoint: 1` |
| `test_add_payload_endpoint_2_after_endpoint_1_round_trips` | AC3.7 | `add-payload --endpoint 1` then `--endpoint 2` (same item or different); `tm flow list-payloads <flow>` returns 2 rows; `--endpoint 1` filter returns 1 |
| `test_add_payload_already_present_returns_already_linked` | AC3.7 | call add-payload twice with same triple; second call → `linked: false, reason: already_linked` |
| `test_remove_payload_returns_unlinked_true` | AC3.7 | seed + add-payload; `remove-payload` returns `unlinked: true` |
| `test_remove_payload_when_absent_returns_not_linked` | (extension) | `remove-payload` without prior add → `unlinked: false, reason: not_linked` |
| `test_endpoint_3_rejected_at_parse_exit_1` | AC3.8 | `--endpoint=3` → exit 1, `error.code == "user_error"`, message mentions `'1', '2'` |
| `test_list_payloads_filtered_by_endpoint` | AC3.7 | seed + add-payload on both endpoints; `--endpoint 2` filter returns subset |
| `test_list_payloads_for_missing_flow_exits_2` | AC1.5 | `tm flow list-payloads 99999` → exit 2 |
| `test_data_item_list_flows_returns_carrying_flow` | (reverse) | seed + add-payload; `tm data-item list-flows <item>` returns the flow |
| `test_data_item_list_flows_for_missing_item_exits_2` | AC1.5 | `tm data-item list-flows 99999` → exit 2 |
| `test_add_payload_cross_diagram_exits_1` | AC5.1 | create a flow in diagram A and a data item in diagram B; add-payload → exit 1 |
| `test_add_payload_using_non_data_item_id_exits_1` | AC5.1 | seed; `tm flow add-payload <flow> --data-item <process_node_id> --endpoint 1` → exit 1 (the kind check rejects) |

A representative test:

```python
import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_add_payload_already_present_returns_already_linked(db_with_seed) -> None:
    _, seed_ids = db_with_seed
    runner = CliRunner(mix_stderr=False)
    args = [
        "flow", "add-payload", str(seed_ids.data_flow_id),
        "--data-item", str(seed_ids.data_item_with_parent_id),
        "--endpoint", "1",
    ]
    first = runner.invoke(cli, args)
    assert first.exit_code == 0, first.stderr
    second = runner.invoke(cli, args)
    assert second.exit_code == 0
    payload = json.loads(second.stdout)
    assert payload["linked"] is False
    assert payload["reason"] == "already_linked"
```

**Commit:** `test(cli): flow_payload junction + reverse view + endpoint validation`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Final operational verification

**Type:** Infrastructure (verification only).

**Files:** none.

**Verification:**

Run: `make lint`, `make test`. Expected: clean.

End-to-end smoke (against a writable `TM_DB_PATH`):

```bash
DI=$(uv run tm diagram create --name=phase7 | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
P=$(uv run tm node create process --diagram-id "$DI" --name=p --description=d --trust-level=admin | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
DS=$(uv run tm node create data-store --diagram-id "$DI" --name=ds --description=d --storage-type=cache --contains-pii --encryption-at-rest | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
F=$(uv run tm flow create --diagram-id "$DI" --node1-id "$DS" --node2-id "$P" --name=f --protocol=HTTPS --authenticated --encrypted | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
uv run tm flow get "$F"   # should show node1_id < node2_id
ITEM=$(uv run tm data-item create --diagram-id "$DI" --identifier=x --name=X --description=d | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
uv run tm flow add-payload "$F" --data-item "$ITEM" --endpoint 1
uv run tm flow list-payloads "$F"
uv run tm flow update "$F" --no-encrypted
uv run tm flow create --diagram-id "$DI" --node1-id "$P" --node2-id "$P" --name=loop --protocol=tcp --authenticated --encrypted 2>&1 1>/dev/null  # self-loop
```

Expected: all but the last command exit 0 with parseable JSON; the last exits 1 with `error.code == "user_error"` and a message mentioning self-loop. The first canonicalization smoke shows `node1_id` < `node2_id` in the response regardless of input order.

**Commit:** none.
<!-- END_TASK_6 -->

---

## Phase 7 — Done When

- `tm flow` and `tm data-item list-flows` are wired into the root group.
- Endpoint canonicalization, self-loop rejection, and update-immutability are all surfaced through the CLI with the expected exit codes and messages.
- `--endpoint` accepts only `1` or `2`; `3` is rejected at parse with exit 1.
- All Phase 7 tests green.
- `make lint` clean.
