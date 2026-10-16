from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from tm_cli.db import (
    DataItemCreate,
    DataItemRepository,
    DataItemUpdate,
    DiagramCreate,
    DiagramRepository,
    NodeRepository,
    ProcessNodeCreate,
    connect,
)


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


def test_create_default_classification(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        item = DataItemRepository(conn).create(
            d, DataItemCreate(identifier="i", name="n", description="x")
        )
    assert item.classification == "unclassified"
    assert item.parent_node_id is None


def test_create_with_parent_node(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_node(conn, d)
        item = DataItemRepository(conn).create(
            d,
            DataItemCreate(
                identifier="i",
                name="n",
                description="x",
                parent_node_id=node,
            ),
        )
    assert item.parent_node_id == node


def test_create_rejects_cross_diagram_parent(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        node_a = _make_node(conn, d_a)
        with pytest.raises(ValueError):
            DataItemRepository(conn).create(
                d_b,
                DataItemCreate(
                    identifier="i",
                    name="n",
                    description="x",
                    parent_node_id=node_a,
                ),
            )


def test_create_rejects_non_node_parent(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        first_item = DataItemRepository(conn).create(
            d, DataItemCreate(identifier="i", name="n", description="x")
        )
        with pytest.raises(ValueError):
            DataItemRepository(conn).create(
                d,
                DataItemCreate(
                    identifier="j",
                    name="n",
                    description="x",
                    parent_node_id=first_item.id,
                ),
            )


def test_get_round_trip(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = DataItemRepository(conn)
        item = repo.create(
            d,
            DataItemCreate(
                identifier="i",
                name="n",
                description="x",
                classification="secret",
            ),
        )
        fetched = repo.get(item.id)
    assert fetched is not None
    assert fetched.classification == "secret"


def test_update_can_clear_parent_node_id(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_node(conn, d)
        repo = DataItemRepository(conn)
        item = repo.create(
            d,
            DataItemCreate(
                identifier="i",
                name="n",
                description="x",
                parent_node_id=node,
            ),
        )
        cleared = repo.update(item.id, DataItemUpdate(parent_node_id=None))
    assert cleared is not None
    assert cleared.parent_node_id is None


def test_update_rejects_cross_diagram_parent(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        a_node = _make_node(conn, d_a)
        b_item = DataItemRepository(conn).create(
            d_b, DataItemCreate(identifier="i", name="n", description="x")
        )
        with pytest.raises(ValueError):
            DataItemRepository(conn).update(
                b_item.id, DataItemUpdate(parent_node_id=a_node)
            )


def test_update_returns_none_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        assert DataItemRepository(conn).update(999, DataItemUpdate(name="x")) is None


def test_parent_node_set_null_on_node_delete(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_node(conn, d)
        repo = DataItemRepository(conn)
        item = repo.create(
            d,
            DataItemCreate(
                identifier="i",
                name="n",
                description="x",
                parent_node_id=node,
            ),
        )
        NodeRepository(conn).delete(node)
        fetched = repo.get(item.id)
    assert fetched is not None
    assert fetched.parent_node_id is None


def test_pydantic_rejects_unknown_classification() -> None:
    with pytest.raises(ValidationError):
        DataItemCreate(
            identifier="i",
            name="n",
            description="x",
            classification="bogus",  # type: ignore[arg-type]
        )


def test_sql_check_rejects_unknown_classification(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        cursor = conn.execute(
            "INSERT INTO entity (diagram_id, kind) VALUES (?, 'data_item')",
            (d,),
        )
        new_id = cursor.lastrowid
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO data_item "
                "(id, identifier, name, description, classification) "
                "VALUES (?, ?, ?, ?, ?)",
                (new_id, "i", "n", "d", "bogus"),
            )


def test_delete_removes_entity_too(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = DataItemRepository(conn)
        item = repo.create(d, DataItemCreate(identifier="i", name="n", description="x"))
        assert repo.delete(item.id) is True
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM entity WHERE id = ?", (item.id,)
            ).fetchone()[0]
            == 0
        )


def test_list_scoped_by_diagram(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        repo = DataItemRepository(conn)
        a1 = repo.create(d_a, DataItemCreate(identifier="i", name="n", description="x"))
        repo.create(d_b, DataItemCreate(identifier="i", name="n", description="x"))
        assert [i.id for i in repo.list(d_a)] == [a1.id]


def test_search_no_args_returns_all_in_diagram(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = DataItemRepository(conn)
        a = repo.create(d, DataItemCreate(identifier="a", name="a", description="x"))
        b = repo.create(d, DataItemCreate(identifier="b", name="b", description="x"))
        assert [i.id for i in repo.search(d)] == [a.id, b.id]


def test_search_matches_identifier_name_description(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = DataItemRepository(conn)
        by_id = repo.create(
            d, DataItemCreate(identifier="payments-id", name="x", description="x")
        )
        by_name = repo.create(
            d, DataItemCreate(identifier="o1", name="payments-name", description="x")
        )
        by_desc = repo.create(
            d, DataItemCreate(identifier="o2", name="x", description="payments here")
        )
        repo.create(d, DataItemCreate(identifier="o3", name="x", description="x"))

        ids = {i.id for i in repo.search(d, text="payments")}
        assert ids == {by_id.id, by_name.id, by_desc.id}


def test_search_filters_by_classification(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = DataItemRepository(conn)
        secret = repo.create(
            d,
            DataItemCreate(
                identifier="s",
                name="payments-token",
                description="x",
                classification="secret",
            ),
        )
        repo.create(
            d,
            DataItemCreate(
                identifier="p",
                name="payments-public",
                description="x",
                classification="public",
            ),
        )
        hits = repo.search(d, text="payments", classification="secret")
        assert [i.id for i in hits] == [secret.id]


def test_search_filters_by_parent_node(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_a = _make_node(conn, d, "a")
        node_b = _make_node(conn, d, "b")
        repo = DataItemRepository(conn)
        on_a = repo.create(
            d,
            DataItemCreate(
                identifier="x",
                name="payments",
                description="x",
                parent_node_id=node_a,
            ),
        )
        repo.create(
            d,
            DataItemCreate(
                identifier="y",
                name="payments",
                description="x",
                parent_node_id=node_b,
            ),
        )
        repo.create(d, DataItemCreate(identifier="z", name="payments", description="x"))
        hits = repo.search(d, text="payments", parent_node_id=node_a)
        assert [i.id for i in hits] == [on_a.id]


def test_search_case_insensitive(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = DataItemRepository(conn)
        item = repo.create(
            d, DataItemCreate(identifier="i", name="mixedcase", description="x")
        )
        assert [r.id for r in repo.search(d, text="MixedCase")] == [item.id]


def test_search_escapes_wildcards(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = DataItemRepository(conn)
        target = repo.create(
            d,
            DataItemCreate(identifier="i", name="safe-target", description="100% safe"),
        )
        decoy = repo.create(
            d,
            DataItemCreate(identifier="j", name="safe-decoy", description="100x safe"),
        )
        ids = {i.id for i in repo.search(d, text="100%")}
        assert target.id in ids
        assert decoy.id not in ids


def test_search_diagram_scope_isolated(db_path: Path) -> None:
    with connect() as conn:
        d1 = _make_diagram(conn, "d1")
        d2 = _make_diagram(conn, "d2")
        repo = DataItemRepository(conn)
        in_d1 = repo.create(
            d1, DataItemCreate(identifier="i", name="payments", description="x")
        )
        repo.create(
            d2, DataItemCreate(identifier="i", name="payments", description="x")
        )
        hits = repo.search(d1, text="payments")
        assert [i.id for i in hits] == [in_d1.id]


def test_search_pagination(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = DataItemRepository(conn)
        ids = [
            repo.create(
                d, DataItemCreate(identifier=f"i{i}", name="hit", description="x")
            ).id
            for i in range(4)
        ]
        page1 = repo.search(d, text="hit", limit=2)
        page2 = repo.search(d, text="hit", limit=2, offset=2)
        assert [i.id for i in page1] == ids[:2]
        assert [i.id for i in page2] == ids[2:]
