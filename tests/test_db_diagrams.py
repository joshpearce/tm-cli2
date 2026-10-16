from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tm_cli.db import (
    ContainerRepository,
    DataFlowCreate,
    DataFlowRepository,
    DataItemCreate,
    DataItemRepository,
    DiagramCreate,
    DiagramRepository,
    DiagramUpdate,
    NodeRepository,
    ProcessNodeCreate,
    TrustBoundaryCreate,
    connect,
)


def test_create_assigns_id_and_created(db_path: Path) -> None:
    before = datetime.now(UTC)
    with connect() as conn:
        d = DiagramRepository(conn).create(DiagramCreate(name="d", author="a"))
    after = datetime.now(UTC)

    assert d.id == 1
    assert d.name == "d"
    assert d.author == "a"
    assert d.description is None
    slack = timedelta(seconds=1)
    assert before - slack <= d.created <= after + slack


def test_create_with_all_fields_none(db_path: Path) -> None:
    with connect() as conn:
        d = DiagramRepository(conn).create(DiagramCreate())
    assert d.name is None
    assert d.description is None
    assert d.author is None


def test_get_returns_none_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        assert DiagramRepository(conn).get(999) is None


def test_get_round_trip(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        d = repo.create(DiagramCreate(name="x"))
        fetched = repo.get(d.id)
    assert fetched is not None
    assert fetched.model_dump() == d.model_dump()


def test_update_partial_fields(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        d = repo.create(DiagramCreate(name="orig", author="a"))
        updated = repo.update(d.id, DiagramUpdate(name="new"))
    assert updated is not None
    assert updated.name == "new"
    assert updated.author == "a"
    assert updated.created == d.created


def test_update_can_clear_nullable_field(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        d = repo.create(DiagramCreate(name="orig", author="a"))
        cleared = repo.update(d.id, DiagramUpdate(author=None))
    assert cleared is not None
    assert cleared.author is None
    assert cleared.name == "orig"


def test_update_returns_none_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        assert DiagramRepository(conn).update(42, DiagramUpdate(name="n")) is None


def test_delete_returns_true_then_false(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        d = repo.create(DiagramCreate(name="d"))
        assert repo.delete(d.id) is True
        assert repo.delete(d.id) is False
        assert repo.get(d.id) is None


def test_list_orders_by_id(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        a = repo.create(DiagramCreate(name="a"))
        b = repo.create(DiagramCreate(name="b"))
        c = repo.create(DiagramCreate(name="c"))

        all_d = repo.list()
        assert [x.id for x in all_d] == [a.id, b.id, c.id]

        page = repo.list(limit=2, offset=1)
        assert [x.name for x in page] == ["b", "c"]


def test_delete_cascades_through_entity_to_all_kinds(db_path: Path) -> None:
    with connect() as conn:
        d = DiagramRepository(conn).create(DiagramCreate(name="d"))
        nr = NodeRepository(conn)
        a = nr.create(
            d.id,
            ProcessNodeCreate(
                name="a",
                description="d",
                trust_level="public",
                assumptions=[],
            ),
        )
        b = nr.create(
            d.id,
            ProcessNodeCreate(
                name="b",
                description="d",
                trust_level="public",
                assumptions=[],
            ),
        )
        cr = ContainerRepository(conn)
        boundary = cr.create(
            d.id,
            TrustBoundaryCreate(
                name="t",
                description="t",
                privilege_level="internet",
            ),
        )
        cr.set_parent(a.id, boundary.id)

        flow = DataFlowRepository(conn).create(
            d.id,
            DataFlowCreate(
                node1_id=a.id,
                node2_id=b.id,
                name="f",
                protocol="tcp",
                authenticated=False,
                encrypted=False,
            ),
        )
        item = DataItemRepository(conn).create(
            d.id,
            DataItemCreate(
                identifier="i",
                name="n",
                description="d",
                parent_node_id=a.id,
            ),
        )
        DataFlowRepository(conn).add_payload(flow.id, item.id, 1)

        # one of each kind in entity table
        kinds = dict(
            conn.execute("SELECT kind, COUNT(*) FROM entity GROUP BY kind").fetchall()
        )
        assert kinds == {"node": 2, "container": 1, "data_flow": 1, "data_item": 1}

        # ids do not overlap across kind tables
        ids: set[int] = set()
        for table in ("node", "container", "data_flow", "data_item"):
            for row in conn.execute(f"SELECT id FROM {table}").fetchall():
                assert row["id"] not in ids
                ids.add(row["id"])

        DiagramRepository(conn).delete(d.id)

        for table in (
            "entity",
            "node",
            "container",
            "container_membership",
            "data_flow",
            "data_item",
            "flow_payload",
        ):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, f"{table} not empty after diagram delete"


def test_search_no_args_returns_all(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        a = repo.create(DiagramCreate(name="alpha"))
        b = repo.create(DiagramCreate(name="beta"))
        assert [d.id for d in repo.search()] == [a.id, b.id]


def test_search_matches_across_name_description_author(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        a = repo.create(DiagramCreate(name="payments", description="x"))
        b = repo.create(DiagramCreate(name="auth", description="payments flow"))
        c = repo.create(
            DiagramCreate(name="other", description="x", author="payments-team")
        )
        repo.create(DiagramCreate(name="unrelated"))

        ids = {d.id for d in repo.search(text="payments")}
        assert ids == {a.id, b.id, c.id}


def test_search_skips_null_columns(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        # All-None diagram should not match any text query
        all_null = repo.create(DiagramCreate())
        match = repo.create(DiagramCreate(name="hit"))

        results = repo.search(text="hit")
        ids = {d.id for d in results}
        assert match.id in ids
        assert all_null.id not in ids


def test_search_multi_token_ands(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        target = repo.create(DiagramCreate(name="auth", description="payments flow"))
        repo.create(DiagramCreate(name="payments-only"))
        repo.create(DiagramCreate(name="auth-only"))

        hits = repo.search(text="auth payments")
        assert [d.id for d in hits] == [target.id]


def test_search_case_insensitive(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        d = repo.create(DiagramCreate(name="mixedcase"))
        assert [r.id for r in repo.search(text="MixedCase")] == [d.id]


def test_search_escapes_wildcards(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        target = repo.create(DiagramCreate(name="target", description="100% complete"))
        decoy = repo.create(DiagramCreate(name="decoy", description="100x complete"))
        ids = {d.id for d in repo.search(text="100%")}
        assert target.id in ids
        assert decoy.id not in ids


def test_search_pagination(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        ids = [repo.create(DiagramCreate(name="hit")).id for _ in range(4)]
        page1 = repo.search(text="hit", limit=2)
        page2 = repo.search(text="hit", limit=2, offset=2)
        assert [d.id for d in page1] == ids[:2]
        assert [d.id for d in page2] == ids[2:]
