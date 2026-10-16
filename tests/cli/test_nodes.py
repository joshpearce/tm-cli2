"""Golden snapshots for tm node JSON output on CRUDL + search verbs."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_three_seeded_node_variants(db_with_seed) -> None:
    """AC1.1: list returns NDJSON with all three seeded node variants."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["node", "list", "--diagram-id", str(seed_ids.diagram_id)],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 3
    nodes = [json.loads(line) for line in lines]
    # Verify we have all three types
    types = {node["type"] for node in nodes}
    assert types == {"process", "external_entity", "data_store"}


def test_get_returns_typed_node(db_with_seed) -> None:
    """AC1.2: get returns a node with its type discriminator."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["node", "get", str(seed_ids.process_node_id)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "process"
    assert payload["id"] == str(seed_ids.process_node_id)


def test_list_filtered_by_type_process(db_with_seed) -> None:
    """AC2.4, AC8.5: list with --type=process returns only processes."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "list",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--type",
            "process",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    nodes = [json.loads(line) for line in lines]
    assert nodes[0]["type"] == "process"


def test_list_filtered_by_type_data_store(db_with_seed) -> None:
    """AC2.4, AC8.5: list with --type=data_store returns only data stores."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "list",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--type",
            "data_store",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    nodes = [json.loads(line) for line in lines]
    assert nodes[0]["type"] == "data_store"


def test_search_filtered_by_type(db_with_seed) -> None:
    """AC2.4, AC8.5: search with --type filter restricts results."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "search",
            "seed",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--type",
            "process",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    nodes = [json.loads(line) for line in lines]
    assert nodes[0]["type"] == "process"


def test_search_text_only_returns_all_matching(db_with_seed) -> None:
    """AC2.1: search without type filter returns all matching nodes."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "search",
            "seed",
            "--diagram-id",
            str(seed_ids.diagram_id),
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 3


def test_get_missing_id_exits_2(db_with_seed) -> None:
    """AC1.5: get with nonexistent id exits 2 (NotFoundError)."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["node", "get", "99999"])
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"


def test_invalid_type_filter_value_exits_1(db_with_seed) -> None:
    """AC1.7: invalid --type choice exits 1 with user_error."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "list",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--type",
            "bogus",
        ],
    )
    assert result.exit_code != 0
    # Click's choice validation produces a UsageError which maps to user_error
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
