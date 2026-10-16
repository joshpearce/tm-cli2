"""Tests for tm agent-info."""

from __future__ import annotations

from typing import get_args

from click.testing import CliRunner

from tm_cli.db.dfd_models import (
    Classification,
    ContainerType,
    ExternalEntityType,
    NodeType,
    PrivilegeLevel,
    StorageType,
    TrustLevel,
)
from tm_cli.db.models import ObservationStatus, ObservationType
from tm_cli.main import cli


def test_agent_info_exits_zero() -> None:
    result = CliRunner().invoke(cli, ["agent-info"])
    assert result.exit_code == 0


def test_agent_info_prints_orientation_snapshot(snapshot) -> None:
    result = CliRunner().invoke(cli, ["agent-info"])
    assert result.exit_code == 0
    assert result.output == snapshot


def test_agent_info_includes_every_enum_value() -> None:
    """Guard against drift: every Literal value must appear in the rendered text.

    `_render()` interpolates these via `typing.get_args`, so this is also a
    sanity check that the helper is wired up correctly.
    """
    output = CliRunner().invoke(cli, ["agent-info"]).output
    literals = (
        ObservationType,
        ObservationStatus,
        NodeType,
        TrustLevel,
        ExternalEntityType,
        StorageType,
        ContainerType,
        PrivilegeLevel,
        Classification,
    )
    for lit in literals:
        for value in get_args(lit):
            assert value in output, f"{value!r} missing from agent-info output"


def test_agent_info_registered_in_command_tree() -> None:
    """The command must be discoverable via `tm commands` so agents can find it."""
    import json

    result = CliRunner().invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.stdout)
    subcommands = {cmd["name"] for cmd in tree["subcommands"]}
    assert "agent-info" in subcommands
