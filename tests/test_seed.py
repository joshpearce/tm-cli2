"""Sanity check that the deterministic seed is reproducible."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

from tests.fixtures.seed import seed
from tm_cli.db import connection as connection_module


def _fresh_path(tmp_path: Path, name: str, *, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Allocate a fresh DB path under ``tmp_path`` and isolate ``init_schema`` cache."""
    p = tmp_path / name
    monkeypatch.setenv("TM_DB_PATH", str(p))
    monkeypatch.setattr(connection_module, "_initialized_paths", set())
    return p


def test_seed_produces_stable_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = seed(_fresh_path(tmp_path, "a.db", monkeypatch=monkeypatch))
    b = seed(_fresh_path(tmp_path, "b.db", monkeypatch=monkeypatch))
    # asdict() compares structurally, including all minted ids.
    assert asdict(a) == asdict(b), "Seed must be deterministic across fresh DBs"
