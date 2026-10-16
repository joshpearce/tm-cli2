"""Smoke tests for the root ``tm`` group."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_cli_help_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "tm — agent-first" in result.output


def test_cli_unknown_subcommand_emits_structured_error() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["this-command-does-not-exist"])
    assert result.exit_code == 1
    # Verify JSON is on stderr, not stdout (documents the contract)
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"


def test_cli_no_subcommand_does_not_crash() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [])
    # Click prints usage and exits 0 (or 2, depending on click version);
    # what we care about is that no Python traceback escaped.
    assert "Traceback" not in result.output
