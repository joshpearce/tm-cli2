"""Golden snapshots for tm threat-catalog --help text."""

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
        ("threat-catalog", "--help"),
        ("threat-catalog", "list", "--help"),
        ("threat-catalog", "get", "--help"),
        ("threat-catalog", "search", "--help"),
        ("threat-catalog", "import-dir", "--help"),
    ],
    ids=[
        "group",
        "list",
        "get",
        "search",
        "import-dir",
    ],
)
def test_help_snapshots(
    args: tuple[str, ...], plain_snapshot: SnapshotAssertion
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0
    assert result.output == plain_snapshot
