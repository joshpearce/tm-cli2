# Plan: Process Components

Add a `process_component` entity type representing internal units (controllers, services, filters, etc.) within a process node. Components are informational — flows remain at the process-node level. Component type is an enum. Data-item parenting to components is deferred.

## Design Decisions

- `process_component` is a DFD entity (minted via `_mint_entity_id` with kind `'process_component'`)
- `component_type` is a CHECK-constrained enum: `controller`, `service`, `filter`, `repository`, `utility`, `client`, `handler`, `interceptor`, `configuration`
- `parent_process_id` references `node(id)` with `ON DELETE CASCADE` — validated at the application layer to ensure the referenced node has `type='process'`
- No flow participation in this iteration
- Links to documents and observations use the existing generic junction tables (`entity_documents`, `entity_observations`)

---

## Step 1: Schema and Models

**What changes:** Add the `process_component` table to `_SCHEMA_SQL` in `connection.py`, add `'process_component'` to the `entity.kind` CHECK constraint, and define Pydantic models.

**Files:**
- `src/tm_cli/db/connection.py` — Add `'process_component'` to entity kind CHECK. Add table:
  ```
  process_component(
    id              INTEGER PK → entity(id) CASCADE,
    parent_process_id INTEGER NOT NULL → node(id) CASCADE,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    component_type  TEXT NOT NULL CHECK(enum values)
  )
  + index on parent_process_id
  ```
- `src/tm_cli/db/dfd_models.py` — Add `ComponentType` Literal, `ProcessComponent`, `ProcessComponentCreate`, `ProcessComponentUpdate` models following existing patterns (e.g. `DataItem` models)

**Acceptance criteria:**
- `make lint` passes
- Existing tests pass unchanged (schema is additive, IF NOT EXISTS)
- Models can be instantiated and validated in a unit test

---

## Step 2: Repository

**What changes:** Create `ProcessComponentRepository` with full CRUDL + search, following `dfd_nodes.py` / `dfd_items.py` patterns.

**Files:**
- `src/tm_cli/db/dfd_process_components.py` — New file. Repository with:
  - `create()` — mints entity id, validates parent node is type='process', inserts row
  - `get()`, `update()`, `delete()`, `list()`, `search()` — standard pattern
  - `list()` and `search()` support `--parent-process-id` and `--component-type` filters
- `src/tm_cli/db/__init__.py` — Export new repository and models

**Acceptance criteria:**
- Unit tests cover create, get, update, delete, list, search
- Creating with a non-process parent node raises an appropriate error
- `search()` filters by text, component_type, and parent_process_id
- Deleting a parent process node cascades to delete its components

---

## Step 3: CLI Commands

**What changes:** Create the `process-component` command group with all CRUD + search + link commands, wire into `main.py`.

**Files:**
- `src/tm_cli/cli/process_components.py` — New file. Commands:
  - `create` — with `--name`, `--description`, `--component-type`, `--parent-process-id`, `--stdin`, `--if-not-exists`, `--dry-run`
  - `list` — with `--parent-process-id`, `--component-type` filters + standard list_options
  - `get <id>`, `update <id>`, `delete <id>`, `search <text>`
  - `link-document`, `unlink-document`, `list-documents`
  - `link-observation`, `unlink-observation`, `list-observations`
  - `set-parent <component_id> <process_node_id>` — reassign parent
- `src/tm_cli/main.py` — Register `process_component_group`
- `src/tm_cli/cli/entities.py` — Add `'process_component'` case to entity resolver

**Acceptance criteria:**
- All commands follow existing CLI patterns (emit JSON, structured errors, stdin batch support on create)
- Snapshot tests for each command's happy path output
- `tm process-component list --parent-process-id X` filters correctly
- `tm entity get <component_id>` resolves correctly

---

## Step 4: Linking + Agent-Info

**What changes:** Wire process components into the linking reverse-lookup queries and update agent-info orientation.

**Files:**
- `src/tm_cli/db/entity_documents.py` — Add `process_components_for_document()` method
- `src/tm_cli/db/entity_observations.py` — Add `process_components_for_observation()` + update `_KIND_TO_FIELD`
- `src/tm_cli/cli/_agent_info.py` — Add process-component guidance to:
  - Domain quick reference (component_type enum values)
  - Entity extraction section: "When ingesting a codebase, create ONE process node per deployable service. Internal classes/services/controllers → `tm process-component create`"
  - Command reference section

**Acceptance criteria:**
- `tm document list-entities <doc_id>` includes linked process components
- `tm agent-info` output includes process-component guidance and enum values
- Existing snapshot tests for agent-info updated to reflect new content

---

## Step 5: Seed Data + Acceptance Tests

**What changes:** Add process component seed data and end-to-end acceptance tests.

**Files:**
- `tests/fixtures/seed.py` — Add sample process components parented to existing seed process nodes
- `tests/acceptance/` — Add acceptance test exercising the full workflow: create process node → create components → list/filter → link docs/observations → search → delete cascade
- Update any affected snapshots

**Acceptance criteria:**
- `make test` passes with all new and existing tests
- `make lint` passes
- Acceptance test covers: create, list with filters, get, update, search, link/unlink document, link/unlink observation, set-parent, delete, cascade delete via parent

---

## Definition of Done

- All 5 steps complete with passing acceptance criteria
- `make lint && make test` green
- No changes to existing entity behavior (all pre-existing tests unchanged or snapshots updated only for agent-info additions)
- `tm commands` output includes the new `process-component` group
