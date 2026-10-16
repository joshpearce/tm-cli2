# pattern: Imperative Shell
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from tm_cli.db._search import _build_text_clause
from tm_cli.db.dfd_models import Diagram, DiagramCreate, DiagramUpdate

_DIAGRAM_COLUMNS = (
    'id, name, description, author, created AS "created [datetime]",'
    " dfd_editor_diagram_id"
)
# Wrap nullable columns with IFNULL so NULL rows don't drop out of LIKE.
_SEARCHABLE_TEXT_COLUMNS = (
    "IFNULL(name, '')",
    "IFNULL(description, '')",
    "IFNULL(author, '')",
)
_UPDATABLE_FIELDS = ("name", "description", "author")


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _row_to_diagram(row: sqlite3.Row) -> Diagram:
    return Diagram(**{key: row[key] for key in row.keys()})


def _mint_entity_id(conn: sqlite3.Connection, diagram_id: int, kind: str) -> int:
    cursor = conn.execute(
        "INSERT INTO entity (diagram_id, kind) VALUES (?, ?)",
        (diagram_id, kind),
    )
    new_id = cursor.lastrowid
    assert new_id is not None
    return new_id


class DiagramRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, data: DiagramCreate) -> Diagram:
        cursor = self._conn.execute(
            "INSERT INTO diagram (name, description, author, created) "
            "VALUES (?, ?, ?, ?)",
            (data.name, data.description, data.author, _now_utc()),
        )
        new_id = cursor.lastrowid
        assert new_id is not None
        fetched = self.get(new_id)
        assert fetched is not None
        return fetched

    def get(self, diagram_id: int) -> Diagram | None:
        row = self._conn.execute(
            f"SELECT {_DIAGRAM_COLUMNS} FROM diagram WHERE id = ?",
            (diagram_id,),
        ).fetchone()
        return _row_to_diagram(row) if row is not None else None

    def update(self, diagram_id: int, patch: DiagramUpdate) -> Diagram | None:
        if self.get(diagram_id) is None:
            return None

        # Nullable fields use exclude_unset semantics: callers may clear by
        # passing None. The "is not None" guard from documents.py is omitted.
        patch_data = patch.model_dump(exclude_unset=True)
        if not patch_data:
            return self.get(diagram_id)

        set_clauses = [
            f"{field} = ?" for field in _UPDATABLE_FIELDS if field in patch_data
        ]
        values: list[object] = [
            patch_data[field] for field in _UPDATABLE_FIELDS if field in patch_data
        ]
        values.append(diagram_id)
        self._conn.execute(
            f"UPDATE diagram SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        return self.get(diagram_id)

    def delete(self, diagram_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM diagram WHERE id = ?",
            (diagram_id,),
        )
        return cursor.rowcount > 0

    def set_remote_id(self, diagram_id: int, remote_uuid: str) -> None:
        """Persist the dfd_editor-minted diagram UUID on this row."""
        cursor = self._conn.execute(
            "UPDATE diagram SET dfd_editor_diagram_id = ? WHERE id = ?",
            (remote_uuid, diagram_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Diagram id={diagram_id} not found")

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Diagram]:
        sql = f"SELECT {_DIAGRAM_COLUMNS} FROM diagram ORDER BY id ASC"
        params: list[object] = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_diagram(row) for row in rows]

    def search(
        self,
        text: str | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Diagram]:
        sql = f"SELECT {_DIAGRAM_COLUMNS} FROM diagram"
        params: list[object] = []
        if text:
            clause, clause_params = _build_text_clause(text, _SEARCHABLE_TEXT_COLUMNS)
            if clause:
                sql += f" WHERE {clause}"
                params.extend(clause_params)
        sql += " ORDER BY id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_diagram(row) for row in rows]
