"""Tests for tm node set-parent/clear-parent/parent-of commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_set_parent_then_parent_of_round_trips(db_with_seed) -> None:
    """AC3.4: set-parent followed by parent-of round-trips correctly."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    # First, set the parent
    result = runner.invoke(
        cli,
        [
            "node",
            "set-parent",
            str(seed_ids.process_node_id),
            str(seed_ids.container_id),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["child_id"] == str(seed_ids.process_node_id)
    assert payload["parent_id"] == str(seed_ids.container_id)

    # Now verify with parent-of
    result = runner.invoke(
        cli,
        ["node", "parent-of", str(seed_ids.process_node_id)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["id"] == str(seed_ids.process_node_id)
    assert payload["parent"] is not None
    assert payload["parent"]["id"] == str(seed_ids.container_id)
    assert payload["parent"]["type"] == "container"


def test_clear_parent_removes_membership(db_with_seed) -> None:
    """AC3.4: clear-parent removes the membership."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    # Set parent
    runner.invoke(
        cli,
        [
            "node",
            "set-parent",
            str(seed_ids.process_node_id),
            str(seed_ids.container_id),
        ],
    )

    # Clear parent
    result = runner.invoke(
        cli,
        ["node", "clear-parent", str(seed_ids.process_node_id)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["cleared"] is True
    assert payload["id"] == str(seed_ids.process_node_id)

    # Verify parent is gone
    result = runner.invoke(
        cli,
        ["node", "parent-of", str(seed_ids.process_node_id)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["parent"] is None


def test_clear_parent_idempotent_when_unmembered(db_with_seed) -> None:
    """AC3.4: clear-parent is idempotent when node has no parent."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["node", "clear-parent", str(seed_ids.process_node_id)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["cleared"] is False
    assert payload["id"] == str(seed_ids.process_node_id)


def test_set_parent_unknown_child_exits_1(db_with_seed) -> None:
    """AC5.1: set-parent with unknown child exits 1 (user_error)."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "node",
            "set-parent",
            "99999",
            str(seed_ids.container_id),
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"


def test_set_parent_unknown_parent_exits_1(db_with_seed) -> None:
    """AC5.1: set-parent with unknown parent exits 1 (user_error)."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "node",
            "set-parent",
            str(seed_ids.process_node_id),
            "99999",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
