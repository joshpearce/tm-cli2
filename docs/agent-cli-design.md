# Design Guidance: An Agent-First CRUD CLI for tm-cli

Last verified: 2026-05-05
Status: Guidance document — feeds into a later implementation plan, not yet implemented.

## Why this document exists

The forthcoming CRUD CLI for tm-cli will be driven by AI agents (primarily Claude Code on Opus models), not by humans typing commands at a prompt. The schema spans eight entities across two domains — Document/Term/Observation in the legacy domain and Diagram/Node/Container/DataFlow/DataItem in the DFD domain — plus four junction tables, with polymorphic variants on Node and Container and meaningful invariants on DataFlow (canonical endpoint ordering, no self-loops).

Designing this CLI for the agent consumer first — instead of retrofitting agent-friendliness later — compounds across every tool call the agent ever makes. This document captures the specific design attributes the CLI must have. It is the spec the implementation plan will satisfy.

---

## 1. Surface shape: `tm <noun> <verb>`, mirroring `gh` and `kubectl`

Claude has been trained on enormous quantities of `gh`, `git`, `kubectl`, `aws`, and `docker` invocations. The single biggest lever is to **look exactly like those tools**.

- `tm document list`, `tm document get <id>`, `tm document create`, `tm document update <id>`, `tm document delete <id>`.
- The same five verbs (`list`, `get`, `create`, `update`, `delete`) for **every** entity. No `add` for one entity and `create` for another. No `show` vs `get`. Pick one and replicate.
- Junction tables get explicit relationship verbs that read like the resource's own actions: `tm document link-term <doc-id> <term-id>` / `unlink-term`; `tm flow add-payload <flow-id> --data-item <id> --from <node-id>` (the source node id — must be one of the flow's two endpoints). Avoid generic `link`/`unlink` subcommands — agents pattern-match on the noun.
- Polymorphic types become explicit subcommands so the type is unambiguous in the command itself: `tm node create process …`, `tm node create external-entity …`, `tm node create data-store …`. Don't ask the agent to remember a `--type` flag whose valid values vary per variant.

## 2. Output: structured by default, with `--json` and field selection

- **Default to JSON on stdout** (one object for `get`/`create`/`update`, NDJSON / one-object-per-line for `list`). Pretty-print only when stdout is a TTY; never when piped or invoked by an agent. Claude reads stdout as text — it parses JSON better than ASCII tables, every time.
- Adopt **`gh`'s `--json field1,field2,…` pattern verbatim**. `tm node list --json id,name,type` is something Claude has seen thousands of times and emits naturally. It also lets the agent project away large fields (`content`, `description`) when it only needs IDs, saving tokens.
- Optionally expose **`--jq <expr>`** (also a `gh` convention) to push filtering server-side and shrink what the agent has to read.
- **Stable field names in snake_case**, matching the Pydantic models exactly. Agents will copy a field name from one command's output into the next command's flag; drift between `last_updated` and `lastUpdated` causes silent failures.
- **ISO 8601 UTC** for every timestamp, no exceptions.

## 3. Errors: stderr, structured, actionable, non-zero exit

- **Data on stdout, errors on stderr.** This lets an agent capture stdout cleanly even when the command fails partway.
- **Non-zero exit codes** with consistent meanings: `0` ok, `1` user error (bad input), `2` not found, `3` constraint violation, `4` system/IO error. Claude is trained to check exit codes; use them.
- Errors are **JSON on stderr** when `--json` is set globally, with shape `{"error": {"code": "not_found", "message": "...", "hint": "...", "input": {...}}}`. The `hint` field is gold for agents — `"hint": "did you mean node id 42? (closest match)"` turns a failure into a self-correcting next call.
- **Echo the offending input back** in the error payload. The agent's context may have moved on; including the input it sent removes ambiguity.
- **Never write a partial success silently.** Bulk operations either succeed atomically or return a per-item result array showing which items succeeded and which failed, with the same error shape per failure.

## 4. Inputs: long flags, stdin for bulk, no positional ambiguity

- **Long flags only in the public contract** (`--title`, `--observation-type`). Short flags are fine to *also* support but never *only* support — `-t` is unmemorable and Claude will prefer the long form anyway.
- **One positional**: the primary key of the resource being acted on (`tm task get <id>`). Everything else is a flag. Positionals are where agents most often mis-order arguments.
- **Boolean flags as `--flag/--no-flag` pairs** (Click supports this natively). `--encryption-at-rest/--no-encryption-at-rest` is unambiguous; bare `--encryption-at-rest` forces the agent to guess what "false" looks like.
- **Accept JSON on stdin for `create` and `update`**, gated by a `--stdin` flag or by detecting non-TTY stdin. This is the bulk-operation escape hatch and also what agents reach for when the field count gets large. Output shape mirrors input shape: object in → object out, array in → array out, same order.
- **Never prompt interactively.** No `Are you sure? [y/N]`. Destructive operations require `--yes` or are naturally idempotent. An agent cannot answer a TTY prompt — it will hang.
- **`--dry-run`** on every mutation. The agent can verify its plan before committing, which is especially valuable for `delete` cascades through the DFD junctions.

## 5. Discoverability: `--help` is a manual, plus a machine-readable schema

- **Every subcommand's `--help` includes 2–3 worked examples** in a final `Examples:` section. Claude is heavily few-shot-driven; one example in help text is worth ten lines of prose. Show real flag combinations, real IDs, real JSON payloads.
- **`tm schema [<entity>]`** dumps JSON Schema for each entity, derivable directly from the Pydantic models via `.model_json_schema()`. An agent can call this once per session to learn the data model instead of guessing field names from prior commands.
- **`tm commands --json`** dumps the full command tree (commands, flags, types, descriptions) as JSON. This is the agent-equivalent of bash completion. Click can produce this from its introspection API.
- **Help text uses the same field names as the JSON output and the schema.** No documentation drift.

## 6. Idempotency and identity

- **`delete` is idempotent**: deleting a missing id exits 0 with `{"deleted": false, "reason": "not_found"}`, not an error. Agents retry; idempotency makes retries safe.
- **`create` supports `--if-not-exists`** keyed on a natural key (e.g. `Term.term`, which is already `UNIQUE`). Returns `{"created": true|false, "term": {...}}`. This eliminates a whole category of "check then create" race conditions an agent would otherwise have to write itself.
- **`update` returns the full resulting object**, not just `{"ok": true}`. Saves the agent a follow-up `get`. Same for `create`.
- **IDs are integers as stated by the schema, but always quoted as strings in JSON output** to avoid the JavaScript-world 53-bit foot-gun and to keep the agent's mental model uniform across IDs of any type. Accept either string or int on input.
- **Accept partial-prefix ID matching only when unambiguous**, like `git`'s short SHAs. Useful for humans, neutral for agents — but it must error (not guess) on ambiguity.

## 7. List commands: pagination, filtering, sorting — all consistent

- Every `list` command supports the **same flag set**: `--limit N` (default something sane like 50, never unbounded), `--offset N` or `--cursor <opaque>`, `--sort <field>`, `--order asc|desc`, `--filter <field>=<value>` (repeatable).
- **Output includes a pagination footer** as the last NDJSON line when there is more: `{"_pagination": {"next_cursor": "...", "total": 1234}}`. Distinguishable from data rows by the `_` prefix.
- **Filter syntax stays simple** — `--filter status=open --filter observation_type=todo` repeated, ANDed together. Don't invent a query DSL; agents will write fragile parsers around it.

## 8. Polymorphism and relationships, made first-class

The DFD domain has discriminated unions (Node, Container) and a forest hierarchy via `container_membership`. Hide none of this:

- **`tm node get <id>`** returns the variant fields inline with a `"type"` discriminator field at the top level — exactly how Pydantic's `Discriminator` serializes. The agent reads `type` and knows which fields to expect.
- **Relationships get their own list endpoints**: `tm document list-terms <doc-id>`, `tm container list-children <container-id>`, `tm flow list-payloads <flow-id>`. Don't make the agent compose joins by hand.
- **DataFlow's canonical-ordering and no-self-loop invariants are enforced by the CLI before the DB sees them**, with errors that explain the rule (`"hint": "endpoints are stored in canonical order; you supplied (5, 3) which is equivalent to (3, 5)"`). Don't surface a raw `IntegrityError`.

## 9. Token economy

- **Default list output excludes large text fields** (`content`, `description`, `definition`) and includes them only with `--json content,…` or `--full`. An agent listing 50 documents shouldn't get 50 KB of body text it didn't ask for.
- **`get` includes everything by default**; `list` is the one that stays lean.
- **Compact JSON** (no indent) when piped, indented when TTY. Indented JSON in an agent's context window is 30–40% more tokens for zero benefit.

## 10. Logging and side-channel noise

- **No banner, no version line, no "Loading config…" on stdout or stderr** during normal operation. Every byte of stdout that isn't the answer is a byte the agent has to skip past.
- **A single `--verbose` / `-v` flag** routes diagnostic logging to stderr, off by default. Useful when the agent (or its human) is debugging; invisible otherwise.

---

## How this guidance feeds the implementation plan

When the implementation plan is written it should:

1. Sequence the work — likely global CLI scaffolding (Click groups, the `--json` flag, the structured-error handler, the `tm schema` and `tm commands` introspection commands) before the per-entity commands.
2. Prove the patterns on the simpler legacy domain (Document, Term, Observation) first, then apply them to the DFD domain where polymorphism and junctions raise the difficulty.
3. Treat output shape as a contract — golden-file tests over JSON output and `--help` text are the right shape of test here, because output stability *is* the API agents depend on.
4. Include a scripted Claude Code acceptance test: an agent should be able to complete "create a diagram with two process nodes and a data flow between them" using only the CLI's output to discover IDs, with no human intervention and no `--help` reads beyond the first.

## Critical files the implementation will touch

- `src/tm_cli/main.py` — Click group, global flags (`--json`, `--verbose`), the error handler that converts exceptions to the structured stderr shape.
- `src/tm_cli/cli/` (new) — one module per entity, each registering a Click subgroup with the five standard verbs plus relationship verbs.
- `src/tm_cli/db/` — already has the Pydantic models; `model_json_schema()` powers `tm schema`. No DB changes are needed for the CLI design itself.
- `tests/` — golden-file tests of help text and JSON output shape.
