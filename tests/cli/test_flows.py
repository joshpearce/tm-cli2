"""Golden snapshots for tm flow JSON output on all verbs."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_seeded_flow(db_with_seed, snapshot) -> None:
    """AC1.1: list returns NDJSON with seeded data flow."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    runner = CliRunner()
    result = runner.invoke(cli, ["flow", "list", "--diagram-id", str(diagram_id)])
    assert result.exit_code == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines == snapshot


def test_get_returns_full_flow(db_with_seed, snapshot) -> None:
    """AC1.2: get returns full DataFlow by id."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    runner = CliRunner()
    result = runner.invoke(cli, ["flow", "get", str(flow_id)])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == snapshot


def test_create_canonicalizes_endpoints_when_n1_gt_n2(db_with_seed, snapshot) -> None:
    """AC1.3, AC11.1: create canonicalizes endpoints (lower id first)."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    process_id = seed_ids.process_node_id
    data_store_id = seed_ids.data_store_node_id

    # Ensure process_id < data_store_id by swapping if needed
    node1_id, node2_id = sorted([process_id, data_store_id])

    # Create with reversed order (larger id first)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "flow",
            "create",
            "--diagram-id",
            str(diagram_id),
            "--node1-id",
            str(node2_id),  # larger
            "--node2-id",
            str(node1_id),  # smaller
            "--name",
            "test-canonicalize",
            "--protocol",
            "HTTP",
            "--no-authenticated",
            "--no-encrypted",
        ],
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    # Result should have canonicalized: node1_id < node2_id
    assert int(payload["node1_id"]) == node1_id
    assert int(payload["node2_id"]) == node2_id
    assert payload == snapshot


def test_create_self_loop_exits_1_with_hint(db_with_seed, snapshot) -> None:
    """AC11.2: create with same node on both endpoints rejected with self-loop hint."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    process_id = seed_ids.process_node_id

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "flow",
            "create",
            "--diagram-id",
            str(diagram_id),
            "--node1-id",
            str(process_id),
            "--node2-id",
            str(process_id),
            "--name",
            "self-loop",
            "--protocol",
            "HTTP",
            "--no-authenticated",
            "--no-encrypted",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    assert "Self-loops" in payload["error"]["message"]
    assert payload == snapshot


def test_create_cross_diagram_exits_1(db_with_seed, snapshot) -> None:
    """AC5.1: create with endpoints from different diagrams rejected."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    process_id = seed_ids.process_node_id

    # Create a second diagram with its own node
    runner = CliRunner()
    diagram_result = runner.invoke(
        cli,
        ["diagram", "create", "--name", "other-diagram"],
    )
    assert diagram_result.exit_code == 0
    other_diagram_id = json.loads(diagram_result.stdout)["id"]

    # Create a node in the other diagram
    node_result = runner.invoke(
        cli,
        [
            "node",
            "create",
            "process",
            "--diagram-id",
            str(other_diagram_id),
            "--name",
            "other-process",
            "--description",
            "in other diagram",
            "--trust-level",
            "public",
        ],
    )
    assert node_result.exit_code == 0
    other_process_id = json.loads(node_result.stdout)["id"]

    # Try to create a flow with endpoints from different diagrams
    result = runner.invoke(
        cli,
        [
            "flow",
            "create",
            "--diagram-id",
            str(diagram_id),
            "--node1-id",
            str(process_id),
            "--node2-id",
            str(other_process_id),
            "--name",
            "cross-diagram",
            "--protocol",
            "HTTP",
            "--no-authenticated",
            "--no-encrypted",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    assert payload == snapshot


def test_update_returns_full_row(db_with_seed, snapshot) -> None:
    """AC1.4: update returns full updated DataFlow."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id

    runner = CliRunner()
    result = runner.invoke(cli, ["flow", "update", str(flow_id), "--no-encrypted"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert int(payload["id"]) == flow_id
    assert payload["encrypted"] is False
    assert payload == snapshot


def test_update_no_node1_or_node2_flag_present(db_with_seed) -> None:
    """AC11.3: update command has no node1_id or node2_id flags."""
    from tm_cli.main import cli as cli_group

    cmd = cli_group.commands["flow"].commands["update"]
    param_names = {p.name for p in cmd.params}

    # These should NOT be present
    assert "node1_id" not in param_names
    assert "node2_id" not in param_names


def test_update_stdin_with_node1_id_in_body_rejected(db_with_seed, snapshot) -> None:
    """AC11.3: update with node1_id in stdin body rejected with immutability hint."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id

    runner = CliRunner()
    body = json.dumps({"name": "updated", "node1_id": 999})
    result = runner.invoke(cli, ["flow", "update", str(flow_id), "--stdin"], input=body)
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    assert "immutable" in payload["error"]["message"].lower()
    assert payload == snapshot


def test_get_missing_id_exits_2(db_with_seed, snapshot) -> None:
    """AC1.5: get missing id exits 2 with not_found error."""
    db_path, seed_ids = db_with_seed

    runner = CliRunner()
    result = runner.invoke(cli, ["flow", "get", "99999"])
    assert result.exit_code == 2
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"
    assert payload == snapshot


def test_update_missing_id_exits_2(db_with_seed, snapshot) -> None:
    """AC1.6: update missing id exits 2 with not_found error."""
    db_path, seed_ids = db_with_seed

    runner = CliRunner()
    result = runner.invoke(cli, ["flow", "update", "99999", "--name", "updated"])
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"
    assert payload == snapshot


def test_search_matches_protocol(db_with_seed, snapshot) -> None:
    """AC2.6: search matches protocol field."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id

    runner = CliRunner()
    result = runner.invoke(
        cli, ["flow", "search", "HTTPS", "--diagram-id", str(diagram_id)]
    )
    assert result.exit_code == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines == snapshot


def test_search_matches_name(db_with_seed, snapshot) -> None:
    """AC2.6: search matches name field."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id

    runner = CliRunner()
    result = runner.invoke(
        cli, ["flow", "search", "seed", "--diagram-id", str(diagram_id)]
    )
    assert result.exit_code == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines == snapshot


def test_search_empty_text_returns_list_shape(db_with_seed) -> None:
    """AC2.7: search with empty text returns same shape as list."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id

    runner = CliRunner()
    list_result = runner.invoke(cli, ["flow", "list", "--diagram-id", str(diagram_id)])
    assert list_result.exit_code == 0
    list_lines = [line for line in list_result.stdout.splitlines() if line.strip()]

    search_result = runner.invoke(
        cli, ["flow", "search", "--diagram-id", str(diagram_id)]
    )
    assert search_result.exit_code == 0
    search_lines = [line for line in search_result.stdout.splitlines() if line.strip()]

    assert len(list_lines) == len(search_lines)
    list_parsed = [json.loads(line) for line in list_lines]
    search_parsed = [json.loads(line) for line in search_lines]
    assert list_parsed == search_parsed
