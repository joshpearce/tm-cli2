from __future__ import annotations

import json
import sqlite3
from typing import cast, get_args

from tm_cli.db._search import _build_text_clause
from tm_cli.db.dfd_models import (
    DataStoreNode,
    DataStoreNodeCreate,
    DataStoreNodeUpdate,
    ExternalEntityNode,
    ExternalEntityNodeCreate,
    ExternalEntityNodeUpdate,
    Node,
    NodeCreate,
    NodeType,
    NodeUpdate,
    ProcessNode,
    ProcessNodeCreate,
    ProcessNodeUpdate,
)
from tm_cli.db.diagrams import _mint_entity_id

_NODE_COLUMNS = (
    "id, type, name, description, "
    "trust_level, assumptions, "
    "entity_type, out_of_scope, "
    "storage_type, contains_pii, encryption_at_rest"
)
_NODE_COLUMNS_QUALIFIED = (
    "node.id, node.type, node.name, node.description, "
    "node.trust_level, node.assumptions, "
    "node.entity_type, node.out_of_scope, "
    "node.storage_type, node.contains_pii, node.encryption_at_rest"
)

_SEARCHABLE_TEXT_COLUMNS = (
    "node.name",
    "node.description",
    "IFNULL(node.assumptions, '')",
)

_NODE_TYPES = cast(tuple[str, ...], get_args(NodeType))


def _row_to_node(row: sqlite3.Row) -> Node:
    node_type = row["type"]
    if node_type == "process":
        assumptions_raw = row["assumptions"]
        assumptions = json.loads(assumptions_raw) if assumptions_raw is not None else []
        return ProcessNode(
            type="process",
            id=row["id"],
            name=row["name"],
            description=row["description"],
            trust_level=row["trust_level"],
            assumptions=assumptions,
        )
    if node_type == "external_entity":
        return ExternalEntityNode(
            type="external_entity",
            id=row["id"],
            name=row["name"],
            description=row["description"],
            entity_type=row["entity_type"],
            out_of_scope=bool(row["out_of_scope"]),
        )
    if node_type == "data_store":
        return DataStoreNode(
            type="data_store",
            id=row["id"],
            name=row["name"],
            description=row["description"],
            storage_type=row["storage_type"],
            contains_pii=bool(row["contains_pii"]),
            encryption_at_rest=bool(row["encryption_at_rest"]),
        )
    raise ValueError(f"Unknown node type in DB row: {node_type!r}")


class NodeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, diagram_id: int, data: NodeCreate) -> Node:
        validated = data
        node_id = _mint_entity_id(self._conn, diagram_id, "node")
        if isinstance(validated, ProcessNodeCreate):
            self._conn.execute(
                "INSERT INTO node "
                "(id, type, name, description, trust_level, assumptions) "
                "VALUES (?, 'process', ?, ?, ?, ?)",
                (
                    node_id,
                    validated.name,
                    validated.description,
                    validated.trust_level,
                    json.dumps(validated.assumptions),
                ),
            )
        elif isinstance(validated, ExternalEntityNodeCreate):
            self._conn.execute(
                "INSERT INTO node "
                "(id, type, name, description, entity_type, out_of_scope) "
                "VALUES (?, 'external_entity', ?, ?, ?, ?)",
                (
                    node_id,
                    validated.name,
                    validated.description,
                    validated.entity_type,
                    int(validated.out_of_scope),
                ),
            )
        elif isinstance(validated, DataStoreNodeCreate):
            self._conn.execute(
                "INSERT INTO node "
                "(id, type, name, description, "
                "storage_type, contains_pii, encryption_at_rest) "
                "VALUES (?, 'data_store', ?, ?, ?, ?, ?)",
                (
                    node_id,
                    validated.name,
                    validated.description,
                    validated.storage_type,
                    int(validated.contains_pii),
                    int(validated.encryption_at_rest),
                ),
            )
        else:
            raise TypeError(
                f"Unsupported NodeCreate variant: {type(validated).__name__}"
            )
        fetched = self.get(node_id)
        assert fetched is not None
        return fetched

    def get(self, node_id: int) -> Node | None:
        row = self._conn.execute(
            f"SELECT {_NODE_COLUMNS} FROM node WHERE id = ?",
            (node_id,),
        ).fetchone()
        return _row_to_node(row) if row is not None else None

    def update(self, node_id: int, patch: NodeUpdate) -> Node | None:
        row = self._conn.execute(
            "SELECT type FROM node WHERE id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            return None
        current_type = row["type"]

        expected_patch_type: type
        common_fields = ("name", "description")
        variant_fields: tuple[str, ...]
        if current_type == "process":
            expected_patch_type = ProcessNodeUpdate
            variant_fields = ("trust_level", "assumptions")
        elif current_type == "external_entity":
            expected_patch_type = ExternalEntityNodeUpdate
            variant_fields = ("entity_type", "out_of_scope")
        elif current_type == "data_store":
            expected_patch_type = DataStoreNodeUpdate
            variant_fields = ("storage_type", "contains_pii", "encryption_at_rest")
        else:
            raise ValueError(f"Unknown node type in DB row: {current_type!r}")

        if not isinstance(patch, expected_patch_type):
            raise ValueError(
                f"Patch type {type(patch).__name__} does not match node type "
                f"{current_type!r}; expected {expected_patch_type.__name__}"
            )

        patch_data = patch.model_dump(exclude_unset=True)
        set_clauses: list[str] = []
        values: list[object] = []
        for field in common_fields + variant_fields:
            if field not in patch_data:
                continue
            raw = patch_data[field]
            if raw is None:
                # Common and variant required fields are NOT NULL on the row;
                # explicit None on update is treated as "no change".
                continue
            set_clauses.append(f"{field} = ?")
            if field == "assumptions":
                values.append(json.dumps(raw))
            elif isinstance(raw, bool):
                values.append(int(raw))
            else:
                values.append(raw)

        if set_clauses:
            values.append(node_id)
            self._conn.execute(
                f"UPDATE node SET {', '.join(set_clauses)} WHERE id = ?",
                values,
            )
        return self.get(node_id)

    def delete(self, node_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM entity WHERE id = ? AND kind = 'node'",
            (node_id,),
        )
        return cursor.rowcount > 0

    def list(
        self,
        diagram_id: int,
        *,
        type: NodeType | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Node]:
        sql = (
            f"SELECT {_NODE_COLUMNS_QUALIFIED} FROM node "
            "JOIN entity ON entity.id = node.id "
            "WHERE entity.diagram_id = ?"
        )
        params: list[object] = [diagram_id]
        if type is not None:
            if type not in _NODE_TYPES:
                raise ValueError(f"Unknown node type filter: {type!r}")
            sql += " AND node.type = ?"
            params.append(type)
        sql += " ORDER BY node.id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_node(row) for row in rows]

    def search(
        self,
        diagram_id: int,
        text: str | None = None,
        *,
        type: NodeType | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Node]:
        sql = (
            f"SELECT {_NODE_COLUMNS_QUALIFIED} FROM node "
            "JOIN entity ON entity.id = node.id "
            "WHERE entity.diagram_id = ?"
        )
        params: list[object] = [diagram_id]
        if type is not None:
            if type not in _NODE_TYPES:
                raise ValueError(f"Unknown node type filter: {type!r}")
            sql += " AND node.type = ?"
            params.append(type)
        if text:
            clause, clause_params = _build_text_clause(text, _SEARCHABLE_TEXT_COLUMNS)
            if clause:
                sql += f" AND {clause}"
                params.extend(clause_params)
        sql += " ORDER BY node.id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_node(row) for row in rows]
