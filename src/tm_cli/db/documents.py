from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from tm_cli.db._search import _build_text_clause
from tm_cli.db.models import (
    Document,
    DocumentCreate,
    DocumentSummary,
    DocumentUpdate,
)

_SEARCHABLE_TEXT_COLUMNS = ("title", "author", "content")

_SUMMARY_COLUMNS = (
    "id, "
    'last_updated AS "last_updated [datetime]", '
    'last_imported AS "last_imported [datetime]", '
    "title, author"
)
_FULL_COLUMNS = f"{_SUMMARY_COLUMNS}, content"
_UPDATABLE_FIELDS = ("last_updated", "title", "author", "content")


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _row_to_document(row: sqlite3.Row) -> Document:
    return Document(**{key: row[key] for key in row.keys()})


def _row_to_summary(row: sqlite3.Row) -> DocumentSummary:
    return DocumentSummary(**{key: row[key] for key in row.keys()})


class DocumentRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, data: DocumentCreate) -> Document:
        cursor = self._conn.execute(
            "INSERT INTO documents "
            "(last_updated, last_imported, title, author, content) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                data.last_updated,
                _now_utc(),
                data.title,
                data.author,
                data.content,
            ),
        )
        new_id = cursor.lastrowid
        assert new_id is not None
        fetched = self.get(new_id)
        assert fetched is not None
        return fetched

    def get(self, doc_id: int) -> Document | None:
        row = self._conn.execute(
            f"SELECT {_FULL_COLUMNS} FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        return _row_to_document(row) if row is not None else None

    def update(self, doc_id: int, patch: DocumentUpdate) -> Document | None:
        if self.get(doc_id) is None:
            return None

        set_clauses: list[str] = ["last_imported = ?"]
        values: list[object] = [_now_utc()]

        patch_data = patch.model_dump(exclude_unset=True)
        for field in _UPDATABLE_FIELDS:
            if field in patch_data and patch_data[field] is not None:
                set_clauses.append(f"{field} = ?")
                values.append(patch_data[field])

        values.append(doc_id)
        self._conn.execute(
            f"UPDATE documents SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        return self.get(doc_id)

    def delete(self, doc_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM documents WHERE id = ?",
            (doc_id,),
        )
        return cursor.rowcount > 0

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DocumentSummary]:
        sql = f"SELECT {_SUMMARY_COLUMNS} FROM documents ORDER BY id ASC"
        params: list[object] = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_summary(row) for row in rows]

    def search(
        self,
        text: str | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DocumentSummary]:
        sql = f"SELECT {_SUMMARY_COLUMNS} FROM documents"
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
        return [_row_to_summary(row) for row in rows]
