"""Golden snapshots for tm finding --help text."""

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
        ("finding", "--help"),
        ("finding", "create", "--help"),
        ("finding", "get", "--help"),
        ("finding", "update", "--help"),
        ("finding", "delete", "--help"),
        ("finding", "list", "--help"),
        ("finding", "search", "--help"),
        ("finding", "clear", "--help"),
    ],
    ids=[
        "group",
        "create",
        "get",
        "update",
        "delete",
        "list",
        "search",
        "clear",
    ],
)
def test_help_snapshots(
    args: tuple[str, ...], plain_snapshot: SnapshotAssertion
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0
    assert result.output == plain_snapshot
