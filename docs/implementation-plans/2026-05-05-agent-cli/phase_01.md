# Agent CLI — Phase 1: Scaffolding

**Goal:** Lay the foundation every entity command will use. No entity commands yet.

**Architecture:** A new `src/tm_cli/cli/` package holds underscore-prefixed shared helpers (`_errors`, `_output`, `_options`, `_stdin`). The root `tm` group lives in `src/tm_cli/main.py` as a custom `click.Group` subclass that wraps `invoke()` to translate any exception (including Click's own `UsageError`/`BadParameter`) into a structured `TmError` subclass with a stable exit code and JSON error body on stderr. Test infrastructure adds a deterministic seed fixture, registers Syrupy as a dev dep, and ships a custom Syrupy serializer that masks volatile fields so golden snapshots remain stable across runs.

**Tech Stack:** Python 3.11+, Click 8.x, Pydantic v2, sqlite3, pytest + Syrupy.

**Scope:** Phase 1 of 8 from `docs/design-plans/2026-05-05-agent-cli.md`.

**Codebase verified:** 2026-05-05 via codebase-investigator. Repositories at `src/tm_cli/db/` are complete; `src/tm_cli/cli/` does not yet exist; `src/tm_cli/main.py` has a placeholder `hello` command; `tests/conftest.py` has a `db_path` fixture; no snapshot library is installed.

**External dependencies verified:** Syrupy registers as a pytest plugin on install (no manual config needed); `pytest --snapshot-update` blesses snapshots. Click's `result_callback` does NOT run on exceptions — use a custom `Group.invoke()` override for centralized exception mapping. Click 8.x has no built-in mutually-exclusive primitive; manual UsageError raising at command entry covers our needs (Phase 2 introduces this; Phase 1 does not).

---

## Acceptance Criteria Coverage

This is an infrastructure phase. **Verifies: None** — no entity commands yet, so no end-to-end ACs from `agent-cli.AC1` through `agent-cli.AC11` are exercised.

The phase ships unit-tested internal helpers that the rest of the build depends on:
- `_errors.map_exception()` — every exit-code path (1/2/3/4) has a unit test (these tests pre-stage the contract that AC5 will exercise end-to-end in Phase 2).
- `db_with_seed` fixture — a sanity test asserts the seeded ids are deterministic and reproducible across two invocations.
- Syrupy is installed and self-tests on a trivial snapshot.

**Note on AC5.6 (`OSError`/`PermissionError` → exit 4):** the unit test for `map_exception` is the only place this exit-code path is verified. End-to-end exercise (e.g., pointing the CLI at a chmod-zeroed file path) is portably awkward and the design's "Done when" criteria do not require it. If a future regression hits this path through some other flow, add coverage then.

---

## Required reading for the executor

- Project README/CLAUDE: `/Users/josh/code/tm-cli/CLAUDE.md` (tech stack, conventions, commands).
- Repository contracts (Phase 1 doesn't call them, but the error mapping must understand their exception surface):
  - `/Users/josh/code/tm-cli/src/tm_cli/db/connection.py` — `connect()` context manager.
  - `/Users/josh/code/tm-cli/src/tm_cli/db/__init__.py` — exported names.
- Existing entry point: `/Users/josh/code/tm-cli/src/tm_cli/main.py` (will be rewritten).
- Existing test fixture: `/Users/josh/code/tm-cli/tests/conftest.py` (will be extended, not replaced).

The executor should activate these skills if relevant in their session:
- `house-style:coding-effectively`
- `house-style:writing-good-tests`
- `ed3d-plan-and-execute:test-driven-development` (for tasks that have tests)
- `ed3d-plan-and-execute:verification-before-completion` (before claiming the phase is done)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add Syrupy as a dev dependency

**Type:** Infrastructure.

**Files:**
- Modify: `/Users/josh/code/tm-cli/pyproject.toml` (the `[dependency-groups] dev` block, currently lines 19-23).

**Implementation:**

Add `"syrupy>=4.6"` to the `dev` list. The `[dependency-groups] dev` block must read:

```toml
[dependency-groups]
dev = [
    "ruff>=0.9",
    "pytest>=8.0",
    "syrupy>=4.6",
]
```

No additional pytest configuration is required — Syrupy auto-registers as a pytest plugin on installation.

**Verification:**

Run: `make install-deps`
Expected: completes without error; `uv.lock` is updated; `.venv/` contains `syrupy`.

Run: `uv run python -c "import syrupy; print(syrupy.__version__)"`
Expected: prints a version >= 4.6.

**Commit:** `chore(deps): add syrupy for golden snapshot testing`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create `src/tm_cli/cli/` package skeleton

**Type:** Infrastructure.

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/__init__.py` (empty file with a one-line module docstring).

**Implementation:**

Create `__init__.py` with exactly:

```python
"""tm CLI — Click command modules and shared helpers."""
```

Do not export anything yet. Subsequent tasks add modules to this package.

**Verification:**

Run: `uv run python -c "import tm_cli.cli"`
Expected: succeeds with no output.

**Commit:** `feat(cli): create cli package skeleton`
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Error hierarchy and `map_exception` mapper

**Type:** Functionality (with tests in Task 4).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/_errors.py`.

**Implementation:**

Create `_errors.py` with the full content below. The module:

- Defines `TmError(click.ClickException)` as the base class with `exit_code: ClassVar[int]` and a `code: ClassVar[str]`. `to_payload()` returns the structured error body. `show()` is overridden to emit JSON to stderr (Click's default emits `Error: <msg>` text — we replace it).
- Defines four subclasses: `UserError` (1), `NotFoundError` (2), `ConstraintError` (3), `SystemError` (4). The class name `SystemError` shadows a builtin; that is intentional — Python resolves it within this module without conflict, and external callers always import it as `from tm_cli.cli._errors import SystemError`.
- Defines `map_exception(exc, *, input_payload=None) -> TmError` that translates raw exceptions into the right subclass. Constraint extraction inspects the `sqlite3.IntegrityError` message prefix to populate `constraint` ∈ {`unique`, `foreign_key`, `check`, `unknown`}.

```python
"""Error mapping and structured JSON exit for the tm CLI.

All exceptions raised inside command callbacks (and during Click's parsing)
flow through ``map_exception`` to produce a stable exit code and a JSON
payload on stderr. ``TmError`` and its subclasses are ``click.ClickException``
subclasses so Click's existing dispatch (``BaseCommand.main`` → ``exception.show()`` →
``sys.exit(exception.exit_code)``) does the right thing automatically.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from typing import Any, ClassVar, IO

import click
from pydantic import ValidationError

_UNIQUE_RE = re.compile(r"^UNIQUE constraint failed", re.IGNORECASE)
_FK_RE = re.compile(r"^FOREIGN KEY constraint failed", re.IGNORECASE)
_CHECK_RE = re.compile(r"^CHECK constraint failed", re.IGNORECASE)


class TmError(click.ClickException):
    """Base class for all CLI-mapped errors."""

    exit_code: ClassVar[int] = 1
    code: ClassVar[str] = "user_error"

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        input_payload: Any = None,
        **extra: Any,
    ) -> None:
        super().__init__(message)
        self.hint = hint
        self.input_payload = input_payload
        self.extra: dict[str, Any] = extra

    def to_payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint is not None:
            body["hint"] = self.hint
        if self.input_payload is not None:
            body["input"] = self.input_payload
        body.update(self.extra)
        return {"error": body}

    def show(self, file: IO[str] | None = None) -> None:  # type: ignore[override]
        target = file if file is not None else sys.stderr
        json.dump(self.to_payload(), target, default=str)
        target.write("\n")


class UserError(TmError):
    exit_code: ClassVar[int] = 1
    code: ClassVar[str] = "user_error"


class NotFoundError(TmError):
    exit_code: ClassVar[int] = 2
    code: ClassVar[str] = "not_found"


class ConstraintError(TmError):
    exit_code: ClassVar[int] = 3
    code: ClassVar[str] = "constraint_violation"


class SystemError(TmError):  # noqa: A001  # CLI-internal type, shadows builtin intentionally
    exit_code: ClassVar[int] = 4
    code: ClassVar[str] = "system_error"


def _classify_integrity(msg: str) -> str:
    if _UNIQUE_RE.match(msg):
        return "unique"
    if _FK_RE.match(msg):
        return "foreign_key"
    if _CHECK_RE.match(msg):
        return "check"
    return "unknown"


def map_exception(exc: BaseException, *, input_payload: Any = None) -> TmError:
    """Translate ``exc`` into the appropriate ``TmError`` subclass.

    Already-mapped ``TmError`` instances are returned unchanged so callers can
    re-raise from inside command code without double-wrapping.
    """

    if isinstance(exc, TmError):
        return exc

    if isinstance(exc, ValidationError):
        return UserError(str(exc), input_payload=input_payload)

    if isinstance(exc, sqlite3.IntegrityError):
        return ConstraintError(
            str(exc),
            input_payload=input_payload,
            constraint=_classify_integrity(str(exc)),
        )

    if isinstance(exc, ValueError):
        return UserError(str(exc), input_payload=input_payload)

    if isinstance(exc, click.UsageError):
        return UserError(exc.format_message(), input_payload=input_payload)

    if isinstance(exc, click.ClickException):
        return UserError(exc.format_message(), input_payload=input_payload)

    if isinstance(exc, (PermissionError, OSError)):
        return SystemError(str(exc), input_payload=input_payload)

    return SystemError(f"{type(exc).__name__}: {exc}", input_payload=input_payload)
```

**Verification:**

Run: `uv run python -c "from tm_cli.cli._errors import TmError, UserError, NotFoundError, ConstraintError, SystemError, map_exception; print('ok')"`
Expected: prints `ok`.

Run: `uv run ruff check src/tm_cli/cli/_errors.py && uv run ruff format --check src/tm_cli/cli/_errors.py`
Expected: passes.

**Commit:** `feat(cli): add structured error hierarchy and map_exception`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Unit tests for `map_exception`

**Type:** Functionality (tests).

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/cli/__init__.py` (empty).
- Create: `/Users/josh/code/tm-cli/tests/cli/test_errors.py`.

**Implementation:**

Tests must verify each exit-code path used by the CLI's stable contract. Use `pytest.raises` only where appropriate; `map_exception` itself does not raise — it returns a `TmError`. Assertions check:

- The returned class.
- `exit_code` (1/2/3/4 per subclass).
- `code` field on the JSON payload.
- For `ConstraintError`, the `constraint` extra is correctly classified.
- The payload roundtrips through `json.dumps` (no non-serializable objects).

Tests to write (one test function per case):

| Test | Input | Expected class | Expected `exit_code` | Expected `code` | Extra assertions |
|---|---|---|---|---|---|
| `test_validation_error_maps_to_user_error` | `pydantic.ValidationError` (build via a tiny `BaseModel(int)` failure) | `UserError` | 1 | `user_error` | message contains the validator string |
| `test_value_error_maps_to_user_error` | `ValueError("self-loop")` | `UserError` | 1 | `user_error` | message echoes raw text |
| `test_click_usage_error_maps_to_user_error` | `click.UsageError("bad flag")` | `UserError` | 1 | `user_error` | — |
| `test_click_bad_parameter_maps_to_user_error` | `click.BadParameter("x")` | `UserError` | 1 | `user_error` | — |
| `test_integrity_unique_maps_to_constraint` | `sqlite3.IntegrityError("UNIQUE constraint failed: terms.term")` | `ConstraintError` | 3 | `constraint_violation` | `extra["constraint"] == "unique"` |
| `test_integrity_foreign_key_maps_to_constraint` | `sqlite3.IntegrityError("FOREIGN KEY constraint failed")` | `ConstraintError` | 3 | `constraint_violation` | `extra["constraint"] == "foreign_key"` |
| `test_integrity_check_maps_to_constraint` | `sqlite3.IntegrityError("CHECK constraint failed: ...")` | `ConstraintError` | 3 | `constraint_violation` | `extra["constraint"] == "check"` |
| `test_integrity_unknown_maps_to_constraint_unknown` | `sqlite3.IntegrityError("garbage")` | `ConstraintError` | 3 | `constraint_violation` | `extra["constraint"] == "unknown"` |
| `test_permission_error_maps_to_system_error` | `PermissionError("denied")` | `SystemError` | 4 | `system_error` | — |
| `test_oserror_maps_to_system_error` | `OSError("ENOENT")` | `SystemError` | 4 | `system_error` | — |
| `test_already_mapped_passthrough` | a pre-built `NotFoundError("missing", id="42")` | `NotFoundError` | 2 | `not_found` | identity-checked: returned object is the same instance |
| `test_unknown_exception_maps_to_system_error` | `RuntimeError("boom")` | `SystemError` | 4 | `system_error` | message starts with `RuntimeError:` |
| `test_payload_includes_hint_and_input_when_provided` | a `UserError("bad", hint="try foo", input_payload={"k":"v"})` | `UserError` | 1 | `user_error` | `to_payload()["error"]` has `hint` and `input` |
| `test_payload_is_json_serializable` | any mapped error | — | — | — | `json.dumps(err.to_payload())` succeeds |
| `test_show_writes_json_to_target` | a `UserError("x")` with an `io.StringIO` passed to `.show(file=...)` | — | — | — | the StringIO contains a parseable JSON object whose `error.code == "user_error"` |

A representative test (others follow the same shape):

```python
import io
import json
import sqlite3

import click
import pytest
from pydantic import BaseModel, ValidationError

from tm_cli.cli._errors import (
    ConstraintError,
    NotFoundError,
    SystemError,
    TmError,
    UserError,
    map_exception,
)


def _make_validation_error() -> ValidationError:
    class _M(BaseModel):
        n: int

    try:
        _M(n="not an int")
    except ValidationError as e:
        return e
    raise AssertionError("ValidationError was not raised")


def test_validation_error_maps_to_user_error() -> None:
    mapped = map_exception(_make_validation_error())
    assert isinstance(mapped, UserError)
    assert mapped.exit_code == 1
    assert mapped.to_payload()["error"]["code"] == "user_error"


def test_integrity_unique_maps_to_constraint() -> None:
    mapped = map_exception(sqlite3.IntegrityError("UNIQUE constraint failed: terms.term"))
    assert isinstance(mapped, ConstraintError)
    assert mapped.exit_code == 3
    body = mapped.to_payload()["error"]
    assert body["code"] == "constraint_violation"
    assert body["constraint"] == "unique"


def test_already_mapped_passthrough() -> None:
    original = NotFoundError("missing", id="42")
    mapped = map_exception(original)
    assert mapped is original


def test_show_writes_json_to_target() -> None:
    err = UserError("x")
    buf = io.StringIO()
    err.show(file=buf)
    payload = json.loads(buf.getvalue())
    assert payload["error"]["code"] == "user_error"
```

Implement the full table above; one test per row.

**Verification:**

Run: `uv run pytest tests/cli/test_errors.py -v`
Expected: all tests pass (15 cases).

Run: `make lint`
Expected: passes.

**Commit:** `test(cli): cover map_exception across all exit-code paths`
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Output module (`emit`, JSON encoder, ID stringification)

**Type:** Infrastructure (the helper is exercised by Phase 2's golden tests; we ship it now to unblock that phase).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/_output.py`.

**Implementation:**

`emit(ctx, payload, *, list_mode=False, limit=None, offset=0)` is the single write path for command output:

- Reads `ctx.obj["json"]` (set in `main.py`) to decide indent: `None` when piped/JSON mode, `2` when on a TTY.
- Pydantic models are converted via `model_dump(mode="json")`.
- Integer fields named `id` or ending in `_id` are post-processed to strings (recursively, including inside lists and nested dicts).
- `datetime` is serialized via ISO-8601 by a custom encoder (Pydantic's `mode="json"` already does this for fields it manages, but the encoder catches stray `datetime` values from non-Pydantic sources).
- `list_mode=True` emits NDJSON (one JSON object per line, never indented). When `limit is not None and len(rows) == limit`, a final `{"_pagination": {"next_offset": offset + limit, "returned": len(rows)}}` line is appended.

```python
"""Output helpers — ``emit()`` is the single write path for all command results."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Iterable

import click

_ID_FIELD_EXACT = frozenset({"id"})
_ID_SUFFIX = "_id"


def _is_id_key(key: str) -> bool:
    return key in _ID_FIELD_EXACT or key.endswith(_ID_SUFFIX)


def _stringify_ids(obj: Any) -> Any:
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if _is_id_key(k) and isinstance(v, int) and not isinstance(v, bool):
                result[k] = str(v)
            else:
                result[k] = _stringify_ids(v)
        return result
    if isinstance(obj, list):
        return [_stringify_ids(item) for item in obj]
    return obj


class _IsoEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:  # noqa: D401
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        return super().default(o)


def _to_jsonable(payload: Any) -> Any:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return _stringify_ids(payload)


def _json_mode(ctx: click.Context) -> bool:
    obj = ctx.obj if ctx.obj is not None else {}
    return bool(obj.get("json", True))


def emit(
    ctx: click.Context,
    payload: object,
    *,
    list_mode: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> None:
    """Emit ``payload`` to stdout.

    list_mode=True writes NDJSON, one row per line, with an optional
    ``_pagination`` footer when ``len(rows) == limit``.
    """

    json_mode = _json_mode(ctx)
    indent = None if json_mode else 2

    if list_mode:
        rows: list[Any] = list(payload) if isinstance(payload, Iterable) else [payload]
        for row in rows:
            click.echo(json.dumps(_to_jsonable(row), cls=_IsoEncoder))
        if limit is not None and len(rows) == limit:
            footer = {
                "_pagination": {
                    "next_offset": offset + limit,
                    "returned": len(rows),
                },
            }
            click.echo(json.dumps(footer, cls=_IsoEncoder))
        return

    click.echo(json.dumps(_to_jsonable(payload), cls=_IsoEncoder, indent=indent))
```

**Verification:**

Run: `uv run python -c "from tm_cli.cli._output import emit; print('ok')"`
Expected: prints `ok`.

Run: `make lint`
Expected: passes.

(End-to-end behavioral verification of `emit` happens in Phase 2's golden tests.)

**Commit:** `feat(cli): add output helper with NDJSON, id stringification, ISO datetimes`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Shared option decorators

**Type:** Infrastructure.

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/_options.py`.

**Implementation:**

Three decorators that subsequent phases stack onto entity commands. **The `resolve_default_diagram_id` function is intentionally NOT included here — it lands in Phase 4.**

```python
"""Shared Click option decorators for the tm CLI.

These decorators are stacked onto entity commands in subsequent phases.
The default-diagram resolver function lands in Phase 4.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import click

F = TypeVar("F", bound=Callable[..., Any])


def list_options(f: F) -> F:
    """Standard pagination + sort options for ``list`` and ``search`` commands."""
    f = click.option(
        "--limit",
        type=click.IntRange(min=1, max=10_000),
        default=50,
        show_default=True,
        help="Maximum rows to return.",
    )(f)
    f = click.option(
        "--offset",
        type=click.IntRange(min=0),
        default=0,
        show_default=True,
        help="Rows to skip from the start.",
    )(f)
    f = click.option(
        "--sort",
        "sort_field",
        default="id",
        show_default=True,
        metavar="FIELD",
        help="Column to sort by.",
    )(f)
    f = click.option(
        "--order",
        type=click.Choice(["asc", "desc"]),
        default="asc",
        show_default=True,
        help="Sort direction.",
    )(f)
    return f


def json_fields_option(f: F) -> F:
    """``--json FIELDS`` projects the listed comma-separated fields on output."""
    return click.option(
        "--json",
        "json_fields",
        metavar="FIELDS",
        default=None,
        help="Comma-separated field names to include in output.",
    )(f)


def dfd_diagram_id_option(f: F) -> F:
    """Hidden ``--diagram-id`` option for DFD entity commands.

    The resolver function (``resolve_default_diagram_id``) lands in Phase 4;
    this decorator only attaches the option so the option is in scope when
    Phase 4 wires it up.
    """
    return click.option(
        "--diagram-id",
        "diagram_id",
        type=click.INT,
        default=None,
        hidden=True,
        help="Diagram id (defaults to looking up or creating a 'default' diagram).",
    )(f)
```

**Verification:**

Run: `uv run python -c "from tm_cli.cli._options import list_options, json_fields_option, dfd_diagram_id_option; print('ok')"`
Expected: prints `ok`.

Run: `make lint`
Expected: passes.

**Commit:** `feat(cli): add shared list/json-fields/diagram-id option decorators`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Stdin reader (`read_json_stdin`)

**Type:** Functionality (with tests).

**Files:**
- Create: `/Users/josh/code/tm-cli/src/tm_cli/cli/_stdin.py`.
- Create: `/Users/josh/code/tm-cli/tests/cli/test_stdin.py`.

**Implementation:**

```python
"""Read JSON from stdin for ``--stdin`` bulk operations."""

from __future__ import annotations

import json
import sys
from typing import Any


def read_json_stdin() -> dict[str, Any] | list[dict[str, Any]]:
    """Read and parse JSON from stdin.

    Returns either a single object (for a single mutation) or a list of objects
    (for batch mode). Raises ``ValueError`` on empty input, malformed JSON, or
    a top-level type that isn't object or array-of-objects.
    """

    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("No JSON input received on stdin.")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON on stdin: {e}") from e

    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        if not all(isinstance(item, dict) for item in parsed):
            raise ValueError("Stdin JSON array must contain only objects.")
        return parsed
    raise ValueError("Stdin JSON must be an object or an array of objects.")
```

Tests (use `monkeypatch` to replace `sys.stdin`):

```python
import io

import pytest

from tm_cli.cli._stdin import read_json_stdin


def _stdin(monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(body))


def test_reads_single_object(monkeypatch: pytest.MonkeyPatch) -> None:
    _stdin(monkeypatch, '{"title": "x"}')
    assert read_json_stdin() == {"title": "x"}


def test_reads_list_of_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    _stdin(monkeypatch, '[{"a": 1}, {"a": 2}]')
    assert read_json_stdin() == [{"a": 1}, {"a": 2}]


def test_empty_input_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stdin(monkeypatch, "   \n  ")
    with pytest.raises(ValueError, match="No JSON input"):
        read_json_stdin()


def test_invalid_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stdin(monkeypatch, "{not json")
    with pytest.raises(ValueError, match="Invalid JSON"):
        read_json_stdin()


def test_top_level_scalar_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stdin(monkeypatch, '"a string"')
    with pytest.raises(ValueError, match="object or an array"):
        read_json_stdin()


def test_array_with_non_object_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stdin(monkeypatch, '[{"a":1}, "oops"]')
    with pytest.raises(ValueError, match="must contain only objects"):
        read_json_stdin()
```

**Verification:**

Run: `uv run pytest tests/cli/test_stdin.py -v`
Expected: all 6 tests pass.

**Commit:** `feat(cli): add stdin JSON reader for bulk create/update`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Root `tm` group and exception-mapping wrapper in `main.py`

**Type:** Functionality (with a smoke test that the wired-up CLI runs and surfaces a structured error).

**Files:**
- Modify (full rewrite): `/Users/josh/code/tm-cli/src/tm_cli/main.py`.
- Modify: `/Users/josh/code/tm-cli/tests/test_main.py` (existing file tests the placeholder `hello` command — that command is being removed, so the test needs to be replaced).

**Implementation:**

The root group is a `TmGroup(click.Group)` subclass that overrides `invoke()` to translate any non-`TmError` exception via `map_exception`. It also overrides `main()` so that Click's own `UsageError` / `BadParameter` / `MissingParameter` (which are raised during `make_context` BEFORE `invoke()`) are intercepted and replayed through `map_exception` for consistent JSON output and exit codes.

The root group declares `--json/--no-json` (TTY-aware default) and `-v/--verbose`. Resolved values land in `ctx.obj`.

Replace `src/tm_cli/main.py` with:

```python
"""tm CLI entry point — root Click group with structured error handling."""

from __future__ import annotations

import sys
from typing import Any

import click
from dotenv import load_dotenv

from tm_cli.cli._errors import TmError, map_exception

load_dotenv()


class TmGroup(click.Group):
    """Click group that funnels every exception through ``map_exception``.

    Click's ``BaseCommand.main()`` already handles ``ClickException`` subclasses
    (it calls ``.show()`` and exits with ``.exit_code``). We override
    ``invoke`` so exceptions raised inside command callbacks are translated to
    ``TmError`` subclasses, and override ``main`` so parse-time exceptions
    (raised in ``make_context`` BEFORE ``invoke`` runs) get the same
    treatment.
    """

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except TmError:
            raise
        except click.exceptions.Exit:
            raise
        except click.ClickException as e:
            raise map_exception(e) from e
        except Exception as e:
            raise map_exception(e) from e

    def main(
        self,
        args: Any = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> Any:
        try:
            return super().main(
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
        except TmError as e:
            if not standalone_mode:
                raise
            e.show()
            sys.exit(e.exit_code)
        except click.exceptions.Exit as e:
            if not standalone_mode:
                raise
            sys.exit(e.exit_code)
        except click.ClickException as e:
            if not standalone_mode:
                raise
            mapped = map_exception(e)
            mapped.show()
            sys.exit(mapped.exit_code)
        except Exception as e:
            if not standalone_mode:
                raise
            mapped = map_exception(e)
            mapped.show()
            sys.exit(mapped.exit_code)


def _default_json_mode() -> bool:
    """Default ``--json`` value: True when stdout is piped, False on a TTY."""
    return not sys.stdout.isatty()


@click.group(cls=TmGroup)
@click.option(
    "--json/--no-json",
    "json_mode",
    default=_default_json_mode,
    show_default="auto-detected from TTY",
    help="Force JSON-mode output (default: detected from stdout TTY).",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose logging.")
@click.pass_context
def cli(ctx: click.Context, json_mode: bool, verbose: bool) -> None:
    """tm — agent-first threat-model database CLI."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_mode
    ctx.obj["verbose"] = verbose
```

Replace `tests/test_main.py` with a smoke test that proves the group is wired up correctly:

```python
"""Smoke tests for the root ``tm`` group."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_cli_help_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "tm — agent-first" in result.output


def test_cli_unknown_subcommand_emits_structured_error() -> None:
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, ["this-command-does-not-exist"])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"


def test_cli_no_subcommand_does_not_crash() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [])
    # Click prints usage and exits 0 (or 2, depending on click version);
    # what we care about is that no Python traceback escaped.
    assert "Traceback" not in result.output
```

**Verification:**

Run: `uv run pytest tests/test_main.py -v`
Expected: all tests pass.

Run: `uv run tm --help`
Expected: prints help text mentioning `tm — agent-first threat-model database CLI`.

Run: `uv run tm bogus 2>&1 1>/dev/null | python -c 'import json,sys; print(json.load(sys.stdin)["error"]["code"])'`
Expected: prints `user_error`.

**Commit:** `feat(cli): wire root tm group with structured exception mapping`
<!-- END_TASK_8 -->

<!-- START_SUBCOMPONENT_C (tasks 9-10) -->

<!-- START_TASK_9 -->
### Task 9: Deterministic seed fixture

**Type:** Functionality (the seed and its sanity test are deliverables).

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/fixtures/__init__.py` (empty).
- Create: `/Users/josh/code/tm-cli/tests/fixtures/seed.py`.
- Modify: `/Users/josh/code/tm-cli/tests/conftest.py` (add `db_with_seed` fixture; keep existing `db_path` fixture intact).
- Create: `/Users/josh/code/tm-cli/tests/test_seed.py`.

**Implementation:**

Goal: a deterministic seed populates a fresh DB with one of every kind of row, so subsequent phases' golden tests can assert against stable data. The seed:

1. Creates one Diagram named **`non-default`** (intentionally NOT `default`, so default-diagram-fallback tests in Phase 4 don't collide).
2. Creates one ProcessNode, one ExternalEntityNode, one DataStoreNode in that diagram.
3. Creates one Container (variant=`container`) and one TrustBoundary in that diagram.
4. Creates one DataFlow between the process and data-store.
5. Creates two DataItems in the diagram (one with `parent_node_id` set to the process node, one without).
6. Creates two Documents.
7. Creates three Terms.
8. Creates two Observations.
9. Returns a `SeedIds` `dataclass` (or plain dict) with every minted id, so tests can address rows by name.

The seed signature: `seed(db_path: Path) -> SeedIds`. It opens its own `connect()` and uses repository constructors directly. **The seed contains NO datetimes that drift between runs** — Pydantic-managed `last_updated` will still drift, but the Syrupy serializer in Task 10 masks them.

`/Users/josh/code/tm-cli/tests/fixtures/seed.py`:

```python
"""Deterministic seed data for golden snapshot tests.

The seed populates a single canonical diagram named ``non-default`` so
default-diagram-fallback tests in Phase 4 don't accidentally pick it up.
Every row is addressable via the returned ``SeedIds`` mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tm_cli.db import (
    ContainerRepository,
    ContainerVariantCreate,
    DataFlowCreate,
    DataFlowRepository,
    DataItemCreate,
    DataItemRepository,
    DataStoreNodeCreate,
    DiagramCreate,
    DiagramRepository,
    DocumentCreate,
    DocumentRepository,
    ExternalEntityNodeCreate,
    NodeRepository,
    Observation,
    ObservationCreate,
    ObservationRepository,
    ProcessNodeCreate,
    Term,
    TermCreate,
    TermRepository,
    TrustBoundaryCreate,
    connect,
)


@dataclass
class SeedIds:
    diagram_id: int
    process_node_id: int
    external_entity_node_id: int
    data_store_node_id: int
    container_id: int
    trust_boundary_id: int
    data_flow_id: int
    data_item_with_parent_id: int
    data_item_without_parent_id: int
    document_ids: list[int] = field(default_factory=list)
    term_ids: list[int] = field(default_factory=list)
    observation_ids: list[int] = field(default_factory=list)


def seed(db_path: Path) -> SeedIds:
    """Populate ``db_path`` with deterministic fixtures and return their ids."""

    with connect(db_path) as conn:
        diagrams = DiagramRepository(conn)
        nodes = NodeRepository(conn)
        containers = ContainerRepository(conn)
        flows = DataFlowRepository(conn)
        items = DataItemRepository(conn)
        documents = DocumentRepository(conn)
        terms = TermRepository(conn)
        observations = ObservationRepository(conn)

        diagram = diagrams.create(
            DiagramCreate(name="non-default", description="seed diagram", author="seeder"),
        )
        process = nodes.create(
            diagram.id,
            ProcessNodeCreate(
                type="process",
                name="seed-process",
                description="A seeded process node.",
                trust_level="authenticated",
                assumptions=["seeded"],
            ),
        )
        external = nodes.create(
            diagram.id,
            ExternalEntityNodeCreate(
                type="external_entity",
                name="seed-external",
                description="A seeded external entity.",
                entity_type="user",
                out_of_scope=False,
            ),
        )
        store = nodes.create(
            diagram.id,
            DataStoreNodeCreate(
                type="data_store",
                name="seed-store",
                description="A seeded data store.",
                storage_type="database",
                contains_pii=True,
                encryption_at_rest=True,
            ),
        )
        container = containers.create(
            diagram.id,
            ContainerVariantCreate(
                type="container",
                name="seed-container",
                description="A seeded container.",
            ),
        )
        boundary = containers.create(
            diagram.id,
            TrustBoundaryCreate(
                type="trust_boundary",
                name="seed-boundary",
                description="A seeded trust boundary.",
                privilege_level="corporate",
            ),
        )
        flow = flows.create(
            diagram.id,
            DataFlowCreate(
                node1_id=process.id,
                node2_id=store.id,
                name="seed-flow",
                protocol="HTTPS",
                authenticated=True,
                encrypted=True,
            ),
        )
        item_with_parent = items.create(
            diagram.id,
            DataItemCreate(
                identifier="seed-item-1",
                name="Item with parent",
                description="seeded data item",
                classification="pii",
                parent_node_id=process.id,
            ),
        )
        item_without_parent = items.create(
            diagram.id,
            DataItemCreate(
                identifier="seed-item-2",
                name="Item without parent",
                description="seeded data item",
                classification="public",
            ),
        )

        doc_ids = [
            documents.create(
                DocumentCreate(
                    title=f"Seed Doc {i}",
                    author="seeder",
                    content=f"Seeded document body {i}.",
                ),
            ).id
            for i in (1, 2)
        ]
        term_ids = [
            terms.create(
                TermCreate(term=f"seed-term-{i}", definition=f"definition {i}"),
            ).id
            for i in (1, 2, 3)
        ]
        obs_ids = [
            observations.create(
                ObservationCreate(
                    content=f"Seed observation {i}",
                    observation_type="todo",
                    status="open",
                ),
            ).id
            for i in (1, 2)
        ]

        return SeedIds(
            diagram_id=diagram.id,
            process_node_id=process.id,
            external_entity_node_id=external.id,
            data_store_node_id=store.id,
            container_id=container.id,
            trust_boundary_id=boundary.id,
            data_flow_id=flow.id,
            data_item_with_parent_id=item_with_parent.id,
            data_item_without_parent_id=item_without_parent.id,
            document_ids=doc_ids,
            term_ids=term_ids,
            observation_ids=obs_ids,
        )
```

**Important:** the executor must verify that each `*Create` model name and field name above matches what `tm_cli.db` exports today. The investigator confirmed `ProcessNodeCreate`, `ExternalEntityNodeCreate`, `DataStoreNodeCreate`, `TrustBoundaryCreate`, `ContainerVariantCreate`, `DataFlowCreate`, `DataItemCreate`, `DocumentCreate`, `TermCreate`, `ObservationCreate`, `DiagramCreate` are all live. If a name diverges, fix the import — do **not** invent a new model.

`tests/conftest.py` becomes (extending the current contents):

```python
"""Pytest fixtures for tm-cli."""

from __future__ import annotations

from pathlib import Path

import pytest

from tm_cli.db import connection as connection_module
from tests.fixtures.seed import SeedIds, seed


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Per-test SQLite path with a fresh schema."""
    path = tmp_path / "tm.db"
    monkeypatch.setenv("TM_DB_PATH", str(path))
    monkeypatch.setattr(connection_module, "_initialized_paths", set())
    return path


@pytest.fixture
def db_with_seed(db_path: Path) -> tuple[Path, SeedIds]:
    """Seeded SQLite path + ``SeedIds`` map for golden tests."""
    ids = seed(db_path)
    return db_path, ids
```

`tests/test_seed.py`:

```python
"""Sanity check that the deterministic seed is reproducible."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

from tests.fixtures.seed import seed
from tm_cli.db import connection as connection_module


def _fresh_path(tmp_path: Path, name: str, *, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Allocate a fresh DB path under ``tmp_path`` and isolate ``init_schema`` cache."""
    p = tmp_path / name
    monkeypatch.setenv("TM_DB_PATH", str(p))
    monkeypatch.setattr(connection_module, "_initialized_paths", set())
    return p


def test_seed_produces_stable_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = seed(_fresh_path(tmp_path, "a.db", monkeypatch=monkeypatch))
    b = seed(_fresh_path(tmp_path, "b.db", monkeypatch=monkeypatch))
    # asdict() compares structurally, including all minted ids.
    assert asdict(a) == asdict(b), "Seed must be deterministic across fresh DBs"
```

**Verification:**

Run: `uv run pytest tests/test_seed.py -v`
Expected: passes.

Run: `uv run pytest tests/ -v`
Expected: all existing tests + new tests pass.

**Commit:** `test(cli): add db_with_seed fixture and deterministic seed module`
<!-- END_TASK_9 -->

<!-- START_TASK_10 -->
### Task 10: Syrupy custom serializer for masking volatile fields

**Type:** Functionality (the masking extension is a deliverable; a sanity test confirms it).

**Files:**
- Create: `/Users/josh/code/tm-cli/tests/fixtures/syrupy_ext.py`.
- Modify: `/Users/josh/code/tm-cli/tests/conftest.py` (add a `snapshot` fixture override that uses the masking extension).
- Create: `/Users/josh/code/tm-cli/tests/test_syrupy_masking.py`.

**Implementation:**

The masking extension subclasses `AmberSnapshotExtension` and walks the serialized data: integer values for keys named `id` or ending in `_id` become the literal string `<INT>`, ISO-8601 datetime strings become `<DATETIME>`. The walk is done before Syrupy's default serializer renders the snapshot, so masked values appear as the placeholder strings.

Two ways Syrupy's extension hooks let us do this:

- Override the `serialize` method (entry point for the snapshot's serialized form).
- Or, simpler: subclass `AmberDataSerializer` and override `serialize`, then point a custom extension at it.

We'll override `serialize` on a small `AmberSnapshotExtension` subclass: take the value, recursively rewrite it (via `model_dump(mode="json")` for Pydantic models, or recursive dict/list traversal), then defer to the parent.

```python
"""Syrupy extension that masks volatile fields (ids, datetimes) for stable golden snapshots."""

from __future__ import annotations

import re
from typing import Any

from syrupy.extensions.amber import AmberSnapshotExtension

# YYYY-MM-DDTHH:MM:SS(.ffffff)?(+HH:MM|Z)? — covers Python's datetime.isoformat() output
_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?$",
)

_ID_KEY_EXACT = frozenset({"id"})
_ID_SUFFIX = "_id"


def _is_id_key(key: str) -> bool:
    return key in _ID_KEY_EXACT or key.endswith(_ID_SUFFIX)


def mask(value: Any) -> Any:
    """Recursively mask ids and ISO datetimes in dicts, lists, and strings."""
    if isinstance(value, dict):
        return {
            k: ("<INT>" if (_is_id_key(k) and isinstance(v, int)) else mask(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [mask(item) for item in value]
    if isinstance(value, str) and _ISO_DATETIME_RE.match(value):
        return "<DATETIME>"
    return value


class MaskingSnapshotExtension(AmberSnapshotExtension):
    """Syrupy extension that masks volatile fields before snapshotting."""

    def serialize(self, data: Any, **kwargs: Any) -> str:  # type: ignore[override]
        return super().serialize(mask(_to_plain(data)), **kwargs)


def _to_plain(data: Any) -> Any:
    """Convert Pydantic models to plain dicts so the mask can walk them."""
    if hasattr(data, "model_dump"):
        return data.model_dump(mode="json")
    if isinstance(data, list):
        return [_to_plain(item) for item in data]
    if isinstance(data, dict):
        return {k: _to_plain(v) for k, v in data.items()}
    return data
```

Add to `tests/conftest.py`:

```python
import pytest
from syrupy.assertion import SnapshotAssertion

from tests.fixtures.syrupy_ext import MaskingSnapshotExtension


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Override Syrupy's default snapshot with our masking extension."""
    return snapshot.use_extension(MaskingSnapshotExtension)
```

`tests/test_syrupy_masking.py`:

```python
"""Verify the masking serializer masks ids and datetimes."""

from __future__ import annotations

from datetime import UTC, datetime


def test_dict_with_id_and_datetime_is_masked(snapshot) -> None:
    payload = {
        "id": 42,
        "user_id": 7,
        "name": "static",
        "created": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC).isoformat(),
        "nested": {"item_id": 99, "label": "static"},
        "rows": [{"id": 1}, {"id": 2}],
    }
    assert payload == snapshot
```

Run the test once with `uv run pytest tests/test_syrupy_masking.py --snapshot-update` to bless the initial snapshot. The snapshot file at `tests/__snapshots__/test_syrupy_masking.ambr` MUST contain `<INT>` and `<DATETIME>` placeholders rather than `42`, `7`, `99`, `1`, `2`, or the ISO datetime string.

After blessing, the snapshot file is checked in.

**Verification:**

Run: `uv run pytest tests/test_syrupy_masking.py --snapshot-update`
Expected: creates `tests/__snapshots__/test_syrupy_masking.ambr`. Inspect the file and confirm placeholders appear instead of raw values.

Run: `uv run pytest tests/test_syrupy_masking.py`
Expected: passes (against the just-blessed snapshot).

Run: `make test`
Expected: every test passes.

**Commit:** `test(cli): add Syrupy masking extension and golden-test infrastructure`
<!-- END_TASK_10 -->

<!-- END_SUBCOMPONENT_C -->

<!-- START_TASK_11 -->
### Task 11: Final operational verification

**Type:** Infrastructure (verification only).

**Files:** none (verification gate before phase completion).

**Verification:**

Run: `make install-deps`
Expected: succeeds; `uv.lock` is consistent.

Run: `make lint`
Expected: passes (ruff check + format check both clean).

Run: `make test`
Expected: every test passes — `tests/cli/test_errors.py`, `tests/cli/test_stdin.py`, `tests/test_main.py`, `tests/test_seed.py`, `tests/test_syrupy_masking.py`, plus all existing `tests/test_db_*.py`.

Run: `uv run tm --help`
Expected: prints help text including `tm — agent-first threat-model database CLI` and the `--json/--no-json`, `-v/--verbose` flags.

Run: `uv run tm --json bogus 2>/tmp/err.json 1>/dev/null; echo "exit=$?"; cat /tmp/err.json`
Expected: prints `exit=1` followed by a parseable JSON object whose `error.code` is `user_error`.

If everything passes, the phase is done. If any check fails, fix the failing component before declaring completion (do not commit a green-but-failing state).

**Commit:** none (verification only — prior tasks already committed). If any fix-up commits are needed, use `chore(cli): phase 1 verification fix-ups`.
<!-- END_TASK_11 -->

---

## Phase 1 — Done When

- `make install-deps`, `make lint`, `make test` all pass.
- `tests/cli/test_errors.py`, `tests/cli/test_stdin.py`, `tests/test_main.py`, `tests/test_seed.py`, `tests/test_syrupy_masking.py` all green.
- `uv run tm --help` prints the new root-group help.
- A bogus subcommand emits a structured JSON error on stderr and exits with code 1.
- The `cli/` package contains `_errors.py`, `_output.py`, `_options.py`, `_stdin.py`, and an `__init__.py`. The `resolve_default_diagram_id` function is **not** present (lands in Phase 4).
- The `db_with_seed` fixture is reproducible (verified by `tests/test_seed.py`).
- The Syrupy masking extension produces snapshots with `<INT>` and `<DATETIME>` placeholders.
