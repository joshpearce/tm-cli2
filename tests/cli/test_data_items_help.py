"""Golden snapshots for tm data-item --help text."""

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
        ("data-item", "--help"),
        ("data-item", "list", "--help"),
        ("data-item", "get", "--help"),
        ("data-item", "create", "--help"),
        ("data-item", "update", "--help"),
        ("data-item", "delete", "--help"),
        ("data-item", "search", "--help"),
        ("data-item", "link-document", "--help"),
        ("data-item", "unlink-document", "--help"),
        ("data-item", "list-documents", "--help"),
        ("data-item", "list-flows", "--help"),
        ("data-item", "link-observation", "--help"),
        ("data-item", "unlink-observation", "--help"),
        ("data-item", "list-observations", "--help"),
    ],
    ids=[
        "group",
        "list",
        "get",
        "create",
        "update",
        "delete",
        "search",
        "link-document",
        "unlink-document",
        "list-documents",
        "list-flows",
        "link-observation",
        "unlink-observation",
        "list-observations",
    ],
)
def test_help_snapshots(
    args: tuple[str, ...], plain_snapshot: SnapshotAssertion
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0
    assert result.output == plain_snapshot
