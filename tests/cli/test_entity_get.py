"""Tests for tm entity get — kind-agnostic DFD entity resolver."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.db import EntityObservationRepository, connect
from tm_cli.main import cli


def test_entity_get_node_returns_node_payload_with_kind(db_with_seed) -> None:
    """tm entity get <node_id> returns tm node get payload plus kind == 'node'."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    node_id = seed_ids.process_node_id

    # Capture baseline from tm node get
    node_result = runner.invoke(cli, ["node", "get", str(node_id)])
    assert node_result.exit_code == 0
    node_payload = json.loads(node_result.stdout)

    # Fetch via tm entity get
    entity_result = runner.invoke(cli, ["entity", "get", str(node_id)])
    assert entity_result.exit_code == 0
    entity_payload = json.loads(entity_result.stdout)

    assert entity_payload["kind"] == "node"
    # Full payload equals node get payload with kind prepended
    expected = {"kind": "node", **node_payload}
    assert entity_payload == expected


def test_entity_get_container_returns_container_payload_with_kind(db_with_seed) -> None:
    """entity get returns the container payload; kind == 'container'."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    container_id = seed_ids.trust_boundary_id

    container_result = runner.invoke(cli, ["container", "get", str(container_id)])
    assert container_result.exit_code == 0
    container_payload = json.loads(container_result.stdout)

    entity_result = runner.invoke(cli, ["entity", "get", str(container_id)])
    assert entity_result.exit_code == 0
    entity_payload = json.loads(entity_result.stdout)

    assert entity_payload["kind"] == "container"
    expected = {"kind": "container", **container_payload}
    assert entity_payload == expected


def test_entity_get_data_flow_returns_flow_payload_with_kind(db_with_seed) -> None:
    """tm entity get <flow_id> returns tm flow get payload plus kind == 'data_flow'."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    flow_id = seed_ids.data_flow_id

    flow_result = runner.invoke(cli, ["flow", "get", str(flow_id)])
    assert flow_result.exit_code == 0
    flow_payload = json.loads(flow_result.stdout)

    entity_result = runner.invoke(cli, ["entity", "get", str(flow_id)])
    assert entity_result.exit_code == 0
    entity_payload = json.loads(entity_result.stdout)

    # kind is raw entity.kind value: data_flow (not "flow")
    assert entity_payload["kind"] == "data_flow"
    expected = {"kind": "data_flow", **flow_payload}
    assert entity_payload == expected


def test_entity_get_data_item_returns_item_payload_with_kind(db_with_seed) -> None:
    """tm entity get <item_id> returns data-item payload plus kind == 'data_item'."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    item_id = seed_ids.data_item_with_parent_id

    item_result = runner.invoke(cli, ["data-item", "get", str(item_id)])
    assert item_result.exit_code == 0
    item_payload = json.loads(item_result.stdout)

    entity_result = runner.invoke(cli, ["entity", "get", str(item_id)])
    assert entity_result.exit_code == 0
    entity_payload = json.loads(entity_result.stdout)

    # kind is raw entity.kind value: data_item (not "data-item")
    assert entity_payload["kind"] == "data_item"
    expected = {"kind": "data_item", **item_payload}
    assert entity_payload == expected


def test_entity_get_missing_id_exits_2(db_with_seed) -> None:
    """tm entity get <missing_id> exits 2 with error.code == 'not_found'."""
    _, _ = db_with_seed
    runner = CliRunner()

    result = runner.invoke(cli, ["entity", "get", "99999"])
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("code") == "not_found"


def test_entity_get_in_tm_commands_introspection(db_with_seed) -> None:
    """tm commands tree contains an 'entity' group with a 'get' command."""
    _, _ = db_with_seed
    runner = CliRunner()

    result = runner.invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.stdout)

    # Find the entity subcommand group at root level
    entity_group = next(
        (cmd for cmd in tree["subcommands"] if cmd["name"] == "entity"),
        None,
    )
    assert entity_group is not None, "No 'entity' group found in tm commands output"

    # entity group must have a 'get' subcommand
    get_command = next(
        (cmd for cmd in entity_group.get("subcommands", []) if cmd["name"] == "get"),
        None,
    )
    assert get_command is not None, "No 'get' command found under 'entity' group"
    assert "options" in get_command
    assert "arguments" in get_command


def test_entity_get_agent_flow_observation_to_flow(db_with_seed) -> None:
    """Agent flow: observation get -> flow_ids[0] -> entity get gives DataFlow."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    obs_id = seed_ids.observation_ids[0]
    flow_id = seed_ids.data_flow_id

    # Link the seeded data flow to the observation directly via repository
    with connect(db_path) as conn:
        EntityObservationRepository(conn).link(flow_id, obs_id)

    # Step 1: tm observation get <obs_id> -> check flow_ids contains the flow
    obs_result = runner.invoke(cli, ["observation", "get", str(obs_id)])
    assert obs_result.exit_code == 0
    obs_payload = json.loads(obs_result.stdout)
    assert "flow_ids" in obs_payload
    assert str(flow_id) in obs_payload["flow_ids"]

    # Step 2: use the flow id from flow_ids[0]
    linked_flow_id = obs_payload["flow_ids"][0]

    # Step 3: tm entity get <flow_ids[0]> -> full DataFlow payload, kind == "data_flow"
    entity_result = runner.invoke(cli, ["entity", "get", linked_flow_id])
    assert entity_result.exit_code == 0
    entity_payload = json.loads(entity_result.stdout)

    assert entity_payload["kind"] == "data_flow"

    # Verify full DataFlow fields are present
    assert entity_payload["id"] == str(flow_id)
    assert "node1_id" in entity_payload
    assert "node2_id" in entity_payload
    assert "name" in entity_payload
    assert "protocol" in entity_payload
    assert "authenticated" in entity_payload
    assert "encrypted" in entity_payload

    # node1_id and node2_id are the seeded process and data store nodes
    assert entity_payload["node1_id"] == str(seed_ids.process_node_id)
    assert entity_payload["node2_id"] == str(seed_ids.data_store_node_id)
    assert entity_payload["name"] == "seed-flow"
    assert entity_payload["protocol"] == "HTTPS"
    assert entity_payload["authenticated"] is True
    assert entity_payload["encrypted"] is True


def test_entity_get_resolves_process_component(db_with_seed, snapshot) -> None:
    """tm entity get <process_component_id> returns process_component payload.

    Includes kind == 'process_component'.
    """
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    component_id = seed_ids.process_component_ids[0]

    # Capture baseline from tm process-component get
    component_result = runner.invoke(
        cli, ["process-component", "get", str(component_id)]
    )
    assert component_result.exit_code == 0
    component_payload = json.loads(component_result.stdout)

    # Fetch via tm entity get
    entity_result = runner.invoke(cli, ["entity", "get", str(component_id)])
    assert entity_result.exit_code == 0
    entity_payload = json.loads(entity_result.stdout)

    # kind is raw entity.kind value: process_component
    assert entity_payload["kind"] == "process_component"
    # Full payload equals process-component get payload with kind prepended
    expected = {"kind": "process_component", **component_payload}
    assert entity_payload == expected
    assert entity_payload == snapshot
