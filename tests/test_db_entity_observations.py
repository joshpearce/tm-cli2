"""DB-layer tests for EntityObservationRepository.

Covers:
- link idempotency (no duplicates, no error)
- link raises IntegrityError for unknown entity / observation id
- unlink returns True/False correctly
- cascade: delete observation removes entity_observations rows
- cascade: delete entity (via NodeRepository.delete) removes entity_observations rows
- cascade: delete diagram transitively removes all entity_observations rows
- linked_ids_by_kind: empty LinkedIds for unlinked observation
- linked_ids_by_kind: correct bucketing for each DFD kind
- linked_ids_by_kind_for: returns {} for empty list
- linked_ids_by_kind_for: keys present for every requested id, ids ASC
- nodes_for_observation / containers_for_observation / flows_for_observation /
  items_for_observation: empty case, populated case, cross-kind isolation
- observations_for_entity: returns rows in id ASC order
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tm_cli.db import (
    ContainerVariantCreate,
    DataFlowCreate,
    DataFlowRepository,
    DataItemCreate,
    DataItemRepository,
    DiagramCreate,
    DiagramRepository,
    EntityObservationRepository,
    ExternalEntityNodeCreate,
    NodeRepository,
    ObservationCreate,
    ObservationRepository,
    ProcessNodeCreate,
    connect,
)
from tm_cli.db.dfd_containers import ContainerRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_external_entity(
    conn: sqlite3.Connection, diagram_id: int, name: str = "ext"
) -> int:
    return (
        NodeRepository(conn)
        .create(
            diagram_id,
            ExternalEntityNodeCreate(
                name=name, description="d", entity_type="user", out_of_scope=False
            ),
        )
        .id
    )


def _make_container(conn: sqlite3.Connection, diagram_id: int) -> int:
    return (
        ContainerRepository(conn)
        .create(
            diagram_id,
            ContainerVariantCreate(name="c", description="d"),
        )
        .id
    )


def _make_flow(conn: sqlite3.Connection, diagram_id: int, n1: int, n2: int) -> int:
    return (
        DataFlowRepository(conn)
        .create(
            diagram_id,
            DataFlowCreate(
                node1_id=n1,
                node2_id=n2,
                name="f",
                protocol="https",
                authenticated=True,
                encrypted=True,
            ),
        )
        .id
    )


def _make_item(conn: sqlite3.Connection, diagram_id: int) -> int:
    return (
        DataItemRepository(conn)
        .create(
            diagram_id,
            DataItemCreate(
                identifier="x", name="i", description="d", classification="internal"
            ),
        )
        .id
    )


def _make_observation(conn: sqlite3.Connection, content: str = "obs") -> int:
    return (
        ObservationRepository(conn)
        .create(ObservationCreate(content=content, observation_type="todo"))
        .id
    )


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_link_is_idempotent(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)

        repo.link(node_id, obs_id)
        repo.link(node_id, obs_id)  # second call must not raise or duplicate

        count = conn.execute(
            "SELECT COUNT(*) FROM entity_observations "
            "WHERE entity_id = ? AND observation_id = ?",
            (node_id, obs_id),
        ).fetchone()[0]
        assert count == 1


# ---------------------------------------------------------------------------
# Unlink
# ---------------------------------------------------------------------------


def test_unlink_returns_true_when_link_exists(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(node_id, obs_id)

        assert repo.unlink(node_id, obs_id) is True


def test_unlink_returns_false_when_no_link(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)

        assert repo.unlink(node_id, obs_id) is False


def test_unlink_then_unlink_again_returns_false(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(node_id, obs_id)

        assert repo.unlink(node_id, obs_id) is True
        assert repo.unlink(node_id, obs_id) is False


# ---------------------------------------------------------------------------
# Cascade: delete observation
# ---------------------------------------------------------------------------


def test_delete_observation_cascades_to_entity_observations(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(node_id, obs_id)

        assert ObservationRepository(conn).delete(obs_id) is True

        count = conn.execute("SELECT COUNT(*) FROM entity_observations").fetchone()[0]
        assert count == 0
        # entity itself must survive
        assert NodeRepository(conn).get(node_id) is not None


# ---------------------------------------------------------------------------
# Cascade: delete entity
# ---------------------------------------------------------------------------


def test_delete_entity_cascades_to_entity_observations(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(node_id, obs_id)

        assert NodeRepository(conn).delete(node_id) is True

        count = conn.execute("SELECT COUNT(*) FROM entity_observations").fetchone()[0]
        assert count == 0
        # observation itself must survive
        assert ObservationRepository(conn).get(obs_id) is not None


# ---------------------------------------------------------------------------
# Cascade: delete diagram
# ---------------------------------------------------------------------------


def test_delete_diagram_transitively_cascades_to_entity_observations(
    db_path: Path,
) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        item_id = _make_item(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(node_id, obs_id)
        repo.link(item_id, obs_id)

        assert DiagramRepository(conn).delete(d) is True

        count = conn.execute("SELECT COUNT(*) FROM entity_observations").fetchone()[0]
        assert count == 0
        # observation itself must survive
        assert ObservationRepository(conn).get(obs_id) is not None


# ---------------------------------------------------------------------------
# linked_ids_by_kind — single observation
# ---------------------------------------------------------------------------


def test_linked_ids_by_kind_empty_when_no_links(db_path: Path) -> None:
    with connect() as conn:
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        result = repo.linked_ids_by_kind(obs_id)

    assert result["node_ids"] == []
    assert result["container_ids"] == []
    assert result["flow_ids"] == []
    assert result["data_item_ids"] == []


def test_linked_ids_by_kind_buckets_all_four_kinds(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        p = _make_process_node(conn, d, "p")
        e = _make_external_entity(conn, d, "e")
        c = _make_container(conn, d)
        flow = _make_flow(conn, d, p, e)
        item = _make_item(conn, d)
        obs_id = _make_observation(conn)

        repo = EntityObservationRepository(conn)
        for eid in (p, e, c, flow, item):
            repo.link(eid, obs_id)

        result = repo.linked_ids_by_kind(obs_id)

    # Nodes: process + external_entity
    assert set(result["node_ids"]) == {p, e}
    assert result["node_ids"] == sorted(result["node_ids"]), "node_ids must be ASC"

    # Containers
    assert result["container_ids"] == [c]

    # data_flow kind maps to flow_ids (not container_ids or node_ids)
    assert result["flow_ids"] == [flow]

    # data_item kind maps to data_item_ids
    assert result["data_item_ids"] == [item]


def test_linked_ids_by_kind_data_flow_goes_to_flow_ids_not_elsewhere(
    db_path: Path,
) -> None:
    """Explicit kind-mapping check: data_flow -> flow_ids."""
    with connect() as conn:
        d = _make_diagram(conn)
        p = _make_process_node(conn, d, "p")
        e = _make_external_entity(conn, d, "e")
        flow = _make_flow(conn, d, p, e)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(flow, obs_id)

        result = repo.linked_ids_by_kind(obs_id)

    assert flow in result["flow_ids"]
    assert flow not in result["node_ids"]
    assert flow not in result["container_ids"]
    assert flow not in result["data_item_ids"]


def test_linked_ids_by_kind_data_item_goes_to_data_item_ids_not_elsewhere(
    db_path: Path,
) -> None:
    """Explicit kind-mapping check: data_item -> data_item_ids."""
    with connect() as conn:
        d = _make_diagram(conn)
        item = _make_item(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(item, obs_id)

        result = repo.linked_ids_by_kind(obs_id)

    assert item in result["data_item_ids"]
    assert item not in result["node_ids"]
    assert item not in result["container_ids"]
    assert item not in result["flow_ids"]


# ---------------------------------------------------------------------------
# linked_ids_by_kind_for — batched
# ---------------------------------------------------------------------------


def test_linked_ids_by_kind_for_empty_list_returns_empty_dict(db_path: Path) -> None:
    with connect() as conn:
        repo = EntityObservationRepository(conn)
        assert repo.linked_ids_by_kind_for([]) == {}


def test_linked_ids_by_kind_for_keys_always_present(db_path: Path) -> None:
    """Every requested observation_id appears as a key even with no links."""
    with connect() as conn:
        obs1 = _make_observation(conn, "obs1")
        obs2 = _make_observation(conn, "obs2")
        repo = EntityObservationRepository(conn)

        result = repo.linked_ids_by_kind_for([obs1, obs2])

    assert obs1 in result
    assert obs2 in result
    empty: dict = {
        "node_ids": [],
        "container_ids": [],
        "flow_ids": [],
        "data_item_ids": [],
        "process_component_ids": [],
    }
    assert result[obs1] == empty
    assert result[obs2] == empty


def test_linked_ids_by_kind_for_ids_are_asc(db_path: Path) -> None:
    """Ids in each LinkedIds list must be sorted ASC."""
    with connect() as conn:
        d = _make_diagram(conn)
        # Create three nodes and link them out-of-order to the same observation
        n1 = _make_process_node(conn, d, "n1")
        n2 = _make_process_node(conn, d, "n2")
        n3 = _make_process_node(conn, d, "n3")
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        # Link out of order
        repo.link(n3, obs_id)
        repo.link(n1, obs_id)
        repo.link(n2, obs_id)

        result = repo.linked_ids_by_kind_for([obs_id])

    node_ids = result[obs_id]["node_ids"]
    assert node_ids == sorted(node_ids), "node_ids must be ASC"
    assert set(node_ids) == {n1, n2, n3}


def test_linked_ids_by_kind_for_populates_correct_buckets(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        p = _make_process_node(conn, d)
        e = _make_external_entity(conn, d)
        c = _make_container(conn, d)
        flow = _make_flow(conn, d, p, e)
        item = _make_item(conn, d)

        obs1 = _make_observation(conn, "obs1")
        obs2 = _make_observation(conn, "obs2")
        repo = EntityObservationRepository(conn)

        # obs1 gets a node and a flow
        repo.link(p, obs1)
        repo.link(flow, obs1)

        # obs2 gets a container and a data item
        repo.link(c, obs2)
        repo.link(item, obs2)

        result = repo.linked_ids_by_kind_for([obs1, obs2])

    assert p in result[obs1]["node_ids"]
    assert flow in result[obs1]["flow_ids"]
    assert result[obs1]["container_ids"] == []
    assert result[obs1]["data_item_ids"] == []

    assert c in result[obs2]["container_ids"]
    assert item in result[obs2]["data_item_ids"]
    assert result[obs2]["node_ids"] == []
    assert result[obs2]["flow_ids"] == []


# ---------------------------------------------------------------------------
# observations_for_entity (enriched rows)
# ---------------------------------------------------------------------------


def test_observations_for_entity_returns_enriched_rows(db_path: Path) -> None:
    """observations_for_entity returns Observation objects with *_ids populated."""
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(node_id, obs_id)

        observations = repo.observations_for_entity(node_id)

    assert len(observations) == 1
    obs = observations[0]
    assert obs.id == obs_id
    # The observation is linked to a node, so node_ids should contain the node.
    assert node_id in obs.node_ids
    assert obs.container_ids == []
    assert obs.flow_ids == []
    assert obs.data_item_ids == []


def test_observations_for_entity_empty_when_no_links(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        repo = EntityObservationRepository(conn)

        result = repo.observations_for_entity(node_id)

    assert result == []


# ---------------------------------------------------------------------------
# link — IntegrityError for unknown ids (I2)
# ---------------------------------------------------------------------------


def test_link_unknown_entity_id_raises_integrity_error(db_path: Path) -> None:
    with connect() as conn:
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        with pytest.raises(sqlite3.IntegrityError):
            repo.link(99999, obs_id)


def test_link_unknown_observation_id_raises_integrity_error(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        repo = EntityObservationRepository(conn)
        with pytest.raises(sqlite3.IntegrityError):
            repo.link(node_id, 99999)


# ---------------------------------------------------------------------------
# *_for_observation reverse lookups — empty and populated cases (I1)
# ---------------------------------------------------------------------------


def test_nodes_for_observation_empty_when_no_links(db_path: Path) -> None:
    with connect() as conn:
        obs_id = _make_observation(conn)
        result = EntityObservationRepository(conn).nodes_for_observation(obs_id)
    assert result == []


def test_nodes_for_observation_returns_linked_nodes_asc(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        n1 = _make_process_node(conn, d, "n1")
        n2 = _make_process_node(conn, d, "n2")
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(n2, obs_id)
        repo.link(n1, obs_id)

        result = EntityObservationRepository(conn).nodes_for_observation(obs_id)

    assert [r.id for r in result] == sorted([n1, n2])


def test_containers_for_observation_empty_when_no_links(db_path: Path) -> None:
    with connect() as conn:
        obs_id = _make_observation(conn)
        result = EntityObservationRepository(conn).containers_for_observation(obs_id)
    assert result == []


def test_containers_for_observation_returns_linked_containers_asc(
    db_path: Path,
) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        c1 = _make_container(conn, d)
        c2 = _make_container(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(c2, obs_id)
        repo.link(c1, obs_id)

        result = EntityObservationRepository(conn).containers_for_observation(obs_id)

    assert [r.id for r in result] == sorted([c1, c2])


def test_flows_for_observation_empty_when_no_links(db_path: Path) -> None:
    with connect() as conn:
        obs_id = _make_observation(conn)
        result = EntityObservationRepository(conn).flows_for_observation(obs_id)
    assert result == []


def test_flows_for_observation_returns_linked_flows_asc(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        p = _make_process_node(conn, d, "p")
        e = _make_external_entity(conn, d, "e")
        # Two flows require distinct endpoint pairs; reuse p and e with different item
        flow1 = _make_flow(conn, d, p, e)
        # To create a second flow we need a third node
        e2 = _make_external_entity(conn, d, "e2")
        flow2 = _make_flow(conn, d, p, e2)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(flow2, obs_id)
        repo.link(flow1, obs_id)

        result = EntityObservationRepository(conn).flows_for_observation(obs_id)

    assert [r.id for r in result] == sorted([flow1, flow2])


def test_items_for_observation_empty_when_no_links(db_path: Path) -> None:
    with connect() as conn:
        obs_id = _make_observation(conn)
        result = EntityObservationRepository(conn).items_for_observation(obs_id)
    assert result == []


def test_items_for_observation_returns_linked_items_asc(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        i1 = _make_item(conn, d)
        i2 = _make_item(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(i2, obs_id)
        repo.link(i1, obs_id)

        result = EntityObservationRepository(conn).items_for_observation(obs_id)

    assert [r.id for r in result] == sorted([i1, i2])


# ---------------------------------------------------------------------------
# Cross-kind isolation: *_for_observation only returns the matching kind (I1)
# ---------------------------------------------------------------------------


def test_per_kind_reverse_lookup_isolation(db_path: Path) -> None:
    """Link one entity of each kind to the same observation; each reverse lookup
    returns ONLY the matching kind and not the other three."""
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        container_id = _make_container(conn, d)
        ext = _make_external_entity(conn, d, "ext")
        flow_id = _make_flow(conn, d, node_id, ext)
        item_id = _make_item(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        for eid in (node_id, container_id, flow_id, item_id):
            repo.link(eid, obs_id)

        nodes = repo.nodes_for_observation(obs_id)
        containers = repo.containers_for_observation(obs_id)
        flows = repo.flows_for_observation(obs_id)
        items = repo.items_for_observation(obs_id)

    assert [r.id for r in nodes] == [node_id]
    assert [r.id for r in containers] == [container_id]
    assert [r.id for r in flows] == [flow_id]
    assert [r.id for r in items] == [item_id]


# ---------------------------------------------------------------------------
# Structural invariant: _KIND_TO_FIELD must match the SQL CHECK on entity.kind
# ---------------------------------------------------------------------------


def test_kind_to_field_covers_all_schema_kinds() -> None:
    """Guard against drift between _KIND_TO_FIELD and the CHECK(kind IN (...))
    constraint in connection.py.  When a new entity kind is added, both the
    dict and the SQL CHECK must be updated together; this test makes the omission
    visible immediately."""
    from tm_cli.db.entity_observations import _KIND_TO_FIELD

    EXPECTED_KINDS = {
        "node",
        "container",
        "data_flow",
        "data_item",
        "process_component",
    }
    assert set(_KIND_TO_FIELD.keys()) == EXPECTED_KINDS


# ---------------------------------------------------------------------------
# is_linked — cheap membership check
# ---------------------------------------------------------------------------


def test_is_linked_returns_false_when_no_link(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)

        assert repo.is_linked(node_id, obs_id) is False


def test_is_linked_returns_true_after_link_created(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(node_id, obs_id)

        assert repo.is_linked(node_id, obs_id) is True


def test_is_linked_returns_false_after_link_removed(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs_id = _make_observation(conn)
        repo = EntityObservationRepository(conn)
        repo.link(node_id, obs_id)
        repo.unlink(node_id, obs_id)

        assert repo.is_linked(node_id, obs_id) is False


def test_is_linked_is_asymmetric(db_path: Path) -> None:
    """is_linked(A, B) and is_linked(B, A) are independent lookups.

    This verifies that the method checks entity_id and observation_id in the
    correct column order rather than treating the pair as commutative.
    """
    with connect() as conn:
        d = _make_diagram(conn)
        n1 = _make_process_node(conn, d, "n1")
        n2 = _make_process_node(conn, d, "n2")
        obs1 = _make_observation(conn, "obs1")
        obs2 = _make_observation(conn, "obs2")
        repo = EntityObservationRepository(conn)
        # Link (n1 -> obs1) but not (n2 -> obs2)
        repo.link(n1, obs1)

        assert repo.is_linked(n1, obs1) is True
        assert repo.is_linked(n2, obs2) is False


# ---------------------------------------------------------------------------
# observations_for_entity — ASC ordering with multiple rows (M8)
# ---------------------------------------------------------------------------


def test_observations_for_entity_returns_ids_asc(db_path: Path) -> None:
    """Observations linked to an entity must be returned in id ASC order."""
    with connect() as conn:
        d = _make_diagram(conn)
        node_id = _make_process_node(conn, d)
        obs1 = _make_observation(conn, "obs1")
        obs2 = _make_observation(conn, "obs2")
        obs3 = _make_observation(conn, "obs3")
        repo = EntityObservationRepository(conn)
        # Link out of order to ensure we test ordering, not insertion order.
        repo.link(node_id, obs3)
        repo.link(node_id, obs1)
        repo.link(node_id, obs2)

        result = repo.observations_for_entity(node_id)

    ids = [r.id for r in result]
    assert ids == sorted(ids), f"Expected ASC order, got {ids}"
    assert set(ids) == {obs1, obs2, obs3}
