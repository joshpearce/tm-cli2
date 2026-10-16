from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from tm_cli.db._search import _build_text_clause
from tm_cli.db.documents import (
    _SUMMARY_COLUMNS as _DOCUMENT_SUMMARY_COLUMNS,
)
from tm_cli.db.documents import (
    _row_to_summary as _row_to_document_summary,
)
from tm_cli.db.models import (
    DocumentSummary,
    Term,
    TermCreate,
    TermUpdate,
)

_TERM_COLUMNS = 'id, term, definition, last_updated AS "last_updated [datetime]"'
_SEARCHABLE_TEXT_COLUMNS = ("term", "definition")
_UPDATABLE_FIELDS = ("term", "definition")


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _row_to_term(row: sqlite3.Row) -> Term:
    return Term(**{key: row[key] for key in row.keys()})


class TermRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, data: TermCreate) -> Term:
        """Insert a term. Raises sqlite3.IntegrityError on duplicate term."""
        cursor = self._conn.execute(
            "INSERT INTO terms (term, definition, last_updated) VALUES (?, ?, ?)",
            (data.term, data.definition, _now_utc()),
        )
        new_id = cursor.lastrowid
        assert new_id is not None
        fetched = self.get(new_id)
        assert fetched is not None
        return fetched

    def get(self, term_id: int) -> Term | None:
        row = self._conn.execute(
            f"SELECT {_TERM_COLUMNS} FROM terms WHERE id = ?",
            (term_id,),
        ).fetchone()
        return _row_to_term(row) if row is not None else None

    def get_by_term(self, term: str) -> Term | None:
        row = self._conn.execute(
            f"SELECT {_TERM_COLUMNS} FROM terms WHERE term = ?",
            (term,),
        ).fetchone()
        return _row_to_term(row) if row is not None else None

    def update(self, term_id: int, patch: TermUpdate) -> Term | None:
        if self.get(term_id) is None:
            return None

        set_clauses: list[str] = ["last_updated = ?"]
        values: list[object] = [_now_utc()]

        patch_data = patch.model_dump(exclude_unset=True)
        for field in _UPDATABLE_FIELDS:
            if field in patch_data and patch_data[field] is not None:
                set_clauses.append(f"{field} = ?")
                values.append(patch_data[field])

        values.append(term_id)
        self._conn.execute(
            f"UPDATE terms SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        return self.get(term_id)

    def delete(self, term_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM terms WHERE id = ?",
            (term_id,),
        )
        return cursor.rowcount > 0

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Term]:
        sql = f"SELECT {_TERM_COLUMNS} FROM terms ORDER BY id ASC"
        params: list[object] = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_term(row) for row in rows]

    def search(
        self,
        text: str | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Term]:
        sql = f"SELECT {_TERM_COLUMNS} FROM terms"
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
        return [_row_to_term(row) for row in rows]

    def link(self, document_id: int, term_id: int) -> None:
        """Idempotently link a document and a term."""
        self._conn.execute(
            "INSERT OR IGNORE INTO document_terms (document_id, term_id) VALUES (?, ?)",
            (document_id, term_id),
        )

    def unlink(self, document_id: int, term_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM document_terms WHERE document_id = ? AND term_id = ?",
            (document_id, term_id),
        )
        return cursor.rowcount > 0

    def documents_for_term(self, term_id: int) -> list[DocumentSummary]:
        rows = self._conn.execute(
            f"SELECT {_DOCUMENT_SUMMARY_COLUMNS} FROM documents "
            "JOIN document_terms ON document_terms.document_id = documents.id "
            "WHERE document_terms.term_id = ? "
            "ORDER BY documents.id ASC",
            (term_id,),
        ).fetchall()
        return [_row_to_document_summary(row) for row in rows]

    def terms_for_document(self, document_id: int) -> list[Term]:
        rows = self._conn.execute(
            f"SELECT {_TERM_COLUMNS} FROM terms "
            "JOIN document_terms ON document_terms.term_id = terms.id "
            "WHERE document_terms.document_id = ? "
            "ORDER BY terms.id ASC",
            (document_id,),
        ).fetchall()
        return [_row_to_term(row) for row in rows]
