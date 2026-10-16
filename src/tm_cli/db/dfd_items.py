from __future__ import annotations

import sqlite3

from tm_cli.db._search import _build_text_clause
from tm_cli.db.dfd_models import (
    Classification,
    DataItem,
    DataItemCreate,
    DataItemUpdate,
)
from tm_cli.db.diagrams import _mint_entity_id

_DATA_ITEM_COLUMNS = "id, identifier, name, description, classification, parent_node_id"
_DATA_ITEM_COLUMNS_QUALIFIED = (
    "data_item.id, data_item.identifier, data_item.name, "
    "data_item.description, data_item.classification, data_item.parent_node_id"
)
_SEARCHABLE_TEXT_COLUMNS = (
    "data_item.identifier",
    "data_item.name",
    "data_item.description",
)
_NULLABLE_FIELDS = ("parent_node_id",)
_REQUIRED_FIELDS = ("identifier", "name", "description", "classification")


def _row_to_data_item(row: sqlite3.Row) -> DataItem:
    return DataItem(**{key: row[key] for key in row.keys()})


def _entity_diagram_id(conn: sqlite3.Connection, entity_id: int) -> int | None:
    row = conn.execute(
        "SELECT diagram_id, kind FROM entity WHERE id = ?",
        (entity_id,),
    ).fetchone()
    if row is None or row["kind"] != "node":
        return None
    return row["diagram_id"]


class DataItemRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, diagram_id: int, data: DataItemCreate) -> DataItem:
        if data.parent_node_id is not None:
            parent_diagram = _entity_diagram_id(self._conn, data.parent_node_id)
            if parent_diagram is None:
                raise ValueError(f"parent_node_id {data.parent_node_id} is not a node")
            if parent_diagram != diagram_id:
                raise ValueError("parent_node_id must belong to the same diagram")

        item_id = _mint_entity_id(self._conn, diagram_id, "data_item")
        self._conn.execute(
            "INSERT INTO data_item "
            "(id, identifier, name, description, classification, parent_node_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                item_id,
                data.identifier,
                data.name,
                data.description,
                data.classification,
                data.parent_node_id,
            ),
        )
        fetched = self.get(item_id)
        assert fetched is not None
        return fetched

    def get(self, data_item_id: int) -> DataItem | None:
        row = self._conn.execute(
            f"SELECT {_DATA_ITEM_COLUMNS} FROM data_item WHERE id = ?",
            (data_item_id,),
        ).fetchone()
        return _row_to_data_item(row) if row is not None else None

    def update(self, data_item_id: int, patch: DataItemUpdate) -> DataItem | None:
        diagram_row = self._conn.execute(
            "SELECT diagram_id FROM entity WHERE id = ? AND kind = 'data_item'",
            (data_item_id,),
        ).fetchone()
        if diagram_row is None:
            return None
        diagram_id = diagram_row["diagram_id"]

        patch_data = patch.model_dump(exclude_unset=True)

        # Validate parent_node_id is in the same diagram (only when explicitly set
        # to a non-None value; passing None clears the linkage).
        if "parent_node_id" in patch_data and patch_data["parent_node_id"] is not None:
            new_parent = patch_data["parent_node_id"]
            parent_diagram = _entity_diagram_id(self._conn, new_parent)
            if parent_diagram is None:
                raise ValueError(f"parent_node_id {new_parent} is not a node")
            if parent_diagram != diagram_id:
                raise ValueError("parent_node_id must belong to the same diagram")

        set_clauses: list[str] = []
        values: list[object] = []
        # Required fields: only set if non-None (None means "no change").
        for field in _REQUIRED_FIELDS:
            if field in patch_data and patch_data[field] is not None:
                set_clauses.append(f"{field} = ?")
                values.append(patch_data[field])
        # Nullable fields: explicit None clears the column.
        for field in _NULLABLE_FIELDS:
            if field in patch_data:
                set_clauses.append(f"{field} = ?")
                values.append(patch_data[field])

        if set_clauses:
            values.append(data_item_id)
            self._conn.execute(
                f"UPDATE data_item SET {', '.join(set_clauses)} WHERE id = ?",
                values,
            )
        return self.get(data_item_id)

    def delete(self, data_item_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM entity WHERE id = ? AND kind = 'data_item'",
            (data_item_id,),
        )
        return cursor.rowcount > 0

    def list(
        self,
        diagram_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DataItem]:
        sql = (
            f"SELECT {_DATA_ITEM_COLUMNS_QUALIFIED} FROM data_item "
            "JOIN entity ON entity.id = data_item.id "
            "WHERE entity.diagram_id = ? "
            "ORDER BY data_item.id ASC"
        )
        params: list[object] = [diagram_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_data_item(row) for row in rows]

    def search(
        self,
        diagram_id: int,
        text: str | None = None,
        *,
        classification: Classification | None = None,
        parent_node_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DataItem]:
        sql = (
            f"SELECT {_DATA_ITEM_COLUMNS_QUALIFIED} FROM data_item "
            "JOIN entity ON entity.id = data_item.id "
            "WHERE entity.diagram_id = ?"
        )
        params: list[object] = [diagram_id]
        if classification is not None:
            sql += " AND data_item.classification = ?"
            params.append(classification)
        if parent_node_id is not None:
            sql += " AND data_item.parent_node_id = ?"
            params.append(parent_node_id)
        if text:
            clause, clause_params = _build_text_clause(text, _SEARCHABLE_TEXT_COLUMNS)
            if clause:
                sql += f" AND {clause}"
                params.extend(clause_params)
        sql += " ORDER BY data_item.id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_data_item(row) for row in rows]
