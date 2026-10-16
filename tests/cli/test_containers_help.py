"""Golden snapshots for tm container --help text."""

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
        ("container", "--help"),
        ("container", "list", "--help"),
        ("container", "get", "--help"),
        ("container", "delete", "--help"),
        ("container", "search", "--help"),
        ("container", "create", "--help"),
        ("container", "create", "trust-boundary", "--help"),
        ("container", "create", "container", "--help"),
        ("container", "update", "--help"),
        ("container", "update", "trust-boundary", "--help"),
        ("container", "update", "container", "--help"),
        ("container", "set-parent", "--help"),
        ("container", "clear-parent", "--help"),
        ("container", "parent-of", "--help"),
        ("container", "list-children", "--help"),
        ("container", "link-document", "--help"),
        ("container", "unlink-document", "--help"),
        ("container", "list-documents", "--help"),
        ("container", "link-observation", "--help"),
        ("container", "unlink-observation", "--help"),
        ("container", "list-observations", "--help"),
    ],
    ids=[
        "group",
        "list",
        "get",
        "delete",
        "search",
        "create",
        "create-trust-boundary",
        "create-container",
        "update",
        "update-trust-boundary",
        "update-container",
        "set-parent",
        "clear-parent",
        "parent-of",
        "list-children",
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
