from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tm_cli.db import (
    ContainerRepository,
    ContainerVariant,
    ContainerVariantCreate,
    ContainerVariantUpdate,
    DataFlowCreate,
    DataFlowRepository,
    DataItemCreate,
    DataItemRepository,
    DiagramCreate,
    DiagramRepository,
    NodeRepository,
    ProcessNodeCreate,
    TrustBoundary,
    TrustBoundaryCreate,
    TrustBoundaryUpdate,
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


def test_create_trust_boundary_and_container(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        tb = repo.create(
            d,
            TrustBoundaryCreate(name="tb", description="x", privilege_level="dmz"),
        )
        cv = repo.create(
            d,
            ContainerVariantCreate(name="cv", description="x"),
        )
    assert isinstance(tb, TrustBoundary)
    assert tb.privilege_level == "dmz"
    assert isinstance(cv, ContainerVariant)


def test_get_round_trip(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        tb = repo.create(
            d,
            TrustBoundaryCreate(
                name="tb", description="x", privilege_level="restricted"
            ),
        )
        fetched = repo.get(tb.id)
    assert isinstance(fetched, TrustBoundary)
    assert fetched.privilege_level == "restricted"


def test_update_trust_boundary(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        tb = repo.create(
            d,
            TrustBoundaryCreate(name="tb", description="x", privilege_level="internet"),
        )
        updated = repo.update(
            tb.id,
            TrustBoundaryUpdate(privilege_level="corporate", name="renamed"),
        )
    assert isinstance(updated, TrustBoundary)
    assert updated.privilege_level == "corporate"
    assert updated.name == "renamed"


def test_update_with_mismatched_variant_raises(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        tb = repo.create(
            d,
            TrustBoundaryCreate(name="tb", description="x", privilege_level="dmz"),
        )
        with pytest.raises(ValueError):
            repo.update(tb.id, ContainerVariantUpdate(name="oops"))


def test_sql_check_rejects_trust_boundary_without_privilege(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        cursor = conn.execute(
            "INSERT INTO entity (diagram_id, kind) VALUES (?, 'container')",
            (d,),
        )
        new_id = cursor.lastrowid
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO container (id, type, name, description) "
                "VALUES (?, 'trust_boundary', ?, ?)",
                (new_id, "tb", "d"),
            )


def test_sql_check_rejects_container_with_privilege(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        cursor = conn.execute(
            "INSERT INTO entity (diagram_id, kind) VALUES (?, 'container')",
            (d,),
        )
        new_id = cursor.lastrowid
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO container "
                "(id, type, name, description, privilege_level) "
                "VALUES (?, 'container', ?, ?, ?)",
                (new_id, "cv", "d", "dmz"),
            )


def test_set_parent_round_trip(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        boundary = repo.create(
            d, TrustBoundaryCreate(name="b", description="x", privilege_level="dmz")
        )
        inner = repo.create(d, ContainerVariantCreate(name="i", description="x"))
        node_id = _make_node(conn, d)

        repo.set_parent(inner.id, boundary.id)
        repo.set_parent(node_id, inner.id)

        assert repo.parent_of(inner.id).id == boundary.id  # type: ignore[union-attr]
        assert repo.parent_of(node_id).id == inner.id  # type: ignore[union-attr]
        children = repo.children_of(inner.id)
        assert [c.id for c in children] == [node_id]


def test_set_parent_rejects_cross_diagram(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        repo = ContainerRepository(conn)
        a_container = repo.create(
            d_a, ContainerVariantCreate(name="x", description="x")
        )
        b_node = _make_node(conn, d_b)
        with pytest.raises(ValueError):
            repo.set_parent(b_node, a_container.id)


def test_set_parent_rejects_cycle(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        a = repo.create(d, ContainerVariantCreate(name="a", description="x"))
        b = repo.create(d, ContainerVariantCreate(name="b", description="x"))
        repo.set_parent(a.id, b.id)
        with pytest.raises(ValueError):
            repo.set_parent(b.id, a.id)


def test_set_parent_rejects_self_parent(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        a = repo.create(d, ContainerVariantCreate(name="a", description="x"))
        with pytest.raises(ValueError):
            repo.set_parent(a.id, a.id)


def test_set_parent_rejects_flow_or_item_as_child(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        nr = NodeRepository(conn)
        n1 = nr.create(
            d,
            ProcessNodeCreate(
                name="n1", description="d", trust_level="public", assumptions=[]
            ),
        )
        n2 = nr.create(
            d,
            ProcessNodeCreate(
                name="n2", description="d", trust_level="public", assumptions=[]
            ),
        )
        flow = DataFlowRepository(conn).create(
            d,
            DataFlowCreate(
                node1_id=n1.id,
                node2_id=n2.id,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        item = DataItemRepository(conn).create(
            d, DataItemCreate(identifier="i", name="n", description="d")
        )
        cr = ContainerRepository(conn)
        boundary = cr.create(
            d, TrustBoundaryCreate(name="b", description="x", privilege_level="dmz")
        )
        with pytest.raises(ValueError):
            cr.set_parent(flow.id, boundary.id)
        with pytest.raises(ValueError):
            cr.set_parent(item.id, boundary.id)


def test_set_parent_replaces_existing(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        p1 = repo.create(d, ContainerVariantCreate(name="p1", description="x"))
        p2 = repo.create(d, ContainerVariantCreate(name="p2", description="x"))
        node_id = _make_node(conn, d)
        repo.set_parent(node_id, p1.id)
        repo.set_parent(node_id, p2.id)
        # Exactly one row in container_membership for this child
        rows = conn.execute(
            "SELECT parent_id FROM container_membership WHERE child_id = ?",
            (node_id,),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["parent_id"] == p2.id


def test_clear_parent_idempotent(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        p = repo.create(d, ContainerVariantCreate(name="p", description="x"))
        node_id = _make_node(conn, d)
        repo.set_parent(node_id, p.id)
        assert repo.clear_parent(node_id) is True
        assert repo.clear_parent(node_id) is False
        assert repo.parent_of(node_id) is None


def test_delete_container_cascades_membership(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        p = repo.create(d, ContainerVariantCreate(name="p", description="x"))
        node_id = _make_node(conn, d)
        repo.set_parent(node_id, p.id)
        assert repo.delete(p.id) is True
        # membership row gone, node still exists
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM container_membership WHERE child_id = ?",
                (node_id,),
            ).fetchone()[0]
            == 0
        )
        assert NodeRepository(conn).get(node_id) is not None


def test_list_filters_by_diagram(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        repo = ContainerRepository(conn)
        a1 = repo.create(d_a, ContainerVariantCreate(name="a1", description="x"))
        repo.create(d_b, ContainerVariantCreate(name="b1", description="x"))
        a_list = repo.list(d_a)
        assert [c.id for c in a_list] == [a1.id]


def test_search_no_args_returns_all_in_diagram(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        a = repo.create(d, ContainerVariantCreate(name="a", description="x"))
        b = repo.create(
            d, TrustBoundaryCreate(name="b", description="x", privilege_level="dmz")
        )
        assert [c.id for c in repo.search(d)] == [a.id, b.id]


def test_search_matches_name_and_description(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        target_name = repo.create(
            d, ContainerVariantCreate(name="payments-zone", description="x")
        )
        target_desc = repo.create(
            d, ContainerVariantCreate(name="other", description="payments stuff")
        )
        repo.create(d, ContainerVariantCreate(name="orders", description="x"))

        ids = {c.id for c in repo.search(d, text="payments")}
        assert ids == {target_name.id, target_desc.id}


def test_search_combines_text_and_type_filter(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        target = repo.create(
            d,
            TrustBoundaryCreate(
                name="payments-boundary", description="x", privilege_level="dmz"
            ),
        )
        repo.create(d, ContainerVariantCreate(name="payments-group", description="x"))
        hits = repo.search(d, text="payments", type="trust_boundary")
        assert [c.id for c in hits] == [target.id]


def test_search_case_insensitive(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        c = repo.create(d, ContainerVariantCreate(name="mixedcase", description="x"))
        assert [r.id for r in repo.search(d, text="MixedCase")] == [c.id]


def test_search_escapes_wildcards(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        target = repo.create(
            d, ContainerVariantCreate(name="safe-target", description="100% safe")
        )
        decoy = repo.create(
            d, ContainerVariantCreate(name="safe-decoy", description="100x safe")
        )
        ids = {c.id for c in repo.search(d, text="100%")}
        assert target.id in ids
        assert decoy.id not in ids


def test_search_diagram_scope_isolated(db_path: Path) -> None:
    with connect() as conn:
        d1 = _make_diagram(conn, "d1")
        d2 = _make_diagram(conn, "d2")
        repo = ContainerRepository(conn)
        in_d1 = repo.create(
            d1, ContainerVariantCreate(name="payments", description="x")
        )
        repo.create(d2, ContainerVariantCreate(name="payments", description="x"))
        hits = repo.search(d1, text="payments")
        assert [c.id for c in hits] == [in_d1.id]


def test_search_pagination(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ContainerRepository(conn)
        ids = [
            repo.create(d, ContainerVariantCreate(name="hit", description="x")).id
            for _ in range(4)
        ]
        page1 = repo.search(d, text="hit", limit=2)
        page2 = repo.search(d, text="hit", limit=2, offset=2)
        assert [c.id for c in page1] == ids[:2]
        assert [c.id for c in page2] == ids[2:]
