"""Tests covering dfd_editor_diagram_id column and DiagramRepository behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from tm_cli.db import DiagramCreate, DiagramRepository, connect


def test_fresh_db_has_dfd_editor_diagram_id_column(db_path: Path) -> None:
    with connect() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(diagram)")}
    assert "dfd_editor_diagram_id" in columns


def test_diagram_model_dump_includes_field(db_path: Path) -> None:
    with connect() as conn:
        diagram = DiagramRepository(conn).create(DiagramCreate(name="x"))

    dumped = diagram.model_dump()
    assert "dfd_editor_diagram_id" in dumped
    assert dumped["dfd_editor_diagram_id"] is None


def test_set_remote_id_persists(db_path: Path) -> None:
    remote_uuid = "00000000-0000-4000-8000-000000000001"
    with connect() as conn:
        repo = DiagramRepository(conn)
        diagram = repo.create(DiagramCreate(name="push-target"))
        repo.set_remote_id(diagram.id, remote_uuid)
        fetched = repo.get(diagram.id)

    assert fetched is not None
    assert fetched.dfd_editor_diagram_id == remote_uuid


def test_set_remote_id_overwrites_existing(db_path: Path) -> None:
    first_uuid = "00000000-0000-4000-8000-000000000001"
    second_uuid = "ffffffff-ffff-4fff-8fff-ffffffffffff"
    with connect() as conn:
        repo = DiagramRepository(conn)
        diagram = repo.create(DiagramCreate(name="overwrite-target"))
        repo.set_remote_id(diagram.id, first_uuid)
        repo.set_remote_id(diagram.id, second_uuid)
        fetched = repo.get(diagram.id)

    assert fetched is not None
    assert fetched.dfd_editor_diagram_id == second_uuid


def test_set_remote_id_missing_raises(db_path: Path) -> None:
    with connect() as conn:
        repo = DiagramRepository(conn)
        with pytest.raises(ValueError, match="99999"):
            repo.set_remote_id(99999, "00000000-0000-4000-8000-000000000001")
