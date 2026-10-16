from __future__ import annotations

import sqlite3

from tm_cli.db._search import _build_text_clause
from tm_cli.db.dfd_models import (
    ComponentType,
    ProcessComponent,
    ProcessComponentCreate,
    ProcessComponentUpdate,
)
from tm_cli.db.diagrams import _mint_entity_id

_COMPONENT_COLUMNS = "id, parent_process_id, name, description, component_type"
_COMPONENT_COLUMNS_QUALIFIED = (
    "process_component.id, process_component.parent_process_id, "
    "process_component.name, process_component.description, "
    "process_component.component_type"
)
_SEARCHABLE_TEXT_COLUMNS = (
    "process_component.name",
    "process_component.description",
)
_REQUIRED_FIELDS = ("name", "description", "component_type")


def _row_to_component(row: sqlite3.Row) -> ProcessComponent:
    return ProcessComponent(**{key: row[key] for key in row.keys()})


def _validate_process_node(
    conn: sqlite3.Connection, parent_process_id: int, diagram_id: int
) -> None:
    """Validate that parent_process_id references a process node in the same diagram."""
    row = conn.execute(
        "SELECT entity.diagram_id, node.type "
        "FROM entity "
        "JOIN node ON node.id = entity.id "
        "WHERE entity.id = ? AND entity.kind = 'node'",
        (parent_process_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"parent_process_id {parent_process_id} is not a node")
    if row["type"] != "process":
        raise ValueError(f"parent_process_id {parent_process_id} is not a process node")
    if row["diagram_id"] != diagram_id:
        raise ValueError("parent_process_id must belong to the same diagram")


class ProcessComponentRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, diagram_id: int, data: ProcessComponentCreate) -> ProcessComponent:
        _validate_process_node(self._conn, data.parent_process_id, diagram_id)

        component_id = _mint_entity_id(self._conn, diagram_id, "process_component")
        self._conn.execute(
            "INSERT INTO process_component "
            "(id, parent_process_id, name, description, component_type) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                component_id,
                data.parent_process_id,
                data.name,
                data.description,
                data.component_type,
            ),
        )
        fetched = self.get(component_id)
        assert fetched is not None
        return fetched

    def get(self, component_id: int) -> ProcessComponent | None:
        row = self._conn.execute(
            f"SELECT {_COMPONENT_COLUMNS} FROM process_component WHERE id = ?",
            (component_id,),
        ).fetchone()
        return _row_to_component(row) if row is not None else None

    def update(
        self, component_id: int, patch: ProcessComponentUpdate
    ) -> ProcessComponent | None:
        diagram_row = self._conn.execute(
            "SELECT diagram_id FROM entity WHERE id = ? AND kind = 'process_component'",
            (component_id,),
        ).fetchone()
        if diagram_row is None:
            return None
        diagram_id = diagram_row["diagram_id"]

        patch_data = patch.model_dump(exclude_unset=True)

        # Validate parent_process_id if being changed
        if "parent_process_id" in patch_data:
            new_parent = patch_data["parent_process_id"]
            if new_parent is None:
                raise ValueError("parent_process_id cannot be set to None")
            _validate_process_node(self._conn, new_parent, diagram_id)

        set_clauses: list[str] = []
        values: list[object] = []
        # All fields are required/NOT NULL - only set if non-None
        # (None means "no change")
        for field in _REQUIRED_FIELDS:
            if field in patch_data and patch_data[field] is not None:
                set_clauses.append(f"{field} = ?")
                values.append(patch_data[field])
        # parent_process_id is also NOT NULL but can be changed
        if (
            "parent_process_id" in patch_data
            and patch_data["parent_process_id"] is not None
        ):
            set_clauses.append("parent_process_id = ?")
            values.append(patch_data["parent_process_id"])

        if set_clauses:
            values.append(component_id)
            self._conn.execute(
                f"UPDATE process_component SET {', '.join(set_clauses)} WHERE id = ?",
                values,
            )
        return self.get(component_id)

    def delete(self, component_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM entity WHERE id = ? AND kind = 'process_component'",
            (component_id,),
        )
        return cursor.rowcount > 0

    def list(
        self,
        diagram_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ProcessComponent]:
        sql = (
            f"SELECT {_COMPONENT_COLUMNS_QUALIFIED} FROM process_component "
            "JOIN entity ON entity.id = process_component.id "
            "WHERE entity.diagram_id = ? "
            "ORDER BY process_component.id ASC"
        )
        params: list[object] = [diagram_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_component(row) for row in rows]

    def search(
        self,
        diagram_id: int,
        text: str | None = None,
        *,
        parent_process_id: int | None = None,
        component_type: ComponentType | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ProcessComponent]:
        sql = (
            f"SELECT {_COMPONENT_COLUMNS_QUALIFIED} FROM process_component "
            "JOIN entity ON entity.id = process_component.id "
            "WHERE entity.diagram_id = ?"
        )
        params: list[object] = [diagram_id]
        if parent_process_id is not None:
            sql += " AND process_component.parent_process_id = ?"
            params.append(parent_process_id)
        if component_type is not None:
            sql += " AND process_component.component_type = ?"
            params.append(component_type)
        if text:
            clause, clause_params = _build_text_clause(text, _SEARCHABLE_TEXT_COLUMNS)
            if clause:
                sql += f" AND {clause}"
                params.extend(clause_params)
        sql += " ORDER BY process_component.id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_component(row) for row in rows]
