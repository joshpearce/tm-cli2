"""Golden snapshots for tm process-component --help text."""

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
        ("process-component", "--help"),
        ("process-component", "list", "--help"),
        ("process-component", "get", "--help"),
        ("process-component", "create", "--help"),
        ("process-component", "update", "--help"),
        ("process-component", "delete", "--help"),
        ("process-component", "search", "--help"),
        ("process-component", "link-document", "--help"),
        ("process-component", "unlink-document", "--help"),
        ("process-component", "list-documents", "--help"),
        ("process-component", "link-observation", "--help"),
        ("process-component", "unlink-observation", "--help"),
        ("process-component", "list-observations", "--help"),
        ("process-component", "set-parent", "--help"),
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
        "link-observation",
        "unlink-observation",
        "list-observations",
        "set-parent",
    ],
)
def test_help_snapshots(
    args: tuple[str, ...], plain_snapshot: SnapshotAssertion
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0
    assert result.output == plain_snapshot
