from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from tm_cli.db._search import _build_text_clause
from tm_cli.db.models import Threat, ThreatCreate, ThreatRating, ThreatUpdate

_THREAT_COLUMNS = (
    "id, threat_catalog_id, title, scenario, rating, description, "
    "mitre_reference, observed_mitigations, recommendations, "
    'last_updated AS "last_updated [datetime]"'
)
_SEARCHABLE_TEXT_COLUMNS = ("title", "scenario", "description", "mitre_reference")
_UPDATABLE_FIELDS = (
    "threat_catalog_id",
    "title",
    "scenario",
    "rating",
    "description",
    "mitre_reference",
    "observed_mitigations",
    "recommendations",
)
_NULLABLE_FIELDS = frozenset({"threat_catalog_id"})


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _row_to_threat(row: sqlite3.Row) -> Threat:
    return Threat(**{key: row[key] for key in row.keys()})


class ThreatRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, data: ThreatCreate) -> Threat:
        cursor = self._conn.execute(
            "INSERT INTO threat "
            "(threat_catalog_id, title, scenario, rating, description, "
            "mitre_reference, observed_mitigations, recommendations, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.threat_catalog_id,
                data.title,
                data.scenario,
                data.rating,
                data.description,
                data.mitre_reference,
                data.observed_mitigations,
                data.recommendations,
                _now_utc(),
            ),
        )
        new_id = cursor.lastrowid
        assert new_id is not None
        fetched = self.get(new_id)
        assert fetched is not None
        return fetched

    def exists(self, threat_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM threat WHERE id = ?", (threat_id,)
        ).fetchone()
        return row is not None

    def get(self, threat_id: int) -> Threat | None:
        row = self._conn.execute(
            f"SELECT {_THREAT_COLUMNS} FROM threat WHERE id = ?",
            (threat_id,),
        ).fetchone()
        if row is None:
            return None
        threat = _row_to_threat(row)
        threat.observation_ids = self._observation_ids_for(threat_id)
        threat.entity_ids = self._entity_ids_for(threat_id)
        return threat

    def update(self, threat_id: int, patch: ThreatUpdate) -> Threat | None:
        if self.get(threat_id) is None:
            return None

        set_clauses: list[str] = ["last_updated = ?"]
        values: list[object] = [_now_utc()]

        patch_data = patch.model_dump(exclude_unset=True)
        for field in _UPDATABLE_FIELDS:
            if field in patch_data:
                if field in _NULLABLE_FIELDS or patch_data[field] is not None:
                    set_clauses.append(f"{field} = ?")
                    values.append(patch_data[field])

        values.append(threat_id)
        self._conn.execute(
            f"UPDATE threat SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        return self.get(threat_id)

    def delete(self, threat_id: int) -> bool:
        cursor = self._conn.execute("DELETE FROM threat WHERE id = ?", (threat_id,))
        return cursor.rowcount > 0

    def list(
        self,
        *,
        rating: ThreatRating | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Threat]:
        sql = f"SELECT {_THREAT_COLUMNS} FROM threat"
        where: list[str] = []
        params: list[object] = []
        if rating is not None:
            where.append("rating = ?")
            params.append(rating)
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
        threats = [_row_to_threat(r) for r in raw_rows]
        if threats:
            self._attach_linked_ids(threats)
        return threats

    def search(
        self,
        text: str | None = None,
        *,
        rating: ThreatRating | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Threat]:
        sql = f"SELECT {_THREAT_COLUMNS} FROM threat"
        where: list[str] = []
        params: list[object] = []
        if rating is not None:
            where.append("rating = ?")
            params.append(rating)
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
        threats = [_row_to_threat(r) for r in raw_rows]
        if threats:
            self._attach_linked_ids(threats)
        return threats

    def link_observation(self, threat_id: int, observation_id: int) -> None:
        """Idempotently link a threat to an observation."""
        self._conn.execute(
            "INSERT OR IGNORE INTO threat_observations (threat_id, observation_id) "
            "VALUES (?, ?)",
            (threat_id, observation_id),
        )

    def unlink_observation(self, threat_id: int, observation_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM threat_observations "
            "WHERE threat_id = ? AND observation_id = ?",
            (threat_id, observation_id),
        )
        return cursor.rowcount > 0

    def link_entity(self, threat_id: int, entity_id: int) -> None:
        """Idempotently link a threat to a DFD entity."""
        self._conn.execute(
            "INSERT OR IGNORE INTO threat_entities (threat_id, entity_id) "
            "VALUES (?, ?)",
            (threat_id, entity_id),
        )

    def unlink_entity(self, threat_id: int, entity_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM threat_entities WHERE threat_id = ? AND entity_id = ?",
            (threat_id, entity_id),
        )
        return cursor.rowcount > 0

    def _observation_ids_for(self, threat_id: int) -> list[int]:
        rows = self._conn.execute(
            "SELECT observation_id FROM threat_observations "
            "WHERE threat_id = ? ORDER BY observation_id",
            (threat_id,),
        ).fetchall()
        return [r["observation_id"] for r in rows]

    def _entity_ids_for(self, threat_id: int) -> list[int]:
        rows = self._conn.execute(
            "SELECT entity_id FROM threat_entities "
            "WHERE threat_id = ? ORDER BY entity_id",
            (threat_id,),
        ).fetchall()
        return [r["entity_id"] for r in rows]

    def _observation_ids_batch(self, threat_ids: list[int]) -> dict[int, list[int]]:
        if not threat_ids:
            return {}
        placeholders = ",".join(["?"] * len(threat_ids))
        rows = self._conn.execute(
            "SELECT threat_id, observation_id FROM threat_observations "
            f"WHERE threat_id IN ({placeholders}) "
            "ORDER BY threat_id, observation_id",
            threat_ids,
        ).fetchall()
        result: dict[int, list[int]] = {tid: [] for tid in threat_ids}
        for r in rows:
            result[r["threat_id"]].append(r["observation_id"])
        return result

    def _entity_ids_batch(self, threat_ids: list[int]) -> dict[int, list[int]]:
        if not threat_ids:
            return {}
        placeholders = ",".join(["?"] * len(threat_ids))
        rows = self._conn.execute(
            "SELECT threat_id, entity_id FROM threat_entities "
            f"WHERE threat_id IN ({placeholders}) "
            "ORDER BY threat_id, entity_id",
            threat_ids,
        ).fetchall()
        result: dict[int, list[int]] = {tid: [] for tid in threat_ids}
        for r in rows:
            result[r["threat_id"]].append(r["entity_id"])
        return result

    def _attach_linked_ids(self, threats: list[Threat]) -> None:
        ids = [t.id for t in threats]
        obs_map = self._observation_ids_batch(ids)
        ent_map = self._entity_ids_batch(ids)
        for t in threats:
            t.observation_ids = obs_map[t.id]
            t.entity_ids = ent_map[t.id]
