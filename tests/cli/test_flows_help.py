"""Golden snapshots for tm flow --help text."""

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
        ("flow", "--help"),
        ("flow", "list", "--help"),
        ("flow", "get", "--help"),
        ("flow", "create", "--help"),
        ("flow", "update", "--help"),
        ("flow", "delete", "--help"),
        ("flow", "search", "--help"),
        ("flow", "add-payload", "--help"),
        ("flow", "remove-payload", "--help"),
        ("flow", "list-payloads", "--help"),
        ("flow", "link-document", "--help"),
        ("flow", "unlink-document", "--help"),
        ("flow", "list-documents", "--help"),
        ("flow", "link-observation", "--help"),
        ("flow", "unlink-observation", "--help"),
        ("flow", "list-observations", "--help"),
    ],
    ids=[
        "group",
        "list",
        "get",
        "create",
        "update",
        "delete",
        "search",
        "add-payload",
        "remove-payload",
        "list-payloads",
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
