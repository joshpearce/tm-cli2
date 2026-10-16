from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tm_cli.db import (
    DataFlowCreate,
    DataFlowRepository,
    DataFlowUpdate,
    DataItemCreate,
    DataItemRepository,
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


def test_create_canonicalizes_endpoints(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        # pass them in reverse order
        flow = DataFlowRepository(conn).create(
            d,
            DataFlowCreate(
                node1_id=b,
                node2_id=a,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
    assert flow.node1_id < flow.node2_id
    assert {flow.node1_id, flow.node2_id} == {a, b}


def test_create_rejects_self_loop(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d)
        with pytest.raises(ValueError):
            DataFlowRepository(conn).create(
                d,
                DataFlowCreate(
                    node1_id=a,
                    node2_id=a,
                    name="f",
                    protocol="tcp",
                    authenticated=False,
                    encrypted=False,
                ),
            )


def test_create_rejects_cross_diagram_endpoints(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        a_node = _make_node(conn, d_a)
        b_node = _make_node(conn, d_b)
        with pytest.raises(ValueError):
            DataFlowRepository(conn).create(
                d_a,
                DataFlowCreate(
                    node1_id=a_node,
                    node2_id=b_node,
                    name="f",
                    protocol="tcp",
                    authenticated=False,
                    encrypted=False,
                ),
            )


def test_sql_check_rejects_non_canonical_endpoints(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        cursor = conn.execute(
            "INSERT INTO entity (diagram_id, kind) VALUES (?, 'data_flow')",
            (d,),
        )
        new_id = cursor.lastrowid
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO data_flow "
                "(id, node1_id, node2_id, name, protocol, authenticated, encrypted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id, max(a, b), min(a, b), "f", "tcp", 0, 0),
            )


def test_update_round_trips_bools(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        repo = DataFlowRepository(conn)
        flow = repo.create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        updated = repo.update(
            flow.id,
            DataFlowUpdate(authenticated=True, encrypted=True, protocol="tls"),
        )
    assert updated is not None
    assert updated.authenticated is True
    assert updated.encrypted is True
    assert updated.protocol == "tls"


def test_list_scoped_by_diagram(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        a1 = _make_node(conn, d_a, "a1")
        a2 = _make_node(conn, d_a, "a2")
        b1 = _make_node(conn, d_b, "b1")
        b2 = _make_node(conn, d_b, "b2")
        repo = DataFlowRepository(conn)
        a_flow = repo.create(
            d_a,
            DataFlowCreate(
                node1_id=a1,
                node2_id=a2,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        repo.create(
            d_b,
            DataFlowCreate(
                node1_id=b1,
                node2_id=b2,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        assert [f.id for f in repo.list(d_a)] == [a_flow.id]


def test_add_payload_idempotent_and_two_endpoints(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        flow_repo = DataFlowRepository(conn)
        item_repo = DataItemRepository(conn)
        flow = flow_repo.create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        item = item_repo.create(
            d, DataItemCreate(identifier="i", name="n", description="x")
        )
        flow_repo.add_payload(flow.id, item.id, 1)
        flow_repo.add_payload(flow.id, item.id, 1)  # idempotent
        flow_repo.add_payload(flow.id, item.id, 2)  # second endpoint -> separate row
        rows = conn.execute(
            "SELECT source_endpoint FROM flow_payload "
            "WHERE flow_id = ? AND data_item_id = ? ORDER BY source_endpoint",
            (flow.id, item.id),
        ).fetchall()
        assert [r["source_endpoint"] for r in rows] == [1, 2]


def test_add_payload_rejects_cross_diagram(db_path: Path) -> None:
    with connect() as conn:
        d_a = _make_diagram(conn, "a")
        d_b = _make_diagram(conn, "b")
        a1 = _make_node(conn, d_a, "a1")
        a2 = _make_node(conn, d_a, "a2")
        flow = DataFlowRepository(conn).create(
            d_a,
            DataFlowCreate(
                node1_id=a1,
                node2_id=a2,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        b_item = DataItemRepository(conn).create(
            d_b, DataItemCreate(identifier="i", name="n", description="x")
        )
        with pytest.raises(ValueError):
            DataFlowRepository(conn).add_payload(flow.id, b_item.id, 1)


def test_payload_for_flow_filtering(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        flow_repo = DataFlowRepository(conn)
        item_repo = DataItemRepository(conn)
        flow = flow_repo.create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        i1 = item_repo.create(
            d, DataItemCreate(identifier="i1", name="n", description="x")
        )
        i2 = item_repo.create(
            d, DataItemCreate(identifier="i2", name="n", description="x")
        )
        flow_repo.add_payload(flow.id, i1.id, 1)
        flow_repo.add_payload(flow.id, i2.id, 2)

        all_items = flow_repo.payload_for_flow(flow.id)
        assert {i.id for i in all_items} == {i1.id, i2.id}

        ep1 = flow_repo.payload_for_flow(flow.id, source_endpoint=1)
        assert [i.id for i in ep1] == [i1.id]

        ep2 = flow_repo.payload_for_flow(flow.id, source_endpoint=2)
        assert [i.id for i in ep2] == [i2.id]


def test_remove_payload(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        flow = DataFlowRepository(conn).create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        item = DataItemRepository(conn).create(
            d, DataItemCreate(identifier="i", name="n", description="x")
        )
        DataFlowRepository(conn).add_payload(flow.id, item.id, 1)
        assert DataFlowRepository(conn).remove_payload(flow.id, item.id, 1) is True
        assert DataFlowRepository(conn).remove_payload(flow.id, item.id, 1) is False


def test_flows_for_data_item(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        flow_repo = DataFlowRepository(conn)
        item_repo = DataItemRepository(conn)
        flow1 = flow_repo.create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f1",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        flow2 = flow_repo.create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f2",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        item = item_repo.create(
            d, DataItemCreate(identifier="i", name="n", description="x")
        )
        flow_repo.add_payload(flow1.id, item.id, 1)
        flow_repo.add_payload(flow2.id, item.id, 2)
        flows = flow_repo.flows_for_data_item(item.id)
        assert sorted(f.id for f in flows) == sorted([flow1.id, flow2.id])


def test_delete_flow_cascades_payload(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        flow = DataFlowRepository(conn).create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        item = DataItemRepository(conn).create(
            d, DataItemCreate(identifier="i", name="n", description="x")
        )
        DataFlowRepository(conn).add_payload(flow.id, item.id, 1)
        DataFlowRepository(conn).delete(flow.id)
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM flow_payload WHERE flow_id = ?", (flow.id,)
            ).fetchone()[0]
            == 0
        )


def test_endpoint_node_delete_cascades_flow(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        flow = DataFlowRepository(conn).create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        NodeRepository(conn).delete(a)
        assert DataFlowRepository(conn).get(flow.id) is None


def _make_flow(
    conn: sqlite3.Connection,
    diagram_id: int,
    *,
    name: str = "f",
    protocol: str = "tcp",
) -> int:
    a = _make_node(conn, diagram_id, f"{name}-a")
    b = _make_node(conn, diagram_id, f"{name}-b")
    return (
        DataFlowRepository(conn)
        .create(
            diagram_id,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name=name,
                protocol=protocol,
                authenticated=False,
                encrypted=False,
            ),
        )
        .id
    )


def test_search_no_args_returns_all_in_diagram(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        f1 = _make_flow(conn, d, name="f1")
        f2 = _make_flow(conn, d, name="f2")
        repo = DataFlowRepository(conn)
        assert [f.id for f in repo.search(d)] == [f1, f2]


def test_search_matches_name_and_protocol(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        target_name = _make_flow(conn, d, name="payments-flow", protocol="tcp")
        target_proto = _make_flow(conn, d, name="other", protocol="payments-rpc")
        _make_flow(conn, d, name="orders", protocol="tcp")

        repo = DataFlowRepository(conn)
        ids = {f.id for f in repo.search(d, text="payments")}
        assert ids == {target_name, target_proto}


def test_search_multi_token_ands(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        target = _make_flow(conn, d, name="payments-flow", protocol="grpc")
        _make_flow(conn, d, name="payments-only", protocol="tcp")
        repo = DataFlowRepository(conn)
        hits = repo.search(d, text="payments grpc")
        assert [f.id for f in hits] == [target]


def test_search_case_insensitive(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        f = _make_flow(conn, d, name="mixedcase")
        repo = DataFlowRepository(conn)
        assert [r.id for r in repo.search(d, text="MixedCase")] == [f]


def test_search_escapes_wildcards(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        target = _make_flow(conn, d, name="wildcard-target", protocol="100% safe")
        decoy = _make_flow(conn, d, name="wildcard-decoy", protocol="100x safe")
        repo = DataFlowRepository(conn)
        ids = {f.id for f in repo.search(d, text="100%")}
        assert target in ids
        assert decoy not in ids


def test_search_diagram_scope_isolated(db_path: Path) -> None:
    with connect() as conn:
        d1 = _make_diagram(conn, "d1")
        d2 = _make_diagram(conn, "d2")
        in_d1 = _make_flow(conn, d1, name="payments")
        _make_flow(conn, d2, name="payments")
        repo = DataFlowRepository(conn)
        hits = repo.search(d1, text="payments")
        assert [f.id for f in hits] == [in_d1]


def test_search_pagination(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        ids = [_make_flow(conn, d, name="hit") for _ in range(4)]
        repo = DataFlowRepository(conn)
        page1 = repo.search(d, text="hit", limit=2)
        page2 = repo.search(d, text="hit", limit=2, offset=2)
        assert [f.id for f in page1] == ids[:2]
        assert [f.id for f in page2] == ids[2:]


# ---------------------------------------------------------------------------
# payloads_for_diagram — bulk lookup for export
# ---------------------------------------------------------------------------


def test_payloads_for_diagram_groups_by_flow_and_endpoint(db_path: Path) -> None:
    """One pass yields {flow_id: {1: [...], 2: [...]}}, sorted, scoped to diagram."""
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        flow_repo = DataFlowRepository(conn)
        item_repo = DataItemRepository(conn)

        f1 = flow_repo.create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f1",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        f2 = flow_repo.create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f2",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        i1 = item_repo.create(
            d, DataItemCreate(identifier="i1", name="n", description="x")
        )
        i2 = item_repo.create(
            d, DataItemCreate(identifier="i2", name="n", description="x")
        )
        i3 = item_repo.create(
            d, DataItemCreate(identifier="i3", name="n", description="x")
        )
        # f1: i2 then i1 on endpoint 1 (insertion-order != id-order so we
        # can verify the result is sorted by data_item_id), i3 on endpoint 2.
        flow_repo.add_payload(f1.id, i2.id, 1)
        flow_repo.add_payload(f1.id, i1.id, 1)
        flow_repo.add_payload(f1.id, i3.id, 2)
        # f2: only endpoint 2 populated.
        flow_repo.add_payload(f2.id, i1.id, 2)

        result = flow_repo.payloads_for_diagram(d)

        assert set(result.keys()) == {f1.id, f2.id}
        # Both endpoint slots are always present for a flow that has any payloads.
        assert set(result[f1.id].keys()) == {1, 2}
        assert set(result[f2.id].keys()) == {1, 2}
        # Sorted by data_item_id ascending (i1 < i2).
        assert result[f1.id][1] == [i1.id, i2.id]
        assert result[f1.id][2] == [i3.id]
        assert result[f2.id][1] == []
        assert result[f2.id][2] == [i1.id]


def test_payloads_for_diagram_scope_isolation(db_path: Path) -> None:
    """Payloads from a sibling diagram do not leak into the result."""
    with connect() as conn:
        d1 = _make_diagram(conn, "d1")
        d2 = _make_diagram(conn, "d2")
        a1, b1 = _make_node(conn, d1, "a1"), _make_node(conn, d1, "b1")
        a2, b2 = _make_node(conn, d2, "a2"), _make_node(conn, d2, "b2")
        flow_repo = DataFlowRepository(conn)
        item_repo = DataItemRepository(conn)

        f1 = flow_repo.create(
            d1,
            DataFlowCreate(
                node1_id=a1,
                node2_id=b1,
                name="f1",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        f2 = flow_repo.create(
            d2,
            DataFlowCreate(
                node1_id=a2,
                node2_id=b2,
                name="f2",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        i1 = item_repo.create(
            d1, DataItemCreate(identifier="i1", name="n", description="x")
        )
        i2 = item_repo.create(
            d2, DataItemCreate(identifier="i2", name="n", description="x")
        )
        flow_repo.add_payload(f1.id, i1.id, 1)
        flow_repo.add_payload(f2.id, i2.id, 1)

        d1_result = flow_repo.payloads_for_diagram(d1)
        assert set(d1_result.keys()) == {f1.id}
        assert d1_result[f1.id][1] == [i1.id]

        d2_result = flow_repo.payloads_for_diagram(d2)
        assert set(d2_result.keys()) == {f2.id}
        assert d2_result[f2.id][1] == [i2.id]


def test_payloads_for_diagram_returns_empty_when_no_payloads(db_path: Path) -> None:
    """No payloads → empty dict (not a dict with empty inner values)."""
    with connect() as conn:
        d = _make_diagram(conn)
        a = _make_node(conn, d, "a")
        b = _make_node(conn, d, "b")
        DataFlowRepository(conn).create(
            d,
            DataFlowCreate(
                node1_id=a,
                node2_id=b,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )

        assert DataFlowRepository(conn).payloads_for_diagram(d) == {}
