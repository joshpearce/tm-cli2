"""Golden snapshots for tm finding JSON output on all verbs."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_diagram(runner: CliRunner) -> str:
    """Create a diagram and return its id."""
    result = runner.invoke(cli, ["diagram", "create", "--name", "test-diagram"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["id"]


def _create_test_node(runner: CliRunner, diagram_id: str) -> str:
    """Create a process node and return its id."""
    result = runner.invoke(
        cli,
        [
            "node",
            "create",
            "process",
            "--diagram-id",
            diagram_id,
            "--name",
            "test-node",
            "--description",
            "a test node",
            "--trust-level",
            "public",
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["id"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_minimal(db_path: Path, snapshot) -> None:
    """Create with required flags returns a finding with expected fields."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)
    result = runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "error",
            "--message",
            "test msg",
            "--source",
            "linter",
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["severity"] == "error"
    assert parsed["message"] == "test msg"
    assert parsed["source"] == "linter"
    assert parsed["diagram_id"] == diagram_id
    assert parsed == snapshot


def test_create_with_entity_id_and_code(db_path: Path, snapshot) -> None:
    """Create with --entity-id and --code stores both optional fields."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)
    node_id = _create_test_node(runner, diagram_id)
    result = runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "warning",
            "--message",
            "missing trust boundary",
            "--source",
            "analyzer",
            "--entity-id",
            node_id,
            "--code",
            "TM-001",
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["severity"] == "warning"
    assert parsed["code"] == "TM-001"
    assert parsed["entity_id"] == node_id
    assert parsed == snapshot


def test_create_via_stdin(db_path: Path, snapshot) -> None:
    """Create with --stdin reads a single JSON object from stdin."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)
    body = json.dumps(
        {
            "severity": "error",
            "message": "stdin finding",
            "source": "scanner",
        }
    )
    result = runner.invoke(
        cli,
        ["finding", "create", "--diagram-id", diagram_id, "--stdin"],
        input=body,
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["message"] == "stdin finding"
    assert parsed["source"] == "scanner"
    assert parsed == snapshot


def test_create_batch_via_stdin(db_path: Path, snapshot) -> None:
    """Create with --stdin accepts a JSON array and returns a JSON array."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)
    batch = json.dumps(
        [
            {"severity": "error", "message": "batch error", "source": "linter"},
            {"severity": "warning", "message": "batch warning", "source": "linter"},
        ]
    )
    result = runner.invoke(
        cli,
        ["finding", "create", "--diagram-id", diagram_id, "--stdin"],
        input=batch,
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed == snapshot


def test_create_dry_run(db_path: Path) -> None:
    """--dry-run returns dry_run: true without persisting."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)
    result = runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "error",
            "--message",
            "dry run test",
            "--source",
            "linter",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["dry_run"] is True

    # Nothing should have been persisted
    list_result = runner.invoke(cli, ["finding", "list", "--diagram-id", diagram_id])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.output.splitlines() if line.strip()]
    assert len(lines) == 0


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


def test_get_found(db_path: Path, snapshot) -> None:
    """Get returns the full finding row after create."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)
    create_result = runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "error",
            "--message",
            "get me",
            "--source",
            "linter",
        ],
    )
    assert create_result.exit_code == 0
    finding_id = json.loads(create_result.output)["id"]

    result = runner.invoke(cli, ["finding", "get", finding_id])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["id"] == finding_id
    assert parsed["message"] == "get me"
    assert parsed == snapshot


def test_get_not_found(db_path: Path) -> None:
    """Get of non-existent id exits with code 2."""
    runner = CliRunner()
    result = runner.invoke(cli, ["finding", "get", "9999"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_severity(db_path: Path, snapshot) -> None:
    """Update changes severity and returns the full updated row."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)
    create_result = runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "error",
            "--message",
            "original message",
            "--source",
            "linter",
        ],
    )
    assert create_result.exit_code == 0
    finding_id = json.loads(create_result.output)["id"]

    result = runner.invoke(
        cli, ["finding", "update", finding_id, "--severity", "warning"]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["severity"] == "warning"
    assert parsed["message"] == "original message"
    assert parsed == snapshot


def test_update_clears_code(db_path: Path) -> None:
    """Update with --code '' sets code to None."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)
    create_result = runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "error",
            "--message",
            "coded finding",
            "--source",
            "linter",
            "--code",
            "TM-999",
        ],
    )
    assert create_result.exit_code == 0
    finding_id = json.loads(create_result.output)["id"]

    result = runner.invoke(cli, ["finding", "update", finding_id, "--code", ""])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["code"] is None


def test_update_not_found(db_path: Path) -> None:
    """Update of non-existent id exits with code 2."""
    runner = CliRunner()
    result = runner.invoke(cli, ["finding", "update", "9999", "--severity", "warning"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_existing(db_path: Path, snapshot) -> None:
    """Delete an existing finding returns deleted: true."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)
    create_result = runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "error",
            "--message",
            "delete me",
            "--source",
            "linter",
        ],
    )
    assert create_result.exit_code == 0
    finding_id = json.loads(create_result.output)["id"]

    result = runner.invoke(cli, ["finding", "delete", finding_id, "--yes"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["deleted"] is True
    assert parsed == snapshot


def test_delete_not_found(db_path: Path, snapshot) -> None:
    """Delete non-existent finding returns deleted: false with reason: not_found."""
    runner = CliRunner()
    result = runner.invoke(cli, ["finding", "delete", "9999", "--yes"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["deleted"] is False
    assert parsed["reason"] == "not_found"
    assert parsed == snapshot


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_returns_findings(db_path: Path, snapshot) -> None:
    """List returns all findings as NDJSON lines."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)

    for i in range(2):
        r = runner.invoke(
            cli,
            [
                "finding",
                "create",
                "--diagram-id",
                diagram_id,
                "--severity",
                "error",
                "--message",
                f"finding {i}",
                "--source",
                "linter",
            ],
        )
        assert r.exit_code == 0

    result = runner.invoke(cli, ["finding", "list", "--diagram-id", diagram_id])
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed == snapshot


def test_list_severity_filter(db_path: Path) -> None:
    """List with --severity error returns only error-severity findings."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)

    runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "error",
            "--message",
            "an error",
            "--source",
            "linter",
        ],
    )
    runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "warning",
            "--message",
            "a warning",
            "--source",
            "linter",
        ],
    )

    result = runner.invoke(
        cli,
        ["finding", "list", "--diagram-id", diagram_id, "--severity", "error"],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["severity"] == "error"


def test_list_source_filter(db_path: Path) -> None:
    """List with --source returns only findings from that source."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)

    runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "error",
            "--message",
            "from linter",
            "--source",
            "linter",
        ],
    )
    runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "error",
            "--message",
            "from scanner",
            "--source",
            "scanner",
        ],
    )

    result = runner.invoke(
        cli,
        ["finding", "list", "--diagram-id", diagram_id, "--source", "linter"],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["source"] == "linter"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_by_message(db_path: Path, snapshot) -> None:
    """Search finds findings whose message contains the query text."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)

    runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "error",
            "--message",
            "injection vulnerability detected",
            "--source",
            "linter",
        ],
    )
    runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "warning",
            "--message",
            "missing authentication",
            "--source",
            "linter",
        ],
    )

    result = runner.invoke(
        cli, ["finding", "search", "injection", "--diagram-id", diagram_id]
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert "injection" in parsed["message"].lower()
    assert [parsed] == snapshot


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


def test_clear_all(db_path: Path) -> None:
    """Clear without --source removes all findings for the diagram."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)

    for i in range(3):
        runner.invoke(
            cli,
            [
                "finding",
                "create",
                "--diagram-id",
                diagram_id,
                "--severity",
                "error",
                "--message",
                f"finding {i}",
                "--source",
                "linter",
            ],
        )

    result = runner.invoke(cli, ["finding", "clear", "--diagram-id", diagram_id])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["cleared"] == 3

    # Nothing should remain
    list_result = runner.invoke(cli, ["finding", "list", "--diagram-id", diagram_id])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.output.splitlines() if line.strip()]
    assert len(lines) == 0


def test_clear_by_source(db_path: Path) -> None:
    """Clear with --source only removes findings from that source."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)

    # Two linter findings, one scanner finding
    for i in range(2):
        runner.invoke(
            cli,
            [
                "finding",
                "create",
                "--diagram-id",
                diagram_id,
                "--severity",
                "error",
                "--message",
                f"linter finding {i}",
                "--source",
                "linter",
            ],
        )
    runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "warning",
            "--message",
            "scanner finding",
            "--source",
            "scanner",
        ],
    )

    result = runner.invoke(
        cli,
        ["finding", "clear", "--diagram-id", diagram_id, "--source", "linter"],
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["cleared"] == 2

    # Scanner finding should still be present
    list_result = runner.invoke(cli, ["finding", "list", "--diagram-id", diagram_id])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.output.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["source"] == "scanner"


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


def test_create_invalid_severity(db_path: Path) -> None:
    """Create with an invalid severity value fails with a non-zero exit code."""
    runner = CliRunner()
    diagram_id = _create_test_diagram(runner)
    result = runner.invoke(
        cli,
        [
            "finding",
            "create",
            "--diagram-id",
            diagram_id,
            "--severity",
            "critical",
            "--message",
            "bad",
            "--source",
            "linter",
        ],
    )
    assert result.exit_code != 0
