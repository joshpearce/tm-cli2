from __future__ import annotations

import sqlite3
from typing import TypedDict

from tm_cli.db.dfd_containers import (
    _CONTAINER_COLUMNS_QUALIFIED,
    _row_to_container,
)
from tm_cli.db.dfd_flows import _FLOW_COLUMNS_QUALIFIED, _row_to_flow
from tm_cli.db.dfd_items import (
    _DATA_ITEM_COLUMNS_QUALIFIED,
    _row_to_data_item,
)
from tm_cli.db.dfd_models import Container, DataFlow, DataItem, Node, ProcessComponent
from tm_cli.db.dfd_nodes import _NODE_COLUMNS_QUALIFIED, _row_to_node
from tm_cli.db.dfd_process_components import (
    _COMPONENT_COLUMNS_QUALIFIED,
    _row_to_component,
)
from tm_cli.db.models import Observation

# _OBSERVATION_COLUMNS and _row_to_observation are the canonical definitions in
# observations.py. They are imported here so this module does not duplicate them.
# observations.py uses a lazy (function-local) import of EntityObservationRepository
# to avoid the circular module-level import cycle.
from tm_cli.db.observations import _OBSERVATION_COLUMNS, _row_to_observation

# NOTE: _KIND_TO_FIELD must be updated alongside the SQL CHECK in connection.py
# any time a new entity kind is added — both are paired update sites.
_KIND_TO_FIELD: dict[str, str] = {
    "node": "node_ids",
    "container": "container_ids",
    "data_flow": "flow_ids",
    "data_item": "data_item_ids",
    "process_component": "process_component_ids",
}


class LinkedIds(TypedDict):
    node_ids: list[int]
    container_ids: list[int]
    flow_ids: list[int]
    data_item_ids: list[int]
    process_component_ids: list[int]


def _empty_linked_ids() -> LinkedIds:
    return {
        "node_ids": [],
        "container_ids": [],
        "flow_ids": [],
        "data_item_ids": [],
        "process_component_ids": [],
    }


class EntityObservationRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def link(self, entity_id: int, observation_id: int) -> None:
        """Idempotently link an entity and an observation.

        Raises sqlite3.IntegrityError if either id does not exist (FK violation;
        uniqueness conflicts are suppressed by ``INSERT OR IGNORE``).
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO entity_observations (entity_id, observation_id) "
            "VALUES (?, ?)",
            (entity_id, observation_id),
        )

    def is_linked(self, entity_id: int, observation_id: int) -> bool:
        """Return True iff the entity-observation pair exists in entity_observations."""
        row = self._conn.execute(
            "SELECT 1 FROM entity_observations "
            "WHERE entity_id = ? AND observation_id = ?",
            (entity_id, observation_id),
        ).fetchone()
        return row is not None

    def unlink(self, entity_id: int, observation_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM entity_observations "
            "WHERE entity_id = ? AND observation_id = ?",
            (entity_id, observation_id),
        )
        return cursor.rowcount > 0

    def observations_for_entity(self, entity_id: int) -> list[Observation]:
        from tm_cli.db.observations import _attach_linked_ids

        rows_raw = self._conn.execute(
            f"SELECT {_OBSERVATION_COLUMNS} FROM observations "
            "JOIN entity_observations "
            "    ON entity_observations.observation_id = observations.id "
            "WHERE entity_observations.entity_id = ? "
            "ORDER BY observations.id ASC",
            (entity_id,),
        ).fetchall()
        obs_rows = [_row_to_observation(row) for row in rows_raw]
        if not obs_rows:
            return obs_rows
        linked_ids_map = self.linked_ids_by_kind_for([r.id for r in obs_rows])
        _attach_linked_ids(obs_rows, linked_ids_map)
        return obs_rows

    def nodes_for_observation(self, observation_id: int) -> list[Node]:
        rows = self._conn.execute(
            f"SELECT {_NODE_COLUMNS_QUALIFIED} FROM node "
            "JOIN entity_observations "
            "    ON entity_observations.entity_id = node.id "
            "WHERE entity_observations.observation_id = ? "
            "ORDER BY node.id ASC",
            (observation_id,),
        ).fetchall()
        return [_row_to_node(row) for row in rows]

    def containers_for_observation(self, observation_id: int) -> list[Container]:
        rows = self._conn.execute(
            f"SELECT {_CONTAINER_COLUMNS_QUALIFIED} FROM container "
            "JOIN entity_observations "
            "    ON entity_observations.entity_id = container.id "
            "WHERE entity_observations.observation_id = ? "
            "ORDER BY container.id ASC",
            (observation_id,),
        ).fetchall()
        return [_row_to_container(row) for row in rows]

    def flows_for_observation(self, observation_id: int) -> list[DataFlow]:
        rows = self._conn.execute(
            f"SELECT {_FLOW_COLUMNS_QUALIFIED} FROM data_flow "
            "JOIN entity_observations "
            "    ON entity_observations.entity_id = data_flow.id "
            "WHERE entity_observations.observation_id = ? "
            "ORDER BY data_flow.id ASC",
            (observation_id,),
        ).fetchall()
        return [_row_to_flow(row) for row in rows]

    def items_for_observation(self, observation_id: int) -> list[DataItem]:
        rows = self._conn.execute(
            f"SELECT {_DATA_ITEM_COLUMNS_QUALIFIED} FROM data_item "
            "JOIN entity_observations "
            "    ON entity_observations.entity_id = data_item.id "
            "WHERE entity_observations.observation_id = ? "
            "ORDER BY data_item.id ASC",
            (observation_id,),
        ).fetchall()
        return [_row_to_data_item(row) for row in rows]

    def process_components_for_observation(
        self, observation_id: int
    ) -> list[ProcessComponent]:
        rows = self._conn.execute(
            f"SELECT {_COMPONENT_COLUMNS_QUALIFIED} FROM process_component "
            "JOIN entity_observations "
            "    ON entity_observations.entity_id = process_component.id "
            "WHERE entity_observations.observation_id = ? "
            "ORDER BY process_component.id ASC",
            (observation_id,),
        ).fetchall()
        return [_row_to_component(row) for row in rows]

    def linked_ids_by_kind(self, observation_id: int) -> LinkedIds:
        """Return entity ids bucketed by kind for a single observation."""
        rows = self._conn.execute(
            "SELECT eo.entity_id, entity.kind "
            "FROM entity_observations eo "
            "JOIN entity ON entity.id = eo.entity_id "
            "WHERE eo.observation_id = ? "
            "ORDER BY entity.id ASC",
            (observation_id,),
        ).fetchall()
        result = _empty_linked_ids()
        for row in rows:
            # KeyError surfaces unknown kinds immediately
            field = _KIND_TO_FIELD[row["kind"]]
            result[field].append(row["entity_id"])  # type: ignore[literal-required]
        return result

    def linked_ids_by_kind_for(
        self, observation_ids: list[int]
    ) -> dict[int, LinkedIds]:
        """Return entity ids bucketed by kind for a batch of observations.

        Keys are present for every input observation_id (empty LinkedIds for
        observations with no links). Returns {} for empty input.
        """
        if not observation_ids:
            return {}
        placeholders = ",".join(["?"] * len(observation_ids))
        rows = self._conn.execute(
            "SELECT eo.observation_id, eo.entity_id, entity.kind "
            "FROM entity_observations eo "
            "JOIN entity ON entity.id = eo.entity_id "
            f"WHERE eo.observation_id IN ({placeholders}) "
            "ORDER BY eo.observation_id ASC, entity.id ASC",
            observation_ids,
        ).fetchall()

        # Seed every requested id with an empty bucket so keys are always present.
        result: dict[int, LinkedIds] = {
            obs_id: _empty_linked_ids() for obs_id in observation_ids
        }
        for row in rows:
            obs_id = row["observation_id"]
            # KeyError surfaces unknown kinds immediately
            field = _KIND_TO_FIELD[row["kind"]]
            result[obs_id][field].append(row["entity_id"])  # type: ignore[literal-required]
        return result
