"""Unit tests for stdin JSON reader."""

from __future__ import annotations

import io

import click
import pytest

from tm_cli.cli._stdin import enforce_stdin_exclusive, read_json_stdin


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


def test_stdin_false_is_noop() -> None:
    enforce_stdin_exclusive(False, {"title": "x"})


def test_stdin_true_with_no_named_flags_passes() -> None:
    enforce_stdin_exclusive(True, {"title": None, "author": None})


def test_stdin_true_with_named_flag_raises() -> None:
    with pytest.raises(click.UsageError, match="--title"):
        enforce_stdin_exclusive(True, {"title": "x", "author": None})


def test_message_lists_all_offending_flags() -> None:
    with pytest.raises(click.UsageError) as exc_info:
        enforce_stdin_exclusive(True, {"title": "x", "author": "y"})
    msg = str(exc_info.value)
    assert "--title" in msg and "--author" in msg
