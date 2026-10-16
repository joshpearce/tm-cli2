# Idea: push validation findings alongside diagram data

## What changed in dfd_editor

The dfd_editor's agent API (`POST /api/agent/diagrams` and
`PUT /api/agent/diagrams/<id>`) now accepts an optional `validation` array
at the top level of the diagram payload. This lets an external system (like
tm-cli) submit errors and warnings alongside the diagram data. The editor
does not compute any validation rules itself — it only displays what you
send it.

## The validation contract

Add a top-level `"validation"` key to the dict returned by
`to_dfd_editor_dict()`. It is an array of finding objects:

```json
{
  "meta": { ... },
  "nodes": [ ... ],
  "containers": [ ... ],
  "data_flows": [ ... ],
  "data_items": [ ... ],
  "validation": [
    {
      "guid": "element-uuid-or-null",
      "severity": "error",
      "message": "Human-readable problem description",
      "code": "OPTIONAL_RULE_CODE"
    }
  ]
}
```

### Finding fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `guid` | UUID string or `null` | No (default `null`) | Must reference a real element in `nodes`, `containers`, `data_flows`, or `data_items`. Omit or set `null` for diagram-level findings. Server rejects unknown GUIDs with HTTP 400. |
| `severity` | `"error"` or `"warning"` | Yes | `"error"` paints a red overlay on the element and blocks the save button. `"warning"` paints an amber overlay. |
| `message` | string | Yes | Shown in the sidebar when the user clicks the flagged element. |
| `code` | string | No | Optional machine-readable rule identifier (e.g. `"UNENCRYPTED_PII_FLOW"`). |

### What the editor does with findings

- **Red/amber overlay** on each flagged block, group, or line on the canvas.
- **Footer badge** showing total error/warning counts.
- **Sidebar panel** (`SelectedObjectProblems`) — click a flagged element to
  read its findings.
- **Save gate** — the save button is disabled when any finding has
  `severity: "error"`.
- **Session-scoped** — findings are NOT persisted by the editor's own saves.
  They exist only for the current browser session. Re-push the diagram (with
  or without findings) to refresh them.

### Server-side validation rules

The server's pydantic schema (`server/schema.py`) enforces:

1. `severity` must be `"error"` or `"warning"` (closed enum).
2. If `guid` is present and non-null, it must resolve to the GUID of a
   node, container, data_flow, or data_item in the same diagram payload.
   Unknown GUIDs are rejected with HTTP 400 + structured error details.
3. `extra="forbid"` — no additional fields beyond `guid`, `severity`,
   `message`, `code`.

## How tm-cli currently pushes diagrams

The push flow is:

1. `cli/diagrams.py:push_diagram` loads entities from SQLite via repositories.
2. `db/dfd_export.py:to_dfd_editor_dict()` converts them to the
   dfd_editor payload dict with deterministic UUIDs (UUIDv5 via `guid_for`).
3. `cli/_dfd_editor_client.py:post_diagram` or `put_diagram` sends the
   dict to the agent API.

The `to_dfd_editor_dict()` return value currently has five top-level keys:
`meta`, `nodes`, `containers`, `data_flows`, `data_items`. Adding
`"validation": [...]` to this dict is all that's needed for the server to
accept and deliver findings to the browser.

Element GUIDs for findings MUST use the same `guid_for(diagram_id,
collection, local_int_id)` function that generates the element GUIDs in the
existing payload. For example, to flag node with local id 7 in diagram 3:

```python
from tm_cli.db.dfd_export import guid_for

finding = {
    "guid": guid_for(3, "nodes", 7),
    "severity": "error",
    "message": "Process has no authenticated inbound data flows",
    "code": "NO_AUTH_INBOUND",
}
```

For a diagram-level finding (not tied to any element), omit `guid` or set
it to `null`:

```python
finding = {
    "severity": "warning",
    "message": "Diagram has no trust boundaries defined",
    "code": "NO_TRUST_BOUNDARIES",
}
```

## What to build

The idea is to let tm-cli compute validation rules against its local
data model and push the results as findings alongside the diagram. The
rules would encode threat-modeling best practices — things like:

- Data flows carrying PII that aren't encrypted
- Processes with no trust boundary
- External entities with no authenticated data flows
- Data stores containing PII with no encryption at rest
- Flows crossing trust boundaries without authentication

The implementation would be a pure function that takes the same entity
inputs as `to_dfd_editor_dict()` and returns a `list[dict]` of findings.
The push command would then merge these into the payload dict before
sending.
