"""Tests for polymorphic container create/update + type-mismatch validation."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_create_trust_boundary_returns_trust_boundary(db_with_seed) -> None:
    """AC1.3, AC8.1, AC8.4: create trust-boundary returns a trust_boundary."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "create",
            "trust-boundary",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "new-trust-boundary",
            "--description",
            "new trust boundary",
            "--privilege-level",
            "dmz",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "trust_boundary"
    assert payload["name"] == "new-trust-boundary"
    assert payload["privilege_level"] == "dmz"


def test_create_container_returns_container(db_with_seed) -> None:
    """AC1.3, AC8.1, AC8.4: create container returns a container."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "create",
            "container",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "new-container",
            "--description",
            "new container",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "container"
    assert payload["name"] == "new-container"
    assert "privilege_level" not in payload


def test_create_with_invalid_privilege_level_exits_1(db_with_seed) -> None:
    """AC1.7: invalid privilege_level choice exits 1 with user_error."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "create",
            "trust-boundary",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "tb",
            "--description",
            "d",
            "--privilege-level",
            "bogus",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"


def test_update_trust_boundary(db_with_seed) -> None:
    """AC1.4, AC8.4: update trust-boundary updates the privilege_level."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "update",
            "trust-boundary",
            str(seed_ids.trust_boundary_id),
            "--privilege-level",
            "restricted",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "trust_boundary"
    assert payload["privilege_level"] == "restricted"
    assert payload["id"] == str(seed_ids.trust_boundary_id)


def test_update_container(db_with_seed) -> None:
    """AC1.4, AC8.4: update container updates the description."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "update",
            "container",
            str(seed_ids.container_id),
            "--description",
            "new description",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "container"
    assert payload["description"] == "new description"
    assert payload["id"] == str(seed_ids.container_id)


def test_update_trust_boundary_against_container_exits_1(db_with_seed) -> None:
    """AC8.4 (mismatch): updating trust-boundary against container exits 1."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "update",
            "trust-boundary",
            str(seed_ids.container_id),
            "--privilege-level",
            "corporate",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    hint = payload["error"].get("hint", "")
    assert "tm container update container" in hint
    assert str(seed_ids.container_id) in hint


def test_update_container_against_trust_boundary_exits_1(db_with_seed) -> None:
    """AC8.4 (mismatch): updating container against trust_boundary exits 1."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "update",
            "container",
            str(seed_ids.trust_boundary_id),
            "--description",
            "new description",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    hint = payload["error"].get("hint", "")
    assert "tm container update trust-boundary" in hint
    assert str(seed_ids.trust_boundary_id) in hint


def test_update_missing_id_exits_2(db_with_seed) -> None:
    """AC1.6: update with nonexistent id exits 2 (NotFoundError)."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "update",
            "container",
            "99999",
            "--name",
            "x",
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"
