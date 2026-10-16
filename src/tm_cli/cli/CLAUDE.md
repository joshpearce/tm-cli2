# cli domain

Last verified: 2026-05-06

## Purpose
The agent-facing surface of `tm`. Translates Click commands into `tm_cli.db` repository calls and emits a stable, machine-parseable JSON contract on stdout/stderr. Designed for LLM agents first; the format guarantees here are part of the public contract.

## Contracts
- **Exposes** (Click groups, registered onto the root `cli` in `tm_cli.main`):
  `diagram_group`, `document_group`, `term_group`, `observation_group`,
  `data_item_group`, `node_group`, `container_group`, `flow_group`, `entity_group`,
  `finding_group`,
  plus the `schema_command`, `commands_command`, and `agent_info_command`
  introspection commands.
- **Stdout (success)**:
  - Single-row results emit one compact JSON object on stdout.
  - List/search results emit NDJSON (one JSON object per line). When `len(rows) == limit`, a final `{"_pagination": {"next_offset": ..., "returned": ...}}` line is appended so agents can detect "more available".
  - With `--no-json` (TTY default), single-row payloads pretty-print with `indent=2`. NDJSON list output is unchanged. The default of `--json/--no-json` is auto-detected from `sys.stdout.isatty()`.
  - With `--id-only` (root flag), only bare entity ids are emitted — one per line for lists, one for singletons; `_pagination` footer is suppressed. See `_output._id_only_value` for the field-resolution rule (bare `id` wins, then first `*_id`-suffixed key).
- **Stderr (errors)**: a single JSON object `{"error": {"code", "message", "hint"?, "input"?, ...}}`. Exit codes are stable:
  - `1` = `user_error` (validation, usage, generic ValueError)
  - `2` = `not_found`
  - `3` = `constraint_violation` (with `constraint` ∈ `unique`/`foreign_key`/`check`/`unknown`)
  - `4` = `system_error` (OSError, PermissionError, anything unmapped, and `DfdEditorError` from `_dfd_editor_client`)
- **Id stringification**: every field named `id` or ending in `_id` is emitted as a JSON string, even though storage uses INTEGER PKs. Fields ending in `_ids` (plural) are treated as id lists — each `int` element is stringified individually. Applies recursively in `emit()` and is part of the contract — agents should not assume numeric ids. Note: link-payloads on the `data-item` group use `item_id` (matching the `link-document` convention in `items.py`), while the `*_ids` fields on observation rows use `data_item_ids` (matching `tm data-item get`) — both refer to the same id space.
- **Stdin**: commands that accept `--stdin` read a single JSON object or an array of objects (batch). `enforce_stdin_exclusive` raises `UserError` if `--stdin` is combined with named flags.
- **Standard list/search options**: `--limit` (1..10000, default 50), `--offset` (≥0, default 0), `--sort FIELD` (default `id`), `--order asc|desc`. Applied uniformly via `list_options`. `--json FIELDS` projects a comma-separated subset on output.
- **Default-diagram fallback**: every DFD entity command (`node`, `container`, `flow`, `data-item`) carries a hidden `--diagram-id`. Resolution order: `--diagram-id` > `$TM_DIAGRAM_ID` (parsed as int; `UserError` on non-int, `NotFoundError` on missing diagram) > scan for a diagram named `default` (lowest id wins). Mutating commands auto-create `default` if none exists; list/search commands pass `create_if_missing=False` and emit an empty list instead.
- **Introspection**: `tm schema [<entity>] [--all]` returns Pydantic JSON Schema for each entity's read/create/update (and DocumentSummary). `tm commands` returns the entire Click command tree (groups, commands, options, arguments, choices, hidden flags) as JSON. `tm agent-info` prints a Markdown orientation document for AI agents (per-document workflow, enum reference, output-format rules); it is the only command that does **not** route through `emit()` because it emits documentation rather than data — pulls enum values dynamically from the live Pydantic Literals so the doc can't drift.

## Dependencies
- **Uses**: `click`, `pydantic`, `tm_cli.db` (every repository).
- **Used by**: `tm_cli.main` wires every group onto the root `cli`.
- **Boundary**: must not import from `tm_cli.main` at module load (would circulate). `_introspection.commands_command` does a function-local import of `cli` to walk the tree.

## Key Decisions
- **`TmGroup` overrides `main`**: Click's default `BaseCommand.main` only catches `ClickException` subclasses. We re-invoke with `standalone_mode=False` and route both parse-time and runtime exceptions through `map_exception`, then exit ourselves. This is the only way to ensure ValidationError, sqlite3 errors, and unexpected exceptions all produce the structured JSON envelope.
- **`TmError` extends `ClickException`**: lets us reuse Click's existing dispatch (`exception.show()` → `sys.exit(exception.exit_code)`) when the call path doesn't go through `TmGroup.main`. `show()` is overridden to write the JSON envelope to stderr instead of Click's default human-readable text.
- **`emit()` is the single write path**: every command body funnels through `_output.emit()` so the id-stringification + ISO-encoding + pagination-footer rules are applied uniformly. Callers never `click.echo(json.dumps(...))` directly.
- **NDJSON for lists, pretty JSON for singletons**: NDJSON is streamable and trivially parseable line-by-line by agents; singletons stay readable when piped to a human. The pagination footer only appears when the page is exactly full, so `len(rows) < limit` is an unambiguous "end-of-data" signal.
- **Hidden `--diagram-id`**: agents that don't know which diagram to use shouldn't have to. Default is the lowest-id diagram named `default`, auto-created on first mutating call.

## Invariants
- Every command callback that touches the DB opens a fresh connection via `with connect() as conn:` (commits on clean exit, rolls back on exception). No long-lived connections.
- `emit()` is the only place that writes structured JSON to stdout from this package.
- `--stdin` is mutually exclusive with the entity's named-value flags; combining them is a `user_error` (exit 1), never a partial write.
- The JSON Schema returned by `tm schema` reflects whatever Pydantic produces from the live model — no hand-maintained schema duplication.
- The `commands` tree includes hidden options with `"hidden": true` so agents can discover the full surface programmatically.

## Key Files
- `_errors.py` - `TmError` hierarchy (`UserError`, `NotFoundError`, `ConstraintError`, `SystemError`) + `map_exception(exc)` translator. Owns the exit-code contract.
- `_dfd_editor_client.py` - Stdlib `urllib`-based HTTP client for the dfd_editor `/api/agent/diagrams` endpoints (Imperative Shell). `post_diagram(server, body)` POSTs and returns the server-minted UUID string. `put_diagram(server, remote_id, body)` PUTs an update. Both raise `DfdEditorError` (status + message) on non-2xx, connection errors, or a missing/non-UUID `id` in the POST response. Redirects are not followed. `DfdEditorError` is mapped to `SystemError` (exit 4) at the `diagrams.push_diagram` boundary via `_map_dfd_editor_error`.
- `_output.py` - `emit()` (single write path), `_stringify_ids` (recursive id→string), `_IsoEncoder` (datetime/date), `project_fields()` (`--json FIELDS` projection).
- `_options.py` - Reusable Click decorators (`list_options`, `json_fields_option`, `dfd_diagram_id_option`), `apply_sort` helper, `parse_json_fields` parser, `resolve_default_diagram_id` (DB-aware fallback).
- `_stdin.py` - `enforce_stdin_exclusive` and `read_json_stdin` (single-object or list-of-objects).
- `_introspection.py` - `schema_command` (Pydantic JSON Schema per entity) and `commands_command` (full Click tree).
- `_agent_info.py` - `agent_info_command` (`tm agent-info`). Prints a Markdown orientation document; `_render()` interpolates enum values from the live Pydantic Literals (`ObservationType`, `ObservationStatus`, `NodeType`, `TrustLevel`, `ExternalEntityType`, `StorageType`, `ContainerType`, `PrivilegeLevel`, `Classification`) so the doc stays in sync with the schema.
- `documents.py`, `terms.py`, `observations.py`, `nodes.py`, `containers.py`, `flows.py`, `items.py` - Per-entity Click groups. CRUDL + `search` shape is uniform across entities; DFD entities also expose `link-document`/`unlink-document`/`list-documents`, `link-observation`/`unlink-observation`/`list-observations`, and entity-specific link commands (e.g. `flow add-payload`, `container set-parent`). `observations.py` also exposes `list-nodes`/`list-containers`/`list-flows`/`list-items` reverse-lookup commands.
- `findings.py` - `finding_group` (`tm finding`). CRUDL + `search` + `clear`. `search` text matches `message`/`code`; both `list` and `search` accept `--severity` and `--source` filters. `clear` bulk-deletes all findings for a diagram (optionally scoped to `--source`) and returns `{"cleared": N, "diagram_id": "..."}`. `create` supports `--stdin` batch. `update` uses a `_parse_code_value` sentinel so passing `--code ""` or `--code none` explicitly clears the column.
- `threat_catalog.py` - `threat_catalog_group` (`tm threat-catalog`). `import-dir PATH` (walks markdown files, parses `### T<id>: <Name>` / `**Platforms:**` / `**Description:**` blocks, derives tactic from filename), `list`, `get`, `search`.
- `threats.py` - `threat_group` (`tm threat`). Full CRUDL + `search` with `--rating` filter. `link-observation`/`unlink-observation` and `link-entity`/`unlink-entity` for many-to-many threat↔observation and threat↔entity junctions.
- `entities.py` - `entity_group` (`tm entity`). Single `get` command: kind-agnostic DFD entity resolver. Looks up `entity.kind` then dispatches to the matching kind repo, emitting the kind-specific payload with a top-level `"kind"` discriminator. Enables agent flows: observation `*_ids` → `tm entity get <id>` → full payload without knowing the kind in advance.
- `diagrams.py` - Same as above plus `push` (`tm diagram push`). On first push, calls `post_diagram` and persists the returned UUID via `DiagramRepository.set_remote_id`; on subsequent pushes, calls `put_diagram` with the stored UUID. Reads `DFD_EDITOR_URL` from the environment if `--server` is not given; raises `UserError` (exit 1) if neither is set. Uses `dfd_export.to_dfd_editor_dict` to assemble the payload from repo reads (loads flow payloads via `DataFlowRepository.payloads_for_diagram` so dfd_editor receives directional `nodeN_src_data_item_refs`).

## Gotchas
- The root `cli` group's `--json/--no-json` is **separate** from `--json FIELDS` on individual list/search commands. The root flag toggles global JSON-mode (compact vs pretty); `--json FIELDS` is a per-command field projection. They don't conflict because they live at different levels and have different value shapes.
- `_introspection.commands_command` does `from tm_cli.main import cli` at call time, not import time. Don't move that import to module top level — `tm_cli.main` imports this module to register the command.
- `emit()` stringifies any int field whose key is `id` or ends in `_id`, and stringifies each int element of any list whose key ends in `_ids`. If you ever introduce a non-id int field with such a name (e.g., `paid_id`), it will be silently coerced. Field-name collisions are the entity author's responsibility (per the comment in `_output._stringify_ids`).
- `TmGroup.main` re-runs `super().main(..., standalone_mode=False)` and then handles `sys.exit` itself. Tests using Click's `CliRunner` rely on `standalone_mode=False` semantics; if you change this you must verify `tests/cli/test_errors.py` still passes.
- `resolve_default_diagram_id(create_if_missing=False)` returns `None` (caller emits empty list); `create_if_missing=True` raises if explicit_id is set but missing. Don't accidentally swap the booleans on list vs mutate paths — list commands MUST pass `create_if_missing=False` or they'd mint a `default` diagram on every empty read.
- DFD command `_create_variant_batch` mutates each model with the resolved `diagram_id` before dispatch; if a stdin batch sets `diagram_id` per-item it gets overridden. This is intentional — the resolved fallback wins — but worth noting if a future caller wants per-item routing.
