"""Tests for tm flow payload junction commands and reverse views."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_add_payload_endpoint_1(db_with_seed, snapshot) -> None:
    """AC3.7: add-payload --from <process_node_id> (endpoint 1) returns linked:true."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    item_id = seed_ids.data_item_with_parent_id

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["linked"] is True
    assert payload["endpoint"] == 1
    assert payload["from_node_id"] == str(seed_ids.process_node_id)
    assert payload == snapshot


def test_add_payload_endpoint_2_after_endpoint_1_round_trips(
    db_with_seed, snapshot
) -> None:
    """AC3.7: add-payload --from on both endpoints; list-payloads round-trips."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    item1_id = seed_ids.data_item_with_parent_id
    item2_id = seed_ids.data_item_without_parent_id

    runner = CliRunner()

    # Add item1 on endpoint 1 (process node)
    result1 = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item1_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    assert result1.exit_code == 0
    payload1 = json.loads(result1.stdout)
    assert payload1["from_node_id"] == str(seed_ids.process_node_id)

    # Add item2 on endpoint 2 (data store node)
    result2 = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item2_id),
            "--from",
            str(seed_ids.data_store_node_id),
        ],
    )
    assert result2.exit_code == 0

    # List all payloads
    list_result = runner.invoke(cli, ["flow", "list-payloads", str(flow_id)])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    all_payloads = [json.loads(line) for line in lines]
    assert all_payloads == snapshot

    # List payloads on endpoint 1 only
    filter_result = runner.invoke(
        cli,
        [
            "flow",
            "list-payloads",
            str(flow_id),
            "--endpoint",
            "1",
        ],
    )
    assert filter_result.exit_code == 0
    filtered_lines = [
        line for line in filter_result.stdout.splitlines() if line.strip()
    ]
    assert len(filtered_lines) == 1
    filtered_payloads = [json.loads(line) for line in filtered_lines]
    assert filtered_payloads == snapshot


def test_add_payload_already_present_returns_already_linked(
    db_with_seed, snapshot
) -> None:
    """AC3.7: calling add-payload twice returns already_linked on second call."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    item_id = seed_ids.data_item_with_parent_id

    runner = CliRunner()
    args = [
        "flow",
        "add-payload",
        str(flow_id),
        "--data-item",
        str(item_id),
        "--from",
        str(seed_ids.process_node_id),
    ]
    first = runner.invoke(cli, args)
    assert first.exit_code == 0

    second = runner.invoke(cli, args)
    assert second.exit_code == 0
    payload = json.loads(second.stdout)
    assert payload["linked"] is False
    assert payload["reason"] == "already_linked"
    assert payload == snapshot


def test_remove_payload_returns_unlinked_true(db_with_seed, snapshot) -> None:
    """AC3.7: remove-payload --from <node_id> when present returns unlinked:true."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    item_id = seed_ids.data_item_with_parent_id

    runner = CliRunner()

    # First add it
    runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )

    # Then remove it
    result = runner.invoke(
        cli,
        [
            "flow",
            "remove-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["unlinked"] is True
    assert payload["from_node_id"] == str(seed_ids.process_node_id)
    assert payload == snapshot


def test_remove_payload_when_absent_returns_not_linked(db_with_seed, snapshot) -> None:
    """Extension: remove-payload --from <node_id> when absent returns unlinked:false."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    item_id = seed_ids.data_item_with_parent_id

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "flow",
            "remove-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["unlinked"] is False
    assert payload["reason"] == "not_linked"
    assert payload["from_node_id"] == str(seed_ids.process_node_id)
    assert payload == snapshot


def test_list_payloads_filtered_by_endpoint(db_with_seed, snapshot) -> None:
    """AC3.7: list-payloads with --endpoint filter returns subset."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    item1_id = seed_ids.data_item_with_parent_id
    item2_id = seed_ids.data_item_without_parent_id

    runner = CliRunner()

    # Add items to both endpoints (list-payloads --endpoint filter is unchanged)
    runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item1_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item2_id),
            "--from",
            str(seed_ids.data_store_node_id),
        ],
    )

    # List without filter
    all_result = runner.invoke(cli, ["flow", "list-payloads", str(flow_id)])
    assert all_result.exit_code == 0
    all_lines = [line for line in all_result.stdout.splitlines() if line.strip()]
    assert len(all_lines) == 2

    # List with endpoint 2 filter (list-payloads still uses --endpoint)
    filtered_result = runner.invoke(
        cli,
        [
            "flow",
            "list-payloads",
            str(flow_id),
            "--endpoint",
            "2",
        ],
    )
    assert filtered_result.exit_code == 0
    filtered_lines = [
        line for line in filtered_result.stdout.splitlines() if line.strip()
    ]
    assert len(filtered_lines) == 1
    filtered_payload = json.loads(filtered_lines[0])
    assert int(filtered_payload["id"]) == item2_id
    assert filtered_payload == snapshot


def test_list_payloads_for_missing_flow_exits_2(db_with_seed, snapshot) -> None:
    """AC1.5: list-payloads for missing flow exits 2 with not_found."""
    db_path, seed_ids = db_with_seed

    runner = CliRunner()
    result = runner.invoke(cli, ["flow", "list-payloads", "99999"])
    assert result.exit_code == 2
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"
    assert payload == snapshot


def test_data_item_list_flows_returns_carrying_flow(db_with_seed, snapshot) -> None:
    """Reverse view: data-item list-flows returns flows carrying the item."""
    db_path, seed_ids = db_with_seed
    item_id = seed_ids.data_item_with_parent_id
    flow_id = seed_ids.data_flow_id

    runner = CliRunner()

    # First add the payload
    runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )

    # Then query the reverse view
    result = runner.invoke(cli, ["data-item", "list-flows", str(item_id)])
    assert result.exit_code == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert int(payload["id"]) == flow_id
    assert payload == snapshot


def test_data_item_list_flows_for_missing_item_exits_2(db_with_seed, snapshot) -> None:
    """AC1.5: data-item list-flows for missing item exits 2 with not_found."""
    db_path, seed_ids = db_with_seed

    runner = CliRunner()
    result = runner.invoke(cli, ["data-item", "list-flows", "99999"])
    assert result.exit_code == 2
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"
    assert payload == snapshot


def test_add_payload_cross_diagram_exits_1(db_with_seed, snapshot) -> None:
    """AC5.1: add-payload with flow and item from different diagrams exits 1."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id

    # Create a second diagram with its own data item
    runner = CliRunner()
    diagram_result = runner.invoke(
        cli,
        ["diagram", "create", "--name", "other-diagram"],
    )
    assert diagram_result.exit_code == 0
    other_diagram_id = json.loads(diagram_result.stdout)["id"]

    # Create a data item in the other diagram
    item_result = runner.invoke(
        cli,
        [
            "data-item",
            "create",
            "--diagram-id",
            str(other_diagram_id),
            "--identifier",
            "other-item",
            "--name",
            "other-item-name",
            "--description",
            "in other diagram",
        ],
    )
    assert item_result.exit_code == 0
    other_item_id = json.loads(item_result.stdout)["id"]

    # Try to add the payload with mismatched diagrams
    result = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(other_item_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    assert "same diagram" in payload["error"]["message"].lower()
    assert payload == snapshot


def test_add_payload_using_non_data_item_id_exits_1(db_with_seed, snapshot) -> None:
    """AC5.1: add-payload with a node id instead of data_item id exits 1."""
    db_path, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    process_id = seed_ids.process_node_id

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(process_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    assert "data_item" in payload["error"]["message"].lower()
    assert payload == snapshot


# ---------------------------------------------------------------------------
# Task B: new error-path and resolution tests
# ---------------------------------------------------------------------------


def test_add_payload_from_other_diagram_node_user_error(db_with_seed) -> None:
    """Node from a different diagram is not a flow endpoint — user_error."""
    _, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    item_id = seed_ids.data_item_with_parent_id

    runner = CliRunner()

    # Create a second diagram and a process node in it
    diag_result = runner.invoke(
        cli, ["diagram", "create", "--name", "other-diag-for-node-test"]
    )
    assert diag_result.exit_code == 0
    other_diagram_id = json.loads(diag_result.stdout)["id"]

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
            "a process in the other diagram",
            "--trust-level",
            "authenticated",
        ],
    )
    assert node_result.exit_code == 0, node_result.output
    other_node_id = json.loads(node_result.stdout)["id"]

    result = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(other_node_id),
        ],
    )
    assert result.exit_code == 1
    error_payload = json.loads(result.stderr)
    err = error_payload["error"]
    assert err["code"] == "user_error"
    n1 = seed_ids.process_node_id
    n2 = seed_ids.data_store_node_id
    assert err["hint"] == f"Pass --from {n1} or --from {n2}."
    assert err["flow_id"] == str(flow_id)
    assert err["from_node_id"] == str(other_node_id)
    assert err["node1_id"] == str(seed_ids.process_node_id)
    assert err["node2_id"] == str(seed_ids.data_store_node_id)


def test_add_payload_from_nonexistent_node_id_user_error(db_with_seed) -> None:
    """--from 999999 (no such node) produces user_error; hint exposes real endpoints."""
    _, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    item_id = seed_ids.data_item_with_parent_id

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            "999999",
        ],
    )
    assert result.exit_code == 1
    error_payload = json.loads(result.stderr)
    err = error_payload["error"]
    assert err["code"] == "user_error"
    n1 = seed_ids.process_node_id
    n2 = seed_ids.data_store_node_id
    assert err["hint"] == f"Pass --from {n1} or --from {n2}."
    assert err["flow_id"] == str(flow_id)
    assert err["from_node_id"] == "999999"
    assert err["node1_id"] == str(seed_ids.process_node_id)
    assert err["node2_id"] == str(seed_ids.data_store_node_id)


def test_add_payload_from_node1_resolves_to_endpoint_1(db_with_seed) -> None:
    """--from <process_node_id> routes to endpoint 1; absent from endpoint 2."""
    _, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id

    runner = CliRunner()

    # Use the item without parent to avoid collisions with other tests
    item_id = seed_ids.data_item_without_parent_id

    add_result = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    assert add_result.exit_code == 0, add_result.stderr
    added = json.loads(add_result.stdout)
    assert added["endpoint"] == 1
    assert added["from_node_id"] == str(seed_ids.process_node_id)

    # Should appear under endpoint 1
    ep1_result = runner.invoke(
        cli,
        ["flow", "list-payloads", str(flow_id), "--endpoint", "1"],
    )
    assert ep1_result.exit_code == 0
    ep1_lines = [line for line in ep1_result.stdout.splitlines() if line.strip()]
    ep1_ids = [json.loads(row)["id"] for row in ep1_lines]
    assert str(item_id) in ep1_ids

    # Must NOT appear under endpoint 2
    ep2_result = runner.invoke(
        cli,
        ["flow", "list-payloads", str(flow_id), "--endpoint", "2"],
    )
    assert ep2_result.exit_code == 0
    ep2_lines = [line for line in ep2_result.stdout.splitlines() if line.strip()]
    ep2_ids = [json.loads(row)["id"] for row in ep2_lines]
    assert str(item_id) not in ep2_ids


def test_add_payload_from_node2_resolves_to_endpoint_2(db_with_seed) -> None:
    """--from <data_store_node_id> routes to endpoint 2; absent from endpoint 1."""
    _, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id

    runner = CliRunner()

    # Use data_item_with_parent_id as a fresh item for this test
    item_id = seed_ids.data_item_with_parent_id

    add_result = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(seed_ids.data_store_node_id),
        ],
    )
    assert add_result.exit_code == 0, add_result.stderr
    added = json.loads(add_result.stdout)
    assert added["endpoint"] == 2
    assert added["from_node_id"] == str(seed_ids.data_store_node_id)

    # Should appear under endpoint 2
    ep2_result = runner.invoke(
        cli,
        ["flow", "list-payloads", str(flow_id), "--endpoint", "2"],
    )
    assert ep2_result.exit_code == 0
    ep2_lines = [line for line in ep2_result.stdout.splitlines() if line.strip()]
    ep2_ids = [json.loads(row)["id"] for row in ep2_lines]
    assert str(item_id) in ep2_ids

    # Must NOT appear under endpoint 1
    ep1_result = runner.invoke(
        cli,
        ["flow", "list-payloads", str(flow_id), "--endpoint", "1"],
    )
    assert ep1_result.exit_code == 0
    ep1_lines = [line for line in ep1_result.stdout.splitlines() if line.strip()]
    ep1_ids = [json.loads(row)["id"] for row in ep1_lines]
    assert str(item_id) not in ep1_ids


def test_remove_payload_from_other_diagram_node_user_error(db_with_seed) -> None:
    """remove-payload --from <other-diagram node> produces user_error with hint."""
    _, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    item_id = seed_ids.data_item_with_parent_id

    runner = CliRunner()

    # Create a second diagram and a process node in it
    diag_result = runner.invoke(
        cli, ["diagram", "create", "--name", "other-diag-for-remove-test"]
    )
    assert diag_result.exit_code == 0
    other_diagram_id = json.loads(diag_result.stdout)["id"]

    node_result = runner.invoke(
        cli,
        [
            "node",
            "create",
            "process",
            "--diagram-id",
            str(other_diagram_id),
            "--name",
            "other-process-for-remove",
            "--description",
            "a process in the other diagram",
            "--trust-level",
            "authenticated",
        ],
    )
    assert node_result.exit_code == 0, node_result.output
    other_node_id = json.loads(node_result.stdout)["id"]

    result = runner.invoke(
        cli,
        [
            "flow",
            "remove-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(other_node_id),
        ],
    )
    assert result.exit_code == 1
    error_payload = json.loads(result.stderr)
    err = error_payload["error"]
    assert err["code"] == "user_error"
    n1 = seed_ids.process_node_id
    n2 = seed_ids.data_store_node_id
    assert err["hint"] == f"Pass --from {n1} or --from {n2}."
    assert err["flow_id"] == str(flow_id)
    assert err["from_node_id"] == str(other_node_id)
    assert err["node1_id"] == str(seed_ids.process_node_id)
    assert err["node2_id"] == str(seed_ids.data_store_node_id)


def test_remove_payload_from_node1_unlinks(db_with_seed) -> None:
    """Round-trip: add --from node1, remove --from node1; endpoint 1 returns empty."""
    _, seed_ids = db_with_seed
    flow_id = seed_ids.data_flow_id
    item_id = seed_ids.data_item_with_parent_id

    runner = CliRunner()

    # Add
    add_result = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    assert add_result.exit_code == 0, add_result.stderr
    assert json.loads(add_result.stdout)["linked"] is True

    # Remove
    remove_result = runner.invoke(
        cli,
        [
            "flow",
            "remove-payload",
            str(flow_id),
            "--data-item",
            str(item_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    assert remove_result.exit_code == 0, remove_result.stderr
    assert json.loads(remove_result.stdout)["unlinked"] is True

    # List endpoint 1 — must be empty
    list_result = runner.invoke(
        cli,
        ["flow", "list-payloads", str(flow_id), "--endpoint", "1"],
    )
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert lines == []


def test_add_payload_unknown_flow_id_not_found(db_with_seed) -> None:
    """Missing flow short-circuits before endpoint validation: exit 2 + not_found."""
    _, seed_ids = db_with_seed

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "flow",
            "add-payload",
            "999999",
            "--data-item",
            str(seed_ids.data_item_with_parent_id),
            "--from",
            str(seed_ids.process_node_id),
        ],
    )
    assert result.exit_code == 2
    error_payload = json.loads(result.stderr)
    err = error_payload["error"]
    assert err["code"] == "not_found"
    assert "Flow id=999999 not found" in err["message"]
