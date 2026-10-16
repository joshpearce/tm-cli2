"""Tests for tm container set-parent/clear-parent/parent-of/list-children commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_set_parent_then_parent_of_round_trips(db_with_seed) -> None:
    """AC3.4: set-parent followed by parent-of round-trips correctly."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    # Create a child container in the same diagram
    result = runner.invoke(
        cli,
        [
            "container",
            "create",
            "container",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "child-container",
            "--description",
            "child container",
        ],
    )
    assert result.exit_code == 0, result.output
    child_payload = json.loads(result.stdout)
    child_id = child_payload["id"]

    # Set the parent
    result = runner.invoke(
        cli,
        [
            "container",
            "set-parent",
            child_id,
            str(seed_ids.trust_boundary_id),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["child_id"] == child_id
    assert payload["parent_id"] == str(seed_ids.trust_boundary_id)

    # Now verify with parent-of
    result = runner.invoke(
        cli,
        ["container", "parent-of", child_id],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["id"] == child_id
    assert payload["parent"] is not None
    assert payload["parent"]["id"] == str(seed_ids.trust_boundary_id)
    assert payload["parent"]["type"] == "trust_boundary"


def test_list_children_includes_node_and_container(db_with_seed) -> None:
    """AC3.4: list-children returns heterogeneous Node and Container rows."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    # Set the seeded process node's parent to the trust boundary
    result = runner.invoke(
        cli,
        [
            "node",
            "set-parent",
            str(seed_ids.process_node_id),
            str(seed_ids.trust_boundary_id),
        ],
    )
    assert result.exit_code == 0, result.output

    # Create a child container in the same diagram and set its parent
    result = runner.invoke(
        cli,
        [
            "container",
            "create",
            "container",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "nested-container",
            "--description",
            "nested container",
        ],
    )
    assert result.exit_code == 0, result.output
    nested_payload = json.loads(result.stdout)
    nested_id = nested_payload["id"]

    result = runner.invoke(
        cli,
        [
            "container",
            "set-parent",
            nested_id,
            str(seed_ids.trust_boundary_id),
        ],
    )
    assert result.exit_code == 0, result.output

    # List children of the trust boundary
    result = runner.invoke(
        cli,
        ["container", "list-children", str(seed_ids.trust_boundary_id)],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    children = [json.loads(line) for line in lines]
    types = {c["type"] for c in children}
    assert types == {"process", "container"}
    # Verify the specific children
    ids = {c["id"] for c in children}
    assert str(seed_ids.process_node_id) in ids
    assert nested_id in ids


def test_clear_parent_then_list_children_excludes_child(db_with_seed) -> None:
    """AC3.4: clear-parent removes the child from list-children."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    # Create a child container
    result = runner.invoke(
        cli,
        [
            "container",
            "create",
            "container",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "child-container",
            "--description",
            "child container",
        ],
    )
    assert result.exit_code == 0, result.output
    child_payload = json.loads(result.stdout)
    child_id = child_payload["id"]

    # Set parent
    result = runner.invoke(
        cli,
        [
            "container",
            "set-parent",
            child_id,
            str(seed_ids.trust_boundary_id),
        ],
    )
    assert result.exit_code == 0, result.output

    # Verify it appears in list-children
    result = runner.invoke(
        cli,
        ["container", "list-children", str(seed_ids.trust_boundary_id)],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1

    # Clear parent
    result = runner.invoke(
        cli,
        ["container", "clear-parent", child_id],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["cleared"] is True
    assert payload["id"] == child_id

    # Verify it no longer appears in list-children
    result = runner.invoke(
        cli,
        ["container", "list-children", str(seed_ids.trust_boundary_id)],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 0


def test_set_parent_cross_diagram_exits_1_with_hint(db_with_seed) -> None:
    """AC3.5: set-parent across diagrams exits 1 with cross-diagram hint."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    # Create a second diagram
    result = runner.invoke(
        cli,
        ["diagram", "create", "--name", "diagram-2"],
    )
    assert result.exit_code == 0, result.output
    diagram_2 = json.loads(result.stdout)
    diagram_2_id = diagram_2["id"]

    # Create a container in the second diagram
    result = runner.invoke(
        cli,
        [
            "container",
            "create",
            "container",
            "--diagram-id",
            diagram_2_id,
            "--name",
            "diagram-2-container",
            "--description",
            "d2 container",
        ],
    )
    assert result.exit_code == 0, result.output
    d2_container = json.loads(result.stdout)
    d2_container_id = d2_container["id"]

    # Try to set a parent from diagram 1 to a container in diagram 2
    result = runner.invoke(
        cli,
        [
            "container",
            "set-parent",
            str(seed_ids.container_id),
            d2_container_id,
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    message = payload["error"]["message"]
    assert "same diagram" in message.lower()


def test_set_parent_self_exits_1(db_with_seed) -> None:
    """AC3.4: set-parent with self exits 1 with self-parent hint."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "container",
            "set-parent",
            str(seed_ids.container_id),
            str(seed_ids.container_id),
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    message = payload["error"]["message"]
    assert "cannot be its own parent" in message.lower()


def test_set_parent_creates_cycle_exits_1_with_hint(db_with_seed) -> None:
    """AC3.6: set-parent that creates a cycle exits 1 with cycle hint."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    # Create container A
    result = runner.invoke(
        cli,
        [
            "container",
            "create",
            "container",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "container-a",
            "--description",
            "container a",
        ],
    )
    assert result.exit_code == 0, result.output
    container_a = json.loads(result.stdout)
    container_a_id = container_a["id"]

    # Create container B
    result = runner.invoke(
        cli,
        [
            "container",
            "create",
            "container",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "container-b",
            "--description",
            "container b",
        ],
    )
    assert result.exit_code == 0, result.output
    container_b = json.loads(result.stdout)
    container_b_id = container_b["id"]

    # Set B's parent to A
    result = runner.invoke(
        cli,
        ["container", "set-parent", container_b_id, container_a_id],
    )
    assert result.exit_code == 0, result.output

    # Try to set A's parent to B (would create a cycle)
    result = runner.invoke(
        cli,
        ["container", "set-parent", container_a_id, container_b_id],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    message = payload["error"]["message"]
    assert "cycle" in message.lower()


def test_list_children_missing_container_exits_2(db_with_seed) -> None:
    """AC1.5: list-children with nonexistent id exits 2 (NotFoundError)."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["container", "list-children", "99999"],
    )
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"


def test_set_parent_unknown_parent_exits_1(db_with_seed) -> None:
    """AC5.1: set-parent with unknown parent exits 1 (user_error)."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "container",
            "set-parent",
            str(seed_ids.container_id),
            "99999",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
