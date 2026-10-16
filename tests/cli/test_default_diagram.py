"""Tests for the default-diagram resolver behavior end-to-end on tm data-item."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_create_without_diagram_id_creates_default_diagram(db_path) -> None:
    """AC9.1: create without --diagram-id creates default diagram and uses it."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["data-item", "create", "--identifier=x", "--name=n", "--description=d"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "diagram_id" in payload
    assert payload["identifier"] == "x"

    # The default diagram must now exist.
    list_result = runner.invoke(cli, ["diagram", "list"])
    assert list_result.exit_code == 0
    diagrams = [
        json.loads(line) for line in list_result.stdout.splitlines() if line.strip()
    ]
    assert len(diagrams) == 1
    assert diagrams[0]["name"] == "default"


def test_list_without_diagram_id_with_no_default_returns_empty(db_path) -> None:
    """AC9.2: list without --diagram-id and no default diagram returns empty NDJSON."""
    runner = CliRunner()
    result = runner.invoke(cli, ["data-item", "list"])
    assert result.exit_code == 0
    # Should have no NDJSON rows, output should be empty
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 0
    # Verify no diagrams were created
    diagram_result = runner.invoke(cli, ["diagram", "list"])
    assert diagram_result.exit_code == 0
    diagram_lines = [
        line for line in diagram_result.stdout.splitlines() if line.strip()
    ]
    assert len(diagram_lines) == 0


def test_search_without_diagram_id_with_no_default_returns_empty(db_path) -> None:
    """AC9.2: search without --diagram-id and no default diagram returns empty."""
    runner = CliRunner()
    result = runner.invoke(cli, ["data-item", "search", "foo"])
    assert result.exit_code == 0
    # Should have no NDJSON rows
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 0
    # Verify no diagrams were created
    diagram_result = runner.invoke(cli, ["diagram", "list"])
    assert diagram_result.exit_code == 0
    diagram_lines = [
        line for line in diagram_result.stdout.splitlines() if line.strip()
    ]
    assert len(diagram_lines) == 0


def test_list_uses_existing_default_diagram(db_path) -> None:
    """AC9.3: list without --diagram-id uses existing default diagram."""
    runner = CliRunner()
    # First, create a default diagram
    diagram_result = runner.invoke(cli, ["diagram", "create", "--name", "default"])
    assert diagram_result.exit_code == 0
    default_diagram = json.loads(diagram_result.stdout)
    default_id = default_diagram["id"]

    # Create a data item in that diagram with explicit --diagram-id
    item_result = runner.invoke(
        cli,
        [
            "data-item",
            "create",
            "--diagram-id",
            str(default_id),
            "--identifier",
            "test-item",
            "--name",
            "test-item-name",
            "--description",
            "Test",
        ],
    )
    assert item_result.exit_code == 0

    # Now list without explicit --diagram-id should use the default
    list_result = runner.invoke(cli, ["data-item", "list"])
    assert list_result.exit_code == 0
    items = [
        json.loads(line) for line in list_result.stdout.splitlines() if line.strip()
    ]
    assert len(items) == 1
    assert items[0]["identifier"] == "test-item"


def test_diagram_id_hidden_in_help(db_path) -> None:
    """AC9.4: --diagram-id does not appear in --help output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["data-item", "create", "--help"])
    assert result.exit_code == 0
    assert "--diagram-id" not in result.output


def test_diagram_id_hidden_param_attribute(db_path) -> None:
    """AC9.4 (structural): diagram_id param has hidden=True."""
    # Reflect on the Click command's params
    from tm_cli.main import cli as root_cli

    data_item_cmd = root_cli.commands["data-item"]
    create_cmd = data_item_cmd.commands["create"]
    diagram_id_param = None
    for param in create_cmd.params:
        if param.name == "diagram_id":
            diagram_id_param = param
            break
    assert diagram_id_param is not None
    assert diagram_id_param.hidden is True
