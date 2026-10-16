# Agent CLI — Phase 8: entity_documents + introspection + final golden sweep

**Goal:** Close out the four entity↔document links and ship the introspection commands (`tm schema` and `tm commands --json`) that complete the agent-facing contract. Add an end-to-end acceptance test that walks the canonical DFD workflow using only stdout-derived ids, and bless help-text snapshots for every leaf command in the tree.

**Architecture:** `EntityDocumentRepository.link/unlink/documents_for_entity` is a single shared implementation that works on any DFD entity id (the row's `kind` column lives on the `entity` master table). Each of the four DFD command modules (`nodes.py`, `containers.py`, `flows.py`, `items.py`) adds the same three subcommands (`link-document`, `unlink-document`, `list-documents`); each is a thin wrapper around the shared repo methods, with a pre-existence check to populate the `linked: true|false` envelope. The reverse view lives on `documents.py` as four separate per-kind listings (`list-nodes`, `list-containers`, `list-flows`, `list-items`). Introspection commands are top-level: `tm schema [<entity>]` walks Pydantic's `model_json_schema()` for read/Create/Update models per entity; `tm commands --json` walks `cli.commands` recursively and emits a stable JSON tree (golden-tested). The final golden sweep snapshots every leaf command's `--help` and at least one representative JSON output, with a meta-test that confirms every leaf in `tm commands --json` has a matching help snapshot.

**Tech Stack:** Same as previous phases.

**Scope:** Phase 8 of 8 from `docs/design-plans/2026-05-05-agent-cli.md`.

**Codebase verified:** 2026-05-05.
- `EntityDocumentRepository` exposes:
  - `link(entity_id, document_id) -> None` — idempotent (`INSERT OR IGNORE`); FK violations on missing entity or document raise `sqlite3.IntegrityError`.
  - `unlink(entity_id, document_id) -> bool` — returns whether a row was deleted.
  - `documents_for_entity(entity_id) -> list[DocumentSummary]` — works for any of the four kinds (the entity table holds them all).
  - `nodes_for_document(document_id) -> list[Node]`, `containers_for_document` -> list[Container], `flows_for_document` -> list[DataFlow], `items_for_document` -> list[DataItem]`.
- Pydantic v2's `Model.model_json_schema()` is a stable API. For discriminated unions (`Node`, `NodeCreate`, etc.), the schema includes a `oneOf` with each variant's schema and the `discriminator: {propertyName: "type"}` block — agents can route on this.
- Click 8.x exposes a command's `params` (mix of `Option` and `Argument`) and a group's `commands` dict. Each `Option` carries `.name`, `.opts` (the long-flag strings), `.help`, `.required`, `.default`, `.hidden`, `.type` (a `ParamType` whose `.name` attribute is its string identifier — e.g., `"INT"`, `"TEXT"`, `"CHOICE"`). For `Choice` types, `.choices` enumerates the allowed values. For arguments, `.name`, `.required`, `.type` are the relevant fields; arguments don't expose long-flag strings.

**External dependencies verified:** none new.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### agent-cli.AC3: Junctions
- **agent-cli.AC3.9 Success:** `link-document` on each of the four DFD entities (`tm node`, `tm container`, `tm flow`, `tm data-item`) works; `list-documents` on the same entity reflects the link.
- **agent-cli.AC3.10 Success:** `tm document list-nodes / list-containers / list-flows / list-items` each return the entities of that kind linked to the document.

### agent-cli.AC10: Introspection
- **agent-cli.AC10.1 Success:** `tm schema document` returns the JSON Schema for the read model plus `DocumentCreate` and `DocumentUpdate`.
- **agent-cli.AC10.2 Success:** `tm schema` (no argument) lists available entity names.
- **agent-cli.AC10.3 Success:** `tm schema --all` returns one document keyed by entity name.
- **agent-cli.AC10.4 Success:** `tm commands --json` walks the full command tree; every leaf has `options` and `arguments` keys (possibly empty arrays).
- **agent-cli.AC10.5 Success:** `tm commands --json` output is pinned by a golden snapshot; drift requires explicit snapshot update.

### agent-cli.AC9.5
- **agent-cli.AC9.5 Success:** `tm commands --json` emits the `--diagram-id` option with `"hidden": true` so curious agents can discover it.

---

## Required reading for the executor

- `/Users/josh/code/tm-cli/src/tm_cli/db/entity_documents.py` (EntityDocumentRepository signatures and FK behavior).
- Phase 2 deliverable `documents.py` (you'll add 4 reverse-listing subcommands; the existing module's `list-terms` is the layout reference).
- Phase 4–7 deliverables `items.py`, `nodes.py`, `containers.py`, `flows.py` (you'll add `link-document`, `unlink-document`, `list-documents` to each).
- Click 8.x docs for `Command.params`, `Option.opts`, `Option.hidden`, `Choice.choices`, `Group.commands`.
- The `agent-cli-design.md` golden scenario referenced by the design plan (search for "create a diagram with two process nodes and a data flow between them" or the AC11 / Glossary sections).

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Per-entity `link-document` / `unlink-document` / `list-documents` on the four DFD modules

**Type:** Functionality (tests in Task 5).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/nodes.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/containers.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/flows.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/items.py`.

**Implementation:**

Each module adds the same three commands. The pattern is identical except for the Click group it registers with and the entity-id argument's name. We inline the three commands per module rather than factor them into a shared helper — Click commands hung off a group via a factory show up in `tm commands --json` with synthesized names that hurt introspection clarity, and the per-module duplication is ~30 lines × 4 modules. Inline is the right call here.

For each of the four modules, add (using `nodes.py` as the template — substitute group name and entity arg name in the others):

```python
from tm_cli.db import EntityDocumentRepository  # add to imports


@node_group.command(name="link-document")
@click.argument("node_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def node_link_document(ctx, node_id: int, doc_id: int) -> None:
    """Link a document to this node. Idempotent."""
    with connect() as conn:
        repo = EntityDocumentRepository(conn)
        existing_ids = {d.id for d in repo.documents_for_entity(node_id)}
        already = doc_id in existing_ids
        repo.link(node_id, doc_id)
    payload = {"linked": not already, "node_id": str(node_id), "document_id": str(doc_id)}
    if already:
        payload["reason"] = "already_linked"
    emit(ctx, payload)


@node_group.command(name="unlink-document")
@click.argument("node_id", type=click.INT)
@click.argument("doc_id", type=click.INT)
@click.pass_context
def node_unlink_document(ctx, node_id: int, doc_id: int) -> None:
    """Remove a document↔node link. Idempotent."""
    with connect() as conn:
        existed = EntityDocumentRepository(conn).unlink(node_id, doc_id)
    payload = {"unlinked": existed, "node_id": str(node_id), "document_id": str(doc_id)}
    if not existed:
        payload["reason"] = "not_linked"
    emit(ctx, payload)


@node_group.command(name="list-documents")
@click.argument("node_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def node_list_documents(ctx, node_id, *, limit, offset, sort_field, order, json_fields) -> None:
    """List documents linked to this node."""
    with connect() as conn:
        if NodeRepository(conn).get(node_id) is None:
            raise NotFoundError(f"Node id={node_id} not found", id=str(node_id))
        rows = EntityDocumentRepository(conn).documents_for_entity(node_id)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    sliced = sorted_rows[offset : offset + limit] if limit else sorted_rows[offset:]
    fields = parse_json_fields(json_fields)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sliced]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
```

For the other three modules, copy and substitute:
- `containers.py`: `container_id` arg; pre-existence check via `ContainerRepository(conn).get(container_id)`.
- `flows.py`: `flow_id` arg; pre-existence check via `DataFlowRepository(conn).get(flow_id)`.
- `items.py`: `item_id` arg; pre-existence check via `DataItemRepository(conn).get(item_id)`.

Each module already imports its primary repository, so only `EntityDocumentRepository` needs adding.

**Verification:**

Run: `uv run tm node link-document --help` and similarly for `container`, `flow`, `data-item`.
Expected: each shows two positional ids and standard list flags on `list-documents`.

**Commit:** `feat(cli): add link-document/unlink-document/list-documents on tm node|container|flow|data-item`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Reverse listings on `tm document` (list-nodes / list-containers / list-flows / list-items)

**Type:** Functionality (tests in Task 5).

**Files:**
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/cli/documents.py`.

**Implementation:**

Add four subcommands. Each one:
1. Pre-checks the document exists via `DocumentRepository(conn).get(doc_id)`.
2. Calls the corresponding `EntityDocumentRepository.<kind>_for_document(doc_id)` method.
3. Applies sort/limit/offset/projection client-side.

```python
from tm_cli.db import EntityDocumentRepository  # add to imports


def _list_for_document(ctx, doc_id, *, limit, offset, sort_field, order, json_fields, query):
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
def list_nodes_for_doc(ctx, doc_id, *, limit, offset, sort_field, order, json_fields) -> None:
    """List nodes linked to a document."""
    _list_for_document(ctx, doc_id,
        limit=limit, offset=offset, sort_field=sort_field, order=order, json_fields=json_fields,
        query=lambda repo, did: repo.nodes_for_document(did))


@document_group.command(name="list-containers")
@click.argument("doc_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_containers_for_doc(ctx, doc_id, *, limit, offset, sort_field, order, json_fields) -> None:
    """List containers linked to a document."""
    _list_for_document(ctx, doc_id,
        limit=limit, offset=offset, sort_field=sort_field, order=order, json_fields=json_fields,
        query=lambda repo, did: repo.containers_for_document(did))


@document_group.command(name="list-flows")
@click.argument("doc_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_flows_for_doc(ctx, doc_id, *, limit, offset, sort_field, order, json_fields) -> None:
    """List flows linked to a document."""
    _list_for_document(ctx, doc_id,
        limit=limit, offset=offset, sort_field=sort_field, order=order, json_fields=json_fields,
        query=lambda repo, did: repo.flows_for_document(did))


@document_group.command(name="list-items")
@click.argument("doc_id", type=click.INT)
@list_options
@json_fields_option
@click.pass_context
def list_items_for_doc(ctx, doc_id, *, limit, offset, sort_field, order, json_fields) -> None:
    """List data items linked to a document."""
    _list_for_document(ctx, doc_id,
        limit=limit, offset=offset, sort_field=sort_field, order=order, json_fields=json_fields,
        query=lambda repo, did: repo.items_for_document(did))
```

**Commit:** `feat(cli): add tm document list-nodes/list-containers/list-flows/list-items reverse views`
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: `tm schema` introspection

**Type:** Functionality (tests in Task 6).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/_introspection.py`.
- Modify: `/Users/josh/code/tm-cli/src/tm_cli/main.py` (register `schema` and `commands` as top-level Click commands — these are NOT subgroups).

**Implementation:**

Each entity has a triple of Pydantic models (Read, Create, Update). For polymorphic entities (Node, Container), the Read/Create models are unions; the schema export resolves them to JSON Schema with discriminated `oneOf`. Pydantic v2 handles this natively via `model_json_schema()` on either the union via `TypeAdapter` or each variant individually.

Approach: maintain a static registry of entity-name → triple of model classes (or the union TypeAdapter). For Node and Container, use `pydantic.TypeAdapter(NodeCreate).json_schema()` etc. since the union itself isn't a `BaseModel`.

Create `src/tm_cli/cli/_introspection.py`:

```python
"""Introspection commands: tm schema and tm commands --json."""

from __future__ import annotations

import json
from typing import Any

import click
from pydantic import BaseModel, TypeAdapter

from tm_cli.cli._output import emit
from tm_cli.db import (
    Container,
    ContainerCreate,
    ContainerUpdate,
    DataFlow,
    DataFlowCreate,
    DataFlowUpdate,
    DataItem,
    DataItemCreate,
    DataItemUpdate,
    Diagram,
    DiagramCreate,
    DiagramUpdate,
    Document,
    DocumentCreate,
    DocumentSummary,
    DocumentUpdate,
    Node,
    NodeCreate,
    NodeUpdate,
    Observation,
    ObservationCreate,
    ObservationUpdate,
    Term,
    TermCreate,
    TermUpdate,
)


def _schema_for(model: Any) -> dict[str, Any]:
    """Return JSON Schema for a Pydantic model class OR a typing union (TypeAdapter)."""
    if isinstance(model, type) and issubclass(model, BaseModel):
        return model.model_json_schema()
    return TypeAdapter(model).json_schema()


_REGISTRY: dict[str, dict[str, Any]] = {
    "document": {"read": Document, "create": DocumentCreate, "update": DocumentUpdate, "summary": DocumentSummary},
    "term": {"read": Term, "create": TermCreate, "update": TermUpdate},
    "observation": {"read": Observation, "create": ObservationCreate, "update": ObservationUpdate},
    "diagram": {"read": Diagram, "create": DiagramCreate, "update": DiagramUpdate},
    "node": {"read": Node, "create": NodeCreate, "update": NodeUpdate},
    "container": {"read": Container, "create": ContainerCreate, "update": ContainerUpdate},
    "flow": {"read": DataFlow, "create": DataFlowCreate, "update": DataFlowUpdate},
    "data-item": {"read": DataItem, "create": DataItemCreate, "update": DataItemUpdate},
}


def _entity_schema(name: str) -> dict[str, Any]:
    triple = _REGISTRY[name]
    return {kind: _schema_for(model) for kind, model in triple.items()}


@click.command(name="schema")
@click.argument("entity", required=False)
@click.option("--all", "all_entities", is_flag=True, default=False,
              help="Return schemas for every known entity, keyed by name.")
@click.pass_context
def schema_command(ctx, entity: str | None, *, all_entities: bool) -> None:
    """Pydantic JSON Schema for read + Create + Update models.

    With no argument, lists available entity names.
    """
    if all_entities:
        emit(ctx, {name: _entity_schema(name) for name in _REGISTRY})
        return
    if entity is None:
        emit(ctx, {"entities": list(_REGISTRY)})
        return
    if entity not in _REGISTRY:
        raise click.UsageError(
            f"Unknown entity: {entity!r}. Known entities: {', '.join(sorted(_REGISTRY))}"
        )
    emit(ctx, _entity_schema(entity))


def _serialize_param(p: click.Parameter) -> dict[str, Any]:
    """Serialize a Click ``Option`` or ``Argument`` for tm commands --json output."""
    type_name = type(p.type).__name__ if p.type else None
    serialized: dict[str, Any] = {
        "name": p.name,
        "type": type_name,
        "required": bool(p.required),
    }
    if isinstance(p, click.Option):
        serialized["opts"] = list(p.opts)
        serialized["secondary_opts"] = list(p.secondary_opts)
        serialized["is_flag"] = bool(p.is_flag)
        serialized["hidden"] = bool(p.hidden)
        serialized["multiple"] = bool(p.multiple)
        serialized["default"] = p.default if not callable(p.default) else None
        serialized["help"] = p.help
    if isinstance(p.type, click.Choice):
        serialized["choices"] = list(p.type.choices)
    return serialized


def _serialize_command(cmd: click.Command, name: str | None = None) -> dict[str, Any]:
    """Recursively serialize a Click ``Command`` (which may be a Group) to a JSON dict."""
    options = [_serialize_param(p) for p in cmd.params if isinstance(p, click.Option)]
    arguments = [_serialize_param(p) for p in cmd.params if isinstance(p, click.Argument)]
    out: dict[str, Any] = {
        "name": name or cmd.name,
        "description": (cmd.help or cmd.short_help or "").strip(),
        "options": options,
        "arguments": arguments,
    }
    if isinstance(cmd, click.Group):
        out["subcommands"] = [
            _serialize_command(sub, sub_name)
            for sub_name, sub in sorted(cmd.commands.items())
        ]
    return out


@click.command(name="commands")
@click.option("--json", "as_json", is_flag=True, default=True,
              help="Emit machine-readable JSON (default; --no-json renders human-readable when on a TTY).")
@click.pass_context
def commands_command(ctx, *, as_json: bool) -> None:
    """Walk the full command tree and emit a stable JSON document.

    Hidden options are included with ``"hidden": true`` so curious agents can
    discover them programmatically.
    """
    from tm_cli.main import cli  # local import to avoid circular import at module load
    tree = _serialize_command(cli, name="tm")
    emit(ctx, tree)
```

In `src/tm_cli/main.py`, add at the bottom:

```python
from tm_cli.cli._introspection import schema_command, commands_command

cli.add_command(schema_command)
cli.add_command(commands_command)
```

**Verification:**

Run: `uv run tm schema`
Expected: `{"entities": ["document", "term", "observation", "diagram", "node", "container", "flow", "data-item"]}`.

Run: `uv run tm schema document | uv run python -c 'import json,sys; d=json.load(sys.stdin); print(sorted(d.keys()))'`
Expected: `['create', 'read', 'summary', 'update']`.

Run: `uv run tm schema --all | uv run python -c 'import json,sys; d=json.load(sys.stdin); print(sorted(d.keys()))'`
Expected: lists all eight entity names.

Run: `uv run tm commands | uv run python -c 'import json,sys; d=json.load(sys.stdin); print([c["name"] for c in d["subcommands"]])'`
Expected: includes `commands`, `container`, `data-item`, `diagram`, `document`, `flow`, `node`, `observation`, `schema`, `term` (sorted).

**Commit:** `feat(cli): add tm schema and tm commands introspection`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Tests for entity_documents on all four kinds + reverse listings on tm document

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC3.9`, `agent-cli.AC3.10`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_entity_documents.py`.

**Implementation:**

| Test | AC | Action |
|---|---|---|
| `test_node_link_unlink_list_round_trip` | AC3.9 | seed; `tm node link-document <node-id> <doc-id>` returns `linked: true`; `tm node list-documents <node-id>` includes the doc; relink returns `linked: false`; `tm node unlink-document` returns `unlinked: true`; subsequent list excludes |
| `test_container_link_unlink_list_round_trip` | AC3.9 | analogous on container |
| `test_flow_link_unlink_list_round_trip` | AC3.9 | analogous on flow |
| `test_data_item_link_unlink_list_round_trip` | AC3.9 | analogous on data-item |
| `test_document_list_nodes_returns_linked_node` | AC3.10 | seed + link node↔doc; `tm document list-nodes <doc-id>` returns the node row with `type` discriminator |
| `test_document_list_containers_returns_linked_container` | AC3.10 | analogous |
| `test_document_list_flows_returns_linked_flow` | AC3.10 | analogous |
| `test_document_list_items_returns_linked_item` | AC3.10 | analogous |
| `test_link_document_unknown_entity_exits_3_fk` | AC5.4 | `tm node link-document 99999 <doc-id>` → exit 3, `error.constraint == "foreign_key"` |
| `test_link_document_unknown_doc_exits_3_fk` | AC5.4 | `tm node link-document <node-id> 99999` → exit 3 |
| `test_document_list_nodes_for_missing_doc_exits_2` | AC1.5 | `tm document list-nodes 99999` → exit 2 |

**Commit:** `test(cli): cover entity_documents link/unlink/list across all four kinds + reverse views`
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Tests for `tm schema` and `tm commands --json`

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC9.5`, `agent-cli.AC10.1`, `agent-cli.AC10.2`, `agent-cli.AC10.3`, `agent-cli.AC10.4`, `agent-cli.AC10.5`.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_introspection.py`.

**Implementation:**

| Test | AC | Action |
|---|---|---|
| `test_schema_no_arg_lists_entity_names` | AC10.2 | `tm schema` → JSON `{"entities": [...]}` containing exactly the 8 known names |
| `test_schema_document_returns_triple_plus_summary` | AC10.1 | `tm schema document` → JSON has keys `read`, `create`, `update`, `summary`; each is a JSON Schema dict (has `properties` or `$ref`) |
| `test_schema_node_returns_discriminated_union` | AC10.1 | `tm schema node` → `read` schema has `oneOf` and `discriminator` |
| `test_schema_all_returns_dict_keyed_by_entity` | AC10.3 | `tm schema --all` → JSON has all 8 entity names as top-level keys |
| `test_schema_unknown_entity_exits_1` | AC5.1 | `tm schema bogus` → exit 1 |
| `test_commands_json_root_has_expected_subgroups` | AC10.4 | `tm commands` → JSON `subcommands` includes the 8 entity groups + `schema` + `commands` |
| `test_commands_json_every_leaf_has_options_and_arguments_keys` | AC10.4 | recursively walk the JSON tree; every node either has `subcommands` or has both `options` and `arguments` (possibly empty arrays) |
| `test_commands_json_includes_hidden_diagram_id_for_dfd_create` | AC9.5 | walk the tree; for any `data-item create` / `node create *` / `container create *` / `flow create` leaf, find an option with `name=="diagram_id"` and `hidden==True` |
| `test_commands_json_for_flow_update_omits_endpoint_options` | AC11.3 | walk the tree; for `flow update`, no option has `name in {"node1_id", "node2_id"}` |
| `test_commands_json_golden_snapshot` | AC10.5 | snapshot the entire `tm commands` JSON output (use the masking serializer; help-text and ids both stable here, but defaults like `--limit 50` make it stable) |

A representative test for the meta-walk:

```python
import json

from click.testing import CliRunner

from tm_cli.main import cli


def _walk(node):
    yield node
    for sub in node.get("subcommands", []):
        yield from _walk(sub)


def test_commands_json_every_leaf_has_options_and_arguments_keys() -> None:
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.stdout)
    for node in _walk(tree):
        # Groups have `subcommands`, leaves don't. Both must have options + arguments lists.
        assert "options" in node, f"{node['name']} is missing 'options'"
        assert "arguments" in node, f"{node['name']} is missing 'arguments'"
        assert isinstance(node["options"], list)
        assert isinstance(node["arguments"], list)
```

For the golden snapshot, the test pinning the full tree is fragile by design: any drift requires running `pytest --snapshot-update` and reviewing the diff with the same rigor as a schema change. Document this in the test file's docstring.

**Commit:** `test(cli): tm schema and tm commands introspection coverage`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: End-to-end DFD-workflow acceptance test

**Type:** Functionality (acceptance test).

**Verifies:** integration of every phase. Not pinned to a single AC but represents the agent-cli-design.md golden scenario.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/acceptance/__init__.py` (empty).
- Create: `/Users/josh/code/tm-cli/tests/acceptance/test_dfd_workflow.py`.

**Implementation:**

The test drives the CLI through a complete workflow using only stdout-derived ids (every id is parsed from a previous command's response). This proves that an agent following only the CLI's contract — never reading the database directly — can complete the workflow.

```python
"""Acceptance test: the canonical DFD workflow end-to-end through the CLI."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from tm_cli.main import cli


def _ok(result):
    assert result.exit_code == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def _ndjson(result):
    assert result.exit_code == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def test_full_dfd_workflow(db_path) -> None:
    """Build a small threat model from scratch through the CLI.

    Steps:
      1. Create a diagram.
      2. Add two process nodes and a data store.
      3. Connect them with a data flow.
      4. Add a data item and attach it as a payload.
      5. Place the process inside a trust boundary.
      6. Create a document and link it to the data flow.
      7. Verify everything via list-* / search / get.
    """
    runner = CliRunner(mix_stderr=False)

    # 1. Diagram
    diagram = _ok(runner.invoke(cli, ["diagram", "create", "--name=tm", "--description=test"]))
    diagram_id = diagram["id"]

    # 2. Nodes
    proc_a = _ok(runner.invoke(cli, [
        "node", "create", "process", "--diagram-id", diagram_id,
        "--name=worker", "--description=background", "--trust-level=admin",
    ]))
    proc_b = _ok(runner.invoke(cli, [
        "node", "create", "process", "--diagram-id", diagram_id,
        "--name=api", "--description=front-door", "--trust-level=public",
    ]))
    store = _ok(runner.invoke(cli, [
        "node", "create", "data-store", "--diagram-id", diagram_id,
        "--name=db", "--description=primary", "--storage-type=database",
        "--contains-pii", "--encryption-at-rest",
    ]))

    # 3. Flow (between worker and store)
    flow = _ok(runner.invoke(cli, [
        "flow", "create", "--diagram-id", diagram_id,
        "--node1-id", proc_a["id"], "--node2-id", store["id"],
        "--name=writes", "--protocol=HTTPS", "--authenticated", "--encrypted",
    ]))
    # Endpoints canonicalized.
    assert int(flow["node1_id"]) < int(flow["node2_id"])

    # 4. Data item + payload
    item = _ok(runner.invoke(cli, [
        "data-item", "create", "--diagram-id", diagram_id,
        "--identifier=user-record", "--name=User Record", "--description=PII",
        "--classification=pii",
    ]))
    payload_link = _ok(runner.invoke(cli, [
        "flow", "add-payload", flow["id"],
        "--data-item", item["id"], "--endpoint", "1",
    ]))
    assert payload_link["linked"] is True

    # 5. Trust boundary + parent
    tb = _ok(runner.invoke(cli, [
        "container", "create", "trust-boundary", "--diagram-id", diagram_id,
        "--name=corp", "--description=corp network", "--privilege-level=corporate",
    ]))
    _ok(runner.invoke(cli, ["node", "set-parent", proc_a["id"], tb["id"]]))
    parent_of = _ok(runner.invoke(cli, ["node", "parent-of", proc_a["id"]]))
    assert parent_of["parent"]["id"] == tb["id"]

    # 6. Document + flow link
    doc = _ok(runner.invoke(cli, [
        "document", "create",
        "--title=Threat Notes", "--author=agent", "--content=...",
    ]))
    link = _ok(runner.invoke(cli, ["flow", "link-document", flow["id"], doc["id"]]))
    assert link["linked"] is True

    # 7. Verify reverse views
    flows_for_doc = _ndjson(runner.invoke(cli, ["document", "list-flows", doc["id"]]))
    assert any(f["id"] == flow["id"] for f in flows_for_doc)

    payloads = _ndjson(runner.invoke(cli, ["flow", "list-payloads", flow["id"]]))
    assert any(p["id"] == item["id"] for p in payloads)

    children = _ndjson(runner.invoke(cli, ["container", "list-children", tb["id"]]))
    assert any(c["id"] == proc_a["id"] for c in children)

    # Search across nodes via the CLI.
    found = _ndjson(runner.invoke(cli, [
        "node", "search", "worker",
        "--diagram-id", diagram_id, "--type=process",
    ]))
    assert any(n["id"] == proc_a["id"] for n in found)
```

**Verification:**

Run: `uv run pytest tests/acceptance/test_dfd_workflow.py -v`
Expected: passes.

**Commit:** `test(acceptance): end-to-end DFD workflow via CLI`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Final golden sweep + meta-test

**Type:** Functionality (tests).

**Verifies:** `agent-cli.AC10.5` (golden snapshot of `tm commands`); meta-coverage that every leaf command has a help snapshot.

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/test_help_meta.py`.
- Bless: `tests/cli/__snapshots__/test_help_*.ambr` (rerun for any new commands added in Phase 8).

**Implementation:**

```python
"""Meta-test: every leaf command in tm commands --json has a corresponding help snapshot.

LIMITATION: this test substring-matches each leaf's "group leaf-name" string against the
concatenated body of every .ambr snapshot file. It catches the common failure mode (a new
leaf added without any snapshot at all) but CANNOT catch:
  - A snapshot whose body was wrong from the start (the body still contains the leaf name).
  - A swapped snapshot where leaf A's snapshot file was accidentally blessed for leaf B.
  - False positives where one leaf's path string appears incidentally inside an unrelated
    snapshot (e.g., the help text for `tm node list` mentions "node list" inside its own
    description, accidentally satisfying a hypothetical leaf with the same path).

Treat the meta-test as a coarse coverage gate, not a correctness check. Drift in individual
snapshots is caught by Syrupy's per-test diff at `pytest --snapshot-update` time.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli


def _walk_leaves(node, path):
    if not node.get("subcommands"):
        yield path + [node["name"]]
        return
    for sub in node["subcommands"]:
        yield from _walk_leaves(sub, path + [node["name"]])


def test_every_leaf_has_a_help_snapshot() -> None:
    runner = CliRunner()
    tree = json.loads(runner.invoke(cli, ["commands"]).output)
    leaves = list(_walk_leaves(tree, []))
    assert leaves, "Tree had no leaves — sanity check failed"

    snapshot_dir = Path("tests/cli/__snapshots__")
    if not snapshot_dir.exists():
        snapshot_dir = Path(__file__).parent / "__snapshots__"

    # Read every .ambr file and concatenate. Snapshots are named test names — we
    # search the concatenated body for the leaf path's printable form so a new
    # leaf without a snapshot fails this test.
    body = "\n".join(p.read_text() for p in snapshot_dir.rglob("*.ambr"))

    missing = []
    for leaf in leaves:
        # Strip the root "tm" segment for the search pattern.
        path_str = " ".join(leaf[1:])
        if path_str and path_str not in body:
            missing.append(path_str)

    assert not missing, f"Leaf commands missing help snapshots: {missing}"
```

For the per-phase help snapshots, this phase re-blesses any that drifted because of the new subcommands added in Tasks 1, 2, 3 — specifically `documents`, `nodes`, `containers`, `flows`, `items`. Run:

```bash
uv run pytest tests/cli/ --snapshot-update
git add tests/cli/__snapshots__
```

Inspect the diff for surprises.

**Verification:**

Run: `uv run pytest tests/cli/test_help_meta.py -v`
Expected: passes (no missing leaves).

**Commit:** `test(cli): meta-test for help-snapshot coverage of every leaf`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Final operational verification

**Type:** Infrastructure (verification only).

**Files:** none.

**Verification:**

Run: `make lint`
Expected: clean.

Run: `make test`
Expected: every test in the repository passes — Phases 1–8.

Run: `uv run tm --help`
Expected: lists every subgroup (`document`, `term`, `observation`, `diagram`, `node`, `container`, `flow`, `data-item`) plus `schema` and `commands`.

Run: `uv run tm commands --no-json | head -40`
Expected: human-readable rendering (when `--no-json`) of the same tree.

End-to-end smoke (against `TM_DB_PATH`):

```bash
uv run tm schema | uv run python -c 'import json,sys; print(len(json.load(sys.stdin)["entities"]))'   # 8
uv run tm commands | uv run python -c 'import json,sys; t=json.load(sys.stdin); print(t["name"]); print(len(t["subcommands"]))'  # tm, 10
```

Expected: prints `8` and `tm` followed by `10`.

If the integration acceptance test `tests/acceptance/test_dfd_workflow.py` fails, do NOT mark the phase done. Investigate and fix.

**Commit:** none. Use `chore(cli): phase 8 verification fix-ups` for any fix-ups.
<!-- END_TASK_8 -->

---

## Phase 8 — Done When

- All four DFD entity modules expose `link-document` / `unlink-document` / `list-documents`.
- `tm document list-nodes / list-containers / list-flows / list-items` are present.
- `tm schema [<entity>] [--all]` and `tm commands` are top-level commands.
- `tm commands --json` includes `--diagram-id` with `hidden=True` on every DFD create command, and excludes `node1_id` / `node2_id` from `flow update`.
- The end-to-end acceptance test passes.
- The meta-test confirms every leaf command in `tm commands --json` has a help snapshot.
- `make lint` clean; `make test` clean.
