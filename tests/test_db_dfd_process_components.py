from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tm_cli.db import (
    DiagramCreate,
    DiagramRepository,
    NodeRepository,
    ProcessComponentCreate,
    ProcessComponentRepository,
    ProcessComponentUpdate,
    ProcessNodeCreate,
    connect,
)


def _make_diagram(conn: sqlite3.Connection, name: str = "d") -> int:
    return DiagramRepository(conn).create(DiagramCreate(name=name)).id


def _make_process_node(
    conn: sqlite3.Connection, diagram_id: int, name: str = "p"
) -> int:
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


def _make_external_entity_node(
    conn: sqlite3.Connection, diagram_id: int, name: str = "e"
) -> int:
    from tm_cli.db.dfd_models import ExternalEntityNodeCreate

    return (
        NodeRepository(conn)
        .create(
            diagram_id,
            ExternalEntityNodeCreate(
                name=name,
                description="d",
                entity_type="user",
            ),
        )
        .id
    )


def test_create(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        repo = ProcessComponentRepository(conn)
        component = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="auth-controller",
                description="Handles authentication",
                component_type="controller",
            ),
        )
    assert component.parent_process_id == node
    assert component.name == "auth-controller"
    assert component.description == "Handles authentication"
    assert component.component_type == "controller"
    assert component.id > 0


def test_get_found(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        repo = ProcessComponentRepository(conn)
        component = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="user-service",
                description="User management service",
                component_type="service",
            ),
        )
        fetched = repo.get(component.id)
    assert fetched is not None
    assert fetched.id == component.id
    assert fetched.name == "user-service"


def test_get_not_found(db_path: Path) -> None:
    with connect() as conn:
        repo = ProcessComponentRepository(conn)
        assert repo.get(999) is None


def test_update_name_description_type(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        repo = ProcessComponentRepository(conn)
        component = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="old-name",
                description="OldDesc",
                component_type="filter",
            ),
        )
        updated = repo.update(
            component.id,
            ProcessComponentUpdate(
                name="new-name",
                description="NewDesc",
                component_type="handler",
            ),
        )
    assert updated is not None
    assert updated.name == "new-name"
    assert updated.description == "NewDesc"
    assert updated.component_type == "handler"
    assert updated.parent_process_id == node


def test_update_parent_process_id(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node1 = _make_process_node(conn, d, "p1")
        node2 = _make_process_node(conn, d, "p2")
        repo = ProcessComponentRepository(conn)
        component = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node1,
                name="component",
                description="d",
                component_type="repository",
            ),
        )
        updated = repo.update(
            component.id,
            ProcessComponentUpdate(parent_process_id=node2),
        )
    assert updated is not None
    assert updated.parent_process_id == node2


def test_update_parent_process_id_to_none_raises(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        repo = ProcessComponentRepository(conn)
        component = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="component",
                description="d",
                component_type="utility",
            ),
        )
        with pytest.raises(ValueError, match="parent_process_id cannot be set to None"):
            repo.update(
                component.id,
                ProcessComponentUpdate(parent_process_id=None),
            )


def test_update_non_existent(db_path: Path) -> None:
    with connect() as conn:
        repo = ProcessComponentRepository(conn)
        result = repo.update(999, ProcessComponentUpdate(name="new-name"))
    assert result is None


def test_delete(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        repo = ProcessComponentRepository(conn)
        component = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="component",
                description="d",
                component_type="client",
            ),
        )
        assert repo.delete(component.id) is True
        assert repo.get(component.id) is None
        assert repo.delete(component.id) is False


def test_list(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        node_a = _make_process_node(conn, d_a)
        node_b = _make_process_node(conn, d_b)
        repo = ProcessComponentRepository(conn)
        c1 = repo.create(
            d_a,
            ProcessComponentCreate(
                parent_process_id=node_a,
                name="c1",
                description="d",
                component_type="handler",
            ),
        )
        c2 = repo.create(
            d_a,
            ProcessComponentCreate(
                parent_process_id=node_a,
                name="c2",
                description="d",
                component_type="service",
            ),
        )
        repo.create(
            d_b,
            ProcessComponentCreate(
                parent_process_id=node_b,
                name="c3",
                description="d",
                component_type="filter",
            ),
        )
        assert [c.id for c in repo.list(d_a)] == [c1.id, c2.id]


def test_search_no_args_returns_all_in_diagram(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        repo = ProcessComponentRepository(conn)
        c1 = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="a",
                description="d",
                component_type="controller",
            ),
        )
        c2 = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="b",
                description="d",
                component_type="service",
            ),
        )
        assert [c.id for c in repo.search(d)] == [c1.id, c2.id]


def test_search_matches_name_description(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        repo = ProcessComponentRepository(conn)
        by_name = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="payments-controller",
                description="x",
                component_type="controller",
            ),
        )
        by_desc = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="x",
                description="handles payments processing",
                component_type="service",
            ),
        )
        repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="x",
                description="x",
                component_type="filter",
            ),
        )

        ids = {c.id for c in repo.search(d, text="payments")}
        assert ids == {by_name.id, by_desc.id}


def test_search_with_component_type_filter(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        repo = ProcessComponentRepository(conn)
        service = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="payments",
                description="d",
                component_type="service",
            ),
        )
        repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="payments",
                description="d",
                component_type="controller",
            ),
        )
        hits = repo.search(d, text="payments", component_type="service")
        assert [c.id for c in hits] == [service.id]


def test_search_with_parent_process_id_filter(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_a = _make_process_node(conn, d, "a")
        node_b = _make_process_node(conn, d, "b")
        repo = ProcessComponentRepository(conn)
        on_a = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node_a,
                name="payments",
                description="d",
                component_type="service",
            ),
        )
        repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node_b,
                name="payments",
                description="d",
                component_type="service",
            ),
        )
        hits = repo.search(d, text="payments", parent_process_id=node_a)
        assert [c.id for c in hits] == [on_a.id]


def test_create_with_non_process_parent_raises(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        entity = _make_external_entity_node(conn, d)
        repo = ProcessComponentRepository(conn)
        with pytest.raises(
            ValueError, match=f"parent_process_id {entity} is not a process node"
        ):
            repo.create(
                d,
                ProcessComponentCreate(
                    parent_process_id=entity,
                    name="component",
                    description="d",
                    component_type="handler",
                ),
            )


def test_create_with_non_existent_parent_raises(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        repo = ProcessComponentRepository(conn)
        with pytest.raises(ValueError, match="parent_process_id 999 is not a node"):
            repo.create(
                d,
                ProcessComponentCreate(
                    parent_process_id=999,
                    name="component",
                    description="d",
                    component_type="interceptor",
                ),
            )


def test_cascade_delete_via_parent_process_node(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        repo = ProcessComponentRepository(conn)
        component = repo.create(
            d,
            ProcessComponentCreate(
                parent_process_id=node,
                name="component",
                description="d",
                component_type="configuration",
            ),
        )
        # Delete the parent process node
        NodeRepository(conn).delete(node)
        # Verify the component is also deleted
        assert repo.get(component.id) is None
        # Verify the entity row is gone
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM entity WHERE id = ?", (component.id,)
            ).fetchone()[0]
            == 0
        )
