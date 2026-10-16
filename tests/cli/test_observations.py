"""Golden snapshots for tm observation JSON output on all verbs."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_all_seeded_observations(db_with_seed, snapshot) -> None:
    """AC1.1: list returns all observations as NDJSON."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["observation", "list"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == len(seed_ids.observation_ids)
    parsed_lines = [json.loads(line) for line in lines]
    for obj in parsed_lines:
        json.loads(json.dumps(obj))
    assert parsed_lines == snapshot


def test_list_filtered_by_type_returns_subset(db_path: Path, snapshot) -> None:
    """AC1.1: list with --observation-type filter returns matching subset."""
    runner = CliRunner()
    # Create one todo and one question
    todo_result = runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--content",
            "Fix the bug",
            "--observation-type",
            "todo",
        ],
    )
    assert todo_result.exit_code == 0

    question_result = runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--content",
            "Is this secure?",
            "--observation-type",
            "question",
        ],
    )
    assert question_result.exit_code == 0

    # Filter by todo
    result = runner.invoke(cli, ["observation", "list", "--observation-type", "todo"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    parsed_lines = [json.loads(line) for line in lines]
    # All should be todos
    for obj in parsed_lines:
        assert obj["observation_type"] == "todo"
    assert parsed_lines == snapshot


def test_list_filtered_by_status(db_with_seed, snapshot) -> None:
    """AC1.1: list with --status filter returns matching subset."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["observation", "list", "--status", "open"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Seed has 2 open todos
    assert len(lines) == 2
    parsed_lines = [json.loads(line) for line in lines]
    for obj in parsed_lines:
        assert obj["status"] == "open"
    assert parsed_lines == snapshot


def test_get_returns_full_observation(db_with_seed, snapshot) -> None:
    """AC1.2: get returns full Observation object."""
    db_path, seed_ids = db_with_seed
    obs_id = seed_ids.observation_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["observation", "get", str(obs_id)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "id" in payload
    assert "content" in payload
    assert "observation_type" in payload
    assert "status" in payload
    assert payload == snapshot


def test_create_with_named_flags(db_path: Path, snapshot) -> None:
    """AC1.3: create with named flags returns the new row."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--content",
            "Review authentication",
            "--observation-type",
            "todo",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["content"] == "Review authentication"
    assert parsed["observation_type"] == "todo"
    assert parsed["status"] == "open"  # Default status
    assert isinstance(parsed["id"], str)
    assert parsed == snapshot


def test_update_returns_full_row(db_with_seed, snapshot) -> None:
    """AC1.4: update with valid patch returns the resulting full Observation."""
    db_path, seed_ids = db_with_seed
    obs_id = seed_ids.observation_ids[0]
    runner = CliRunner()
    result = runner.invoke(
        cli, ["observation", "update", str(obs_id), "--status", "closed"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["status"] == "closed"
    assert parsed == snapshot


def test_get_missing_id_exits_2(db_path: Path) -> None:
    """AC1.5: get of missing id exits 2 with error.code = 'not_found'."""
    runner = CliRunner()
    result = runner.invoke(cli, ["observation", "get", "9999"])
    assert result.exit_code == 2
    stderr = result.output
    payload = json.loads(stderr)
    assert payload.get("error", {}).get("code") == "not_found"


def test_update_missing_id_exits_2(db_path: Path) -> None:
    """AC1.6: update of missing id exits 2 with error.code = 'not_found'."""
    runner = CliRunner()
    result = runner.invoke(cli, ["observation", "update", "9999", "--status", "closed"])
    assert result.exit_code == 2
    stderr = result.output
    payload = json.loads(stderr)
    assert payload.get("error", {}).get("code") == "not_found"


def test_invalid_enum_value_exits_1(db_path: Path) -> None:
    """AC1.7: invalid enum value exits 1 at Click parser with Choice error."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--observation-type",
            "bogus",
            "--content",
            "x",
        ],
    )
    assert result.exit_code == 1
    stderr = result.output
    payload = json.loads(stderr)
    assert payload.get("error", {}).get("code") == "user_error"
    # Error message should mention the invalid value
    assert (
        "bogus" in payload.get("error", {}).get("message", "").lower()
        or "choice" in payload.get("error", {}).get("message", "").lower()
    )


def test_search_case_insensitive(db_with_seed, snapshot) -> None:
    """AC2.1: search matches case-insensitively across searchable columns."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["observation", "search", "SEED"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Should match both seeded observations
    assert len(lines) == 2
    parsed_lines = [json.loads(line) for line in lines]
    for obj in parsed_lines:
        assert "seed" in obj["content"].lower()
    assert parsed_lines == snapshot


def test_search_multi_token_and(db_with_seed, snapshot) -> None:
    """AC2.2: multi-token search AND-combines tokens."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["observation", "search", "seed 1"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Should match only "Seed observation 1"
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert "Seed observation 1" in parsed_lines[0]["content"]
    assert parsed_lines == snapshot


def test_search_text_plus_filters_and_combined(db_path: Path, snapshot) -> None:
    """AC2.3: search text AND filters combine."""
    runner = CliRunner()
    # Create one open todo "todo X" and one closed todo "todo Y"
    open_result = runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--content",
            "todo X",
            "--observation-type",
            "todo",
            "--status",
            "open",
        ],
    )
    assert open_result.exit_code == 0

    closed_result = runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--content",
            "todo Y",
            "--observation-type",
            "todo",
            "--status",
            "closed",
        ],
    )
    assert closed_result.exit_code == 0

    # Search for "todo" with type=todo and status=open
    result = runner.invoke(
        cli,
        [
            "observation",
            "search",
            "todo",
            "--observation-type",
            "todo",
            "--status",
            "open",
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Should match only the open todo
    assert len(lines) >= 1
    parsed_lines = [json.loads(line) for line in lines]
    # Check that we have at least the "todo X" entry with open status
    matching = [
        obj
        for obj in parsed_lines
        if "todo X" in obj.get("content", "") and obj.get("status") == "open"
    ]
    assert len(matching) >= 1
    assert parsed_lines == snapshot


def test_search_empty_text_with_filters_matches_list_shape(
    db_with_seed, snapshot
) -> None:
    """AC2.7: search with empty text + filters returns same shape as list."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    # Call search with no text but with filters
    search_result = runner.invoke(cli, ["observation", "search", "--status", "open"])
    assert search_result.exit_code == 0

    # Call list with same filters
    list_result = runner.invoke(cli, ["observation", "list", "--status", "open"])
    assert list_result.exit_code == 0

    # Both should return the same rows
    search_lines = [line for line in search_result.stdout.splitlines() if line.strip()]
    list_lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(search_lines) == len(list_lines)

    search_parsed = [json.loads(line) for line in search_lines]
    list_parsed = [json.loads(line) for line in list_lines]

    # Sort by id for comparison (order may differ)
    search_parsed.sort(key=lambda x: x["id"])
    list_parsed.sort(key=lambda x: x["id"])

    assert search_parsed == list_parsed == snapshot
