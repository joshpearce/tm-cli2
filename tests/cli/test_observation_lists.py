"""Tests for tm observation list-nodes/list-containers/list-flows/list-items."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.db import EntityObservationRepository, connect
from tm_cli.main import cli


def test_observation_list_nodes_returns_linked_node(db_with_seed) -> None:
    """list-nodes returns the linked node with its type discriminator."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    node_id = seed_ids.process_node_id
    obs_id = seed_ids.observation_ids[0]

    # Link node to observation directly via repository
    with connect(db_path) as conn:
        EntityObservationRepository(conn).link(node_id, obs_id)

    result = runner.invoke(cli, ["observation", "list-nodes", str(obs_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    nodes = [json.loads(line) for line in lines]
    found = next((n for n in nodes if n["id"] == str(node_id)), None)
    assert found is not None
    assert found["type"] == "process"


def test_observation_list_containers_returns_linked_container(db_with_seed) -> None:
    """list-containers returns the linked container with its type discriminator."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    container_id = seed_ids.trust_boundary_id
    obs_id = seed_ids.observation_ids[0]

    with connect(db_path) as conn:
        EntityObservationRepository(conn).link(container_id, obs_id)

    result = runner.invoke(cli, ["observation", "list-containers", str(obs_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    containers = [json.loads(line) for line in lines]
    found = next((c for c in containers if c["id"] == str(container_id)), None)
    assert found is not None
    assert found["type"] == "trust_boundary"


def test_observation_list_flows_returns_linked_flow(db_with_seed) -> None:
    """list-flows returns the linked flow."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    flow_id = seed_ids.data_flow_id
    obs_id = seed_ids.observation_ids[0]

    with connect(db_path) as conn:
        EntityObservationRepository(conn).link(flow_id, obs_id)

    result = runner.invoke(cli, ["observation", "list-flows", str(obs_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    flows = [json.loads(line) for line in lines]
    found = next((f for f in flows if f["id"] == str(flow_id)), None)
    assert found is not None


def test_observation_list_items_returns_linked_item(db_with_seed) -> None:
    """list-items returns the linked data item."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    item_id = seed_ids.data_item_with_parent_id
    obs_id = seed_ids.observation_ids[0]

    with connect(db_path) as conn:
        EntityObservationRepository(conn).link(item_id, obs_id)

    result = runner.invoke(cli, ["observation", "list-items", str(obs_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    items = [json.loads(line) for line in lines]
    found = next((i for i in items if i["id"] == str(item_id)), None)
    assert found is not None


def test_observation_list_nodes_for_missing_observation_exits_2(
    db_path: Path,
) -> None:
    """list-nodes for a missing observation exits 2 with not_found."""
    runner = CliRunner()
    result = runner.invoke(cli, ["observation", "list-nodes", "99999"])
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("code") == "not_found"


def test_observation_list_nodes_empty_when_no_links(db_with_seed) -> None:
    """list-nodes for an observation with no node links returns an empty stream."""
    _, seed_ids = db_with_seed
    runner = CliRunner()

    obs_id = seed_ids.observation_ids[0]

    result = runner.invoke(cli, ["observation", "list-nodes", str(obs_id)])
    assert result.exit_code == 0
    # No rows and no _pagination footer for an empty result
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines == []


def test_observation_list_nodes_pagination_footer_on_full_page(db_with_seed) -> None:
    """list-nodes --limit 1 with one linked node produces row + _pagination footer."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    node_id = seed_ids.process_node_id
    obs_id = seed_ids.observation_ids[0]

    with connect(db_path) as conn:
        EntityObservationRepository(conn).link(node_id, obs_id)

    result = runner.invoke(
        cli, ["observation", "list-nodes", str(obs_id), "--limit", "1"]
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Expect at least 2 lines: the node row + the _pagination footer
    assert len(lines) >= 2
    footer = json.loads(lines[-1])
    assert "_pagination" in footer
