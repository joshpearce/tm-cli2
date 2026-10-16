from __future__ import annotations

import sqlite3

from tm_cli.db.dfd_containers import (
    _CONTAINER_COLUMNS_QUALIFIED,
    _row_to_container,
)
from tm_cli.db.dfd_flows import _FLOW_COLUMNS_QUALIFIED, _row_to_flow
from tm_cli.db.dfd_items import (
    _DATA_ITEM_COLUMNS_QUALIFIED,
    _row_to_data_item,
)
from tm_cli.db.dfd_models import Container, DataFlow, DataItem, Node, ProcessComponent
from tm_cli.db.dfd_nodes import _NODE_COLUMNS_QUALIFIED, _row_to_node
from tm_cli.db.dfd_process_components import (
    _COMPONENT_COLUMNS_QUALIFIED,
    _row_to_component,
)
from tm_cli.db.documents import (
    _SUMMARY_COLUMNS as _DOCUMENT_SUMMARY_COLUMNS,
)
from tm_cli.db.documents import (
    _row_to_summary as _row_to_document_summary,
)
from tm_cli.db.models import DocumentSummary


class EntityDocumentRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def link(self, entity_id: int, document_id: int) -> None:
        """Idempotently link an entity and a document.

        Raises sqlite3.IntegrityError if either id does not exist.
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO entity_documents (entity_id, document_id) "
            "VALUES (?, ?)",
            (entity_id, document_id),
        )

    def unlink(self, entity_id: int, document_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM entity_documents WHERE entity_id = ? AND document_id = ?",
            (entity_id, document_id),
        )
        return cursor.rowcount > 0

    def documents_for_entity(self, entity_id: int) -> list[DocumentSummary]:
        rows = self._conn.execute(
            f"SELECT {_DOCUMENT_SUMMARY_COLUMNS} FROM documents "
            "JOIN entity_documents "
            "    ON entity_documents.document_id = documents.id "
            "WHERE entity_documents.entity_id = ? "
            "ORDER BY documents.id ASC",
            (entity_id,),
        ).fetchall()
        return [_row_to_document_summary(row) for row in rows]

    def nodes_for_document(self, document_id: int) -> list[Node]:
        rows = self._conn.execute(
            f"SELECT {_NODE_COLUMNS_QUALIFIED} FROM node "
            "JOIN entity_documents ON entity_documents.entity_id = node.id "
            "WHERE entity_documents.document_id = ? "
            "ORDER BY node.id ASC",
            (document_id,),
        ).fetchall()
        return [_row_to_node(row) for row in rows]

    def containers_for_document(self, document_id: int) -> list[Container]:
        rows = self._conn.execute(
            f"SELECT {_CONTAINER_COLUMNS_QUALIFIED} FROM container "
            "JOIN entity_documents "
            "    ON entity_documents.entity_id = container.id "
            "WHERE entity_documents.document_id = ? "
            "ORDER BY container.id ASC",
            (document_id,),
        ).fetchall()
        return [_row_to_container(row) for row in rows]

    def flows_for_document(self, document_id: int) -> list[DataFlow]:
        rows = self._conn.execute(
            f"SELECT {_FLOW_COLUMNS_QUALIFIED} FROM data_flow "
            "JOIN entity_documents "
            "    ON entity_documents.entity_id = data_flow.id "
            "WHERE entity_documents.document_id = ? "
            "ORDER BY data_flow.id ASC",
            (document_id,),
        ).fetchall()
        return [_row_to_flow(row) for row in rows]

    def items_for_document(self, document_id: int) -> list[DataItem]:
        rows = self._conn.execute(
            f"SELECT {_DATA_ITEM_COLUMNS_QUALIFIED} FROM data_item "
            "JOIN entity_documents "
            "    ON entity_documents.entity_id = data_item.id "
            "WHERE entity_documents.document_id = ? "
            "ORDER BY data_item.id ASC",
            (document_id,),
        ).fetchall()
        return [_row_to_data_item(row) for row in rows]

    def process_components_for_document(
        self, document_id: int
    ) -> list[ProcessComponent]:
        rows = self._conn.execute(
            f"SELECT {_COMPONENT_COLUMNS_QUALIFIED} FROM process_component "
            "JOIN entity_documents "
            "    ON entity_documents.entity_id = process_component.id "
            "WHERE entity_documents.document_id = ? "
            "ORDER BY process_component.id ASC",
            (document_id,),
        ).fetchall()
        return [_row_to_component(row) for row in rows]
