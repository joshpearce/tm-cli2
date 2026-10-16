from __future__ import annotations

from pathlib import Path

import pytest

from tm_cli.db import (
    DiagramCreate,
    DiagramRepository,
    NodeRepository,
    ObservationCreate,
    ObservationRepository,
    ProcessNodeCreate,
    ThreatCatalogCreate,
    ThreatCatalogRepository,
    ThreatCreate,
    ThreatRepository,
    ThreatUpdate,
    connect,
)
from tm_cli.db import connection as connection_module


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tm.db"
    monkeypatch.setenv("TM_DB_PATH", str(path))
    monkeypatch.setattr(connection_module, "_initialized_paths", set())
    return path


@pytest.fixture
def seeded_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """DB populated with deterministic seed data."""
    path = tmp_path / "seed.db"
    monkeypatch.setenv("TM_DB_PATH", str(path))
    monkeypatch.setattr(connection_module, "_initialized_paths", set())
    from tests.fixtures.seed import seed

    ids = seed(path)
    return path, ids


def _catalog_create(mitre_id: str = "T1078") -> ThreatCatalogCreate:
    return ThreatCatalogCreate(
        mitre_id=mitre_id,
        name="Valid Accounts",
        platforms="Windows, Linux",
        description="Adversaries may use valid accounts.",
    )


def _threat_create(catalog_id: int | None = None) -> ThreatCreate:
    return ThreatCreate(
        threat_catalog_id=catalog_id,
        title="Credential abuse",
        scenario="Attacker obtains valid credentials",
        rating="high",
        description="Compromised credentials used for lateral movement.",
        mitre_reference="T1078",
        observed_mitigations="MFA enforced.",
        recommendations="Rotate all credentials.",
    )


def test_create_and_get(db_path: Path) -> None:
    with connect() as conn:
        catalog = ThreatCatalogRepository(conn).create(
            _catalog_create(), ["initial-access"]
        )
        threat = ThreatRepository(conn).create(_threat_create(catalog.id))
    assert threat.id >= 1
    assert threat.title == "Credential abuse"
    assert threat.rating == "high"
    assert threat.threat_catalog_id == catalog.id
    assert threat.observation_ids == []
    assert threat.entity_ids == []

    with connect() as conn:
        fetched = ThreatRepository(conn).get(threat.id)
    assert fetched is not None
    assert fetched.id == threat.id
    assert fetched.title == threat.title


def test_update(db_path: Path) -> None:
    with connect() as conn:
        threat = ThreatRepository(conn).create(_threat_create())
    with connect() as conn:
        updated = ThreatRepository(conn).update(
            threat.id, ThreatUpdate(title="Updated title")
        )
    assert updated is not None
    assert updated.title == "Updated title"
    assert updated.rating == "high"
    assert updated.last_updated >= threat.last_updated


def test_delete(db_path: Path) -> None:
    with connect() as conn:
        threat = ThreatRepository(conn).create(_threat_create())
        repo = ThreatRepository(conn)
        assert repo.delete(threat.id) is True
        assert repo.delete(threat.id) is False
        assert repo.get(threat.id) is None


def test_list_with_rating_filter(db_path: Path) -> None:
    with connect() as conn:
        repo = ThreatRepository(conn)
        high = repo.create(_threat_create())
        low = repo.create(
            ThreatCreate(
                title="Low threat",
                scenario="Unlikely scenario",
                rating="low",
                description="Low severity.",
                mitre_reference="T1078",
                observed_mitigations="Nothing.",
                recommendations="None.",
            )
        )
        all_threats = repo.list()
        high_only = repo.list(rating="high")
        low_only = repo.list(rating="low")

    assert len(all_threats) == 2
    assert [t.id for t in high_only] == [high.id]
    assert [t.id for t in low_only] == [low.id]


def test_search_by_text(db_path: Path) -> None:
    with connect() as conn:
        repo = ThreatRepository(conn)
        repo.create(_threat_create())
        repo.create(
            ThreatCreate(
                title="Phishing campaign",
                scenario="Spear phishing email sent",
                rating="medium",
                description="Social engineering attack.",
                mitre_reference="T1566",
                observed_mitigations="Email filtering.",
                recommendations="User awareness training.",
            )
        )
        results = repo.search(text="Credential")
    assert len(results) == 1
    assert results[0].title == "Credential abuse"


def test_link_observation(db_path: Path) -> None:
    with connect() as conn:
        obs = ObservationRepository(conn).create(
            ObservationCreate(content="auth issue", observation_type="todo")
        )
        threat = ThreatRepository(conn).create(_threat_create())
        repo = ThreatRepository(conn)
        repo.link_observation(threat.id, obs.id)
        fetched = repo.get(threat.id)
    assert fetched is not None
    assert obs.id in fetched.observation_ids


def test_unlink_observation(db_path: Path) -> None:
    with connect() as conn:
        obs = ObservationRepository(conn).create(
            ObservationCreate(content="auth issue", observation_type="todo")
        )
        threat = ThreatRepository(conn).create(_threat_create())
        repo = ThreatRepository(conn)
        repo.link_observation(threat.id, obs.id)
        removed = repo.unlink_observation(threat.id, obs.id)
        fetched = repo.get(threat.id)
    assert removed is True
    assert fetched is not None
    assert fetched.observation_ids == []


def test_link_entity(seeded_db) -> None:
    """Seed already links threat1 to the process node; verify entity_ids populated."""
    _path, seed_ids = seeded_db
    with connect() as conn:
        fetched = ThreatRepository(conn).get(seed_ids.threat_ids[0])
    assert fetched is not None
    assert seed_ids.process_node_id in fetched.entity_ids


def test_unlink_entity(db_path: Path) -> None:
    with connect() as conn:
        diagram = DiagramRepository(conn).create(DiagramCreate(name="threat-diagram"))
        node = NodeRepository(conn).create(
            diagram.id,
            ProcessNodeCreate(
                name="auth-service",
                description="handles auth",
                trust_level="authenticated",
            ),
        )
        threat = ThreatRepository(conn).create(_threat_create())
        repo = ThreatRepository(conn)
        repo.link_entity(threat.id, node.id)
        removed = repo.unlink_entity(threat.id, node.id)
        missing = repo.unlink_entity(threat.id, node.id)
    assert removed is True
    assert missing is False
