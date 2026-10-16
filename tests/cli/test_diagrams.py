"""Golden snapshots for tm diagram JSON output on all verbs."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_seeded_diagram(db_with_seed, snapshot) -> None:
    """AC1.1: list returns NDJSON with seeded diagram."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "list"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines == snapshot


def test_get_returns_diagram(db_with_seed, snapshot) -> None:
    """AC1.2: get returns the full diagram object."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "get", str(diagram_id)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "id" in payload
    assert payload["name"] == "non-default"
    assert payload == snapshot


def test_create_returns_new_diagram(db_path, snapshot) -> None:
    """AC1.3: create with named flags returns the new diagram."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "diagram",
            "create",
            "--name",
            "fresh",
            "--description",
            "A fresh diagram",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["name"] == "fresh"
    assert parsed["description"] == "A fresh diagram"
    assert isinstance(parsed["id"], str)
    assert parsed == snapshot


def test_create_no_args_creates_unnamed_diagram(db_path, snapshot) -> None:
    """AC1.3: create with no args (all-optional fields) returns unnamed diagram."""
    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "create"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["name"] is None
    assert parsed["description"] is None
    assert parsed["author"] is None
    assert isinstance(parsed["id"], str)
    assert parsed == snapshot


def test_update_returns_updated_diagram(db_with_seed, snapshot) -> None:
    """AC1.4: update returns the full updated diagram."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    runner = CliRunner()
    result = runner.invoke(
        cli, ["diagram", "update", str(diagram_id), "--description", "new description"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["description"] == "new description"
    assert parsed["name"] == "non-default"
    assert parsed == snapshot


def test_get_missing_id_exits_2(db_with_seed) -> None:
    """AC1.5: get with missing id exits 2."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "get", "9999"])
    assert result.exit_code == 2


def test_update_missing_id_exits_2(db_with_seed) -> None:
    """AC1.6: update with missing id exits 2."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "update", "9999", "--name", "new"])
    assert result.exit_code == 2


def test_list_under_limit_no_pagination_footer(db_with_seed) -> None:
    """AC1.8: no pagination footer when result count < limit."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "list", "--limit", "50"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # 1 seeded diagram + no footer
    assert len(lines) == 1
    # Last line should not be a pagination footer
    last = json.loads(lines[-1])
    assert "_pagination" not in last
