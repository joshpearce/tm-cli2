# Agent CLI — Test Requirements

This document maps every acceptance criterion in `docs/design-plans/2026-05-05-agent-cli.md` (slug-prefixed `agent-cli.AC1.*` through `agent-cli.AC11.*`) to the concrete automated test or human-verification step that proves it. It is the contract between the design plan and the implementation phases: every AC must land here with either a runnable test or a documented manual procedure, and every phase's "Acceptance Criteria Coverage" section must be reflected by a test rooted in this document.

The order below is: introduction (taxonomy, conventions, special cases), AC1–AC11 each broken out criterion-by-criterion, and a coverage summary table at the end.

---

## Introduction

### Test taxonomy

The plan uses four test categories, listed from cheapest to most expensive:

- **Unit tests** — pure-logic tests of internal helpers in `tests/cli/test_*.py`. These cover the `_errors.map_exception` mapper, the `_options.resolve_default_diagram_id` resolver, the `_options` sort/projection helpers, the `_stdin.read_json_stdin` parser, and the `_introspection.serialize_command_tree` walker. They never hit Click and never open a database connection (or use an in-memory connection minimally for the resolver tests). Each unit test is named after the helper it exercises.

- **Integration tests** — `click.testing.CliRunner` driven against an in-memory SQLite database via the `db_path` and `db_with_seed` fixtures from `tests/conftest.py`. One test file per entity (`tests/cli/test_documents.py`, `tests/cli/test_terms.py`, `tests/cli/test_observations.py`, `tests/cli/test_diagrams.py`, `tests/cli/test_data_items.py`, `tests/cli/test_nodes.py`, `tests/cli/test_containers.py`, `tests/cli/test_flows.py`) plus per-junction files where the junction crosses entities (`tests/cli/test_document_terms.py`, `tests/cli/test_node_variants.py`, `tests/cli/test_container_membership.py`, `tests/cli/test_flow_payload.py`, `tests/cli/test_entity_documents.py`). These tests assert exit codes, stdout/stderr split (via `mix_stderr=False`), parsed JSON shape, and pre/post DB state.

- **Acceptance test** — a single end-to-end workflow test at `tests/acceptance/test_dfd_workflow.py` that drives the full CLI through the agent-cli-design.md golden scenario ("create a diagram with two process nodes and a data flow between them"). It uses only stdout-derived ids — the test simulates an agent that reads the help text and works from JSON output alone. It is the integration test that proves the API surface composes.

- **Golden help / output snapshots** — Syrupy-pinned snapshots under `tests/cli/__snapshots__/test_*_help.ambr` (help text) and `tests/golden/json/*` (representative JSON outputs). Volatile fields (timestamps, ids beyond the deterministic seed) are masked by a custom Syrupy serializer to `"<DATETIME>"` / `"<INT>"`. Drift fails the build; a developer must explicitly run `pytest --snapshot-update` to bless a change. Treat snapshot updates with the same review rigor as schema changes — they are the agent-facing contract.

### Conventions

- All test paths are relative to the repository root.
- Where a single AC is exercised across multiple phases (the universal CRUDL behaviors in `agent-cli.AC1`, for example), the criterion is listed once and each phase's contribution is enumerated underneath.
- The "phase" column in the summary table refers to the phase that ships and verifies the test, not the phase that consumes the helper.

### Special cases (read these before scanning the AC mapping)

These four ACs deviate from the standard "one integration test per criterion" pattern. They are flagged here so a future reviewer does not chase ghosts.

1. **`agent-cli.AC5.5` (CHECK constraint exit code 3) is structurally unreachable through the CLI.** Pydantic `Literal` validation on enum fields (`ObservationType`, `ObservationStatus`, `Classification`, `TrustLevel`, `ExternalEntityType`, `StorageType`, `PrivilegeLevel`, `NodeType`, `ContainerType`) rejects bad values at the Click parser layer before the SQL CHECK can fire. There is no end-to-end CLI invocation that produces a `sqlite3.IntegrityError("CHECK constraint failed: ...")`. The criterion is therefore covered solely by the unit test `tests/cli/test_errors.py::test_integrity_check_maps_to_constraint`, which constructs the exception directly and asserts that `_errors.map_exception` produces a `ConstraintError` with `constraint="check"` and exit code 3. This is a documented limitation, not a gap; if a future entity adds a CHECK constraint reachable without enum validation (e.g., a numeric range), it must add an integration test then.

2. **`agent-cli.AC5.6` (`OSError` / `PermissionError` → exit 4) is similarly unit-only.** End-to-end exercise (e.g., `chmod 000` on the database file path and invoking `tm document list`) is portably awkward across CI environments and the design's "Done when" criteria do not require it. Coverage is the unit test `tests/cli/test_errors.py::test_oserror_maps_to_system_error` plus `test_permissionerror_maps_to_system_error`, which feed a freshly raised `PermissionError` and `OSError` through `map_exception` and assert `SystemError` with exit code 4. If a future flow surfaces this path through normal use, add coverage then.

3. **`agent-cli.AC9.5` (`--diagram-id` hidden=true visible in `tm commands --json`) is split across Phase 4 and Phase 8.** Phase 4 verifies the structural attribute via Click reflection (`Command.params` introspection on each DFD command shows the option exists with `hidden=True`). Phase 8 verifies it end-to-end by invoking `tm commands --json` and walking the tree to find the option with `name=="diagram_id"` and `hidden==True` on every DFD `create` leaf. Both contribute; both are listed below.

4. **`agent-cli.AC10.5` (commands tree golden snapshot) is explicitly fragile by design.** A snapshot of the full `tm commands --json` output is pinned via Syrupy and the masking serializer. Any drift — including the addition of a single new option, the rename of a command, or a tweak to a help string — fails the test. This is intentional: the command tree is the agent contract. Drift requires explicit `pytest --snapshot-update` and human review of the diff.

### Fixtures referenced below

- `db_path` — produces a temporary SQLite file path with `init_schema()` already run, no rows. Useful for tests that seed their own data.
- `db_with_seed` — `db_path` plus a deterministic seed checked in at `tests/fixtures/seed.py` (one diagram named `"non-default"`, one process node, one external-entity, one data-store, one container, one flow, two data-items, two documents, three terms, two observations). Seed ids are deterministic and asserted by a sanity test in Phase 1.
- `cli_runner` — a `click.testing.CliRunner(mix_stderr=False)` instance configured to suppress stdin and propagate `TM_DB_PATH` from the active fixture into the subprocess environment.

---

## agent-cli.AC1: Standard CRUDL behaviors (universal across entities)

> Every entity exposes the same six verbs (`list`, `get`, `create`, `update`, `delete`, `search`) with consistent semantics. AC1 is exercised once per entity, per phase that introduces the entity. The criteria below are listed once with a row per phase contribution.

### agent-cli.AC1.1 Success: `list` returns NDJSON when piped

**Criterion:** `list` returns all rows for an entity as NDJSON when stdout is piped (one JSON object per line).

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 2 | Document | `tests/cli/test_documents.py` | `test_list_pipes_ndjson` | seeded fixture; `tm document list`; stdout has N parseable JSON lines (one per row); no `[`/`]` wrapper. |
| 3 | Term | `tests/cli/test_terms.py` | `test_list_pipes_ndjson` | same shape, three seeded terms. |
| 3 | Observation | `tests/cli/test_observations.py` | `test_list_pipes_ndjson` | two seeded observations. |
| 4 | Diagram | `tests/cli/test_diagrams.py` | `test_list_pipes_ndjson` | one seeded diagram. |
| 4 | DataItem | `tests/cli/test_data_items.py` | `test_list_pipes_ndjson` | two seeded items, scoped to default-or-explicit diagram. |
| 5 | Node | `tests/cli/test_nodes.py` | `test_list_pipes_ndjson` | three seeded nodes (mixed variants). |
| 6 | Container | `tests/cli/test_containers.py` | `test_list_pipes_ndjson` | one seeded container. |
| 7 | DataFlow | `tests/cli/test_flows.py` | `test_list_pipes_ndjson` | one seeded flow. |

### agent-cli.AC1.2 Success: `get` returns the full model

**Criterion:** `get` returns the full model for an existing id (including server-set fields like `last_imported`).

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 2 | Document | `tests/cli/test_documents.py` | `test_get_returns_full_model_with_content` | response includes `content` (which `list`/`search` exclude) and `last_imported`. |
| 3 | Term | `tests/cli/test_terms.py` | `test_get_returns_full_model` | full Term row with `last_updated`. |
| 3 | Observation | `tests/cli/test_observations.py` | `test_get_returns_full_model` | full Observation row including `observation_type` and `status`. |
| 4 | Diagram | `tests/cli/test_diagrams.py` | `test_get_returns_full_model` | name, description, author, created. |
| 4 | DataItem | `tests/cli/test_data_items.py` | `test_get_returns_full_model` | including `parent_node_id` and `classification`. |
| 5 | Node | `tests/cli/test_nodes.py` | `test_get_returns_full_model_per_variant` | parametrized over the three variants; result includes the variant-specific fields. |
| 6 | Container | `tests/cli/test_containers.py` | `test_get_returns_full_model_per_variant` | parametrized over `trust_boundary` and `container`. |
| 7 | DataFlow | `tests/cli/test_flows.py` | `test_get_returns_full_model` | full row with canonical-ordered endpoints. |

### agent-cli.AC1.3 Success: `create` returns new row with id

**Criterion:** `create` with valid flags returns the new row, including the synthesized id (string-quoted) and any server-managed timestamps.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 2 | Document | `tests/cli/test_documents.py` | `test_create_returns_new_row` | id is a string; `last_imported` is set; round-trips via `get`. |
| 3 | Term | `tests/cli/test_terms.py` | `test_create_returns_new_row` | id stringified; `last_updated` set. |
| 3 | Observation | `tests/cli/test_observations.py` | `test_create_returns_new_row` | enum fields persist as their literal string values. |
| 4 | Diagram | `tests/cli/test_diagrams.py` | `test_create_returns_new_row` | created timestamp set. |
| 4 | DataItem | `tests/cli/test_data_items.py` | `test_create_returns_new_row` | scoped to a diagram (default-resolver may have created one). |
| 5 | Node | `tests/cli/test_nodes.py` | `test_create_<variant>_returns_new_row` | one test per variant: process, external-entity, data-store. Each verifies its variant-specific fields. |
| 6 | Container | `tests/cli/test_containers.py` | `test_create_<variant>_returns_new_row` | one test per variant. |
| 7 | DataFlow | `tests/cli/test_flows.py` | `test_create_returns_new_row` | endpoints stringified, canonical ordering applied (covered also by AC11.1). |

### agent-cli.AC1.4 Success: `update` returns the resulting row

**Criterion:** `update` with a valid patch returns the resulting row (full object, not `{"ok": true}`).

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 2 | Document | `tests/cli/test_documents.py` | `test_update_returns_full_row` | response is the full Document, not an envelope. |
| 3 | Term | `tests/cli/test_terms.py` | `test_update_returns_full_row` | same. |
| 3 | Observation | `tests/cli/test_observations.py` | `test_update_returns_full_row` | same. |
| 4 | Diagram | `tests/cli/test_diagrams.py` | `test_update_returns_full_row` | same. |
| 4 | DataItem | `tests/cli/test_data_items.py` | `test_update_returns_full_row` | same. |
| 5 | Node | `tests/cli/test_nodes.py` | `test_update_<variant>_returns_full_row` | per variant. |
| 6 | Container | `tests/cli/test_containers.py` | `test_update_<variant>_returns_full_row` | per variant. |
| 7 | DataFlow | `tests/cli/test_flows.py` | `test_update_returns_full_row` | endpoints unchanged (immutable on update — see AC11.3). |

### agent-cli.AC1.5 Failure: `get` of missing id exits 2 with `not_found`

**Criterion:** `get` of a missing id exits 2 with `error.code = "not_found"`.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 2 | Document | `tests/cli/test_documents.py` | `test_get_missing_id_exits_2` | `tm document get 999999`; exit code 2; stderr is JSON with `error.code == "not_found"`; stdout empty. |
| 3 | Term | `tests/cli/test_terms.py` | `test_get_missing_id_exits_2` | same shape. |
| 3 | Observation | `tests/cli/test_observations.py` | `test_get_missing_id_exits_2` | same. |
| 4 | Diagram | `tests/cli/test_diagrams.py` | `test_get_missing_id_exits_2` | same. |
| 4 | DataItem | `tests/cli/test_data_items.py` | `test_get_missing_id_exits_2` | same. |
| 5 | Node | `tests/cli/test_nodes.py` | `test_get_missing_id_exits_2` | same. |
| 6 | Container | `tests/cli/test_containers.py` | `test_get_missing_id_exits_2` | same. |
| 7 | DataFlow | `tests/cli/test_flows.py` | `test_get_missing_id_exits_2` | same. (Phase 7 also explicitly verifies AC1.5 in its coverage table.) |

### agent-cli.AC1.6 Failure: `update` of missing id exits 2 with `not_found`

**Criterion:** `update` of a missing id exits 2 with `error.code = "not_found"`.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 2 | Document | `tests/cli/test_documents.py` | `test_update_missing_id_exits_2` | same shape as AC1.5 but on `update`. |
| 3 | Term | `tests/cli/test_terms.py` | `test_update_missing_id_exits_2` | same. |
| 3 | Observation | `tests/cli/test_observations.py` | `test_update_missing_id_exits_2` | same. |
| 4 | Diagram | `tests/cli/test_diagrams.py` | `test_update_missing_id_exits_2` | same. |
| 4 | DataItem | `tests/cli/test_data_items.py` | `test_update_missing_id_exits_2` | same. |
| 5 | Node | `tests/cli/test_nodes.py` | `test_update_missing_id_exits_2` | parametrized over variant. |
| 6 | Container | `tests/cli/test_containers.py` | `test_update_missing_id_exits_2` | parametrized over variant. |
| 7 | DataFlow | `tests/cli/test_flows.py` | `test_update_missing_id_exits_2` | same. |

### agent-cli.AC1.7 Failure: invalid enum at parse time exits 1

**Criterion:** `create` with an invalid enum value (e.g., `--observation-type=bogus`) exits 1 at the Click parser with a Choice error.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 3 | Observation | `tests/cli/test_observations.py` | `test_create_invalid_observation_type_exits_1_at_parser` | `tm observation create --observation-type=bogus ...`; exit code 1; stderr message comes from Click `Choice`, includes the literal `bogus` and the allowed values. |
| 5 | Node | `tests/cli/test_nodes.py` | `test_create_<variant>_invalid_enum_exits_1` | parametrized over each variant's enum field (`trust_level`, `entity_type`, `storage_type`); same shape. |

### agent-cli.AC1.8 Edge: `list --limit N` larger than rowcount has no pagination footer

**Criterion:** `list --limit N` where `N` exceeds the row count returns all rows with no `_pagination` footer.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 2 | Document | `tests/cli/test_documents.py` | `test_list_limit_exceeding_rowcount_has_no_footer` | `tm document list --limit 100` against 2 rows; output is exactly 2 NDJSON lines, no `_pagination` line. |
| 4 | Diagram | `tests/cli/test_diagrams.py` | `test_list_limit_exceeding_rowcount_has_no_footer` | same shape. |
| 4 | DataItem | `tests/cli/test_data_items.py` | `test_list_limit_exceeding_rowcount_has_no_footer` | same. |

(One canonical instance per pagination-bearing entity is sufficient — the footer logic lives in `_output.emit` and is shared across all `list`/`search` commands.)

---

## agent-cli.AC2: Search

### agent-cli.AC2.1 Success: case-insensitive text match

**Criterion:** `search "X"` matches case-insensitively across all searchable text columns for the entity (per the repo's `search()` columns).

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 2 | Document | `tests/cli/test_documents.py` | `test_search_case_insensitive_across_columns` | seed Document with title "Threat Model" and content "PII handling"; `tm document search "PII"` and `tm document search "threat"` and `tm document search "MODEL"` all return that row. |
| 3 | Term | `tests/cli/test_terms.py` | `test_search_case_insensitive_across_columns` | term and definition columns. |
| 3 | Observation | `tests/cli/test_observations.py` | `test_search_case_insensitive_across_columns` | description column. |

### agent-cli.AC2.2 Success: multi-token AND combine

**Criterion:** Multi-token text (`search "foo bar"`) AND-combines tokens; each token must match at least one searchable column.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 2 | Document | `tests/cli/test_documents.py` | `test_search_multi_token_and_combines` | seed two Documents: title="alpha", content="beta"; title="alpha gamma". `tm document search "alpha beta"` returns only the first; `tm document search "alpha"` returns both. |
| 3 | Term | `tests/cli/test_terms.py` | `test_search_multi_token_and_combines` | same shape. |
| 3 | Observation | `tests/cli/test_observations.py` | `test_search_multi_token_and_combines` | same. |

### agent-cli.AC2.3 Success: text plus filter AND combine on observation

**Criterion:** `tm observation search "todo" --observation-type=todo --status=open` AND-combines text and filters.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 3 | Observation | `tests/cli/test_observations.py` | `test_search_text_and_filters_and_combine` | seed three observations matching different combinations; assert only the one matching all three constraints appears. |

### agent-cli.AC2.4 Success: `tm node search --type=process` filters

**Criterion:** `tm node search "..." --type=process` filters results to the named variant.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 5 | Node | `tests/cli/test_nodes.py` | `test_search_with_type_filter` | seed mixed-variant nodes with overlapping names; `tm node search "shared" --type=process` returns only process variants. |

### agent-cli.AC2.5 Success: data-item filters AND combine

**Criterion:** `tm data-item search` with `--classification` and `--parent-node-id` filters returns the AND of those constraints.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 4 | DataItem | `tests/cli/test_data_items.py` | `test_search_classification_and_parent_node_id_and_combine` | seed four items across two parent nodes and two classifications; assert only the AND-cell appears. |

### agent-cli.AC2.6 Success: `tm flow search` matches name and protocol

**Criterion:** `tm flow search "X"` matches against `name` and `protocol` columns.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 7 | DataFlow | `tests/cli/test_flows.py` | `test_search_matches_name_and_protocol_columns` | seed two flows: `(name="alpha", protocol="http")` and `(name="beta", protocol="alpha")`; `tm flow search "alpha"` returns both. |

### agent-cli.AC2.7 Edge: empty text plus filters equals filtered list

**Criterion:** `search` with empty text plus filters returns the same shape as `list` with those filters.

**Test type:** Integration.

**Phase contributions:**

| Phase | Entity | Test file | Test name | What it verifies |
|---|---|---|---|---|
| 3 | Observation | `tests/cli/test_observations.py` | `test_search_empty_text_with_filters_equals_filtered_list` | `tm observation search "" --status=open` and `tm observation list --status=open` produce identical NDJSON. |
| 7 | DataFlow | `tests/cli/test_flows.py` | `test_search_empty_text_equals_list` | `tm flow search ""` equals `tm flow list` (flow has no filter flags besides `--diagram-id`). |

---

## agent-cli.AC3: Junctions

### agent-cli.AC3.1 Success: link-term then list-terms includes term

**Criterion:** `tm document link-term <doc-id> <term-id>` creates the link; subsequent `tm document list-terms <doc-id>` includes the term.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 3 | `tests/cli/test_document_terms.py` | `test_link_term_then_list_terms_includes_term` | seed; `link-term`; `list-terms`; assert the term id appears in the NDJSON. |

### agent-cli.AC3.2 Success: re-link returns `{"linked": false, "reason": "already_linked"}`

**Criterion:** Re-linking the same pair returns `{"linked": false, "reason": "already_linked"}` and exits 0.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 3 | `tests/cli/test_document_terms.py` | `test_relink_returns_not_linked_already_linked_reason` | call `link-term` twice; second call exits 0; stdout is `{"linked": false, ..., "reason": "already_linked"}`. |

### agent-cli.AC3.3 Success: unlink-term removes the link

**Criterion:** `tm document unlink-term` removes the link; the term no longer appears in `list-terms`.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 3 | `tests/cli/test_document_terms.py` | `test_unlink_term_removes_link` | link, unlink, list-terms; the term id is absent. |

### agent-cli.AC3.4 Success: container set-parent / parent-of round-trip; list-children includes child with discriminator

**Criterion:** `tm container set-parent` followed by `tm container parent-of` round-trips; `tm container list-children` includes the new child with a `type` discriminator.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 5 | `tests/cli/test_node_variants.py` | `test_node_set_parent_then_parent_of_round_trip` | node-side: `tm node set-parent` then `tm node parent-of` returns the container. |
| 6 | `tests/cli/test_container_membership.py` | `test_container_set_parent_then_parent_of_round_trip` | container-side: `tm container set-parent <child> <parent>` then `tm container parent-of <child>` returns the parent container. |
| 6 | `tests/cli/test_container_membership.py` | `test_list_children_includes_child_with_type_discriminator` | mixed children (a node and a sub-container); each row in NDJSON has its own `type` field. |

### agent-cli.AC3.5 Failure: cross-diagram set-parent exits 1 with cross-diagram hint

**Criterion:** `set-parent` across diagrams exits 1 with a hint naming the cross-diagram constraint.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 6 | `tests/cli/test_container_membership.py` | `test_set_parent_cross_diagram_exits_1_with_hint` | seed two diagrams, each with one container; `tm container set-parent <child-in-A> <parent-in-B>`; exit 1; stderr `error.hint` contains "same diagram" wording from `ContainerRepository.set_parent`. |

### agent-cli.AC3.6 Failure: cycle exits 1 with cycle hint

**Criterion:** `set-parent` that would create a cycle exits 1 with a cycle-detected hint.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 6 | `tests/cli/test_container_membership.py` | `test_set_parent_cycle_exits_1_with_hint` | seed A→B; attempt B→A; exit 1; hint contains "cycle". |

### agent-cli.AC3.7 Success: add-payload round-trips with --endpoint filter

**Criterion:** `tm flow add-payload <flow-id> --data-item ID --endpoint 1` plus a second call with `--endpoint 2` round-trips through `tm flow list-payloads`; `--endpoint` filter on list returns just the matching payloads.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 7 | `tests/cli/test_flow_payload.py` | `test_add_payload_round_trips_with_endpoint_filter` | add two items at endpoints 1 and 2; `list-payloads` returns both; `list-payloads --endpoint=1` returns only the first; `--endpoint=2` returns only the second. |

### agent-cli.AC3.8 Failure: add-payload --endpoint=3 rejected at parse

**Criterion:** `tm flow add-payload --endpoint=3` rejected by Click's `Choice` at parse (exit 1).

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 7 | `tests/cli/test_flow_payload.py` | `test_add_payload_invalid_endpoint_rejected_at_parser` | `tm flow add-payload <id> --data-item <id> --endpoint=3`; exit code 1; stderr is Click's Choice error mentioning "1" and "2". |

### agent-cli.AC3.9 Success: link-document on each DFD entity round-trips through list-documents

**Criterion:** `link-document` on each of the four DFD entities (`tm node`, `tm container`, `tm flow`, `tm data-item`) works; `list-documents` on the same entity reflects the link.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 8 | `tests/cli/test_entity_documents.py` | `test_link_document_round_trip_for_each_kind` | parametrized over `node`, `container`, `flow`, `data-item`; for each: `link-document`, `list-documents` includes the doc; `unlink-document`; `list-documents` no longer includes it. |

### agent-cli.AC3.10 Success: document list-{nodes,containers,flows,items} returns linked entities

**Criterion:** `tm document list-nodes / list-containers / list-flows / list-items` each return the entities of that kind linked to the document.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 8 | `tests/cli/test_entity_documents.py` | `test_document_reverse_listing_per_kind` | parametrized over the four kinds; seed one of each linked to a document; assert each reverse listing returns the right kind only (no cross-leakage). |

---

## agent-cli.AC4: Output format

### agent-cli.AC4.1 Success: piped list/search is NDJSON

**Criterion:** Piped `list` and `search` output is NDJSON (no surrounding `[`/`]`); each row is one parseable JSON object.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_piped_list_is_ndjson_no_array_wrapper` | stdout's first char is `{`, last char is `}` plus newline; no `[` or `]` anywhere; every line `json.loads`-ables. |

(One canonical instance per output-emit code path is sufficient; the helper is shared.)

### agent-cli.AC4.2 Success: piped get/create/update is single compact JSON

**Criterion:** Piped `get` / `create` / `update` output is a single compact JSON object on stdout.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_piped_point_read_is_compact_json` | `tm document get <id>` produces exactly one line, no leading/trailing whitespace, no indentation. |

### agent-cli.AC4.3 Success: TTY output is indented

**Criterion:** When stdout is a TTY, all JSON output is indented with `indent=2`.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_tty_output_is_indent_2` | invoke with `--no-json=False` and a runner whose stdout reports `isatty()==True` (use the `--json/--no-json` override on the root group: `tm --json document get <id>` paired with monkeypatched `sys.stdout.isatty` returning True via the runner's `mix_stderr=False` and a manual TTY shim); assert output contains `\n  "` indentation. |

### agent-cli.AC4.4 Success: integer ids serialize as JSON strings

**Criterion:** Integer id fields serialize as JSON strings (e.g., `"id": "5"`, not `5`).

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_id_fields_serialize_as_strings` | parsed JSON's `id` is a Python `str`, not `int`. Also covers `*_id` fields where they appear (e.g., `parent_node_id` in DataItem responses). |

(The custom encoder lives in `_output.py` and is exercised by every command; one canonical assertion is enough.)

### agent-cli.AC4.5 Success: pagination footer when len(rows) == limit

**Criterion:** Pagination footer `{"_pagination": {"next_offset": N, "returned": N}}` is the final NDJSON line when `len(rows) == limit`.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_list_limit_equals_rowcount_emits_pagination_footer` | seed 3 documents; `tm document list --limit=3`; output has 3 row lines + 1 footer line; footer parses to `{"_pagination": {"next_offset": 3, "returned": 3}}`. |

### agent-cli.AC4.6 Success: --json projection on list and get

**Criterion:** `--json id,name` projects only the requested fields on both `list` and `get`.

**Test type:** Integration plus unit.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_options_helpers.py` | `test_project_fields_keeps_requested_keys` | unit test of the `_output.project_fields` helper directly: dict-in, dict-out with only requested keys; missing keys are silently dropped; nested types pass through. |
| 2 | `tests/cli/test_documents.py` | `test_json_fields_projection_on_get` | `tm document get <id> --json id,title`; parsed output has only those keys. |
| 2 | `tests/cli/test_documents.py` | `test_json_fields_projection_on_list` | `tm document list --json id,title`; each NDJSON row has only those keys. |

---

## agent-cli.AC5: Errors and exit codes

### agent-cli.AC5.1 Success: ValidationError → exit 1, code=user_error

**Criterion:** `pydantic.ValidationError` from a repo call → exit 1, `error.code = "user_error"`.

**Test type:** Unit + integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 1 | `tests/cli/test_errors.py` | `test_validation_error_maps_to_user_error` | unit: feed a `ValidationError` directly through `map_exception`; assert returned `UserError` has `exit_code == 1` and the payload includes `code == "user_error"`. |
| 2 | `tests/cli/test_documents.py` | `test_create_validation_error_exits_1` | end-to-end: `tm document create` with input that fails Pydantic validation (e.g., a stdin object missing a required field); exit 1; stderr `error.code == "user_error"`. |

### agent-cli.AC5.2 Success: repo None → exit 2, code=not_found

**Criterion:** Repo returning `None` from `get`/`update` → exit 2, `error.code = "not_found"`.

**Test type:** Unit + integration (already covered as AC1.5/AC1.6 end-to-end).

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 1 | `tests/cli/test_errors.py` | `test_not_found_maps_to_not_found_error` | unit: `map_exception` returns `NotFoundError` with `exit_code == 2`. |
| 2 | `tests/cli/test_documents.py` | `test_get_missing_id_exits_2` | reuses the AC1.5 case (single test, dual coverage). |

### agent-cli.AC5.3 Success: UNIQUE → exit 3, constraint=unique

**Criterion:** UNIQUE constraint violation (e.g., duplicate `Term.term`) → exit 3, `error.constraint = "unique"`.

**Test type:** Unit + integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 1 | `tests/cli/test_errors.py` | `test_integrity_unique_maps_to_constraint` | unit: feed `sqlite3.IntegrityError("UNIQUE constraint failed: terms.term")`; assert `ConstraintError` with `constraint=="unique"` and exit code 3. |
| 3 | `tests/cli/test_terms.py` | `test_create_duplicate_term_exits_3_unique` | end-to-end: create the same term twice (without `--if-not-exists`); second call exits 3; stderr `error.constraint == "unique"`. |

### agent-cli.AC5.4 Success: FOREIGN KEY → exit 3, constraint=foreign_key

**Criterion:** FOREIGN KEY violation → exit 3, `error.constraint = "foreign_key"`.

**Test type:** Unit + integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 1 | `tests/cli/test_errors.py` | `test_integrity_foreign_key_maps_to_constraint` | unit: feed `sqlite3.IntegrityError("FOREIGN KEY constraint failed")`; assert `ConstraintError` with `constraint=="foreign_key"` and exit code 3. |
| 3 | `tests/cli/test_document_terms.py` | `test_link_term_with_missing_document_exits_3_fk` | end-to-end: `tm document link-term 999999 <term-id>` (or vice versa); exit 3; stderr `error.constraint == "foreign_key"`. |

### agent-cli.AC5.5 Success: CHECK → exit 3, constraint=check

**Criterion:** CHECK violation → exit 3, `error.constraint = "check"`.

**Test type:** Unit only (see special case 1 in the introduction).

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 1 | `tests/cli/test_errors.py` | `test_integrity_check_maps_to_constraint` | unit: feed `sqlite3.IntegrityError("CHECK constraint failed: observations")`; assert `ConstraintError` with `constraint=="check"` and exit code 3. **No end-to-end test exists** because Pydantic Literal validation rejects bad enum values before the SQL CHECK can fire (documented in Phase 3's coverage section). This is a structural limitation of the v1 CLI surface. |

### agent-cli.AC5.6 Success: OSError/PermissionError → exit 4, code=system_error

**Criterion:** `OSError` / `PermissionError` (e.g., DB path unwritable) → exit 4, `error.code = "system_error"`.

**Test type:** Unit only (see special case 2 in the introduction).

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 1 | `tests/cli/test_errors.py` | `test_oserror_maps_to_system_error` | unit: `map_exception(OSError("disk full"))` returns `SystemError` with `exit_code == 4`. |
| 1 | `tests/cli/test_errors.py` | `test_permissionerror_maps_to_system_error` | unit: `map_exception(PermissionError("denied"))` returns `SystemError` with `exit_code == 4`. **No end-to-end test exists** because the chmod/portable-failure surface is awkward across CI environments and the design's "Done when" criteria don't require it. |

### agent-cli.AC5.7 Success: error JSON on stderr; stdout untouched or parseable

**Criterion:** Error JSON is written to stderr; stdout is either empty or remains a parseable JSON document.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_error_payload_on_stderr_stdout_clean` | drive `tm document get 999999`; assert stdout is empty bytes; assert stderr parses to a JSON document with an `error` key. Repeat with `tm document create` (validation error) — same shape. (`mix_stderr=False` on `CliRunner` is required for this assertion.) |

---

## agent-cli.AC6: Idempotency and --dry-run

### agent-cli.AC6.1 Success: term --if-not-exists short-circuits on natural key

**Criterion:** `tm term create --if-not-exists --term foo --definition bar` with `foo` already present returns the existing row with `{"created": false, ...}` and exits 0.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 3 | `tests/cli/test_terms.py` | `test_create_if_not_exists_returns_existing_with_created_false` | seed; call create with `--if-not-exists` for the same term; exit 0; payload has `"created": false` and the existing id. Also verify `"created": true` on a fresh term. |

### agent-cli.AC6.2 Success: delete existing returns deleted=true

**Criterion:** `delete <existing-id>` returns `{"deleted": true, "id": "..."}` and exits 0.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_delete_existing_id_returns_deleted_true` | seed; `tm document delete <id>`; payload has `{"deleted": true, "id": "<id>"}`; subsequent `get` exits 2. |

### agent-cli.AC6.3 Success: delete missing returns deleted=false

**Criterion:** `delete <missing-id>` returns `{"deleted": false, "id": "...", "reason": "not_found"}` and exits 0.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_delete_missing_id_returns_deleted_false_not_found` | `tm document delete 999999`; exit 0; payload as specified. |

### agent-cli.AC6.4 Success: create --dry-run returns would_create

**Criterion:** `create --dry-run` returns `{"dry_run": true, "would_create": {...}}` and writes nothing to the DB.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_create_dry_run_returns_would_create_no_writes` | `tm document create --dry-run --title "X" ...`; payload as specified; subsequent `tm document list` shows no new row. |

### agent-cli.AC6.5 Success: update --dry-run returns would_update

**Criterion:** `update --dry-run` returns `{"dry_run": true, "would_update": {...}}` and modifies nothing.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_update_dry_run_returns_would_update_no_writes` | seed; `tm document update <id> --dry-run --title "Y"`; payload as specified; subsequent `get` shows the original title unchanged. |

---

## agent-cli.AC7: Stdin bulk

### agent-cli.AC7.1 Success: --stdin with object creates one row

**Criterion:** `tm document create --stdin` with a single JSON object on stdin creates one row and returns one object.

**Test type:** Unit + integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 1 | `tests/cli/test_stdin.py` | `test_read_json_stdin_object_returns_dict` | unit: feed an object on stdin; helper returns `dict`. |
| 2 | `tests/cli/test_documents.py` | `test_create_stdin_object_creates_one_row` | end-to-end: pass a JSON object via stdin; output is one object; one new row exists. |

### agent-cli.AC7.2 Success: --stdin with array creates N rows in order

**Criterion:** `tm document create --stdin` with a JSON array creates N rows in input order and returns an array of N objects in the same order, all in a single connection.

**Test type:** Unit + integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 1 | `tests/cli/test_stdin.py` | `test_read_json_stdin_array_returns_list` | unit: feed an array; helper returns `list[dict]`. |
| 2 | `tests/cli/test_documents.py` | `test_create_stdin_array_creates_n_rows_in_order` | feed a 3-item array; output is a 3-item array in input order; all three rows exist; the connection-rollback path is tested by AC7.3. |

### agent-cli.AC7.3 Failure: invalid item rolls back batch with index

**Criterion:** A single invalid item in an input array rolls back the whole batch; the error payload includes the failing item's array index.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_create_stdin_array_invalid_item_rolls_back_with_index` | feed a 3-item array where item index 1 fails Pydantic validation; exit 1; stderr `error.input.array_index == 1`; pre/post DB row counts identical. |

### agent-cli.AC7.4 Failure: --stdin with --field flag rejected at parser

**Criterion:** `--stdin` combined with any `--field` flag is rejected at the Click parser (mutually exclusive).

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 2 | `tests/cli/test_documents.py` | `test_stdin_plus_field_flag_rejected_at_parser` | `tm document create --stdin --title "X"`; exit 1; stderr message identifies the mutual exclusion. |

---

## agent-cli.AC8: Polymorphism (Node, Container)

### agent-cli.AC8.1 Success: variant subcommand dispatch

**Criterion:** `tm node create process|external-entity|data-store` dispatches to the correct variant; each subcommand exposes only its variant's fields as flags.

**Test type:** Integration plus golden help snapshot.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 5 | `tests/cli/test_nodes.py` | `test_create_<variant>_dispatches_correctly` | one test per variant; verifies row is persisted with the right `type` discriminator and variant-specific fields. |
| 5 | `tests/cli/__snapshots__/test_nodes_help.ambr` | (snapshot) | `tm node create process --help` snapshot shows ONLY process fields; same for the other two variants. Drift requires `--snapshot-update`. |
| 6 | `tests/cli/test_containers.py` | `test_create_<variant>_dispatches_correctly` | parametrized over `trust-boundary` and `container`. |
| 6 | `tests/cli/__snapshots__/test_containers_help.ambr` | (snapshot) | per-variant help text. |

### agent-cli.AC8.2 Success: update process on a process row works

**Criterion:** `tm node update process <id>` against a process row updates the row and returns the updated process node.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 5 | `tests/cli/test_nodes.py` | `test_update_process_on_process_row_succeeds` | seed a process node; `tm node update process <id> --description "new"`; payload is the updated process; subsequent `get` reflects the change. |

### agent-cli.AC8.3 Failure: update with mismatched variant exits 1

**Criterion:** `tm node update process <data-store-id>` exits 1 with `error.code = "user_error"` and a hint identifying the actual row type.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 5 | `tests/cli/test_nodes.py` | `test_update_variant_mismatch_exits_1_with_hint` | seed a data-store node; `tm node update process <id> --description "new"`; exit 1; stderr `error.code == "user_error"`; hint contains "type mismatch" and the actual row type. |

### agent-cli.AC8.4 Success: container variants and matching update enforces type-match

**Criterion:** `tm container create trust-boundary|container` dispatches correctly; matching `update` subcommands enforce the type-match rule.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 6 | `tests/cli/test_containers.py` | `test_update_variant_mismatch_exits_1_with_hint` | seed a `trust_boundary`; `tm container update container <id>` exits 1 with hint mentioning "trust_boundary". |

### agent-cli.AC8.5 Success: --type filter on list and search

**Criterion:** `--type` filter on `list` and `search` restricts results to the named variant.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 5 | `tests/cli/test_nodes.py` | `test_list_with_type_filter` | seed mixed; `tm node list --type=process` returns only process variants. (Search half is AC2.4.) |
| 6 | `tests/cli/test_containers.py` | `test_list_and_search_with_type_filter` | seed mixed; `tm container list --type=container` and `tm container search "" --type=container`. |

---

## agent-cli.AC9: Default-diagram fallback

### agent-cli.AC9.1 Success: DFD create without --diagram-id auto-creates default

**Criterion:** A DFD `create` command without `--diagram-id` creates a diagram named "default" when none exists, then creates the entity in it; the response includes the resolved `diagram_id`.

**Test type:** Unit + integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 4 | `tests/cli/test_options_resolver.py` | `test_resolve_default_diagram_id_creates_when_missing_on_write` | unit: empty DB; resolver with `create_if_missing=True` returns a fresh id and the diagram exists with name "default". |
| 4 | `tests/cli/test_data_items.py` | `test_create_without_diagram_id_creates_default_diagram` | end-to-end: empty diagrams table; `tm data-item create --name foo --identifier bar`; response has `diagram_id` set; `tm diagram list` shows one diagram named "default". |

### agent-cli.AC9.2 Success: DFD list/search without default returns empty

**Criterion:** DFD `list` / `search` without `--diagram-id` and no default diagram in the DB returns empty NDJSON (no implicit creation on read).

**Test type:** Unit + integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 4 | `tests/cli/test_options_resolver.py` | `test_resolve_default_diagram_id_returns_none_on_read_when_missing` | unit: empty DB; resolver with `create_if_missing=False` returns None; no diagram is created. |
| 4 | `tests/cli/test_data_items.py` | `test_list_without_default_returns_empty_ndjson` | end-to-end: empty diagrams table; `tm data-item list` produces zero output bytes (or zero-length JSON list, depending on emit semantics — assert no items, no implicit diagram created). |

### agent-cli.AC9.3 Success: DFD list/search uses default when one exists

**Criterion:** DFD `list` / `search` without `--diagram-id` uses the default diagram's id when one exists.

**Test type:** Unit + integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 4 | `tests/cli/test_options_resolver.py` | `test_resolve_default_diagram_id_lookup_when_default_exists` | unit: seed a "default" diagram; resolver returns its id without writing. Also tested: `test_resolve_default_diagram_id_lowest_id_wins_on_tie`. |
| 4 | `tests/cli/test_data_items.py` | `test_list_with_default_present_returns_items_in_default` | seed default + 2 items; `tm data-item list` returns both. |

### agent-cli.AC9.4 Success: --diagram-id hidden from --help

**Criterion:** `--diagram-id` does not appear in any DFD command's `--help` output.

**Test type:** Integration / golden snapshot.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 4 | `tests/cli/test_data_items.py` | `test_diagram_id_not_in_help_for_dfd_commands` | parametrize over each DFD command (`data-item create`, `list`, `search`, etc.); `--help` output does not contain the literal "--diagram-id". Golden help snapshots in `tests/cli/__snapshots__/test_data_items_help.ambr` reinforce this. |
| 5 | `tests/cli/test_nodes.py` | `test_diagram_id_not_in_help_for_dfd_commands` | same shape for `tm node` commands. |
| 6 | `tests/cli/test_containers.py` | `test_diagram_id_not_in_help_for_dfd_commands` | same for `tm container`. |
| 7 | `tests/cli/test_flows.py` | `test_diagram_id_not_in_help_for_dfd_commands` | same for `tm flow`. |

### agent-cli.AC9.5 Success: --diagram-id with hidden=true in `tm commands --json`

**Criterion:** `tm commands --json` emits the `--diagram-id` option with `"hidden": true` so curious agents can discover it.

**Test type:** Integration (split across two phases — see special case 3 in the introduction).

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 4 | `tests/cli/test_data_items.py` | `test_diagram_id_option_is_registered_with_hidden_true` | structural: walk `Command.params` on each DFD command; assert an option with `name == "diagram_id"` exists and `hidden is True`. (Phase 4 verifies the structural attribute; the introspection command itself doesn't exist yet.) |
| 8 | `tests/cli/test_introspection.py` | `test_commands_json_includes_hidden_diagram_id_for_dfd_create` | end-to-end: `tm commands --json`; walk the resulting tree; for each `data-item create`, `node create *`, `container create *`, `flow create` leaf, find an option with `name == "diagram_id"` and `hidden == true`. |

---

## agent-cli.AC10: Introspection

### agent-cli.AC10.1 Success: `tm schema document` returns read+create+update schemas

**Criterion:** `tm schema document` returns the JSON Schema for the read model plus `DocumentCreate` and `DocumentUpdate`.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 8 | `tests/cli/test_introspection.py` | `test_schema_document_returns_read_create_update` | `tm schema document`; parsed JSON has top-level keys `read`, `create`, `update` (or equivalent), each a valid JSON Schema document derived from `Document.model_json_schema()`, `DocumentCreate.model_json_schema()`, `DocumentUpdate.model_json_schema()`. |

### agent-cli.AC10.2 Success: `tm schema` lists entity names

**Criterion:** `tm schema` (no argument) lists available entity names.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 8 | `tests/cli/test_introspection.py` | `test_schema_no_arg_lists_entity_names` | `tm schema`; output enumerates each known entity (`document`, `term`, `observation`, `diagram`, `node`, `container`, `flow`, `data-item`). |

### agent-cli.AC10.3 Success: `tm schema --all` returns one document per entity

**Criterion:** `tm schema --all` returns one document keyed by entity name.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 8 | `tests/cli/test_introspection.py` | `test_schema_all_returns_keyed_document` | `tm schema --all`; output is a single JSON object whose keys are entity names; each value is the same shape as `tm schema <entity>`. |

### agent-cli.AC10.4 Success: `tm commands --json` walks tree; every leaf has options/arguments

**Criterion:** `tm commands --json` walks the full command tree; every leaf has `options` and `arguments` keys (possibly empty arrays).

**Test type:** Integration plus unit.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 8 | `tests/cli/test_introspection.py` | `test_serialize_command_tree_every_leaf_has_options_and_arguments` | unit on `_introspection.serialize_command_tree`: walk the result; for every node without `subcommands`, assert `options` and `arguments` keys exist (arrays, possibly empty). |
| 8 | `tests/cli/test_introspection.py` | `test_commands_json_walks_full_tree` | end-to-end: `tm commands --json`; same walk; same assertion. Also asserts at least one known leaf (e.g., `document get`) is present. |

### agent-cli.AC10.5 Success: golden snapshot of `tm commands --json`

**Criterion:** `tm commands --json` output is pinned by a golden snapshot; drift requires explicit snapshot update.

**Test type:** Golden snapshot (see special case 4 in the introduction).

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 8 | `tests/cli/test_introspection.py` | `test_commands_json_golden_snapshot` | snapshot the entire `tm commands --json` output via Syrupy's masking serializer. Defaults like `--limit 50` are included; help-text and option names are stable. **Drift fails the build; bless via `pytest --snapshot-update` only after human review.** |

A meta-test (`test_help_snapshots_cover_every_leaf` in Phase 8) walks the same tree and asserts that every leaf has a corresponding `--help` snapshot under `tests/cli/__snapshots__/`. This guards against forgetting a snapshot when adding a new command.

---

## agent-cli.AC11: Entity-specific invariants

### agent-cli.AC11.1 Success: flow create canonicalizes endpoints

**Criterion:** `tm flow create --node1-id 5 --node2-id 3 ...` produces a row with `node1_id=3, node2_id=5` (canonicalized transparently by the repo).

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 7 | `tests/cli/test_flows.py` | `test_create_canonicalizes_endpoints_when_n1_gt_n2` | seed two nodes with `id_a < id_b`; `tm flow create --node1-id=<id_b> --node2-id=<id_a> ...`; result has `node1_id == id_a` and `node2_id == id_b`. |

### agent-cli.AC11.2 Failure: self-loop exits 1 with hint

**Criterion:** `tm flow create --node1-id 5 --node2-id 5 ...` exits 1 with a self-loop hint.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 7 | `tests/cli/test_flows.py` | `test_create_self_loop_exits_1_with_hint` | seed one node; `--node1-id=<id> --node2-id=<id>`; exit 1; stderr `error.code == "user_error"`; hint contains "Self-loops". |

### agent-cli.AC11.3 Constraint: flow update has no node1/node2 flags

**Criterion:** `tm flow update --help` shows no `--node1-id` or `--node2-id` flags; `tm commands --json` output for `flow update` likewise omits them.

**Test type:** Integration plus golden help snapshot.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 7 | `tests/cli/test_flows.py` | `test_update_no_node1_or_node2_flag_present` | structural: inspect `update_flow` Click command's params; `{"node1_id", "node2_id"}.isdisjoint(p.name for p in cmd.params)`. |
| 7 | `tests/cli/test_flows.py` | `test_update_stdin_with_node1_id_in_body_rejected` | `tm flow update <id> --stdin` with `{"node1_id": 99}` in body; exit 1; message mentions "immutable". |
| 7 | `tests/cli/__snapshots__/test_flows_help.ambr` | (snapshot) | `tm flow update --help` snapshot does not contain `--node1-id` or `--node2-id`. |
| 8 | `tests/cli/test_introspection.py` | `test_commands_json_for_flow_update_omits_endpoint_options` | walk `tm commands --json` tree; for `flow update`, no option has `name in {"node1_id", "node2_id"}`. |

### agent-cli.AC11.4 Success: clearing parent_node_id sets it to NULL

**Criterion:** `tm data-item update <id> --parent-node-id ""` (or the equivalent stdin-cleared form) sets the row's `parent_node_id` to NULL.

**Test type:** Integration.

**Phase contributions:**

| Phase | Test file | Test name | What it verifies |
|---|---|---|---|
| 4 | `tests/cli/test_data_items.py` | `test_update_clear_parent_node_id_with_empty_string` | seed item with parent; `tm data-item update <id> --parent-node-id ""`; subsequent `get` shows `parent_node_id == None`. |
| 4 | `tests/cli/test_data_items.py` | `test_update_clear_parent_node_id_with_none_literal` | seed; `tm data-item update <id> --parent-node-id none` → same effect. |
| 4 | `tests/cli/test_data_items.py` | `test_update_clear_parent_node_id_via_stdin` | seed; `tm data-item update <id> --stdin` with body `{"parent_node_id": null}` → same effect. |

---

## Acceptance test (cross-AC end-to-end)

A single workflow test composes many of the criteria above through a realistic agent scenario. It is not the primary verification for any AC, but it provides cross-AC integration coverage and proves the help-text-only contract works.

| Test file | Test name | What it verifies |
|---|---|---|
| `tests/acceptance/test_dfd_workflow.py` | `test_create_diagram_with_two_processes_and_a_flow` | end-to-end workflow: create a diagram, two process nodes, and a flow between them, using only stdout-derived ids. Validates that an agent following the help text alone could complete the workflow. Touches AC1.* (CRUD), AC4.* (output format), AC8.1/8.2 (variant dispatch), AC9.1/9.3 (default-diagram resolver), AC11.1 (canonical ordering). |

---

## Coverage Summary

The table below maps every AC ID to its primary test type, file, and the phase that produces the test. Where coverage is split across phases (universal CRUDL ACs and the AC9.5 dual-coverage case), the cell lists each contribution.

| AC ID | Test type | Test file(s) | Phase(s) |
|---|---|---|---|
| agent-cli.AC1.1 | Integration | `tests/cli/test_documents.py`, `test_terms.py`, `test_observations.py`, `test_diagrams.py`, `test_data_items.py`, `test_nodes.py`, `test_containers.py`, `test_flows.py` | 2, 3, 4, 5, 6, 7 |
| agent-cli.AC1.2 | Integration | (same set as AC1.1) | 2, 3, 4, 5, 6, 7 |
| agent-cli.AC1.3 | Integration | (same set as AC1.1) | 2, 3, 4, 5, 6, 7 |
| agent-cli.AC1.4 | Integration | (same set as AC1.1) | 2, 3, 4, 5, 6, 7 |
| agent-cli.AC1.5 | Integration | (same set as AC1.1) | 2, 3, 4, 5, 6, 7 |
| agent-cli.AC1.6 | Integration | (same set as AC1.1) | 2, 3, 4, 5, 6, 7 |
| agent-cli.AC1.7 | Integration | `tests/cli/test_observations.py`, `tests/cli/test_nodes.py` | 3, 5 |
| agent-cli.AC1.8 | Integration | `tests/cli/test_documents.py`, `test_diagrams.py`, `test_data_items.py` | 2, 4 |
| agent-cli.AC2.1 | Integration | `tests/cli/test_documents.py`, `test_terms.py`, `test_observations.py` | 2, 3 |
| agent-cli.AC2.2 | Integration | `tests/cli/test_documents.py`, `test_terms.py`, `test_observations.py` | 2, 3 |
| agent-cli.AC2.3 | Integration | `tests/cli/test_observations.py` | 3 |
| agent-cli.AC2.4 | Integration | `tests/cli/test_nodes.py` | 5 |
| agent-cli.AC2.5 | Integration | `tests/cli/test_data_items.py` | 4 |
| agent-cli.AC2.6 | Integration | `tests/cli/test_flows.py` | 7 |
| agent-cli.AC2.7 | Integration | `tests/cli/test_observations.py`, `tests/cli/test_flows.py` | 3, 7 |
| agent-cli.AC3.1 | Integration | `tests/cli/test_document_terms.py` | 3 |
| agent-cli.AC3.2 | Integration | `tests/cli/test_document_terms.py` | 3 |
| agent-cli.AC3.3 | Integration | `tests/cli/test_document_terms.py` | 3 |
| agent-cli.AC3.4 | Integration | `tests/cli/test_node_variants.py`, `tests/cli/test_container_membership.py` | 5, 6 |
| agent-cli.AC3.5 | Integration | `tests/cli/test_container_membership.py` | 6 |
| agent-cli.AC3.6 | Integration | `tests/cli/test_container_membership.py` | 6 |
| agent-cli.AC3.7 | Integration | `tests/cli/test_flow_payload.py` | 7 |
| agent-cli.AC3.8 | Integration | `tests/cli/test_flow_payload.py` | 7 |
| agent-cli.AC3.9 | Integration | `tests/cli/test_entity_documents.py` | 8 |
| agent-cli.AC3.10 | Integration | `tests/cli/test_entity_documents.py` | 8 |
| agent-cli.AC4.1 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC4.2 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC4.3 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC4.4 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC4.5 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC4.6 | Unit + Integration | `tests/cli/test_options_helpers.py`, `tests/cli/test_documents.py` | 2 |
| agent-cli.AC5.1 | Unit + Integration | `tests/cli/test_errors.py`, `tests/cli/test_documents.py` | 1, 2 |
| agent-cli.AC5.2 | Unit + Integration | `tests/cli/test_errors.py`, (covered end-to-end via AC1.5/1.6) | 1, 2 |
| agent-cli.AC5.3 | Unit + Integration | `tests/cli/test_errors.py`, `tests/cli/test_terms.py` | 1, 3 |
| agent-cli.AC5.4 | Unit + Integration | `tests/cli/test_errors.py`, `tests/cli/test_document_terms.py` | 1, 3 |
| agent-cli.AC5.5 | **Unit only** (CHECK unreachable through CLI; see special case 1) | `tests/cli/test_errors.py` | 1 |
| agent-cli.AC5.6 | **Unit only** (chmod test portably awkward; see special case 2) | `tests/cli/test_errors.py` | 1 |
| agent-cli.AC5.7 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC6.1 | Integration | `tests/cli/test_terms.py` | 3 |
| agent-cli.AC6.2 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC6.3 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC6.4 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC6.5 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC7.1 | Unit + Integration | `tests/cli/test_stdin.py`, `tests/cli/test_documents.py` | 1, 2 |
| agent-cli.AC7.2 | Unit + Integration | `tests/cli/test_stdin.py`, `tests/cli/test_documents.py` | 1, 2 |
| agent-cli.AC7.3 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC7.4 | Integration | `tests/cli/test_documents.py` | 2 |
| agent-cli.AC8.1 | Integration + Golden help | `tests/cli/test_nodes.py`, `test_containers.py`, `__snapshots__/test_nodes_help.ambr`, `__snapshots__/test_containers_help.ambr` | 5, 6 |
| agent-cli.AC8.2 | Integration | `tests/cli/test_nodes.py` | 5 |
| agent-cli.AC8.3 | Integration | `tests/cli/test_nodes.py` | 5 |
| agent-cli.AC8.4 | Integration | `tests/cli/test_containers.py` | 6 |
| agent-cli.AC8.5 | Integration | `tests/cli/test_nodes.py`, `tests/cli/test_containers.py` | 5, 6 |
| agent-cli.AC9.1 | Unit + Integration | `tests/cli/test_options_resolver.py`, `tests/cli/test_data_items.py` | 4 |
| agent-cli.AC9.2 | Unit + Integration | `tests/cli/test_options_resolver.py`, `tests/cli/test_data_items.py` | 4 |
| agent-cli.AC9.3 | Unit + Integration | `tests/cli/test_options_resolver.py`, `tests/cli/test_data_items.py` | 4 |
| agent-cli.AC9.4 | Integration + Golden help | `tests/cli/test_data_items.py`, `test_nodes.py`, `test_containers.py`, `test_flows.py` | 4, 5, 6, 7 |
| agent-cli.AC9.5 | Integration (split across two phases — see special case 3) | `tests/cli/test_data_items.py` (structural), `tests/cli/test_introspection.py` (end-to-end) | 4, 8 |
| agent-cli.AC10.1 | Integration | `tests/cli/test_introspection.py` | 8 |
| agent-cli.AC10.2 | Integration | `tests/cli/test_introspection.py` | 8 |
| agent-cli.AC10.3 | Integration | `tests/cli/test_introspection.py` | 8 |
| agent-cli.AC10.4 | Unit + Integration | `tests/cli/test_introspection.py` | 8 |
| agent-cli.AC10.5 | **Golden snapshot** (fragile by design — see special case 4) | `tests/cli/test_introspection.py` + `__snapshots__/test_introspection.ambr` | 8 |
| agent-cli.AC11.1 | Integration | `tests/cli/test_flows.py` | 7 |
| agent-cli.AC11.2 | Integration | `tests/cli/test_flows.py` | 7 |
| agent-cli.AC11.3 | Integration + Golden help | `tests/cli/test_flows.py`, `__snapshots__/test_flows_help.ambr`, `tests/cli/test_introspection.py` | 7, 8 |
| agent-cli.AC11.4 | Integration | `tests/cli/test_data_items.py` | 4 |

---

## Human verification

No criterion in this design requires manual human verification. Every AC maps to at least one automated test. The two ACs covered only at the unit level (`agent-cli.AC5.5` and `agent-cli.AC5.6`) are documented limitations of the CLI's structural surface area, not gaps in automation — the unit tests directly exercise the mapper that the runtime would invoke if the CLI ever were able to reach those exception sources. Both special cases are flagged inline in their AC sections and in the coverage table above so a future reviewer can re-evaluate them if the CLI surface changes.

The closest thing to manual verification in this plan is the **explicit human review** required when a Syrupy snapshot drifts (see special case 4 and the `agent-cli.AC10.5` row). Snapshot updates are not automatic; a developer must run `pytest --snapshot-update` and review the diff before committing. Treat snapshot diffs with the same rigor as schema migrations — they are the agent contract.
