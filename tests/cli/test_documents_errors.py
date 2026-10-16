"""Error-path tests for tm document commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli


def test_get_missing_id_exits_2_not_found(db_with_seed, snapshot) -> None:
    """AC1.5, AC5.2, AC5.7: get missing id exits 2 with not_found error."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "get", "9999"])
    assert result.exit_code == 2
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"
    assert payload == snapshot


def test_update_missing_id_exits_2_not_found(db_with_seed, snapshot) -> None:
    """AC1.6, AC5.2: update missing id exits 2 with not_found error."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "update", "9999", "--title", "X"])
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"
    assert payload == snapshot


def test_create_missing_required_field_exits_1(db_path: Path, snapshot) -> None:
    """AC5.1: create missing required field exits 1 with user_error."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["document", "create", "--title", "T"]
    )  # missing --author and --content
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    assert payload == snapshot


def test_stdin_invalid_item_in_array_rolls_back_batch(db_path: Path, snapshot) -> None:
    """AC7.3: invalid item in array causes rollback and error reports index."""
    runner = CliRunner()
    body = json.dumps(
        [
            {
                "last_updated": "2026-01-01T00:00:00+00:00",
                "title": "ok",
                "author": "a",
                "content": "c",
            },
            {
                "last_updated": "2026-01-01T00:00:00+00:00",
                "author": "a",
                "content": "c",
            },  # missing title
        ]
    )
    result = runner.invoke(cli, ["document", "create", "--stdin"], input=body)
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    assert payload["error"]["input"]["index"] == 1
    # Rollback proof: an immediate list returns nothing.
    list_result = runner.invoke(cli, ["document", "list"])
    assert list_result.exit_code == 0
    assert list_result.stdout.strip() == ""
    assert payload == snapshot


def test_stdin_combined_with_named_flag_exits_1_user_error(
    db_path: Path, snapshot
) -> None:
    """AC7.4: --stdin combined with named flags is rejected."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["document", "create", "--stdin", "--title", "X"], input="{}"
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    assert "--stdin" in payload["error"]["message"]
    assert payload == snapshot


def test_search_with_empty_text_exits_1(db_with_seed, snapshot) -> None:
    """AC5.1: search with empty text exits 1 with user_error."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "search", ""])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    assert payload == snapshot
