from __future__ import annotations

from pathlib import Path

import pytest

from tm_cli.db import (
    ThreatCatalogCreate,
    ThreatCatalogRepository,
    connect,
)
from tm_cli.db import connection as connection_module


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tm.db"
    monkeypatch.setenv("TM_DB_PATH", str(path))
    monkeypatch.setattr(connection_module, "_initialized_paths", set())
    return path


def _make_entry(
    mitre_id: str = "T1078", name: str = "Valid Accounts"
) -> ThreatCatalogCreate:
    return ThreatCatalogCreate(
        mitre_id=mitre_id,
        name=name,
        platforms="Windows, Linux",
        description="Test technique description.",
    )


def test_create_and_get(db_path: Path) -> None:
    with connect() as conn:
        repo = ThreatCatalogRepository(conn)
        entry = repo.create(_make_entry(), ["initial-access"])
    assert entry.id >= 1
    assert entry.mitre_id == "T1078"
    assert entry.name == "Valid Accounts"
    assert entry.platforms == "Windows, Linux"
    assert entry.description == "Test technique description."

    with connect() as conn:
        fetched = ThreatCatalogRepository(conn).get(entry.id)
    assert fetched is not None
    assert fetched.id == entry.id
    assert fetched.mitre_id == entry.mitre_id
    assert fetched.name == entry.name


def test_create_duplicate_mitre_id_reuses_existing(db_path: Path) -> None:
    with connect() as conn:
        repo = ThreatCatalogRepository(conn)
        first = repo.create(_make_entry(), ["initial-access"])
        second = repo.create(_make_entry(), ["persistence"])
    assert first.id == second.id


def test_create_adds_tactic_links(db_path: Path) -> None:
    with connect() as conn:
        repo = ThreatCatalogRepository(conn)
        entry = repo.create(_make_entry(), ["initial-access", "persistence"])
    assert sorted(entry.tactics) == ["initial-access", "persistence"]


def test_ensure_tactic_idempotent(db_path: Path) -> None:
    with connect() as conn:
        repo = ThreatCatalogRepository(conn)
        id1 = repo.ensure_tactic("initial-access")
        id2 = repo.ensure_tactic("initial-access")
    assert id1 == id2


def test_list(db_path: Path) -> None:
    with connect() as conn:
        repo = ThreatCatalogRepository(conn)
        a = repo.create(_make_entry("T1078", "Valid Accounts"), ["initial-access"])
        b = repo.create(
            _make_entry("T1190", "Exploit Public-Facing"), ["initial-access"]
        )
        entries = repo.list()
    assert len(entries) == 2
    assert [e.id for e in entries] == [a.id, b.id]


def test_search_by_name(db_path: Path) -> None:
    with connect() as conn:
        repo = ThreatCatalogRepository(conn)
        repo.create(_make_entry("T1078", "Valid Accounts"), ["initial-access"])
        repo.create(_make_entry("T1190", "Exploit Public-Facing"), ["initial-access"])
        results = repo.search(text="Valid")
    assert len(results) == 1
    assert results[0].name == "Valid Accounts"


def test_technique_with_multiple_tactics(db_path: Path) -> None:
    """A technique created from two separate calls accumulates all tactic links."""
    with connect() as conn:
        repo = ThreatCatalogRepository(conn)
        repo.create(_make_entry(), ["initial-access"])
        entry = repo.create(_make_entry(), ["persistence"])
    assert sorted(entry.tactics) == ["initial-access", "persistence"]
