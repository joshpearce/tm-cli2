# Plan: CLI ergonomics — `--from`, `--id-only`, `TM_DIAGRAM_ID`

## Summary

Three small, independent CLI changes that surfaced as genuine friction
when writing
[`examples/demo-prompt-java-webapp.md`](../../examples/demo-prompt-java-webapp.md):
the demo had to introduce two `bash` helpers (`mk_item`, `mk_flow`) just
to keep the per-step shell calls readable. Each helper papered over one
of the three issues below. Fixing them lets the demo (and any agent
script that resembles it) drop the helpers and write straight-line
shell.

## Decisions (confirmed)

1. **Replace `--endpoint 1|2` with `--from <node_id>`** on
   `tm flow add-payload` and `tm flow remove-payload`. The integer
   endpoint is meaningless to callers; what they actually know is which
   node the data item is sourced at. This is a **breaking change** to
   the CLI surface (project is pre-1.0; the CLI is the agent contract,
   not a stable user UI). Repository method `add_payload(flow_id,
   data_item_id, source_endpoint)` is unchanged — only the CLI
   translates `--from` to `source_endpoint` by reading the flow's
   canonical `node1_id` / `node2_id`.

2. **Add a global `--id-only` root flag**. When set, single-row emits
   print just the entity's `id` (no JSON envelope, no newline-padding);
   list emits print one id per line. Replaces the universal
   `$(tm ... create | jq -r .id)` pattern with `$(tm --id-only ... create)`.

3. **Add `TM_DIAGRAM_ID` env var**. Resolution order on every DFD
   entity command becomes:
   `--diagram-id <int>` > `$TM_DIAGRAM_ID` > scan-for-`default` >
   (mutate-only) create `default`. Mirrors how `TM_DB_PATH` already
   works. Lets a script set the diagram once and stop repeating
   `--diagram-id "$D"` on every line.

The three changes are independent and can be implemented in any order;
the steps below are sequenced shortest-to-largest blast radius.

## Steps

### 1. `TM_DIAGRAM_ID` env var

**Files**: `src/tm_cli/cli/_options.py`,
`src/tm_cli/cli/_agent_info.py`, `src/tm_cli/cli/CLAUDE.md`,
`.env.example`, `tests/cli/test_resolve_default_diagram_id.py` (extend).

Update `resolve_default_diagram_id(conn, explicit_id, *,
create_if_missing)`:

```
explicit_id is not None  -> verify exists (existing behavior)
$TM_DIAGRAM_ID set       -> parse int (UserError on non-int);
                            verify exists (NotFoundError if not);
                            return its id.
otherwise                -> existing default-diagram fallback
```

Env-var consumption is local to this function — no other call site
needs to change. Place the `os.environ.get` lookup behind the
`explicit_id is None` branch so explicit always wins.

`.env.example` gets a commented entry:

```
# Optional: bind every DFD entity command to this diagram id by default.
# --diagram-id on a specific command still wins.
# TM_DIAGRAM_ID=
```

`tm agent-info` gets one sentence in the existing
"Default-diagram fallback" / "DFD entities" paragraph noting the env
var slots between `--diagram-id` and the `default` scan.

`tests/cli/test_resolve_default_diagram_id.py` adds six cases:

- env set + valid existing id → returns that id (no `default` scan, no
  creation).
- env set + valid id format but missing diagram → `NotFoundError`
  (exit 2).
- env set + non-integer string → `UserError` (exit 1) with hint.
- env set + explicit `--diagram-id` also set → explicit wins.
- env unset → existing behavior unchanged (regression pin).
- env set to `""` (empty string) → treated as unset (pins the
  falsy-env contract).

**Acceptance**:
- All five new test cases pass; existing tests unchanged.
- `.env.example` documents the new var.
- `tm agent-info` mentions it.
- `make lint` / `make test` clean.

### 2. Global `--id-only` flag

**Files**: `src/tm_cli/main.py`, `src/tm_cli/cli/_output.py`,
`src/tm_cli/cli/_agent_info.py`, `src/tm_cli/cli/CLAUDE.md`,
`tests/cli/test_id_only.py` (new), plus mechanical snapshot updates for
the root-group help / introspection trees.

Add `--id-only` to the root `cli` group alongside the existing
`--json/--no-json` and `--verbose`. Store on `ctx.obj["id_only"]`.

Update `_output.emit()`:

- Read `ctx.obj.get("id_only", False)`. When False, behavior is
  unchanged.
- When True:
  - If `payload` is a single dict containing an `id` key → print
    `str(payload["id"])` (one line, no JSON wrapping). Note: ids are
    already stringified upstream by `_to_jsonable`/`_stringify_ids`, so
    use the post-stringify value.
  - If `list_mode=True` → for each row that's a dict with `id`, print
    `str(row["id"])` on its own line; rows lacking `id` are silently
    skipped (e.g., the `_pagination` footer is dropped under
    `--id-only`).
  - If `payload` is a dict without `id` (e.g., `delete` returns
    `{"deleted": true, "id": ...}` — has id; `push` returns
    `{"diagram_id": ..., "remote_id": ..., "operation": ...}` — has
    neither bare `id` nor a single canonical choice) → emit the
    payload's *first* `_id`-suffixed value (so `tm diagram push
    --id-only` prints the local `diagram_id`). Document this in the
    flag's help text.
  - If the payload is a non-dict scalar or a non-id-bearing dict →
    fall back to normal JSON emission. Don't crash.

**Important**: the existing `--json/--no-json` toggle (compact vs
pretty-print) and the existing `--json FIELDS` per-command projection
are independent of `--id-only` — `--id-only` is about *what* gets
emitted; `--json` is about *how*. When both are set, `--id-only`
wins (the output is a bare id, no JSON).

`tests/cli/test_id_only.py` covers:

- `tm --id-only diagram create --name x` → stdout is the id, exit 0.
- `tm --id-only diagram list` (with seeded diagram) → stdout has one
  id per line, no `_pagination` footer even when page is full.
- `tm --id-only diagram update <id> --name y` → stdout is the id.
- `tm --id-only diagram delete <id>` → stdout is the id (from the
  `{"deleted": ..., "id": ...}` payload).
- `tm --id-only diagram push --server http://stub` (with mocked
  `post_diagram`) → stdout is the local diagram id (the first
  `*_id`-suffixed field).
- `tm --id-only schema document` → falls back to JSON (schema output
  is not id-bearing); regression-pins the fallback.
- `--id-only` + `--json` together → still emits the bare id.

`tm agent-info` "Usage patterns" section gets one bullet documenting
the flag.

**Acceptance**:
- New tests pass. Existing tests unchanged.
- Help / introspection snapshots regenerated (mechanical).
- `make lint` / `make test` clean.

### 3. `tm flow {add,remove}-payload --from <node_id>`

**Files**: `src/tm_cli/cli/flows.py`, `src/tm_cli/cli/_agent_info.py`,
`src/tm_cli/cli/CLAUDE.md`, `tests/cli/test_flow_payloads.py`,
`tests/acceptance/test_dfd_workflow.py` (if it uses the old flag),
`examples/demo-prompt-java-webapp.md` (drop the `mk_flow` helper),
plus mechanical snapshot updates for `flow add-payload --help`,
`flow remove-payload --help`, and `tm commands`.

Replace the option:

```python
# was:
@click.option("--endpoint", type=click.Choice(["1", "2"]), required=True)

# becomes:
@click.option(
    "--from",
    "from_node_id",            # 'from' is a Python keyword
    type=click.INT,
    required=True,
    help="Node id this data item is sourced at (must be node1 or node2 of the flow).",
)
```

Command-body lookup logic (shared between `add-payload` and
`remove-payload`):

```python
flow = DataFlowRepository(conn).get(flow_id)
if flow is None:
    raise NotFoundError(f"Flow id={flow_id} not found", id=str(flow_id))
if from_node_id == flow.node1_id:
    endpoint = 1
elif from_node_id == flow.node2_id:
    endpoint = 2
else:
    raise UserError(
        f"Node id={from_node_id} is not an endpoint of flow id={flow_id}",
        flow_id=str(flow_id),
        from_node_id=str(from_node_id),
        node1_id=str(flow.node1_id),
        node2_id=str(flow.node2_id),
        hint=f"Pass --from {flow.node1_id} or --from {flow.node2_id}.",
    )
```

The hint exposing both endpoints is deliberate — the agent's most
likely error is mismatching node ids across canonical-order swaps; the
hint tells them exactly what's accepted.

`DataFlowRepository.add_payload(...)` / `remove_payload(...)` are
unchanged — they already take a `source_endpoint` int and the CLI now
computes it.

`tests/cli/test_flow_payloads.py` updates:

- Replace every existing `--endpoint 1` / `--endpoint 2` with
  `--from <node_id>`.
- Add new cases:
  - `--from <other-diagram-node-id>` → user_error with the hint
    listing both real endpoints.
  - `--from <non-existent-id>` → same user_error.
  - `--from <flow's actual node1>` → endpoint=1 internally; payload
    appears at endpoint 1 on `payload-for-flow`.
  - `--from <flow's actual node2>` → endpoint=2.
  - Symmetric coverage for `remove-payload`.

`tests/acceptance/test_dfd_workflow.py`: search for any
`add-payload --endpoint` and migrate.

`tm agent-info`: update the per-document workflow line that mentions
`--endpoint 1|2` to read `--from <node_id>` with a one-line note that
the value must be one of the flow's two endpoints.

`examples/demo-prompt-java-webapp.md`: delete the `mk_flow` helper and
its callers; replace each `attach "$F1" "$FWD" "$D1"` with a direct
`tm flow add-payload "$F1" --data-item "$D1" --from "$EE_USER"`.
Verify the demo's directional intent is preserved without the
`if F1_N1 = ...` guard.

**Acceptance**:
- Old `--endpoint` flag is gone (Click reports "no such option" if
  passed).
- All `flow add-payload` / `flow remove-payload` tests pass after
  migration.
- The acceptance test (`test_dfd_workflow`) and the new error-path
  cases pass.
- The demo prompt no longer needs `mk_flow`; re-running it
  end-to-end against a stub WSGI server (or by hand against a local
  `dfd_editor`) produces the same diagram as before this change.
- Help and `tm commands` snapshots regenerated.
- `make lint` / `make test` clean.

## Definition of Done

- All step-level acceptance criteria met.
- `make lint` and `make test` clean.
- No regression in existing CLI snapshots beyond the mechanical
  updates listed above.
- `.env.example` documents `TM_DIAGRAM_ID`.
- `tm agent-info` reflects all three changes.
- `examples/demo-prompt-java-webapp.md` no longer needs the `mk_flow`,
  `mk_item`, or `attach` shell helpers — every per-step `tm` invocation
  reads as straight-line shell. (The file's total line count grows
  because each previously batched `attach "$F1" "$FWD" "$D1" "$D5" ...`
  call expands to one `tm flow add-payload` line per data item; this is
  intentional, since straight-line shell is what an LLM agent reads
  most reliably.)
- The CLI surface is the same shape as before for everything outside
  these three knobs (no incidental refactors).
