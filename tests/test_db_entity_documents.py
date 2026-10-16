from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tm_cli.db import (
    ContainerVariant,
    ContainerVariantCreate,
    DataFlow,
    DataFlowCreate,
    DataFlowRepository,
    DataItem,
    DataItemCreate,
    DataItemRepository,
    DataStoreNode,
    DataStoreNodeCreate,
    DiagramCreate,
    DiagramRepository,
    Document,
    DocumentCreate,
    DocumentRepository,
    DocumentSummary,
    EntityDocumentRepository,
    ExternalEntityNode,
    ExternalEntityNodeCreate,
    NodeRepository,
    ProcessNode,
    ProcessNodeCreate,
    TrustBoundary,
    TrustBoundaryCreate,
    connect,
)
from tm_cli.db.dfd_containers import ContainerRepository


def _sample_doc(**overrides: object) -> DocumentCreate:
    base: dict[str, object] = {
        "last_updated": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        "title": "T",
        "author": "alice",
        "content": "body",
    }
    base.update(overrides)
    return DocumentCreate(**base)  # type: ignore[arg-type]


def _make_diagram(conn: sqlite3.Connection, name: str = "d") -> int:
    return DiagramRepository(conn).create(DiagramCreate(name=name)).id


def _make_process_node(
    conn: sqlite3.Connection, diagram_id: int, name: str = "p"
) -> ProcessNode:
    node = NodeRepository(conn).create(
        diagram_id,
        ProcessNodeCreate(
            name=name, description="d", trust_level="public", assumptions=[]
        ),
    )
    assert isinstance(node, ProcessNode)
    return node


def _make_external_entity(
    conn: sqlite3.Connection, diagram_id: int
) -> ExternalEntityNode:
    node = NodeRepository(conn).create(
        diagram_id,
        ExternalEntityNodeCreate(
            name="user", description="d", entity_type="user", out_of_scope=False
        ),
    )
    assert isinstance(node, ExternalEntityNode)
    return node


def _make_data_store(conn: sqlite3.Connection, diagram_id: int) -> DataStoreNode:
    node = NodeRepository(conn).create(
        diagram_id,
        DataStoreNodeCreate(
            name="db",
            description="d",
            storage_type="database",
            contains_pii=False,
            encryption_at_rest=True,
        ),
    )
    assert isinstance(node, DataStoreNode)
    return node


def _make_trust_boundary(conn: sqlite3.Connection, diagram_id: int) -> TrustBoundary:
    container = ContainerRepository(conn).create(
        diagram_id,
        TrustBoundaryCreate(name="tb", description="d", privilege_level="dmz"),
    )
    assert isinstance(container, TrustBoundary)
    return container


def _make_container(conn: sqlite3.Connection, diagram_id: int) -> ContainerVariant:
    container = ContainerRepository(conn).create(
        diagram_id, ContainerVariantCreate(name="c", description="d")
    )
    assert isinstance(container, ContainerVariant)
    return container


def _make_flow(conn: sqlite3.Connection, diagram_id: int, n1: int, n2: int) -> DataFlow:
    return DataFlowRepository(conn).create(
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


def _make_item(conn: sqlite3.Connection, diagram_id: int) -> DataItem:
    return DataItemRepository(conn).create(
        diagram_id,
        DataItemCreate(
            identifier="x", name="i", description="d", classification="internal"
        ),
    )


def test_link_round_trip(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        doc = DocumentRepository(conn).create(_sample_doc(title="One"))
        repo = EntityDocumentRepository(conn)

        repo.link(node.id, doc.id)

        docs = repo.documents_for_entity(node.id)
        assert len(docs) == 1
        assert isinstance(docs[0], DocumentSummary)
        assert docs[0].id == doc.id
        assert docs[0].title == "One"

        nodes = repo.nodes_for_document(doc.id)
        assert len(nodes) == 1
        assert isinstance(nodes[0], ProcessNode)
        assert nodes[0].id == node.id


def test_link_is_idempotent(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        doc = DocumentRepository(conn).create(_sample_doc())
        repo = EntityDocumentRepository(conn)

        repo.link(node.id, doc.id)
        repo.link(node.id, doc.id)

        count = conn.execute(
            "SELECT COUNT(*) FROM entity_documents "
            "WHERE entity_id = ? AND document_id = ?",
            (node.id, doc.id),
        ).fetchone()[0]
        assert count == 1


def test_unlink_returns_true_then_false(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        doc = DocumentRepository(conn).create(_sample_doc())
        repo = EntityDocumentRepository(conn)
        repo.link(node.id, doc.id)

        assert repo.unlink(node.id, doc.id) is True
        assert repo.unlink(node.id, doc.id) is False
        assert repo.documents_for_entity(node.id) == []


def test_link_works_for_all_four_kinds(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        process = _make_process_node(conn, d, "p")
        external = _make_external_entity(conn, d)
        store = _make_data_store(conn, d)
        boundary = _make_trust_boundary(conn, d)
        container = _make_container(conn, d)
        # use process + external for the flow endpoints
        flow = _make_flow(conn, d, process.id, external.id)
        item = _make_item(conn, d)

        doc = DocumentRepository(conn).create(_sample_doc())
        repo = EntityDocumentRepository(conn)

        for entity_id in (
            process.id,
            external.id,
            store.id,
            boundary.id,
            container.id,
            flow.id,
            item.id,
        ):
            repo.link(entity_id, doc.id)

        # Every entity sees the doc.
        for entity_id in (
            process.id,
            external.id,
            store.id,
            boundary.id,
            container.id,
            flow.id,
            item.id,
        ):
            assert [d.id for d in repo.documents_for_entity(entity_id)] == [doc.id]


def test_documents_for_entity_orders_and_returns_summaries(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        docs_repo = DocumentRepository(conn)
        d1 = docs_repo.create(_sample_doc(title="A"))
        d2 = docs_repo.create(_sample_doc(title="B"))
        d3 = docs_repo.create(_sample_doc(title="C"))

        repo = EntityDocumentRepository(conn)
        # link out of order to verify ordering by documents.id
        repo.link(node.id, d2.id)
        repo.link(node.id, d3.id)
        repo.link(node.id, d1.id)

        result = repo.documents_for_entity(node.id)
        assert [r.id for r in result] == [d1.id, d2.id, d3.id]
        for r in result:
            assert isinstance(r, DocumentSummary)
            assert not isinstance(r, Document)


def test_per_kind_reverse_lookup_returns_correct_subclass(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        process = _make_process_node(conn, d, "p")
        external = _make_external_entity(conn, d)
        store = _make_data_store(conn, d)
        boundary = _make_trust_boundary(conn, d)
        container = _make_container(conn, d)
        flow = _make_flow(conn, d, process.id, external.id)
        item = _make_item(conn, d)

        doc = DocumentRepository(conn).create(_sample_doc())
        repo = EntityDocumentRepository(conn)
        for entity_id in (
            process.id,
            external.id,
            store.id,
            boundary.id,
            container.id,
            flow.id,
            item.id,
        ):
            repo.link(entity_id, doc.id)

        nodes = repo.nodes_for_document(doc.id)
        assert {n.id for n in nodes} == {process.id, external.id, store.id}
        node_types = {type(n) for n in nodes}
        assert node_types == {ProcessNode, ExternalEntityNode, DataStoreNode}

        containers = repo.containers_for_document(doc.id)
        assert {c.id for c in containers} == {boundary.id, container.id}
        container_types = {type(c) for c in containers}
        assert container_types == {TrustBoundary, ContainerVariant}

        flows = repo.flows_for_document(doc.id)
        assert [f.id for f in flows] == [flow.id]
        assert isinstance(flows[0], DataFlow)

        items = repo.items_for_document(doc.id)
        assert [i.id for i in items] == [item.id]
        assert isinstance(items[0], DataItem)


def test_unknown_entity_id_raises_integrity_error(db_path: Path) -> None:
    with connect() as conn:
        doc = DocumentRepository(conn).create(_sample_doc())
        repo = EntityDocumentRepository(conn)
        with pytest.raises(sqlite3.IntegrityError):
            repo.link(9999, doc.id)


def test_unknown_document_id_raises_integrity_error(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        repo = EntityDocumentRepository(conn)
        with pytest.raises(sqlite3.IntegrityError):
            repo.link(node.id, 9999)


def test_delete_document_cascades_links(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        doc = DocumentRepository(conn).create(_sample_doc())
        repo = EntityDocumentRepository(conn)
        repo.link(node.id, doc.id)

        assert DocumentRepository(conn).delete(doc.id) is True

        assert repo.documents_for_entity(node.id) == []
        count = conn.execute("SELECT COUNT(*) FROM entity_documents").fetchone()[0]
        assert count == 0
        # node itself untouched
        assert NodeRepository(conn).get(node.id) is not None


def test_delete_entity_cascades_links(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        doc = DocumentRepository(conn).create(_sample_doc())
        repo = EntityDocumentRepository(conn)
        repo.link(node.id, doc.id)

        assert NodeRepository(conn).delete(node.id) is True

        assert repo.nodes_for_document(doc.id) == []
        count = conn.execute("SELECT COUNT(*) FROM entity_documents").fetchone()[0]
        assert count == 0
        # document itself untouched
        assert DocumentRepository(conn).get(doc.id) is not None


def test_delete_diagram_cascades_links(db_path: Path) -> None:
    with connect() as conn:
        d = _make_diagram(conn)
        node = _make_process_node(conn, d)
        item = _make_item(conn, d)
        doc = DocumentRepository(conn).create(_sample_doc())
        repo = EntityDocumentRepository(conn)
        repo.link(node.id, doc.id)
        repo.link(item.id, doc.id)

        assert DiagramRepository(conn).delete(d) is True

        count = conn.execute("SELECT COUNT(*) FROM entity_documents").fetchone()[0]
        assert count == 0
        assert DocumentRepository(conn).get(doc.id) is not None
