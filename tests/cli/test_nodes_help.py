"""Golden snapshots for tm node --help text."""

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
        ("node", "--help"),
        ("node", "list", "--help"),
        ("node", "get", "--help"),
        ("node", "delete", "--help"),
        ("node", "search", "--help"),
        ("node", "create", "--help"),
        ("node", "create", "process", "--help"),
        ("node", "create", "external-entity", "--help"),
        ("node", "create", "data-store", "--help"),
        ("node", "update", "--help"),
        ("node", "update", "process", "--help"),
        ("node", "update", "external-entity", "--help"),
        ("node", "update", "data-store", "--help"),
        ("node", "set-parent", "--help"),
        ("node", "clear-parent", "--help"),
        ("node", "parent-of", "--help"),
        ("node", "link-document", "--help"),
        ("node", "unlink-document", "--help"),
        ("node", "list-documents", "--help"),
        ("node", "link-observation", "--help"),
        ("node", "unlink-observation", "--help"),
        ("node", "list-observations", "--help"),
    ],
    ids=[
        "group",
        "list",
        "get",
        "delete",
        "search",
        "create",
        "create-process",
        "create-external-entity",
        "create-data-store",
        "update",
        "update-process",
        "update-external-entity",
        "update-data-store",
        "set-parent",
        "clear-parent",
        "parent-of",
        "link-document",
        "unlink-document",
        "list-documents",
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
