"""Golden snapshots for tm data-item JSON output on all verbs."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_seeded_items(db_with_seed, snapshot) -> None:
    """AC1.1: list returns NDJSON with seeded data items."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    runner = CliRunner()
    result = runner.invoke(cli, ["data-item", "list", "--diagram-id", str(diagram_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines == snapshot


def test_list_filtered_by_classification(db_with_seed, snapshot) -> None:
    """AC2.5: list with --classification filter returns only matching items."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "data-item",
            "list",
            "--diagram-id",
            str(diagram_id),
            "--classification",
            "pii",
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Only the seeded item with classification="pii" should match
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines[0]["classification"] == "pii"
    assert parsed_lines == snapshot


def test_list_filtered_by_parent_node_id(db_with_seed, snapshot) -> None:
    """AC2.5: list with --parent-node-id filter returns only matching items."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    process_id = seed_ids.process_node_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "data-item",
            "list",
            "--diagram-id",
            str(diagram_id),
            "--parent-node-id",
            str(process_id),
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Only the seeded item with parent_node_id should match
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines[0]["parent_node_id"] == str(process_id)
    assert parsed_lines == snapshot


def test_list_filtered_by_classification_and_parent_node(
    db_with_seed, snapshot
) -> None:
    """AC2.5: combining filters AND-combines constraints."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    process_id = seed_ids.process_node_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "data-item",
            "list",
            "--diagram-id",
            str(diagram_id),
            "--classification",
            "pii",
            "--parent-node-id",
            str(process_id),
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Only the seeded item with both pii classification AND parent should match
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines[0]["classification"] == "pii"
    assert parsed_lines[0]["parent_node_id"] == str(process_id)
    assert parsed_lines == snapshot


def test_get_returns_item(db_with_seed, snapshot) -> None:
    """AC1.2: get returns the full data item object."""
    db_path, seed_ids = db_with_seed
    item_id = seed_ids.data_item_with_parent_id
    runner = CliRunner()
    result = runner.invoke(cli, ["data-item", "get", str(item_id)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "id" in payload
    assert payload["identifier"] == "seed-item-1"
    assert payload == snapshot


def test_create_with_named_flags_in_seeded_diagram(db_with_seed, snapshot) -> None:
    """AC1.3: create with explicit --diagram-id (hidden but functional) works."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "data-item",
            "create",
            "--diagram-id",
            str(diagram_id),
            "--identifier",
            "new-item",
            "--name",
            "new-item",
            "--description",
            "A new item",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["identifier"] == "new-item"
    assert parsed["name"] == "new-item"
    assert parsed["diagram_id"] == str(diagram_id)
    assert isinstance(parsed["id"], str)
    assert parsed == snapshot


def test_update_returns_full_row(db_with_seed, snapshot) -> None:
    """AC1.4: update returns the full updated data item."""
    db_path, seed_ids = db_with_seed
    item_id = seed_ids.data_item_with_parent_id
    runner = CliRunner()
    result = runner.invoke(
        cli, ["data-item", "update", str(item_id), "--name", "updated-name"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["name"] == "updated-name"
    assert parsed["identifier"] == "seed-item-1"
    assert parsed == snapshot


def test_update_clear_parent_node_id_with_empty_string(db_with_seed) -> None:
    """AC11.4: update with --parent-node-id "" clears the field to NULL."""
    db_path, seed_ids = db_with_seed
    item_id = seed_ids.data_item_with_parent_id
    runner = CliRunner()
    # Update to clear the parent_node_id
    result = runner.invoke(
        cli, ["data-item", "update", str(item_id), "--parent-node-id", ""]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["parent_node_id"] is None
    # Verify with get that it actually cleared
    get_result = runner.invoke(cli, ["data-item", "get", str(item_id)])
    assert get_result.exit_code == 0
    get_payload = json.loads(get_result.stdout)
    assert get_payload["parent_node_id"] is None


def test_update_clear_parent_node_id_with_none_literal(db_with_seed) -> None:
    """AC11.4: update with --parent-node-id none clears the field to NULL."""
    db_path, seed_ids = db_with_seed
    item_id = seed_ids.data_item_with_parent_id
    runner = CliRunner()
    # Update to clear the parent_node_id using "none" literal
    result = runner.invoke(
        cli, ["data-item", "update", str(item_id), "--parent-node-id", "none"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["parent_node_id"] is None
    # Verify with get that it actually cleared
    get_result = runner.invoke(cli, ["data-item", "get", str(item_id)])
    assert get_result.exit_code == 0
    get_payload = json.loads(get_result.stdout)
    assert get_payload["parent_node_id"] is None


def test_update_clear_parent_node_id_via_stdin(db_with_seed) -> None:
    """AC11.4: update with --stdin {"parent_node_id": null} clears the field."""
    db_path, seed_ids = db_with_seed
    item_id = seed_ids.data_item_with_parent_id
    runner = CliRunner()
    body = json.dumps({"parent_node_id": None})
    # Update to clear the parent_node_id via stdin
    result = runner.invoke(
        cli, ["data-item", "update", str(item_id), "--stdin"], input=body
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["parent_node_id"] is None
    # Verify with get that it actually cleared
    get_result = runner.invoke(cli, ["data-item", "get", str(item_id)])
    assert get_result.exit_code == 0
    get_payload = json.loads(get_result.stdout)
    assert get_payload["parent_node_id"] is None


def test_get_missing_id_exits_2(db_with_seed) -> None:
    """AC1.5: get with missing id exits 2."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["data-item", "get", "9999"])
    assert result.exit_code == 2


def test_update_missing_id_exits_2(db_with_seed) -> None:
    """AC1.6: update with missing id exits 2."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["data-item", "update", "9999", "--name", "new"])
    assert result.exit_code == 2
