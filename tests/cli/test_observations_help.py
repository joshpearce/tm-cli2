"""Golden snapshots for tm observation --help text."""

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
        ("observation", "--help"),
        ("observation", "list", "--help"),
        ("observation", "get", "--help"),
        ("observation", "create", "--help"),
        ("observation", "update", "--help"),
        ("observation", "delete", "--help"),
        ("observation", "search", "--help"),
        ("observation", "list-nodes", "--help"),
        ("observation", "list-containers", "--help"),
        ("observation", "list-flows", "--help"),
        ("observation", "list-items", "--help"),
    ],
    ids=[
        "group",
        "list",
        "get",
        "create",
        "update",
        "delete",
        "search",
        "list-nodes",
        "list-containers",
        "list-flows",
        "list-items",
    ],
)
def test_help_snapshots(
    args: tuple[str, ...], plain_snapshot: SnapshotAssertion
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0
    assert result.output == plain_snapshot
