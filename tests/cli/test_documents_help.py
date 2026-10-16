"""Golden snapshots for tm document --help text."""

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
        ("document", "--help"),
        ("document", "list", "--help"),
        ("document", "get", "--help"),
        ("document", "create", "--help"),
        ("document", "update", "--help"),
        ("document", "delete", "--help"),
        ("document", "search", "--help"),
        ("document", "link-term", "--help"),
        ("document", "unlink-term", "--help"),
        ("document", "list-terms", "--help"),
        ("document", "list-nodes", "--help"),
        ("document", "list-containers", "--help"),
        ("document", "list-flows", "--help"),
        ("document", "list-items", "--help"),
    ],
    ids=[
        "group",
        "list",
        "get",
        "create",
        "update",
        "delete",
        "search",
        "link-term",
        "unlink-term",
        "list-terms",
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
