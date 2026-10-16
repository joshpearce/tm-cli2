from __future__ import annotations

import sqlite3

from tm_cli.db._search import _build_text_clause
from tm_cli.db.models import ThreatCatalogCreate, ThreatCatalogEntry

_CATALOG_COLUMNS = "id, mitre_id, name, platforms, description"
_SEARCHABLE_TEXT_COLUMNS = ("name", "description", "mitre_id")


class ThreatCatalogRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def ensure_tactic(self, name: str) -> int:
        """INSERT OR IGNORE + SELECT id for a tactic name."""
        self._conn.execute("INSERT OR IGNORE INTO tactic (name) VALUES (?)", (name,))
        row = self._conn.execute(
            "SELECT id FROM tactic WHERE name = ?", (name,)
        ).fetchone()
        assert row is not None
        return row["id"]

    def create(
        self, data: ThreatCatalogCreate, tactic_names: list[str]
    ) -> ThreatCatalogEntry:
        """Create or return existing catalog entry, linking to tactics.

        Deduplicates by ``mitre_id``: if the technique already exists the
        existing row is reused and any new tactic links are added.
        """
        existing = self._conn.execute(
            "SELECT id FROM threat_catalog WHERE mitre_id = ?", (data.mitre_id,)
        ).fetchone()

        if existing is not None:
            catalog_id = existing["id"]
        else:
            cursor = self._conn.execute(
                "INSERT INTO threat_catalog (mitre_id, name, platforms, description) "
                "VALUES (?, ?, ?, ?)",
                (data.mitre_id, data.name, data.platforms, data.description),
            )
            catalog_id = cursor.lastrowid
            assert catalog_id is not None

        for tactic_name in tactic_names:
            tactic_id = self.ensure_tactic(tactic_name)
            self._conn.execute(
                "INSERT OR IGNORE INTO technique_tactics (technique_id, tactic_id) "
                "VALUES (?, ?)",
                (catalog_id, tactic_id),
            )

        result = self.get(catalog_id)
        assert result is not None
        return result

    def get(self, catalog_id: int) -> ThreatCatalogEntry | None:
        row = self._conn.execute(
            f"SELECT {_CATALOG_COLUMNS} FROM threat_catalog WHERE id = ?",
            (catalog_id,),
        ).fetchone()
        if row is None:
            return None
        entry = ThreatCatalogEntry(**{k: row[k] for k in row.keys()})
        entry.tactics = self._tactics_for(catalog_id)
        return entry

    def exists(self, catalog_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM threat_catalog WHERE id = ?", (catalog_id,)
        ).fetchone()
        return row is not None

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ThreatCatalogEntry]:
        sql = f"SELECT {_CATALOG_COLUMNS} FROM threat_catalog ORDER BY id ASC"
        params: list[object] = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        raw_rows = self._conn.execute(sql, params).fetchall()
        entries = [ThreatCatalogEntry(**{k: r[k] for k in r.keys()}) for r in raw_rows]
        if entries:
            tactics_map = self._tactics_for_batch([e.id for e in entries])
            for e in entries:
                e.tactics = tactics_map[e.id]
        return entries

    def search(
        self,
        text: str | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ThreatCatalogEntry]:
        sql = f"SELECT {_CATALOG_COLUMNS} FROM threat_catalog"
        where: list[str] = []
        params: list[object] = []
        if text:
            clause, clause_params = _build_text_clause(text, _SEARCHABLE_TEXT_COLUMNS)
            if clause:
                where.append(clause)
                params.extend(clause_params)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        raw_rows = self._conn.execute(sql, params).fetchall()
        entries = [ThreatCatalogEntry(**{k: r[k] for k in r.keys()}) for r in raw_rows]
        if entries:
            tactics_map = self._tactics_for_batch([e.id for e in entries])
            for e in entries:
                e.tactics = tactics_map[e.id]
        return entries

    def _tactics_for(self, catalog_id: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT t.name FROM tactic t "
            "JOIN technique_tactics tt ON tt.tactic_id = t.id "
            "WHERE tt.technique_id = ? ORDER BY t.name",
            (catalog_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def _tactics_for_batch(self, catalog_ids: list[int]) -> dict[int, list[str]]:
        if not catalog_ids:
            return {}
        placeholders = ",".join(["?"] * len(catalog_ids))
        rows = self._conn.execute(
            "SELECT tt.technique_id, t.name FROM tactic t "
            "JOIN technique_tactics tt ON tt.tactic_id = t.id "
            f"WHERE tt.technique_id IN ({placeholders}) "
            "ORDER BY tt.technique_id, t.name",
            catalog_ids,
        ).fetchall()
        result: dict[int, list[str]] = {cid: [] for cid in catalog_ids}
        for r in rows:
            result[r["technique_id"]].append(r["name"])
        return result
