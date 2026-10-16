"""Golden snapshots for tm threat JSON output on all verbs."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_seeded_threats(db_with_seed, snapshot) -> None:
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["threat", "list"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == len(seed_ids.threat_ids)
    parsed = [json.loads(line) for line in lines]
    assert parsed == snapshot


def test_get_returns_full_threat(db_with_seed, snapshot) -> None:
    db_path, seed_ids = db_with_seed
    threat_id = seed_ids.threat_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["threat", "get", str(threat_id)])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert "title" in parsed
    assert "rating" in parsed
    assert "observation_ids" in parsed
    assert "entity_ids" in parsed
    assert parsed == snapshot


def test_create_with_named_flags(db_path: Path, snapshot) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "threat",
            "create",
            "--title",
            "SQL injection risk",
            "--scenario",
            "Attacker sends malformed query",
            "--rating",
            "high",
            "--description",
            "Unsanitised user input reaches the DB.",
            "--mitre-reference",
            "T1190",
            "--observed-mitigations",
            "Input validation in place.",
            "--recommendations",
            "Use parameterised queries.",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["title"] == "SQL injection risk"
    assert parsed["rating"] == "high"
    assert parsed == snapshot


def test_update(db_with_seed, snapshot) -> None:
    db_path, seed_ids = db_with_seed
    threat_id = seed_ids.threat_ids[0]
    runner = CliRunner()
    result = runner.invoke(
        cli, ["threat", "update", str(threat_id), "--title", "Updated threat title"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["title"] == "Updated threat title"
    assert parsed == snapshot


def test_delete(db_with_seed) -> None:
    db_path, seed_ids = db_with_seed
    threat_id = seed_ids.threat_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["threat", "delete", str(threat_id)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["deleted"] is True
    assert payload["id"] == str(threat_id)


def test_search(db_with_seed, snapshot) -> None:
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["threat", "search", "Valid account"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    parsed = [json.loads(line) for line in lines]
    assert parsed == snapshot


def test_link_observation(db_with_seed) -> None:
    db_path, seed_ids = db_with_seed
    threat_id = seed_ids.threat_ids[0]
    obs_id = seed_ids.observation_ids[1]
    runner = CliRunner()
    result = runner.invoke(
        cli, ["threat", "link-observation", str(threat_id), str(obs_id)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["linked"] is True
    assert payload["threat_id"] == str(threat_id)
    assert payload["observation_id"] == str(obs_id)


def test_unlink_observation(db_with_seed) -> None:
    db_path, seed_ids = db_with_seed
    threat_id = seed_ids.threat_ids[0]
    obs_id = seed_ids.observation_ids[0]  # seed linked obs[0] to threat1
    runner = CliRunner()
    result = runner.invoke(
        cli, ["threat", "unlink-observation", str(threat_id), str(obs_id)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["unlinked"] is True
    assert payload["threat_id"] == str(threat_id)
    assert payload["observation_id"] == str(obs_id)


def test_link_entity(db_with_seed) -> None:
    db_path, seed_ids = db_with_seed
    threat_id = seed_ids.threat_ids[0]
    entity_id = seed_ids.data_store_node_id
    runner = CliRunner()
    result = runner.invoke(
        cli, ["threat", "link-entity", str(threat_id), str(entity_id)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["linked"] is True
    assert payload["threat_id"] == str(threat_id)
    assert payload["entity_id"] == str(entity_id)


def test_unlink_entity(db_with_seed) -> None:
    db_path, seed_ids = db_with_seed
    threat_id = seed_ids.threat_ids[0]
    entity_id = seed_ids.process_node_id  # seed linked process to threat1
    runner = CliRunner()
    result = runner.invoke(
        cli, ["threat", "unlink-entity", str(threat_id), str(entity_id)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["unlinked"] is True
    assert payload["threat_id"] == str(threat_id)
    assert payload["entity_id"] == str(entity_id)
