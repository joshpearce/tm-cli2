from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from tm_cli.db._search import _build_text_clause
from tm_cli.db.dfd_models import (
    FindingSeverity,
    ValidationFinding,
    ValidationFindingCreate,
    ValidationFindingUpdate,
)

_FINDING_COLUMNS = (
    "id, diagram_id, entity_id, severity, message, source, code, "
    'created AS "created [datetime]"'
)
_REQUIRED_FIELDS = ("severity", "message", "source")
_NULLABLE_FIELDS = ("code",)
_SEARCHABLE_TEXT_COLUMNS = (
    "validation_finding.message",
    "IFNULL(validation_finding.code, '')",
)


def _row_to_finding(row: sqlite3.Row) -> ValidationFinding:
    return ValidationFinding(**{key: row[key] for key in row.keys()})


def _entity_diagram_id(conn: sqlite3.Connection, entity_id: int) -> int | None:
    """Return the diagram_id for entity_id, or None if not found."""
    row = conn.execute(
        "SELECT diagram_id FROM entity WHERE id = ?",
        (entity_id,),
    ).fetchone()
    return row["diagram_id"] if row is not None else None


class ValidationFindingRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self, diagram_id: int, data: ValidationFindingCreate
    ) -> ValidationFinding:
        if data.entity_id is not None:
            entity_diagram = _entity_diagram_id(self._conn, data.entity_id)
            if entity_diagram is None:
                raise ValueError(f"entity_id {data.entity_id} does not exist")
            if entity_diagram != diagram_id:
                raise ValueError("entity_id must belong to the same diagram")

        created = datetime.now(UTC)
        cursor = self._conn.execute(
            "INSERT INTO validation_finding "
            "(diagram_id, entity_id, severity, message, source, code, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                diagram_id,
                data.entity_id,
                data.severity,
                data.message,
                data.source,
                data.code,
                created,
            ),
        )
        new_id = cursor.lastrowid
        assert new_id is not None
        fetched = self.get(new_id)
        assert fetched is not None
        return fetched

    def get(self, finding_id: int) -> ValidationFinding | None:
        row = self._conn.execute(
            f"SELECT {_FINDING_COLUMNS} FROM validation_finding WHERE id = ?",
            (finding_id,),
        ).fetchone()
        return _row_to_finding(row) if row is not None else None

    def update(
        self, finding_id: int, patch: ValidationFindingUpdate
    ) -> ValidationFinding | None:
        if self.get(finding_id) is None:
            return None

        patch_data = patch.model_dump(exclude_unset=True)
        if not patch_data:
            return self.get(finding_id)

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
            values.append(finding_id)
            self._conn.execute(
                f"UPDATE validation_finding SET {', '.join(set_clauses)} WHERE id = ?",
                values,
            )
        return self.get(finding_id)

    def delete(self, finding_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM validation_finding WHERE id = ?",
            (finding_id,),
        )
        return cursor.rowcount > 0

    def list(
        self,
        diagram_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ValidationFinding]:
        sql = (
            f"SELECT {_FINDING_COLUMNS} FROM validation_finding "
            "WHERE diagram_id = ? "
            "ORDER BY id ASC"
        )
        params: list[object] = [diagram_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_finding(row) for row in rows]

    def search(
        self,
        diagram_id: int,
        text: str | None = None,
        *,
        severity: FindingSeverity | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ValidationFinding]:
        sql = f"SELECT {_FINDING_COLUMNS} FROM validation_finding WHERE diagram_id = ?"
        params: list[object] = [diagram_id]
        if severity is not None:
            sql += " AND severity = ?"
            params.append(severity)
        if source is not None:
            sql += " AND source = ?"
            params.append(source)
        if text:
            clause, clause_params = _build_text_clause(text, _SEARCHABLE_TEXT_COLUMNS)
            if clause:
                sql += f" AND {clause}"
                params.extend(clause_params)
        sql += " ORDER BY id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_finding(row) for row in rows]

    def clear(self, diagram_id: int, *, source: str | None = None) -> int:
        """Bulk delete findings for a diagram. Returns count deleted."""
        if source is not None:
            cursor = self._conn.execute(
                "DELETE FROM validation_finding WHERE diagram_id = ? AND source = ?",
                (diagram_id, source),
            )
        else:
            cursor = self._conn.execute(
                "DELETE FROM validation_finding WHERE diagram_id = ?",
                (diagram_id,),
            )
        return cursor.rowcount

    def for_diagram(self, diagram_id: int) -> list[ValidationFinding]:
        """Return all findings for a diagram (no limit). Used by the push path."""
        rows = self._conn.execute(
            f"SELECT {_FINDING_COLUMNS} FROM validation_finding "
            "WHERE diagram_id = ? "
            "ORDER BY id ASC",
            (diagram_id,),
        ).fetchall()
        return [_row_to_finding(row) for row in rows]
