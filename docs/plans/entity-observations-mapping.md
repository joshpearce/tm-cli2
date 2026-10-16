# Entity ↔ Observation Mapping

## Goal

Mirror entity ↔ document linking for observations: any DFD entity kind linkable to any number of observations and vice versa, idempotent link/unlink, reverse listings on both sides. Observation reads (`get` / `list` / `search`) carry the linked entity ids inline, split by kind so agents can call the matching `tm <kind> get` directly. Add a kind-agnostic `tm entity get <id>` resolver for any DFD entity id.

## Approach

Direct mirror of `entity_documents`: one junction table, one repository, symmetric CLI commands. Every DFD kind's PK = `entity.id`, so a single junction covers all four kinds; the same fact lets `tm entity get` dispatch via a one-table `kind` lookup. No migration framework — PR description must tell consumers to wipe `$TM_DB_PATH`.

## Step 1 — Schema, repository, and Observation read shape

**Schema** — add to `_SCHEMA_SQL` in `src/tm_cli/db/connection.py`, immediately after `entity_documents`:

```
entity_observations (
  entity_id      REFERENCES entity(id)       ON DELETE CASCADE,
  observation_id REFERENCES observations(id) ON DELETE CASCADE,
  PRIMARY KEY (entity_id, observation_id)
) STRICT
+ idx_entity_observations_observation_id ON entity_observations(observation_id)
```

**Repository** — create `src/tm_cli/db/entity_observations.py` defining `EntityObservationRepository(conn)`:

- `link(entity_id, observation_id)` — INSERT OR IGNORE
- `unlink(entity_id, observation_id) -> bool`
- `observations_for_entity(entity_id) -> list[Observation]`
- `nodes_for_observation`, `containers_for_observation`, `flows_for_observation`, `items_for_observation` — JOIN via `entity_observations.entity_id = <kind>.id`, ordered by id
- `linked_ids_by_kind(observation_id) -> LinkedIds` — single `entity_observations` ⨝ `entity` query, ids bucketed by `entity.kind`. `LinkedIds` is a TypedDict with `node_ids`, `container_ids`, `flow_ids`, `data_item_ids` (each `list[int]`, ASC, `[]` default). Kind mapping: `'data_flow'` → `flow_ids` (matches `tm flow get`); `'data_item'` → `data_item_ids` (matches `tm data-item get`).
- `linked_ids_by_kind_for(observation_ids: list[int]) -> dict[int, LinkedIds]` — single batched query (`WHERE eo.observation_id IN (?, …)`) plus Python-side grouping; keys always present.

Reuse the `_<KIND>_COLUMNS_QUALIFIED` / `_row_to_<kind>` helpers exactly as `entity_documents.py` does. Re-export the repo from `src/tm_cli/db/__init__.py`.

**Observation read shape** — in `src/tm_cli/db/models.py`, extend the `Observation` read model with `node_ids: list[int] = []`, `container_ids: list[int] = []`, `flow_ids: list[int] = []`, `data_item_ids: list[int] = []`. `ObservationCreate` and `ObservationUpdate` unchanged (links are mutated only via the new CLI commands). In `src/tm_cli/db/observations.py`:

- `get(id)`: populate from `EntityObservationRepository.linked_ids_by_kind(id)`.
- `list(...)` / `search(...)`: one `linked_ids_by_kind_for([r["id"] for r in rows])` call, then attach per-row. No N+1.

**Emit contract extension** — in `src/tm_cli/cli/_output.py`, extend `_is_id_key` to also match the `_ids` suffix, and update `_stringify_ids` to walk such values as lists and stringify each `int` element (skip `bool`, leave non-ints alone). Generalizes the existing `_id`-string contract to plural lists.

**Docs** — update `db/CLAUDE.md` (new repo, the four per-kind id lists on Observation, cascade behavior) and `cli/CLAUDE.md` (the `_ids`-plural stringification rule).

**Acceptance**:
- Schema cascades fire on observation delete and on transitive `diagram` → `entity` → `entity_observations` delete; `link` is idempotent.
- `tm observation get <id>` includes the four `*_ids` fields (stringified, ASC, `[]` when none); a node-linked observation produces `node_ids: ["5"]` and not, e.g., `container_ids: ["5"]`.
- `tm observation list` / `search` emit the four fields on every row using a single batched query (verifiable by trace callback or row-count fake).
- `tm schema observation` reflects the new fields.

## Step 2 — Observation CLI: reverse-lookup commands

In `src/tm_cli/cli/observations.py`:

- Import `EntityObservationRepository`.
- Add a `_list_for_observation(ctx, obs_id, *, limit, offset, sort_field, order, json_fields, query)` helper structurally identical to `_list_for_document` in `documents.py`: 404 on missing observation, run the query lambda against `EntityObservationRepository`, apply sort/slice/project, emit NDJSON.
- Add four commands to `observation_group`: `list-nodes`, `list-containers`, `list-flows`, `list-items`. Each takes `obs_id`, decorated with `@list_options @json_fields_option`, delegates to the helper with a lambda over the matching `<kind>_for_observation` method.

**Acceptance**: `tm observation list-nodes <id>` returns NDJSON of linked nodes (empty list when none; `_pagination` footer only on full pages). Missing observation returns the standard `not_found` envelope (exit 2). Same shape for `list-containers`/`list-flows`/`list-items`.

## Step 3 — DFD entity CLI: link/unlink/list-observations

In each of `src/tm_cli/cli/nodes.py`, `containers.py`, `flows.py`, `items.py`, append a block mirroring the existing `link-document`/`unlink-document`/`list-documents` commands at the bottom of the file:

- `link-observation <entity_id> <obs_id>` — emits `{"linked": bool, "<entity>_id": str, "observation_id": str, "reason"?: "already_linked"}`. Uses the existing already-linked pattern (`observations_for_entity` membership check, then INSERT OR IGNORE).
- `unlink-observation <entity_id> <obs_id>` — emits `{"unlinked": bool, "<entity>_id": str, "observation_id": str, "reason"?: "not_linked"}`.
- `list-observations <entity_id>` — `@list_options @json_fields_option`; 404 via the kind repo if the entity is missing; calls `observations_for_entity`; NDJSON output (each row carries its own `*_ids` fields).

Add `EntityObservationRepository` to each file's `tm_cli.db` import block. `_agent_info.py` requires no edits — enums are pulled dynamically and new commands surface through `tm commands` automatically.

**Acceptance**: idempotency holds on both `link-observation` and `unlink-observation` across all four DFD groups with the documented `reason` field on no-ops. `tm <kind> list-observations <id>` returns observations in `id ASC` (each row carrying its own `*_ids` fields). Deleting either endpoint removes the link.

## Step 4 — `tm entity get` kind-agnostic resolver

Create `src/tm_cli/cli/entities.py` defining `entity_group` (`tm entity ...`) with a single `get` command:

- `tm entity get <id>` — `SELECT kind FROM entity WHERE id = ?`; miss → standard NotFoundError. Hit → dispatch to the matching kind repo and emit `{"kind": <entity.kind literal>, **<kind_payload>}` (kind-specific fields flattened with a top-level `kind` discriminator). `kind` is the raw `entity.kind` value (so `data_flow`, not `flow`); agents map `data_flow` → `tm flow get`, `data_item` → `tm data-item get`. Standard `emit()` so `--id-only` and `--json FIELDS` work.

Register `entity_group` in `src/tm_cli/main.py`. No new DB code — existing kind repos handle the reads.

**Acceptance**:
- `tm entity get <id>` returns the same payload as `tm <kind> get <id>` plus a top-level `kind` field, for any of the four DFD kinds.
- `tm entity get <missing-id>` returns the standard `not_found` envelope (exit 2).
- The command appears in `tm commands` introspection.
- An agent flow works end-to-end: `tm observation get O` → read e.g. `flow_ids[0]` → `tm entity get <that_id>` → full DataFlow payload with `"kind": "data_flow"`.

## Step 5 — Tests + snapshots

- `tests/cli/test_entity_observations.py` mirroring `tests/cli/test_entity_documents.py`: link/unlink idempotency across all four DFD kinds, reverse listing on both sides, cascade-on-delete (observation, entity, diagram), 404 for missing endpoint. Syrupy where the existing file does.
- `Observation`-`*_ids` round-trip coverage: present on `get`/`list`/`search`; an observation linked to one of each kind populates exactly the right field; unlinked observations show four empty lists; list path verified to add a single batched query (row-count fake or `set_trace_callback`).
- `tests/cli/test_entity_get.py` (or extend an existing kind test): kind-agnostic `tm entity get` for all four kinds + 404; verify the `kind` field matches `entity.kind`; verify the inner payload equals what `tm <kind> get` returns (modulo the added `kind` field).
- Unit test for `_stringify_ids` on a `*_ids` field with empty and non-empty values.
- Run `make test` and accept the snapshot churn:
  - Every existing observation snapshot gains four `*_ids: []` fields — largest footprint: `test_observations`, `test_observations_help`, snapshots of `tm schema observation` and `tm commands`.
  - `test_introspection` / `test_help_meta` gain the new commands (3 per DFD group + 4 on observation_group + the entire `tm entity` group).

**Acceptance**: `make lint && make test` passes; every accepted snapshot diff traces to (a) new `*_ids` fields on observation payloads, (b) new commands in introspection/help, or (c) the `_ids` stringification rule applied to populated lists.

## Definition of done

All step-level criteria met, `make lint && make test` green, both `CLAUDE.md` files updated, PR description tells consumers to drop their local DB.
