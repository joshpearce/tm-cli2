from __future__ import annotations

import sqlite3

from tm_cli.db._search import _build_text_clause
from tm_cli.db.dfd_models import (
    Container,
    ContainerCreate,
    ContainerUpdate,
    ContainerVariant,
    ContainerVariantCreate,
    ContainerVariantUpdate,
    Node,
    TrustBoundary,
    TrustBoundaryCreate,
    TrustBoundaryUpdate,
)
from tm_cli.db.dfd_nodes import _row_to_node
from tm_cli.db.diagrams import _mint_entity_id

_CONTAINER_COLUMNS = "id, type, name, description, privilege_level"
_CONTAINER_COLUMNS_QUALIFIED = (
    "container.id, container.type, container.name, "
    "container.description, container.privilege_level"
)
_SEARCHABLE_TEXT_COLUMNS = ("container.name", "container.description")
_NODE_COLUMNS_QUALIFIED = (
    "node.id AS id, node.type AS type, node.name AS name, "
    "node.description AS description, "
    "node.trust_level AS trust_level, node.assumptions AS assumptions, "
    "node.entity_type AS entity_type, node.out_of_scope AS out_of_scope, "
    "node.storage_type AS storage_type, node.contains_pii AS contains_pii, "
    "node.encryption_at_rest AS encryption_at_rest"
)


def _row_to_container(row: sqlite3.Row) -> Container:
    if row["type"] == "trust_boundary":
        return TrustBoundary(
            type="trust_boundary",
            id=row["id"],
            name=row["name"],
            description=row["description"],
            privilege_level=row["privilege_level"],
        )
    if row["type"] == "container":
        return ContainerVariant(
            type="container",
            id=row["id"],
            name=row["name"],
            description=row["description"],
        )
    raise ValueError(f"Unknown container type in DB row: {row['type']!r}")


class ContainerRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, diagram_id: int, data: ContainerCreate) -> Container:
        validated = data
        container_id = _mint_entity_id(self._conn, diagram_id, "container")
        if isinstance(validated, TrustBoundaryCreate):
            self._conn.execute(
                "INSERT INTO container "
                "(id, type, name, description, privilege_level) "
                "VALUES (?, 'trust_boundary', ?, ?, ?)",
                (
                    container_id,
                    validated.name,
                    validated.description,
                    validated.privilege_level,
                ),
            )
        elif isinstance(validated, ContainerVariantCreate):
            self._conn.execute(
                "INSERT INTO container (id, type, name, description) "
                "VALUES (?, 'container', ?, ?)",
                (container_id, validated.name, validated.description),
            )
        else:
            raise TypeError(
                f"Unsupported ContainerCreate variant: {type(validated).__name__}"
            )
        fetched = self.get(container_id)
        assert fetched is not None
        return fetched

    def get(self, container_id: int) -> Container | None:
        row = self._conn.execute(
            f"SELECT {_CONTAINER_COLUMNS} FROM container WHERE id = ?",
            (container_id,),
        ).fetchone()
        return _row_to_container(row) if row is not None else None

    def update(self, container_id: int, patch: ContainerUpdate) -> Container | None:
        row = self._conn.execute(
            "SELECT type FROM container WHERE id = ?",
            (container_id,),
        ).fetchone()
        if row is None:
            return None
        current_type = row["type"]

        if current_type == "trust_boundary":
            expected = TrustBoundaryUpdate
            variant_fields: tuple[str, ...] = ("privilege_level",)
        elif current_type == "container":
            expected = ContainerVariantUpdate
            variant_fields = ()
        else:
            raise ValueError(f"Unknown container type in DB row: {current_type!r}")

        if not isinstance(patch, expected):
            raise ValueError(
                f"Patch type {type(patch).__name__} does not match container "
                f"type {current_type!r}; expected {expected.__name__}"
            )

        patch_data = patch.model_dump(exclude_unset=True)
        set_clauses: list[str] = []
        values: list[object] = []
        for field in ("name", "description") + variant_fields:
            if field not in patch_data:
                continue
            raw = patch_data[field]
            if raw is None:
                continue
            set_clauses.append(f"{field} = ?")
            values.append(raw)

        if set_clauses:
            values.append(container_id)
            self._conn.execute(
                f"UPDATE container SET {', '.join(set_clauses)} WHERE id = ?",
                values,
            )
        return self.get(container_id)

    def delete(self, container_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM entity WHERE id = ? AND kind = 'container'",
            (container_id,),
        )
        return cursor.rowcount > 0

    def list(
        self,
        diagram_id: int,
        *,
        type: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Container]:
        sql = (
            f"SELECT {_CONTAINER_COLUMNS_QUALIFIED} FROM container "
            "JOIN entity ON entity.id = container.id "
            "WHERE entity.diagram_id = ?"
        )
        params: list[object] = [diagram_id]
        if type is not None:
            if type not in ("trust_boundary", "container"):
                raise ValueError(f"Unknown container type filter: {type!r}")
            sql += " AND container.type = ?"
            params.append(type)
        sql += " ORDER BY container.id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_container(row) for row in rows]

    def search(
        self,
        diagram_id: int,
        text: str | None = None,
        *,
        type: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Container]:
        sql = (
            f"SELECT {_CONTAINER_COLUMNS_QUALIFIED} FROM container "
            "JOIN entity ON entity.id = container.id "
            "WHERE entity.diagram_id = ?"
        )
        params: list[object] = [diagram_id]
        if type is not None:
            if type not in ("trust_boundary", "container"):
                raise ValueError(f"Unknown container type filter: {type!r}")
            sql += " AND container.type = ?"
            params.append(type)
        if text:
            clause, clause_params = _build_text_clause(text, _SEARCHABLE_TEXT_COLUMNS)
            if clause:
                sql += f" AND {clause}"
                params.extend(clause_params)
        sql += " ORDER BY container.id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_container(row) for row in rows]

    def set_parent(self, child_id: int, parent_container_id: int) -> None:
        if child_id == parent_container_id:
            raise ValueError("A container cannot be its own parent")

        child_row = self._conn.execute(
            "SELECT diagram_id, kind FROM entity WHERE id = ?",
            (child_id,),
        ).fetchone()
        if child_row is None:
            raise ValueError(f"Unknown child entity id: {child_id}")
        if child_row["kind"] not in ("node", "container"):
            raise ValueError(
                "Container children must be nodes or containers; "
                f"got kind={child_row['kind']!r}"
            )

        parent_row = self._conn.execute(
            "SELECT diagram_id, kind FROM entity WHERE id = ?",
            (parent_container_id,),
        ).fetchone()
        if parent_row is None or parent_row["kind"] != "container":
            raise ValueError(f"Unknown container id: {parent_container_id}")

        if child_row["diagram_id"] != parent_row["diagram_id"]:
            raise ValueError("Child and parent must belong to the same diagram")

        # Acyclicity: walk parent's ancestors; if child appears, reject.
        visited: set[int] = set()
        cursor: int | None = parent_container_id
        while cursor is not None and cursor not in visited:
            if cursor == child_id:
                raise ValueError(
                    "Setting this parent would introduce a container hierarchy cycle"
                )
            visited.add(cursor)
            row = self._conn.execute(
                "SELECT parent_id FROM container_membership WHERE child_id = ?",
                (cursor,),
            ).fetchone()
            cursor = row["parent_id"] if row else None

        self._conn.execute(
            "INSERT OR REPLACE INTO container_membership (child_id, parent_id) "
            "VALUES (?, ?)",
            (child_id, parent_container_id),
        )

    def clear_parent(self, child_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM container_membership WHERE child_id = ?",
            (child_id,),
        )
        return cursor.rowcount > 0

    def parent_of(self, child_id: int) -> Container | None:
        row = self._conn.execute(
            f"SELECT {_CONTAINER_COLUMNS_QUALIFIED} FROM container "
            "JOIN container_membership "
            "    ON container_membership.parent_id = container.id "
            "WHERE container_membership.child_id = ?",
            (child_id,),
        ).fetchone()
        return _row_to_container(row) if row is not None else None

    def children_of(self, container_id: int) -> list[Node | Container]:
        rows = self._conn.execute(
            "SELECT entity.id AS id, entity.kind AS kind "
            "FROM container_membership "
            "JOIN entity ON entity.id = container_membership.child_id "
            "WHERE container_membership.parent_id = ? "
            "ORDER BY entity.id ASC",
            (container_id,),
        ).fetchall()
        results: list[object] = []
        for row in rows:
            kind = row["kind"]
            if kind == "node":
                node_row = self._conn.execute(
                    f"SELECT {_NODE_COLUMNS_QUALIFIED} FROM node WHERE id = ?",
                    (row["id"],),
                ).fetchone()
                assert node_row is not None
                results.append(_row_to_node(node_row))
            elif kind == "container":
                container_row = self._conn.execute(
                    f"SELECT {_CONTAINER_COLUMNS} FROM container WHERE id = ?",
                    (row["id"],),
                ).fetchone()
                assert container_row is not None
                results.append(_row_to_container(container_row))
            else:
                raise ValueError(
                    f"Unexpected child kind in container_membership: {kind!r}"
                )
        return results  # type: ignore[return-value]
