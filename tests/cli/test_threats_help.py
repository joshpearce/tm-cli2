"""Golden snapshots for tm threat --help text."""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from tm_cli.main import cli


@pytest.fixture
def plain_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Bypass the masking extension - help text has no volatile fields to mask."""
    from syrupy.extensions.amber import AmberSnapshotExtension

    return snapshot.use_extension(AmberSnapshotExtension)


@pytest.mark.parametrize(
    "args",
    [
        ("threat", "--help"),
        ("threat", "list", "--help"),
        ("threat", "get", "--help"),
        ("threat", "create", "--help"),
        ("threat", "update", "--help"),
        ("threat", "delete", "--help"),
        ("threat", "search", "--help"),
        ("threat", "link-observation", "--help"),
        ("threat", "unlink-observation", "--help"),
        ("threat", "link-entity", "--help"),
        ("threat", "unlink-entity", "--help"),
    ],
    ids=[
        "group",
        "list",
        "get",
        "create",
        "update",
        "delete",
        "search",
        "link-observation",
        "unlink-observation",
        "link-entity",
        "unlink-entity",
    ],
)
def test_help_snapshots(
    args: tuple[str, ...], plain_snapshot: SnapshotAssertion
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0
    assert result.output == plain_snapshot
