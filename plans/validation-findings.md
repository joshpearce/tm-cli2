# Plan: Validation Findings Surface

## Summary

Add a `validation_finding` entity to tm-cli that lets callers attach error/warning findings to diagram entities, persisted in SQLite, exposed via `tm finding` CLI commands (CRUDL + bulk-clear), and included in the `tm diagram push` payload as the `"validation"` array the dfd_editor server already accepts.

---

## Step 1: DB models + schema + repository

**What changes:**

- `dfd_models.py` — add `FindingSeverity = Literal["error", "warning"]`, plus `ValidationFindingCreate`, `ValidationFindingUpdate`, `ValidationFinding` Pydantic models:
  - `ValidationFindingCreate`: `entity_id: int | None = None`, `severity: FindingSeverity`, `message: str`, `source: str`, `code: str | None = None`. `extra="forbid"`.
  - `ValidationFindingUpdate`: all fields optional, same set minus `entity_id` (entity binding is immutable, like flow endpoints). `extra="forbid"`.
  - `ValidationFinding` (read model): `id: int`, `diagram_id: int`, `entity_id: int | None`, `severity`, `message`, `source`, `code: str | None`, `created: datetime`.
- `connection.py` — add `validation_finding` table to `_SCHEMA_SQL`:
  ```
  validation_finding (
    id          INTEGER PRIMARY KEY,
    diagram_id  INTEGER NOT NULL REFERENCES diagram(id) ON DELETE CASCADE,
    entity_id   INTEGER REFERENCES entity(id) ON DELETE CASCADE,
    severity    TEXT NOT NULL CHECK (severity IN ('error', 'warning')),
    message     TEXT NOT NULL,
    source      TEXT NOT NULL,
    code        TEXT,
    created     TEXT NOT NULL  -- repo-managed UTC ISO 8601
  ) STRICT
  ```
  No entry in the `entity` master-id table — findings are metadata, not DFD elements.
- New file `dfd_findings.py` — `ValidationFindingRepository(conn)`:
  - `create(diagram_id, ValidationFindingCreate)` — validates `entity_id` belongs to `diagram_id` if non-null (same-diagram check, like flow endpoint validation), sets `created = now(UTC)`, returns `ValidationFinding`.
  - `get(finding_id)` — returns row or raises `ValueError`.
  - `update(finding_id, ValidationFindingUpdate)` — partial patch via `model_dump(exclude_unset=True)`, DFD nullable-update pattern.
  - `delete(finding_id)` — returns `bool`.
  - `list(diagram_id, *, limit, offset)` — standard list with diagram scope.
  - `search(diagram_id, text=None, *, severity=None, source=None, limit, offset)` — text searches `message` and `code`; optional severity/source filters.
  - `clear(diagram_id, *, source=None)` — bulk delete. If `source` given, deletes only that source's findings. Returns count deleted.
  - `for_diagram(diagram_id)` — returns all findings (no limit), used internally by the push path.
- `__init__.py` — re-export new models and repo.

**Files:** `dfd_models.py`, `connection.py`, `dfd_findings.py` (new), `__init__.py`

**Verify:** Unit tests for repository CRUD, the same-diagram entity_id check, cascade delete (delete diagram removes findings, delete entity removes its findings), clear with and without source filter, and search with severity/source filters.

---

## Step 2: Wire findings into `dfd_export.py` and the push path

**What changes:**

- `dfd_export.py` — add a `findings` parameter to `to_dfd_editor_dict()`:
  ```
  findings: list[ValidationFinding] = []
  ```
  Map each finding to the server contract shape:
  - `guid`: if `entity_id` is non-null, look up the entity's `kind` from a provided mapping to derive the collection name, then call `guid_for(diagram_id, collection, entity_id)`. If `entity_id` is null, emit `null`.
  - `severity`, `message`, `code` map directly.
  Add `"validation": [...]` to the returned dict (only when the list is non-empty, to avoid sending an empty array on clean diagrams).

  The `kind` lookup needs a new parameter: `entity_kinds: dict[int, str]` — a mapping of `entity_id -> kind` for all entities in the diagram. The push command already loads all four entity types; building this mapping from those lists is trivial. Alternatively, the push command can query `entity` directly for a bulk id→kind map. Either works.

  Add a helper `_ENTITY_KIND_TO_COLLECTION = {"node": "nodes", "container": "containers", "data_flow": "data_flows", "data_item": "data_items"}` for the guid_for dispatch.

- `cli/diagrams.py` `push_diagram` — after loading entities and before calling `to_dfd_editor_dict`:
  1. `ValidationFindingRepository(conn).for_diagram(diagram_id)` to load findings.
  2. Build `entity_kinds` map from the already-loaded node/container/flow/item lists.
  3. Pass both to `to_dfd_editor_dict(... findings=findings, entity_kinds=entity_kinds)`.
  4. Add `error_count`, `warning_count` to the emitted output dict (computed from loaded findings before push).

**Files:** `dfd_export.py`, `cli/diagrams.py`

**Verify:** Unit tests for `to_dfd_editor_dict` with findings (entity-level + diagram-level + empty), correct GUID generation matching existing element GUIDs. Push CLI test (monkeypatched) asserting `"validation"` array appears in the body sent to the server, and that `error_count`/`warning_count` appear in the emitted output.

---

## Step 3: CLI commands (`tm finding`)

**What changes:**

- New file `cli/findings.py` — `finding_group` Click group (`tm finding`):
  - `create` — `--diagram-id` (uses `dfd_diagram_id_option`), `--entity-id` (optional), `--severity`, `--message`, `--source`, `--code` (optional). Supports `--stdin` (single or batch). Uses `resolve_default_diagram_id(create_if_missing=True)`.
  - `get ID` — standard get.
  - `update ID` — partial update (severity, message, source, code). `--stdin` supported.
  - `delete ID` — standard delete, returns `{"deleted": bool, "id": str}`.
  - `list` — `--diagram-id`, standard `list_options`. `resolve_default_diagram_id(create_if_missing=False)`.
  - `search` — `--diagram-id`, `--severity`, `--source`, text argument. Standard `list_options`.
  - `clear` — `--diagram-id`, `--source` (optional). Bulk delete. Returns `{"cleared": int, "diagram_id": str}`. `resolve_default_diagram_id(create_if_missing=False)`.

  All commands follow existing patterns: `with connect() as conn`, `emit()` for output, `map_exception` for errors.

- `main.py` — register `finding_group` on the root `cli`.
- `_agent_info.py` — add findings section to the agent-info markdown (optional, can defer).
- `_introspection.py` — findings models auto-discovered via existing `tm schema` if models are re-exported properly.

**Files:** `cli/findings.py` (new), `main.py`, optionally `_agent_info.py`

**Verify:** CLI tests with `CliRunner` + Syrupy snapshots for each command. Stdin batch mode. Error paths (invalid severity, entity_id not in diagram, finding not found).

---

## Step 4: Test fixtures + acceptance test

**What changes:**

- `tests/fixtures/seed.py` — add 2-3 seed findings to `seed()` (one entity-targeted error, one diagram-level warning, varying sources). Add `finding_id_*` fields to `SeedIds`.
- `tests/acceptance/` — new `test_finding_workflow.py`: end-to-end create/list/search/clear/push cycle driven via `CliRunner`. Verify that `tm diagram push` (with the in-process WSGI stub from existing acceptance tests) includes the `"validation"` array with correct GUIDs matching pushed elements.
- Update existing push snapshot tests if the push output shape changed (added `error_count`/`warning_count`).

**Files:** `tests/fixtures/seed.py`, `tests/acceptance/test_finding_workflow.py` (new), possibly `tests/cli/test_diagram_push.py` snapshot updates.

**Verify:** `make test` passes. Snapshots are stable. Acceptance test confirms round-trip: create findings -> push -> server receives correct validation array.

---

## Definition of Done

1. `make lint` passes with zero violations.
2. `make test` passes — all existing tests green, no regressions.
3. `tm finding create/get/update/delete/list/search/clear` all work and emit the standard JSON contract.
4. `tm diagram push` includes `"validation"` array in the payload when findings exist for the diagram.
5. Push output includes `error_count` and `warning_count` fields.
6. Deleting a diagram cascades to its findings. Deleting an entity cascades to its findings.
7. `clear --source X` deletes only source X's findings; `clear` without `--source` deletes all.
8. Snapshot tests cover all CLI command happy paths.
9. Acceptance test covers the create-findings → push → server-receives-validation-array flow.
