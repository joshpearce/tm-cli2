"""Golden snapshots for tm container JSON output on CRUDL + search verbs."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_two_seeded_containers(db_with_seed) -> None:
    """AC1.1: list returns NDJSON with all two seeded container variants."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["container", "list", "--diagram-id", str(seed_ids.diagram_id)],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    containers = [json.loads(line) for line in lines]
    # Verify we have both types
    types = {c["type"] for c in containers}
    assert types == {"trust_boundary", "container"}


def test_get_trust_boundary_returns_typed(db_with_seed) -> None:
    """AC1.2: get returns a trust_boundary with its type and privilege_level."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["container", "get", str(seed_ids.trust_boundary_id)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "trust_boundary"
    assert payload["id"] == str(seed_ids.trust_boundary_id)
    assert payload["privilege_level"] == "corporate"


def test_get_container_returns_typed(db_with_seed) -> None:
    """AC1.2: get returns a container with its type (no privilege_level)."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["container", "get", str(seed_ids.container_id)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "container"
    assert payload["id"] == str(seed_ids.container_id)
    assert "privilege_level" not in payload


def test_list_filtered_by_type_trust_boundary(db_with_seed) -> None:
    """AC8.5: list with --type=trust_boundary returns only trust boundaries."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "list",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--type",
            "trust_boundary",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    containers = [json.loads(line) for line in lines]
    assert containers[0]["type"] == "trust_boundary"


def test_list_filtered_by_type_container(db_with_seed) -> None:
    """AC8.5: list with --type=container returns only containers."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "list",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--type",
            "container",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    containers = [json.loads(line) for line in lines]
    assert containers[0]["type"] == "container"


def test_search_text_matches_seeded_names(db_with_seed) -> None:
    """AC2.1: search with text filter matches both containers."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "container",
            "search",
            "seed",
            "--diagram-id",
            str(seed_ids.diagram_id),
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    containers = [json.loads(line) for line in lines]
    assert all("seed" in c["name"].lower() for c in containers)


def test_get_missing_id_exits_2(db_with_seed) -> None:
    """AC1.5: get with nonexistent id exits 2 (NotFoundError)."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["container", "get", "99999"],
    )
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"
