"""Golden snapshots for tm diagram --help text."""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from tm_cli.main import cli


@pytest.fixture
def plain_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Bypass the masking extension — help text has no volatile fields to mask."""
    from syrupy.extensions.amber import AmberSnapshotExtension

    return snapshot.use_extension(AmberSnapshotExtension)


@pytest.mark.parametrize(
    "args",
    [
        ("diagram", "--help"),
        ("diagram", "list", "--help"),
        ("diagram", "get", "--help"),
        ("diagram", "create", "--help"),
        ("diagram", "update", "--help"),
        ("diagram", "delete", "--help"),
        ("diagram", "search", "--help"),
        ("diagram", "push", "--help"),
    ],
    ids=[
        "group",
        "list",
        "get",
        "create",
        "update",
        "delete",
        "search",
        "push",
    ],
)
def test_help_snapshots(
    args: tuple[str, ...], plain_snapshot: SnapshotAssertion
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0
    assert result.output == plain_snapshot
