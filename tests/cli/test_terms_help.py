"""Golden snapshots for tm term --help text."""

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
        ("term", "--help"),
        ("term", "list", "--help"),
        ("term", "get", "--help"),
        ("term", "create", "--help"),
        ("term", "update", "--help"),
        ("term", "delete", "--help"),
        ("term", "search", "--help"),
        ("term", "list-documents", "--help"),
    ],
    ids=[
        "group",
        "list",
        "get",
        "create",
        "update",
        "delete",
        "search",
        "list-documents",
    ],
)
def test_help_snapshots(
    args: tuple[str, ...], plain_snapshot: SnapshotAssertion
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0
    assert result.output == plain_snapshot
