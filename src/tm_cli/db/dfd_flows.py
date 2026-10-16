from __future__ import annotations

import sqlite3

from tm_cli.db._search import _build_text_clause
from tm_cli.db.dfd_items import _DATA_ITEM_COLUMNS_QUALIFIED, _row_to_data_item
from tm_cli.db.dfd_models import (
    DataFlow,
    DataFlowCreate,
    DataFlowUpdate,
    DataItem,
    SourceEndpoint,
)
from tm_cli.db.diagrams import _mint_entity_id

_FLOW_COLUMNS = "id, node1_id, node2_id, name, protocol, authenticated, encrypted"
_FLOW_COLUMNS_QUALIFIED = (
    "data_flow.id, data_flow.node1_id, data_flow.node2_id, "
    "data_flow.name, data_flow.protocol, "
    "data_flow.authenticated, data_flow.encrypted"
)
_SEARCHABLE_TEXT_COLUMNS = ("data_flow.name", "data_flow.protocol")
_UPDATABLE_FIELDS = ("name", "protocol", "authenticated", "encrypted")


def _row_to_flow(row: sqlite3.Row) -> DataFlow:
    return DataFlow(
        id=row["id"],
        node1_id=row["node1_id"],
        node2_id=row["node2_id"],
        name=row["name"],
        protocol=row["protocol"],
        authenticated=bool(row["authenticated"]),
        encrypted=bool(row["encrypted"]),
    )


def _entity_kind_diagram(
    conn: sqlite3.Connection, entity_id: int
) -> tuple[str, int] | None:
    row = conn.execute(
        "SELECT kind, diagram_id FROM entity WHERE id = ?",
        (entity_id,),
    ).fetchone()
    if row is None:
        return None
    return row["kind"], row["diagram_id"]


class DataFlowRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, diagram_id: int, data: DataFlowCreate) -> DataFlow:
        if data.node1_id == data.node2_id:
            raise ValueError("Self-loops are not allowed")

        for endpoint_id in (data.node1_id, data.node2_id):
            kd = _entity_kind_diagram(self._conn, endpoint_id)
            if kd is None or kd[0] != "node":
                raise ValueError(f"Endpoint {endpoint_id} is not a node entity")
            if kd[1] != diagram_id:
                raise ValueError(
                    f"Endpoint {endpoint_id} is not in diagram {diagram_id}"
                )

        a, b = sorted((data.node1_id, data.node2_id))
        flow_id = _mint_entity_id(self._conn, diagram_id, "data_flow")
        self._conn.execute(
            "INSERT INTO data_flow "
            "(id, node1_id, node2_id, name, protocol, authenticated, encrypted) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                flow_id,
                a,
                b,
                data.name,
                data.protocol,
                int(data.authenticated),
                int(data.encrypted),
            ),
        )
        fetched = self.get(flow_id)
        assert fetched is not None
        return fetched

    def get(self, flow_id: int) -> DataFlow | None:
        row = self._conn.execute(
            f"SELECT {_FLOW_COLUMNS} FROM data_flow WHERE id = ?",
            (flow_id,),
        ).fetchone()
        return _row_to_flow(row) if row is not None else None

    def update(self, flow_id: int, patch: DataFlowUpdate) -> DataFlow | None:
        if self.get(flow_id) is None:
            return None

        patch_data = patch.model_dump(exclude_unset=True)
        set_clauses: list[str] = []
        values: list[object] = []
        for field in _UPDATABLE_FIELDS:
            if field not in patch_data or patch_data[field] is None:
                continue
            raw = patch_data[field]
            set_clauses.append(f"{field} = ?")
            values.append(int(raw) if isinstance(raw, bool) else raw)

        if set_clauses:
            values.append(flow_id)
            self._conn.execute(
                f"UPDATE data_flow SET {', '.join(set_clauses)} WHERE id = ?",
                values,
            )
        return self.get(flow_id)

    def delete(self, flow_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM entity WHERE id = ? AND kind = 'data_flow'",
            (flow_id,),
        )
        return cursor.rowcount > 0

    def list(
        self,
        diagram_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DataFlow]:
        sql = (
            f"SELECT {_FLOW_COLUMNS_QUALIFIED} FROM data_flow "
            "JOIN entity ON entity.id = data_flow.id "
            "WHERE entity.diagram_id = ? "
            "ORDER BY data_flow.id ASC"
        )
        params: list[object] = [diagram_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_flow(row) for row in rows]

    def search(
        self,
        diagram_id: int,
        text: str | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DataFlow]:
        sql = (
            f"SELECT {_FLOW_COLUMNS_QUALIFIED} FROM data_flow "
            "JOIN entity ON entity.id = data_flow.id "
            "WHERE entity.diagram_id = ?"
        )
        params: list[object] = [diagram_id]
        if text:
            clause, clause_params = _build_text_clause(text, _SEARCHABLE_TEXT_COLUMNS)
            if clause:
                sql += f" AND {clause}"
                params.extend(clause_params)
        sql += " ORDER BY data_flow.id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_flow(row) for row in rows]

    def add_payload(
        self,
        flow_id: int,
        data_item_id: int,
        source_endpoint: SourceEndpoint,
    ) -> None:
        if source_endpoint not in (1, 2):
            raise ValueError(f"source_endpoint must be 1 or 2; got {source_endpoint!r}")
        flow_kd = _entity_kind_diagram(self._conn, flow_id)
        if flow_kd is None or flow_kd[0] != "data_flow":
            raise ValueError(f"flow_id {flow_id} is not a data_flow")
        item_kd = _entity_kind_diagram(self._conn, data_item_id)
        if item_kd is None or item_kd[0] != "data_item":
            raise ValueError(f"data_item_id {data_item_id} is not a data_item")
        if flow_kd[1] != item_kd[1]:
            raise ValueError("flow and data_item must belong to the same diagram")
        self._conn.execute(
            "INSERT OR IGNORE INTO flow_payload "
            "(flow_id, data_item_id, source_endpoint) VALUES (?, ?, ?)",
            (flow_id, data_item_id, source_endpoint),
        )

    def remove_payload(
        self,
        flow_id: int,
        data_item_id: int,
        source_endpoint: SourceEndpoint,
    ) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM flow_payload "
            "WHERE flow_id = ? AND data_item_id = ? AND source_endpoint = ?",
            (flow_id, data_item_id, source_endpoint),
        )
        return cursor.rowcount > 0

    def payload_for_flow(
        self,
        flow_id: int,
        *,
        source_endpoint: SourceEndpoint | None = None,
    ) -> list[DataItem]:
        sql = (
            f"SELECT {_DATA_ITEM_COLUMNS_QUALIFIED} FROM data_item "
            "JOIN flow_payload ON flow_payload.data_item_id = data_item.id "
            "WHERE flow_payload.flow_id = ?"
        )
        params: list[object] = [flow_id]
        if source_endpoint is not None:
            sql += " AND flow_payload.source_endpoint = ?"
            params.append(source_endpoint)
        sql += " ORDER BY data_item.id ASC"
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_data_item(row) for row in rows]

    def payloads_for_diagram(self, diagram_id: int) -> dict[int, dict[int, list[int]]]:
        """Bulk-load every flow_payload row for a diagram, grouped for export.

        Returns ``{flow_id: {1: [data_item_id, ...], 2: [...]}}``. Both endpoint
        keys (1 and 2) are always present for any flow that has at least one
        payload, so callers can index by endpoint without a ``KeyError``. The
        item-id lists are sorted ascending for deterministic output (the
        dfd_editor push body must be stable across re-pushes).
        """
        rows = self._conn.execute(
            "SELECT flow_payload.flow_id, flow_payload.source_endpoint, "
            "       flow_payload.data_item_id "
            "FROM flow_payload "
            "JOIN entity ON entity.id = flow_payload.flow_id "
            "WHERE entity.diagram_id = ? "
            "ORDER BY flow_payload.flow_id, flow_payload.source_endpoint, "
            "         flow_payload.data_item_id",
            (diagram_id,),
        ).fetchall()
        result: dict[int, dict[int, list[int]]] = {}
        for row in rows:
            by_endpoint = result.setdefault(row["flow_id"], {1: [], 2: []})
            by_endpoint[row["source_endpoint"]].append(row["data_item_id"])
        return result

    def flows_for_data_item(self, data_item_id: int) -> list[DataFlow]:
        rows = self._conn.execute(
            f"SELECT {_FLOW_COLUMNS_QUALIFIED} FROM data_flow "
            "JOIN flow_payload ON flow_payload.flow_id = data_flow.id "
            "WHERE flow_payload.data_item_id = ? "
            "ORDER BY data_flow.id ASC",
            (data_item_id,),
        ).fetchall()
        return [_row_to_flow(row) for row in rows]
