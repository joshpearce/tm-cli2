from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from tm_cli.db import (
    DataItemCreate,
    DataItemRepository,
    DiagramCreate,
    DiagramRepository,
    NodeRepository,
    ProcessNodeCreate,
    ValidationFindingCreate,
    ValidationFindingRepository,
    ValidationFindingUpdate,
    connect,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_diagram(conn: sqlite3.Connection, name: str = "d") -> int:
    return DiagramRepository(conn).create(DiagramCreate(name=name)).id


def _make_node(conn: sqlite3.Connection, diagram_id: int, name: str = "n") -> int:
    return (
        NodeRepository(conn)
        .create(
            diagram_id,
            ProcessNodeCreate(
                name=name, description="d", trust_level="public", assumptions=[]
            ),
        )
        .id
    )


def _make_finding(
    conn: sqlite3.Connection,
    diagram_id: int,
    *,
    severity: str = "error",
    message: str = "msg",
    source: str = "src",
    entity_id: int | None = None,
    code: str | None = None,
) -> int:
    return (
        ValidationFindingRepository(conn)
        .create(
            diagram_id,
            ValidationFindingCreate(
                severity=severity,  # type: ignore[arg-type]
                message=message,
                source=source,
                entity_id=entity_id,
                code=code,
            ),
        )
        .id
    )


# ---------------------------------------------------------------------------
# CRUD basics
# ---------------------------------------------------------------------------


def test_create_minimal(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        finding = ValidationFindingRepository(conn).create(
            d,
            ValidationFindingCreate(
                severity="error", message="something bad", source="linter"
            ),
        )
    assert finding.severity == "error"
    assert finding.message == "something bad"
    assert finding.source == "linter"
    assert finding.entity_id is None
    assert finding.code is None
    assert isinstance(finding.created, datetime)


def test_create_with_entity_id(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_node(conn, d)
        finding = ValidationFindingRepository(conn).create(
            d,
            ValidationFindingCreate(
                severity="warning", message="check this", source="rules", entity_id=node
            ),
        )
    assert finding.entity_id == node


def test_create_with_code(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        finding = ValidationFindingRepository(conn).create(
            d,
            ValidationFindingCreate(
                severity="error", message="msg", source="src", code="ERR001"
            ),
        )
    assert finding.code == "ERR001"


def test_get_returns_none_for_unknown(db_path: Path) -> None:
    with connect() as conn:
        result = ValidationFindingRepository(conn).get(999)
    assert result is None


def test_get_round_trip(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_node(conn, d)
        repo = ValidationFindingRepository(conn)
        created = repo.create(
            d,
            ValidationFindingCreate(
                severity="warning",
                message="round trip",
                source="checker",
                entity_id=node,
                code="W42",
            ),
        )
        fetched = repo.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.diagram_id == d
    assert fetched.entity_id == node
    assert fetched.severity == "warning"
    assert fetched.message == "round trip"
    assert fetched.source == "checker"
    assert fetched.code == "W42"
    assert isinstance(fetched.created, datetime)


# ---------------------------------------------------------------------------
# Same-diagram entity validation
# ---------------------------------------------------------------------------


def test_create_rejects_cross_diagram_entity(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        node_a = _make_node(conn, d_a)
        with pytest.raises(ValueError):
            ValidationFindingRepository(conn).create(
                d_b,
                ValidationFindingCreate(
                    severity="error",
                    message="msg",
                    source="src",
                    entity_id=node_a,
                ),
            )


def test_create_rejects_nonexistent_entity(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        with pytest.raises(ValueError):
            ValidationFindingRepository(conn).create(
                d,
                ValidationFindingCreate(
                    severity="error", message="msg", source="src", entity_id=9999
                ),
            )


def test_create_accepts_any_entity_kind(db_path: Path) -> None:
    """entity_id is not restricted to nodes — data_items work too."""
    with connect() as conn:
        d = _make_diagram(conn)
        item = DataItemRepository(conn).create(
            d, DataItemCreate(identifier="i", name="n", description="x")
        )
        finding = ValidationFindingRepository(conn).create(
            d,
            ValidationFindingCreate(
                severity="warning",
                message="data item finding",
                source="src",
                entity_id=item.id,
            ),
        )
    assert finding.entity_id == item.id


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_severity(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ValidationFindingRepository(conn)
        fid = _make_finding(conn, d, severity="error")
        updated = repo.update(fid, ValidationFindingUpdate(severity="warning"))
    assert updated is not None
    assert updated.severity == "warning"


def test_update_clears_code_with_none(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ValidationFindingRepository(conn)
        fid = _make_finding(conn, d, code="ERR001")
        updated = repo.update(fid, ValidationFindingUpdate(code=None))
    assert updated is not None
    assert updated.code is None


def test_update_returns_none_for_unknown(db_path: Path) -> None:
    with connect() as conn:
        result = ValidationFindingRepository(conn).update(
            999, ValidationFindingUpdate(message="x")
        )
    assert result is None


def test_update_no_fields_is_noop(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ValidationFindingRepository(conn)
        fid = _make_finding(conn, d, message="original", source="orig-src")
        updated = repo.update(fid, ValidationFindingUpdate())
    assert updated is not None
    assert updated.message == "original"
    assert updated.source == "orig-src"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_returns_true(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ValidationFindingRepository(conn)
        fid = _make_finding(conn, d)
        assert repo.delete(fid) is True
        assert repo.get(fid) is None


def test_delete_returns_false_for_unknown(db_path: Path) -> None:
    with connect() as conn:
        assert ValidationFindingRepository(conn).delete(999) is False


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------


def test_cascade_delete_diagram_removes_findings(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        fid = _make_finding(conn, d)
        DiagramRepository(conn).delete(d)
        count = conn.execute(
            "SELECT COUNT(*) FROM validation_finding WHERE id = ?", (fid,)
        ).fetchone()[0]
    assert count == 0


def test_cascade_delete_entity_removes_findings(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_node(conn, d)
        fid = _make_finding(conn, d, entity_id=node)
        NodeRepository(conn).delete(node)
        count = conn.execute(
            "SELECT COUNT(*) FROM validation_finding WHERE id = ?", (fid,)
        ).fetchone()[0]
    assert count == 0


def test_cascade_entity_delete_leaves_diagram_level_findings(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_node(conn, d)
        # Entity-scoped finding (tied to node)
        _make_finding(conn, d, entity_id=node)
        # Diagram-level finding (no entity_id)
        diagram_fid = _make_finding(conn, d, message="diagram-level")
        NodeRepository(conn).delete(node)
        repo = ValidationFindingRepository(conn)
        assert repo.get(diagram_fid) is not None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_scoped_by_diagram(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        fid_a = _make_finding(conn, d_a, message="in-a")
        _make_finding(conn, d_b, message="in-b")
        ids = [f.id for f in ValidationFindingRepository(conn).list(d_a)]
    assert ids == [fid_a]


def test_list_pagination(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        fids = [_make_finding(conn, d, message=f"msg{i}") for i in range(4)]
        repo = ValidationFindingRepository(conn)
        page1 = [f.id for f in repo.list(d, limit=2)]
        page2 = [f.id for f in repo.list(d, limit=2, offset=2)]
    assert page1 == fids[:2]
    assert page2 == fids[2:]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_matches_message(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        target = _make_finding(conn, d, message="missing trust boundary")
        _make_finding(conn, d, message="unrelated finding")
        hits = ValidationFindingRepository(conn).search(d, "trust")
    assert [f.id for f in hits] == [target]


def test_search_matches_code(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        target = _make_finding(conn, d, code="TRUST-001")
        _make_finding(conn, d, code=None)
        hits = ValidationFindingRepository(conn).search(d, "TRUST-001")
    assert [f.id for f in hits] == [target]


def test_search_filters_by_severity(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        err = _make_finding(conn, d, severity="error", message="err finding")
        _make_finding(conn, d, severity="warning", message="warn finding")
        hits = ValidationFindingRepository(conn).search(d, severity="error")
    assert [f.id for f in hits] == [err]


def test_search_filters_by_source(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        from_linter = _make_finding(conn, d, source="linter", message="a")
        _make_finding(conn, d, source="rules-engine", message="b")
        hits = ValidationFindingRepository(conn).search(d, source="linter")
    assert [f.id for f in hits] == [from_linter]


def test_search_combined_text_and_filters(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        match = _make_finding(conn, d, severity="error", message="flow unchecked")
        # Same text, different severity — should not appear
        _make_finding(conn, d, severity="warning", message="flow unchecked")
        # Same severity, different text — should not appear
        _make_finding(conn, d, severity="error", message="something else")
        hits = ValidationFindingRepository(conn).search(d, "flow", severity="error")
    assert [f.id for f in hits] == [match]


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


def test_clear_all(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        for i in range(3):
            _make_finding(conn, d, message=f"msg{i}")
        repo = ValidationFindingRepository(conn)
        count = repo.clear(d)
        remaining = repo.list(d)
    assert count == 3
    assert remaining == []


def test_clear_by_source(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        _make_finding(conn, d, source="linter", message="a")
        _make_finding(conn, d, source="linter", message="b")
        kept_id = _make_finding(conn, d, source="rules-engine", message="c")
        repo = ValidationFindingRepository(conn)
        count = repo.clear(d, source="linter")
        remaining = repo.list(d)
    assert count == 2
    assert [f.id for f in remaining] == [kept_id]


def test_clear_empty_diagram(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        count = ValidationFindingRepository(conn).clear(d)
    assert count == 0


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


def test_pydantic_rejects_invalid_severity() -> None:
    with pytest.raises(ValidationError):
        ValidationFindingCreate(
            severity="critical",  # type: ignore[arg-type]
            message="msg",
            source="src",
        )


def test_pydantic_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ValidationFindingCreate(
            severity="error",
            message="x",
            source="y",
            unknown_field="z",  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# for_diagram
# ---------------------------------------------------------------------------


def test_for_diagram_returns_all(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        fids = [_make_finding(conn, d, message=f"msg{i}") for i in range(5)]
        result = ValidationFindingRepository(conn).for_diagram(d)
    assert [f.id for f in result] == fids
