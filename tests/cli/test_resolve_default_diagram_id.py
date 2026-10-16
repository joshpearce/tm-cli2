"""Unit tests for resolve_default_diagram_id resolver."""

from __future__ import annotations

import pytest

from tm_cli.cli._errors import NotFoundError, UserError
from tm_cli.cli._options import resolve_default_diagram_id
from tm_cli.db import DiagramCreate, DiagramRepository, connect


def test_explicit_id_returns_id_when_exists(db_path) -> None:
    """If explicit_id is provided and diagram exists, return that id."""
    with connect(db_path) as conn:
        repo = DiagramRepository(conn)
        created = repo.create(DiagramCreate(name="test"))
        result = resolve_default_diagram_id(conn, created.id, create_if_missing=False)
    assert result == created.id


def test_explicit_id_raises_not_found_when_missing(db_path) -> None:
    """If explicit_id is provided but diagram does not exist, raise NotFoundError."""
    with connect(db_path) as conn:
        with pytest.raises(NotFoundError):
            resolve_default_diagram_id(conn, 999, create_if_missing=False)


def test_no_explicit_no_default_no_create_returns_none(db_path) -> None:
    """If no explicit_id, no default diagram exists, and create_if_missing=False, return None."""  # noqa: E501
    with connect(db_path) as conn:
        result = resolve_default_diagram_id(conn, None, create_if_missing=False)
    assert result is None


def test_no_explicit_no_default_with_create_creates_and_returns_id(db_path) -> None:
    """If no explicit_id, no default diagram exists, and create_if_missing=True, create and return its id."""  # noqa: E501
    with connect(db_path) as conn:
        created_id = resolve_default_diagram_id(conn, None, create_if_missing=True)
        assert created_id is not None
        diagram = DiagramRepository(conn).get(created_id)
    assert diagram is not None
    assert diagram.name == "default"


def test_no_explicit_default_exists_returns_default_id(db_path) -> None:
    """If no explicit_id and a default diagram exists, return its id (regardless of create_if_missing)."""  # noqa: E501
    with connect(db_path) as conn:
        repo = DiagramRepository(conn)
        default = repo.create(DiagramCreate(name="default"))
        result_no_create = resolve_default_diagram_id(
            conn,
            None,
            create_if_missing=False,
        )
        result_with_create = resolve_default_diagram_id(
            conn,
            None,
            create_if_missing=True,
        )
    assert result_no_create == default.id
    assert result_with_create == default.id


def test_two_default_diagrams_lowest_id_wins(db_path) -> None:
    """If multiple diagrams named 'default' exist, return the lowest id."""
    with connect(db_path) as conn:
        repo = DiagramRepository(conn)
        first = repo.create(DiagramCreate(name="default"))
        second = repo.create(DiagramCreate(name="default"))
        result = resolve_default_diagram_id(conn, None, create_if_missing=False)
    assert result == first.id
    assert first.id < second.id


def test_no_explicit_only_other_named_diagrams_no_create(db_path) -> None:
    """If no explicit_id, only non-default diagrams exist, and create_if_missing=False, return None."""  # noqa: E501
    with connect(db_path) as conn:
        repo = DiagramRepository(conn)
        repo.create(DiagramCreate(name="non-default"))
        result = resolve_default_diagram_id(conn, None, create_if_missing=False)
    assert result is None


def test_no_explicit_only_other_named_diagrams_with_create(db_path) -> None:
    """If no explicit_id, only non-default diagrams exist, and create_if_missing=True, create a new one."""  # noqa: E501
    with connect(db_path) as conn:
        repo = DiagramRepository(conn)
        non_default = repo.create(DiagramCreate(name="non-default"))
        created_id = resolve_default_diagram_id(
            conn,
            None,
            create_if_missing=True,
        )
        assert created_id is not None
        default = repo.get(created_id)
    assert default is not None
    assert default.name == "default"
    # Verify it's a different diagram, not the non-default one.
    assert default.id != non_default.id


# ---------------------------------------------------------------------------
# TM_DIAGRAM_ID env-var fallback cases
# ---------------------------------------------------------------------------


def test_env_set_valid_id_returns_that_id(db_path, monkeypatch) -> None:
    """env set + valid existing id → returns that id (no default scan, no creation)."""
    with connect(db_path) as conn:
        repo = DiagramRepository(conn)
        created = repo.create(DiagramCreate(name="env-diagram"))
        monkeypatch.setenv("TM_DIAGRAM_ID", str(created.id))
        result = resolve_default_diagram_id(conn, None, create_if_missing=False)
        # No diagram named "default" should have been created.
        default_diagrams = [d for d in repo.list() if d.name == "default"]
    assert result == created.id
    assert default_diagrams == []


def test_env_set_missing_diagram_raises_not_found(db_path, monkeypatch) -> None:
    """env set + valid id format but missing diagram → NotFoundError with $TM_DIAGRAM_ID hint."""  # noqa: E501
    monkeypatch.setenv("TM_DIAGRAM_ID", "999")
    with connect(db_path) as conn:
        with pytest.raises(NotFoundError) as ei:
            resolve_default_diagram_id(conn, None, create_if_missing=False)
    assert "from $TM_DIAGRAM_ID" in str(ei.value)


def test_env_set_non_integer_raises_user_error(db_path, monkeypatch) -> None:
    """env set + non-integer string → UserError with TM_DIAGRAM_ID in message and hint."""  # noqa: E501
    monkeypatch.setenv("TM_DIAGRAM_ID", "not-an-int")
    with connect(db_path) as conn:
        with pytest.raises(UserError) as ei:
            resolve_default_diagram_id(conn, None, create_if_missing=False)
    assert "TM_DIAGRAM_ID" in str(ei.value)
    assert "Unset TM_DIAGRAM_ID" in (ei.value.hint or "")


def test_env_set_explicit_id_wins(db_path, monkeypatch) -> None:
    """env set + explicit --diagram-id also set → explicit id wins, env var is ignored."""  # noqa: E501
    with connect(db_path) as conn:
        repo = DiagramRepository(conn)
        diagram_a = repo.create(DiagramCreate(name="diagram-a"))
        diagram_b = repo.create(DiagramCreate(name="diagram-b"))
        monkeypatch.setenv("TM_DIAGRAM_ID", str(diagram_b.id))
        result = resolve_default_diagram_id(conn, diagram_a.id, create_if_missing=False)
    assert result == diagram_a.id


def test_env_unset_existing_behavior_unchanged(db_path, monkeypatch) -> None:
    """env unset → default-creation path still works (regression pin)."""
    monkeypatch.delenv("TM_DIAGRAM_ID", raising=False)
    with connect(db_path) as conn:
        created_id = resolve_default_diagram_id(conn, None, create_if_missing=True)
        assert created_id is not None
        diagram = DiagramRepository(conn).get(created_id)
    assert diagram is not None
    assert diagram.name == "default"


def test_env_set_empty_string_treated_as_unset(db_path, monkeypatch) -> None:
    """env set to empty string → treated as unset; default diagram is auto-created."""
    monkeypatch.setenv("TM_DIAGRAM_ID", "")
    with connect(db_path) as conn:
        created_id = resolve_default_diagram_id(conn, None, create_if_missing=True)
        assert created_id is not None
        diagram = DiagramRepository(conn).get(created_id)
    assert diagram is not None
    assert diagram.name == "default"
