"""Unit tests for error mapping and structured JSON exit."""

from __future__ import annotations

import io
import json
import sqlite3

import click
from pydantic import BaseModel, ValidationError

from tm_cli.cli._errors import (
    ConstraintError,
    NotFoundError,
    SystemError,
    UserError,
    map_exception,
)


def _make_validation_error() -> ValidationError:
    """Create a ValidationError by deliberately failing Pydantic validation."""

    class _M(BaseModel):
        n: int

    try:
        _M(n="not an int")
    except ValidationError as e:
        return e
    raise AssertionError("ValidationError was not raised")


def test_validation_error_maps_to_user_error() -> None:
    """ValidationError should map to UserError with code 'user_error'."""
    mapped = map_exception(_make_validation_error())
    assert isinstance(mapped, UserError)
    assert mapped.exit_code == 1
    assert mapped.to_payload()["error"]["code"] == "user_error"
    # Verify message contains validation info
    assert "int" in mapped.message.lower() or "validation" in mapped.message.lower()


def test_value_error_maps_to_user_error() -> None:
    """ValueError should map to UserError."""
    exc = ValueError("self-loop")
    mapped = map_exception(exc)
    assert isinstance(mapped, UserError)
    assert mapped.exit_code == 1
    assert mapped.to_payload()["error"]["code"] == "user_error"
    assert "self-loop" in mapped.message


def test_click_usage_error_maps_to_user_error() -> None:
    """click.UsageError should map to UserError."""
    exc = click.UsageError("bad flag")
    mapped = map_exception(exc)
    assert isinstance(mapped, UserError)
    assert mapped.exit_code == 1
    assert mapped.to_payload()["error"]["code"] == "user_error"


def test_click_bad_parameter_maps_to_user_error() -> None:
    """click.BadParameter should map to UserError."""
    exc = click.BadParameter("x")
    mapped = map_exception(exc)
    assert isinstance(mapped, UserError)
    assert mapped.exit_code == 1
    assert mapped.to_payload()["error"]["code"] == "user_error"


def test_integrity_unique_maps_to_constraint() -> None:
    """IntegrityError with UNIQUE constraint maps to ConstraintError with 'unique'."""
    exc = sqlite3.IntegrityError("UNIQUE constraint failed: terms.term")
    mapped = map_exception(exc)
    assert isinstance(mapped, ConstraintError)
    assert mapped.exit_code == 3
    body = mapped.to_payload()["error"]
    assert body["code"] == "constraint_violation"
    assert body["constraint"] == "unique"


def test_integrity_foreign_key_maps_to_constraint() -> None:
    """IntegrityError with FOREIGN KEY constraint maps to ConstraintError."""
    exc = sqlite3.IntegrityError("FOREIGN KEY constraint failed")
    mapped = map_exception(exc)
    assert isinstance(mapped, ConstraintError)
    assert mapped.exit_code == 3
    body = mapped.to_payload()["error"]
    assert body["code"] == "constraint_violation"
    assert body["constraint"] == "foreign_key"


def test_integrity_check_maps_to_constraint() -> None:
    """IntegrityError with CHECK constraint maps to ConstraintError with 'check'."""
    exc = sqlite3.IntegrityError("CHECK constraint failed: ...")
    mapped = map_exception(exc)
    assert isinstance(mapped, ConstraintError)
    assert mapped.exit_code == 3
    body = mapped.to_payload()["error"]
    assert body["code"] == "constraint_violation"
    assert body["constraint"] == "check"


def test_integrity_unknown_maps_to_constraint_unknown() -> None:
    """IntegrityError with unrecognized message maps to ConstraintError."""
    exc = sqlite3.IntegrityError("garbage")
    mapped = map_exception(exc)
    assert isinstance(mapped, ConstraintError)
    assert mapped.exit_code == 3
    body = mapped.to_payload()["error"]
    assert body["code"] == "constraint_violation"
    assert body["constraint"] == "unknown"


def test_permission_error_maps_to_system_error() -> None:
    """PermissionError should map to SystemError."""
    exc = PermissionError("denied")
    mapped = map_exception(exc)
    assert isinstance(mapped, SystemError)
    assert mapped.exit_code == 4
    assert mapped.to_payload()["error"]["code"] == "system_error"


def test_oserror_maps_to_system_error() -> None:
    """OSError should map to SystemError."""
    exc = OSError("ENOENT")
    mapped = map_exception(exc)
    assert isinstance(mapped, SystemError)
    assert mapped.exit_code == 4
    assert mapped.to_payload()["error"]["code"] == "system_error"


def test_already_mapped_passthrough() -> None:
    """Pre-mapped TmError should be returned unchanged (identity check)."""
    original = NotFoundError("missing", id="42")
    mapped = map_exception(original)
    # Identity check: same object
    assert mapped is original


def test_unknown_exception_maps_to_system_error() -> None:
    """Unmapped exceptions should map to SystemError with type and message."""
    exc = RuntimeError("boom")
    mapped = map_exception(exc)
    assert isinstance(mapped, SystemError)
    assert mapped.exit_code == 4
    assert mapped.to_payload()["error"]["code"] == "system_error"
    assert "RuntimeError:" in mapped.message
    assert "boom" in mapped.message


def test_payload_includes_hint_and_input_when_provided() -> None:
    """UserError with hint and input_payload should include them in to_payload()."""
    exc = UserError("bad", hint="try foo", input_payload={"k": "v"})
    payload = exc.to_payload()["error"]
    assert "hint" in payload
    assert payload["hint"] == "try foo"
    assert "input" in payload
    assert payload["input"] == {"k": "v"}


def test_payload_is_json_serializable() -> None:
    """Any mapped error's to_payload() should be JSON-serializable."""
    errors = [
        map_exception(_make_validation_error()),
        map_exception(ValueError("test")),
        map_exception(sqlite3.IntegrityError("UNIQUE constraint failed")),
        map_exception(PermissionError("denied")),
        map_exception(RuntimeError("unknown")),
    ]
    for err in errors:
        payload = err.to_payload()
        # Should not raise
        json_str = json.dumps(payload)
        assert len(json_str) > 0


def test_show_writes_json_to_target() -> None:
    """UserError.show(file=...) should write parseable JSON to target file."""
    err = UserError("x")
    buf = io.StringIO()
    err.show(file=buf)
    output = buf.getvalue()
    payload = json.loads(output)
    assert payload["error"]["code"] == "user_error"
