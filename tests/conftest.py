"""Pytest fixtures for tm-cli."""

from __future__ import annotations

from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from tests.fixtures.seed import SeedIds, seed
from tests.fixtures.syrupy_ext import MaskingSnapshotExtension
from tm_cli.db import connection as connection_module


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Per-test SQLite path with a fresh schema."""
    path = tmp_path / "tm.db"
    monkeypatch.setenv("TM_DB_PATH", str(path))
    monkeypatch.setattr(connection_module, "_initialized_paths", set())
    return path


@pytest.fixture
def db_with_seed(db_path: Path) -> tuple[Path, SeedIds]:
    """Seeded SQLite path + ``SeedIds`` map for golden tests."""
    ids = seed(db_path)
    return db_path, ids


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Override Syrupy's default snapshot with our masking extension."""
    return snapshot.use_extension(MaskingSnapshotExtension)
