"""Tests for entity↔observation links (all four DFD kinds).

Reverse listing (observation list-nodes / list-containers / list-flows / list-items)
is already covered in tests/cli/test_observation_lists.py and is not duplicated here.

Cascade-on-delete behaviour is covered at the DB level in
tests/test_db_entity_observations.py and is not duplicated here.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli


def test_node_link_unlink_list_observations_round_trip(db_with_seed) -> None:
    """node link-observation / list-observations / unlink-observation round trip."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    node_id = seed_ids.process_node_id
    obs_id = seed_ids.observation_ids[0]

    # Link: first time should return linked: true
    link_result = runner.invoke(
        cli, ["node", "link-observation", str(node_id), str(obs_id)]
    )
    assert link_result.exit_code == 0
    payload = json.loads(link_result.stdout)
    assert payload["linked"] is True
    assert payload["node_id"] == str(node_id)
    assert payload["observation_id"] == str(obs_id)

    # List should include the observation
    list_result = runner.invoke(cli, ["node", "list-observations", str(node_id)])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    observations = [json.loads(line) for line in lines]
    assert any(o["id"] == str(obs_id) for o in observations)

    # Relink: second time should return linked: false with reason
    relink_result = runner.invoke(
        cli, ["node", "link-observation", str(node_id), str(obs_id)]
    )
    assert relink_result.exit_code == 0
    payload = json.loads(relink_result.stdout)
    assert payload["linked"] is False
    assert payload.get("reason") == "already_linked"

    # Unlink
    unlink_result = runner.invoke(
        cli, ["node", "unlink-observation", str(node_id), str(obs_id)]
    )
    assert unlink_result.exit_code == 0
    payload = json.loads(unlink_result.stdout)
    assert payload["unlinked"] is True
    assert payload["node_id"] == str(node_id)
    assert payload["observation_id"] == str(obs_id)

    # List after unlink: observation should not be present
    list_after = runner.invoke(cli, ["node", "list-observations", str(node_id)])
    assert list_after.exit_code == 0
    lines = [line for line in list_after.stdout.splitlines() if line.strip()]
    observations = [json.loads(line) for line in lines]
    assert all(o["id"] != str(obs_id) for o in observations)


def test_container_link_unlink_list_observations_round_trip(db_with_seed) -> None:
    """container: link-observation / unlink-observation / list-observations."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    container_id = seed_ids.trust_boundary_id
    obs_id = seed_ids.observation_ids[0]

    # Link: first time should return linked: true
    link_result = runner.invoke(
        cli, ["container", "link-observation", str(container_id), str(obs_id)]
    )
    assert link_result.exit_code == 0
    payload = json.loads(link_result.stdout)
    assert payload["linked"] is True
    assert payload["container_id"] == str(container_id)
    assert payload["observation_id"] == str(obs_id)

    # List should include the observation
    list_result = runner.invoke(
        cli, ["container", "list-observations", str(container_id)]
    )
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    observations = [json.loads(line) for line in lines]
    assert any(o["id"] == str(obs_id) for o in observations)

    # Relink: second time should return linked: false with reason
    relink_result = runner.invoke(
        cli, ["container", "link-observation", str(container_id), str(obs_id)]
    )
    assert relink_result.exit_code == 0
    payload = json.loads(relink_result.stdout)
    assert payload["linked"] is False
    assert payload.get("reason") == "already_linked"

    # Unlink
    unlink_result = runner.invoke(
        cli, ["container", "unlink-observation", str(container_id), str(obs_id)]
    )
    assert unlink_result.exit_code == 0
    payload = json.loads(unlink_result.stdout)
    assert payload["unlinked"] is True

    # List after unlink: observation should not be present
    list_after = runner.invoke(
        cli, ["container", "list-observations", str(container_id)]
    )
    assert list_after.exit_code == 0
    lines = [line for line in list_after.stdout.splitlines() if line.strip()]
    observations = [json.loads(line) for line in lines]
    assert all(o["id"] != str(obs_id) for o in observations)


def test_flow_link_unlink_list_observations_round_trip(db_with_seed) -> None:
    """flow link-observation / list-observations / unlink-observation round trip."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    flow_id = seed_ids.data_flow_id
    obs_id = seed_ids.observation_ids[0]

    # Link: first time should return linked: true
    link_result = runner.invoke(
        cli, ["flow", "link-observation", str(flow_id), str(obs_id)]
    )
    assert link_result.exit_code == 0
    payload = json.loads(link_result.stdout)
    assert payload["linked"] is True
    assert payload["flow_id"] == str(flow_id)
    assert payload["observation_id"] == str(obs_id)

    # List should include the observation
    list_result = runner.invoke(cli, ["flow", "list-observations", str(flow_id)])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    observations = [json.loads(line) for line in lines]
    assert any(o["id"] == str(obs_id) for o in observations)

    # Relink: second time should return linked: false with reason
    relink_result = runner.invoke(
        cli, ["flow", "link-observation", str(flow_id), str(obs_id)]
    )
    assert relink_result.exit_code == 0
    payload = json.loads(relink_result.stdout)
    assert payload["linked"] is False
    assert payload.get("reason") == "already_linked"

    # Unlink
    unlink_result = runner.invoke(
        cli, ["flow", "unlink-observation", str(flow_id), str(obs_id)]
    )
    assert unlink_result.exit_code == 0
    payload = json.loads(unlink_result.stdout)
    assert payload["unlinked"] is True

    # List after unlink: observation should not be present
    list_after = runner.invoke(cli, ["flow", "list-observations", str(flow_id)])
    assert list_after.exit_code == 0
    lines = [line for line in list_after.stdout.splitlines() if line.strip()]
    observations = [json.loads(line) for line in lines]
    assert all(o["id"] != str(obs_id) for o in observations)


def test_data_item_link_unlink_list_observations_round_trip(db_with_seed) -> None:
    """data-item: link-observation / unlink-observation / list-observations."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    item_id = seed_ids.data_item_with_parent_id
    obs_id = seed_ids.observation_ids[0]

    # Link: first time should return linked: true
    link_result = runner.invoke(
        cli, ["data-item", "link-observation", str(item_id), str(obs_id)]
    )
    assert link_result.exit_code == 0
    payload = json.loads(link_result.stdout)
    assert payload["linked"] is True
    assert payload["item_id"] == str(item_id)
    assert payload["observation_id"] == str(obs_id)

    # List should include the observation
    list_result = runner.invoke(cli, ["data-item", "list-observations", str(item_id)])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    observations = [json.loads(line) for line in lines]
    assert any(o["id"] == str(obs_id) for o in observations)

    # Relink: second time should return linked: false with reason
    relink_result = runner.invoke(
        cli, ["data-item", "link-observation", str(item_id), str(obs_id)]
    )
    assert relink_result.exit_code == 0
    payload = json.loads(relink_result.stdout)
    assert payload["linked"] is False
    assert payload.get("reason") == "already_linked"

    # Unlink
    unlink_result = runner.invoke(
        cli, ["data-item", "unlink-observation", str(item_id), str(obs_id)]
    )
    assert unlink_result.exit_code == 0
    payload = json.loads(unlink_result.stdout)
    assert payload["unlinked"] is True

    # List after unlink: observation should not be present
    list_after = runner.invoke(cli, ["data-item", "list-observations", str(item_id)])
    assert list_after.exit_code == 0
    lines = [line for line in list_after.stdout.splitlines() if line.strip()]
    observations = [json.loads(line) for line in lines]
    assert all(o["id"] != str(obs_id) for o in observations)


def test_link_observation_unknown_entity_exits_3_fk(db_with_seed) -> None:
    """Linking to a missing entity exits 3 with constraint=foreign_key."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    obs_id = seed_ids.observation_ids[0]

    result = runner.invoke(cli, ["node", "link-observation", "99999", str(obs_id)])
    assert result.exit_code == 3
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("constraint") == "foreign_key"


def test_link_observation_unknown_obs_exits_3_fk(db_with_seed) -> None:
    """Linking a missing observation exits 3 with constraint=foreign_key."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    node_id = seed_ids.process_node_id

    result = runner.invoke(cli, ["node", "link-observation", str(node_id), "99999"])
    assert result.exit_code == 3
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("constraint") == "foreign_key"


def test_node_list_observations_for_missing_node_exits_2(db_path: Path) -> None:
    """list-observations for a missing node exits 2 with not_found."""
    runner = CliRunner()
    result = runner.invoke(cli, ["node", "list-observations", "99999"])
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("code") == "not_found"
