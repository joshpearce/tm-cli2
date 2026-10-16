# Plan: `tm diagram push`

## Summary

Add a `tm diagram push` command that exports a local diagram (default or
`--diagram-id N`) to a running dfd_editor server via its `/api/agent`
HTTP API, creating on first push and updating thereafter. Identity is
preserved by persisting the server-minted diagram UUID locally on the
`diagram` row, and element UUIDs are derived deterministically (UUIDv5)
from local integer ids so dfd_editor-side layout survives re-pushes.
The HTTP client is stdlib `urllib.request`; the body builder is a pure
function over already-loaded entities.

## Decisions (confirmed)

1. **Stateful identity** — store the server's diagram UUID on the local
   `diagram` row so subsequent pushes PUT to the same target.
2. **Deterministic element UUIDs** — `uuid5(NS_TM_DIAGRAM_PUSH,
   f"{diagram_int_id}:{collection}:{local_int_id}")`. Same local id →
   same remote UUID forever.
3. **stdlib HTTP** — `urllib.request`, no new runtime dependency.
4. **Implicit assumptions**: no auth; `DFD_EDITOR_URL` env var,
   overridable by `--server URL`; tm-cli container parent/child
   relationships fill the dfd_editor `children` arrays.

## Mapping notes (key cross-model translations)

The taxonomy already aligns: tm-cli `NodeType = "process" |
"external_entity" | "data_store"` and `ContainerType = "trust_boundary"
| "container"` — same shape as dfd_editor. Translation is therefore
limited to (a) flat → `properties`-wrapped, (b) int id → UUIDv5, and
(c) populating `children` from the parent/child mapping.

| tm-cli (flat, int ids)                          | dfd_editor (UUIDs, `properties` wrapper)            |
| ----------------------------------------------- | --------------------------------------------------- |
| `ProcessNode`, `ExternalEntityNode`, `DataStoreNode` | `nodes[]`, fields moved under `properties`     |
| `TrustBoundary`, `ContainerVariant`             | `containers[]`, fields moved under `properties`     |
| Container parent → children mapping             | `children: [<child_guid>, ...]` on parent container |
| `DataFlow.node1_id` / `.node2_id`               | `node1` / `node2` UUIDs (server canonicalizes)      |
| `DataItem.parent_node_id`                       | `DataItem.parent` (UUID or null)                    |
| (no equivalent)                                 | `node{1,2}_src_data_item_refs: []` (always empty)   |

## Steps

### 1. Schema: persist `dfd_editor_diagram_id` on `diagram`

Add nullable `dfd_editor_diagram_id TEXT` column to the `diagram` table
DDL in `db/connection.py`. Schema init is run-on-empty today, so add an
idempotent `ALTER TABLE diagram ADD COLUMN ... IF NOT EXISTS`-style
guard (Python-side: introspect `PRAGMA table_info` and add if absent)
to handle existing local databases. Extend `Diagram` Pydantic model
(`db/dfd_models.py`) with `dfd_editor_diagram_id: str | None = None`.
Add `DiagramRepository.set_remote_id(diagram_id: int, remote_uuid:
str) -> None`.

**Files**: `db/connection.py`, `db/dfd_models.py`, `db/diagrams.py`,
`tests/cli/test_diagrams.py` (or new `tests/db/test_diagrams.py`).

**Acceptance**:
- Fresh DB has the column; an existing DB seeded under the old DDL
  acquires the column on first `connect()` without losing data.
- `Diagram.model_dump()` includes the field.
- `set_remote_id` persists the UUID; `repo.get(id).dfd_editor_diagram_id`
  returns it.
- All existing tests pass unchanged.

### 2. Body builder: pure function `build_minimal_doc`

New module `src/tm_cli/db/dfd_export.py` exposing one function:

```
build_minimal_doc(
    diagram: Diagram,
    nodes: list[NodeUnion],
    containers: list[ContainerVariant],
    container_parents: dict[int, int],   # child_int_id -> parent_int_id
    flows: list[DataFlow],
    items: list[DataItem],
) -> dict
```

Logic (pseudocode-level):
- Helper `guid_for(diagram_int_id, collection, local_int_id) -> str`
  returns `uuid5(NS_TM_DIAGRAM_PUSH, …)`. Collection segments are the
  dfd_editor segment names: `"nodes"`, `"containers"`, `"data_flows"`,
  `"data_items"`.
- Build `meta = {name, description, author, created}` from the diagram.
- For each node (process / external_entity / data_store): emit into
  `nodes[]` with the type-specific fields moved under `properties`.
- For each container (`trust_boundary` / `container`): emit into
  `containers[]` with type-specific fields moved under `properties`.
- Walk `container_parents`: append each child guid to its parent's
  `children` list.
- For each flow: emit `{guid, node1, node2, properties: {name,
  protocol, authenticated, encrypted, node1_src_data_item_refs: [],
  node2_src_data_item_refs: []}}`.
- For each item: emit `{guid, parent: guid_for_node_or_None,
  identifier, name, description, classification}`.

**Files**: `src/tm_cli/db/dfd_export.py`,
`tests/db/test_dfd_export.py`.

**Acceptance**:
- Given a seeded fixture with one of each entity type, `build_minimal_doc`
  output validates against `dfd_editor.schema.Diagram.model_validate(...)`
  (run dfd_editor's pydantic model in the test as a contract check).
- Determinism: same input → byte-identical JSON serialization (sorted
  keys).
- Per-type field placement: every type-specific field (e.g.
  `trust_level`, `entity_type`, `privilege_level`) lives under
  `properties`, with only `type` / `guid` / `children` (containers) /
  `node1` / `node2` (flows) / data-item top-level fields at the root.

### 3. HTTP client wrapper

New module `src/tm_cli/cli/_dfd_editor_client.py`:

```
def post_diagram(server: str, body: dict, *, timeout: float = 30.0) -> str
def put_diagram(server: str, remote_id: str, body: dict, *, timeout: float = 30.0) -> None
```

- Build `urllib.request.Request(url, data=json.dumps(body).encode(),
  headers={"Content-Type": "application/json"}, method=...)`.
- Use a custom `OpenerDirector` without `HTTPRedirectHandler` so
  redirects are not followed.
- Map non-2xx → `DfdEditorError(status, body_excerpt)`. Map
  `URLError`/socket errors → `DfdEditorError(None, str(exc))`.
- On POST, parse `{"id": "<uuid>", ...}`; validate via `uuid.UUID(s)`
  and return the string. Raise `DfdEditorError` if missing/invalid.

**Files**: `src/tm_cli/cli/_dfd_editor_client.py`,
`tests/cli/test_dfd_editor_client.py` (mock `urlopen`).

**Acceptance**:
- 201 with valid `id` → returns the UUID string.
- 200 PUT → returns `None`.
- Non-2xx status → raises `DfdEditorError` carrying status + truncated
  body.
- Connection failure → raises `DfdEditorError` with `status=None`.
- Redirect responses are not followed (verified by mock).
- Timeout default applied.

### 4. CLI command + error mapping + env wiring

Add `push_diagram` to `cli/diagrams.py` registered as `tm diagram push`:

- Options: `--diagram-id INT` (hidden, via `dfd_diagram_id_option`),
  `--server URL` (overrides `DFD_EDITOR_URL`).
- Resolve diagram via `resolve_default_diagram_id(create_if_missing=True)`.
- Resolve server URL: `--server` > `os.environ["DFD_EDITOR_URL"]` >
  raise `UserError`.
- Open a single connection, load diagram + all 4 element kinds + the
  container-parent map via existing repos.
- Call `build_minimal_doc(...)`.
- If `diagram.dfd_editor_diagram_id` is set → `put_diagram(...)`,
  `operation = "updated"`. Else → `post_diagram(...)` then
  `repo.set_remote_id(...)`, `operation = "created"`.
- `emit(ctx, {"diagram_id": id, "remote_id": uuid, "operation":
  operation})`.
- Map `DfdEditorError` in `cli/_errors.py` → `SystemError` (exit code
  4) with structured `{error: {code, message, status, server}}`.
- Add `DFD_EDITOR_URL` to `.env.example` with a localhost placeholder.

**Files**: `src/tm_cli/cli/diagrams.py`,
`src/tm_cli/cli/_errors.py`, `.env.example`,
`tests/cli/test_diagrams.py`.

**Acceptance**:
- Create path: empty `dfd_editor_diagram_id` → POST called with full
  body → returned UUID stored on row → emitted JSON has
  `operation="created"`, `remote_id=<uuid>`, exit 0.
- Update path: column already populated → PUT called against that UUID,
  no re-POST, `operation="updated"`.
- `--server` overrides env; missing both → `user_error` exit 1 with
  hint.
- HTTP failure → exit 4 with structured error body on stderr.
- Existing default-diagram resolver behaviour unchanged.

### 5. Acceptance test + `agent-info` doc update

Add `tests/acceptance/test_diagram_push.py` that stands up an
in-process WSGI stub (using `wsgiref.simple_server` on an ephemeral
port in a thread) capturing the POST/PUT body, drives the CLI twice
(create then update), and asserts: (a) first invocation POSTs to
`/api/agent/diagrams` with a valid `Diagram`-shaped body, (b) second
invocation PUTs to `/api/agent/diagrams/<id>` with the **same element
UUIDs** as the first, (c) local `dfd_editor_diagram_id` is persisted.
Also add a one-line entry to `cli/_agent_info.py` documenting the new
command.

**Files**: `tests/acceptance/test_diagram_push.py`,
`src/tm_cli/cli/_agent_info.py`.

**Acceptance**:
- Test passes against a real (in-process) HTTP server, not just mocks.
- Element UUIDs are byte-identical across the two pushes.
- `tm agent-info` output mentions `diagram push`.

## Definition of Done

- All step-level acceptance criteria met.
- `make lint` and `make test` clean.
- No regression in existing CLI snapshots or acceptance tests.
- `.env.example` documents `DFD_EDITOR_URL`.
- Re-running `tm diagram push` against the same local diagram is
  idempotent on dfd_editor (same UUIDs, layout preserved).
