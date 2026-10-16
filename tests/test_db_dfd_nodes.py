from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from tm_cli.db import (
    DataStoreNode,
    DataStoreNodeCreate,
    DataStoreNodeUpdate,
    DiagramCreate,
    DiagramRepository,
    ExternalEntityNode,
    ExternalEntityNodeCreate,
    ExternalEntityNodeUpdate,
    NodeRepository,
    ProcessNode,
    ProcessNodeCreate,
    ProcessNodeUpdate,
    connect,
)


def _make_diagram(conn: sqlite3.Connection, name: str = "d") -> int:
    return DiagramRepository(conn).create(DiagramCreate(name=name)).id


def test_create_process_node_round_trip(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        node = repo.create(
            d,
            ProcessNodeCreate(
                name="p",
                description="d",
                trust_level="admin",
                assumptions=["x", "y"],
            ),
        )
        fetched = repo.get(node.id)
    assert isinstance(fetched, ProcessNode)
    assert fetched.trust_level == "admin"
    assert fetched.assumptions == ["x", "y"]


def test_create_external_entity_node_round_trip(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        node = repo.create(
            d,
            ExternalEntityNodeCreate(
                name="user",
                description="d",
                entity_type="user",
                out_of_scope=True,
            ),
        )
        fetched = repo.get(node.id)
    assert isinstance(fetched, ExternalEntityNode)
    assert fetched.out_of_scope is True


def test_create_data_store_node_round_trip(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        node = repo.create(
            d,
            DataStoreNodeCreate(
                name="s",
                description="d",
                storage_type="cache",
                contains_pii=False,
                encryption_at_rest=True,
            ),
        )
        fetched = repo.get(node.id)
    assert isinstance(fetched, DataStoreNode)
    assert fetched.storage_type == "cache"
    assert fetched.contains_pii is False
    assert fetched.encryption_at_rest is True


def test_assumptions_round_trips_empty_and_unicode(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        empty = repo.create(
            d,
            ProcessNodeCreate(
                name="p", description="d", trust_level="public", assumptions=[]
            ),
        )
        unicode_node = repo.create(
            d,
            ProcessNodeCreate(
                name="p2",
                description="d",
                trust_level="public",
                assumptions=["café", "🛡 boundary", "newline\nhere"],
            ),
        )
        empty_fetched = repo.get(empty.id)
        unicode_fetched = repo.get(unicode_node.id)
    assert isinstance(empty_fetched, ProcessNode)
    assert empty_fetched.assumptions == []
    assert isinstance(unicode_fetched, ProcessNode)
    assert unicode_fetched.assumptions == ["café", "🛡 boundary", "newline\nhere"]


def test_update_process_node(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        node = repo.create(
            d,
            ProcessNodeCreate(
                name="p",
                description="d",
                trust_level="public",
                assumptions=["a"],
            ),
        )
        updated = repo.update(
            node.id,
            ProcessNodeUpdate(name="renamed", assumptions=["b", "c"]),
        )
    assert isinstance(updated, ProcessNode)
    assert updated.name == "renamed"
    assert updated.assumptions == ["b", "c"]
    assert updated.trust_level == "public"


def test_update_with_mismatched_variant_raises(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        node = repo.create(
            d,
            ProcessNodeCreate(
                name="p", description="d", trust_level="public", assumptions=[]
            ),
        )
        with pytest.raises(ValueError):
            repo.update(node.id, DataStoreNodeUpdate(storage_type="cache"))


def test_update_returns_none_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        assert NodeRepository(conn).update(999, ProcessNodeUpdate(name="n")) is None


def test_list_filters_by_type_and_diagram(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        repo = NodeRepository(conn)
        a_proc = repo.create(
            d_a,
            ProcessNodeCreate(
                name="ap", description="d", trust_level="public", assumptions=[]
            ),
        )
        a_ext = repo.create(
            d_a,
            ExternalEntityNodeCreate(name="ae", description="d", entity_type="user"),
        )
        repo.create(
            d_b,
            ProcessNodeCreate(
                name="bp", description="d", trust_level="public", assumptions=[]
            ),
        )

        a_all = repo.list(d_a)
        assert {n.id for n in a_all} == {a_proc.id, a_ext.id}

        a_processes = repo.list(d_a, type="process")
        assert [n.id for n in a_processes] == [a_proc.id]

        b_externals = repo.list(d_b, type="external_entity")
        assert b_externals == []


def test_pydantic_rejects_unknown_node_type() -> None:
    with pytest.raises(ValidationError):
        ProcessNodeCreate(
            name="x",
            description="d",
            trust_level="bogus",  # type: ignore[arg-type]
            assumptions=[],
        )


def test_sql_check_rejects_process_without_trust_level(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        cursor = conn.execute(
            "INSERT INTO entity (diagram_id, kind) VALUES (?, 'node')",
            (d,),
        )
        new_id = cursor.lastrowid
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO node (id, type, name, description) "
                "VALUES (?, 'process', ?, ?)",
                (new_id, "p", "d"),
            )


def test_sql_check_rejects_cross_variant_columns(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        cursor = conn.execute(
            "INSERT INTO entity (diagram_id, kind) VALUES (?, 'node')",
            (d,),
        )
        new_id = cursor.lastrowid
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO node "
                "(id, type, name, description, trust_level, assumptions, "
                "entity_type) "
                "VALUES (?, 'process', ?, ?, ?, ?, ?)",
                (new_id, "p", "d", "public", "[]", "user"),
            )


def test_delete_removes_entity_row_too(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        node = repo.create(
            d,
            ProcessNodeCreate(
                name="p", description="d", trust_level="public", assumptions=[]
            ),
        )
        assert repo.delete(node.id) is True

        node_count = conn.execute(
            "SELECT COUNT(*) FROM node WHERE id = ?", (node.id,)
        ).fetchone()[0]
        entity_count = conn.execute(
            "SELECT COUNT(*) FROM entity WHERE id = ?", (node.id,)
        ).fetchone()[0]
        assert node_count == 0
        assert entity_count == 0


def test_delete_returns_false_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        assert NodeRepository(conn).delete(999) is False


def test_update_external_entity_out_of_scope_round_trip(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        node = repo.create(
            d,
            ExternalEntityNodeCreate(
                name="u", description="d", entity_type="user", out_of_scope=False
            ),
        )
        updated = repo.update(
            node.id,
            ExternalEntityNodeUpdate(out_of_scope=True),
        )
    assert isinstance(updated, ExternalEntityNode)
    assert updated.out_of_scope is True


def test_search_no_args_returns_all_in_diagram(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        a = repo.create(
            d,
            ProcessNodeCreate(name="proc", description="x", trust_level="admin"),
        )
        b = repo.create(
            d,
            ExternalEntityNodeCreate(name="user", description="x", entity_type="user"),
        )
        assert [n.id for n in repo.search(d)] == [a.id, b.id]


def test_search_text_matches_name_description_assumptions(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        by_name = repo.create(
            d,
            ProcessNodeCreate(
                name="payments-service", description="x", trust_level="admin"
            ),
        )
        by_desc = repo.create(
            d,
            ProcessNodeCreate(
                name="other",
                description="handles payments",
                trust_level="admin",
            ),
        )
        by_assumption = repo.create(
            d,
            ProcessNodeCreate(
                name="other2",
                description="x",
                trust_level="admin",
                assumptions=["only payments allowed"],
            ),
        )
        repo.create(
            d,
            ProcessNodeCreate(name="orders", description="x", trust_level="admin"),
        )

        ids = {n.id for n in repo.search(d, text="payments")}
        assert ids == {by_name.id, by_desc.id, by_assumption.id}


def test_search_combines_text_and_type_filter(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        target = repo.create(
            d,
            ProcessNodeCreate(
                name="payments-worker", description="x", trust_level="admin"
            ),
        )
        repo.create(
            d,
            ExternalEntityNodeCreate(
                name="payments-user", description="x", entity_type="user"
            ),
        )
        hits = repo.search(d, text="payments", type="process")
        assert [n.id for n in hits] == [target.id]


def test_search_case_insensitive(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        n = repo.create(
            d,
            ProcessNodeCreate(name="mixedcase", description="x", trust_level="admin"),
        )
        assert [r.id for r in repo.search(d, text="MixedCase")] == [n.id]


def test_search_escapes_wildcards(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        target = repo.create(
            d,
            ProcessNodeCreate(
                name="success-target", description="100% success", trust_level="admin"
            ),
        )
        decoy = repo.create(
            d,
            ProcessNodeCreate(
                name="success-decoy", description="100x success", trust_level="admin"
            ),
        )
        ids = {n.id for n in repo.search(d, text="100%")}
        assert target.id in ids
        assert decoy.id not in ids


def test_search_diagram_scope_isolated(db_path: Path) -> None:
    with connect() as conn:
        d1 = _make_diagram(conn, "d1")
        d2 = _make_diagram(conn, "d2")
        repo = NodeRepository(conn)
        in_d1 = repo.create(
            d1,
            ProcessNodeCreate(name="payments", description="x", trust_level="admin"),
        )
        repo.create(
            d2,
            ProcessNodeCreate(name="payments", description="x", trust_level="admin"),
        )
        hits = repo.search(d1, text="payments")
        assert [n.id for n in hits] == [in_d1.id]


def test_search_pagination(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = NodeRepository(conn)
        ids = [
            repo.create(
                d,
                ProcessNodeCreate(name="hit", description="x", trust_level="admin"),
            ).id
            for _ in range(4)
        ]
        page1 = repo.search(d, text="hit", limit=2)
        page2 = repo.search(d, text="hit", limit=2, offset=2)
        assert [n.id for n in page1] == ids[:2]
        assert [n.id for n in page2] == ids[2:]
