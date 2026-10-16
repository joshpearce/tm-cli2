# pattern: Imperative Shell
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from tm_cli.db._search import _build_text_clause
from tm_cli.db.models import (
    Observation,
    ObservationCreate,
    ObservationStatus,
    ObservationType,
    ObservationUpdate,
)

if TYPE_CHECKING:
    from tm_cli.db.entity_observations import EntityObservationRepository, LinkedIds

_OBSERVATION_COLUMNS = (
    'id, content, observation_type, status, last_updated AS "last_updated [datetime]"'
)
_SEARCHABLE_TEXT_COLUMNS = ("content",)
_UPDATABLE_FIELDS = ("content", "observation_type", "status")


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _eo_repo(conn: sqlite3.Connection) -> EntityObservationRepository:
    from tm_cli.db.entity_observations import EntityObservationRepository

    return EntityObservationRepository(conn)


def _row_to_observation(row: sqlite3.Row) -> Observation:
    return Observation(**{key: row[key] for key in row.keys()})


def _attach_linked_ids(
    rows: list[Observation],
    linked_ids_map: dict[int, LinkedIds],
) -> None:
    """Attach *_ids fields to each Observation row in-place.

    Callers must pass a map produced by ``linked_ids_by_kind_for``, which
    guarantees a key for every requested obs.id. KeyError here means the
    invariant was violated.
    """
    for obs in rows:
        ids = linked_ids_map[obs.id]
        obs.node_ids = ids["node_ids"]
        obs.container_ids = ids["container_ids"]
        obs.flow_ids = ids["flow_ids"]
        obs.data_item_ids = ids["data_item_ids"]


class ObservationRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, data: ObservationCreate) -> Observation:
        cursor = self._conn.execute(
            "INSERT INTO observations "
            "(content, observation_type, status, last_updated) "
            "VALUES (?, ?, ?, ?)",
            (data.content, data.observation_type, data.status, _now_utc()),
        )
        new_id = cursor.lastrowid
        assert new_id is not None
        fetched = self.get(new_id)
        assert fetched is not None
        return fetched

    def exists(self, observation_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM observations WHERE id = ?",
            (observation_id,),
        ).fetchone()
        return row is not None

    def get(self, observation_id: int) -> Observation | None:
        row = self._conn.execute(
            f"SELECT {_OBSERVATION_COLUMNS} FROM observations WHERE id = ?",
            (observation_id,),
        ).fetchone()
        if row is None:
            return None
        obs = _row_to_observation(row)
        linked = _eo_repo(self._conn).linked_ids_by_kind(observation_id)
        obs.node_ids = linked["node_ids"]
        obs.container_ids = linked["container_ids"]
        obs.flow_ids = linked["flow_ids"]
        obs.data_item_ids = linked["data_item_ids"]
        return obs

    def update(
        self, observation_id: int, patch: ObservationUpdate
    ) -> Observation | None:
        if self.get(observation_id) is None:
            return None

        set_clauses: list[str] = ["last_updated = ?"]
        values: list[object] = [_now_utc()]

        patch_data = patch.model_dump(exclude_unset=True)
        for field in _UPDATABLE_FIELDS:
            if field in patch_data and patch_data[field] is not None:
                set_clauses.append(f"{field} = ?")
                values.append(patch_data[field])

        values.append(observation_id)
        self._conn.execute(
            f"UPDATE observations SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        return self.get(observation_id)

    def delete(self, observation_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM observations WHERE id = ?",
            (observation_id,),
        )
        return cursor.rowcount > 0

    def list(
        self,
        *,
        observation_type: ObservationType | None = None,
        status: ObservationStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Observation]:
        sql = f"SELECT {_OBSERVATION_COLUMNS} FROM observations"
        where: list[str] = []
        params: list[object] = []
        if observation_type is not None:
            where.append("observation_type = ?")
            params.append(observation_type)
        if status is not None:
            where.append("status = ?")
            params.append(status)
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
        obs_rows = [_row_to_observation(row) for row in raw_rows]
        if obs_rows:
            linked_map = _eo_repo(self._conn).linked_ids_by_kind_for(
                [r.id for r in obs_rows]
            )
            _attach_linked_ids(obs_rows, linked_map)
        return obs_rows

    def search(
        self,
        text: str | None = None,
        *,
        observation_type: ObservationType | None = None,
        status: ObservationStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Observation]:
        sql = f"SELECT {_OBSERVATION_COLUMNS} FROM observations"
        where: list[str] = []
        params: list[object] = []
        if observation_type is not None:
            where.append("observation_type = ?")
            params.append(observation_type)
        if status is not None:
            where.append("status = ?")
            params.append(status)
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
        obs_rows = [_row_to_observation(row) for row in raw_rows]
        if obs_rows:
            linked_map = _eo_repo(self._conn).linked_ids_by_kind_for(
                [r.id for r in obs_rows]
            )
            _attach_linked_ids(obs_rows, linked_map)
        return obs_rows
