"""Meta-test: every leaf command in tm commands --json has a help snapshot.

LIMITATION: this test substring-matches each leaf's "group leaf-name" string against
the concatenated body of every .ambr snapshot file. It catches the common failure mode
(a new leaf added without any snapshot at all) but CANNOT catch:
  - A snapshot whose body was wrong from the start (the body still contains the leaf).
  - A swapped snapshot where leaf A's snapshot was blessed for leaf B.
  - False positives where one leaf's path appears incidentally inside an unrelated
    snapshot (e.g., the help text for `tm node list` mentions "node list" inside its own
    description, accidentally satisfying a hypothetical leaf with the same path).

Treat the meta-test as a coarse coverage gate, not a correctness check. Drift in
individual snapshots is caught by Syrupy's per-test diff at `pytest --snapshot-update`.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli


def _walk_leaves(node, path):
    """Walk tree and yield paths to leaf commands (no subcommands)."""
    if not node.get("subcommands"):
        yield path + [node["name"]]
        return
    for sub in node["subcommands"]:
        yield from _walk_leaves(sub, path + [node["name"]])


def test_every_leaf_has_a_help_snapshot() -> None:
    """Every leaf in tm commands --json has at least one help snapshot."""
    runner = CliRunner()
    tree = json.loads(runner.invoke(cli, ["commands"]).stdout)
    leaves = list(_walk_leaves(tree, []))
    assert leaves, "Tree had no leaves — sanity check failed"

    snapshot_dir = Path("tests/cli/__snapshots__")
    if not snapshot_dir.exists():
        snapshot_dir = Path(__file__).parent / "__snapshots__"

    # Read every .ambr file and concatenate. Snapshots are named test names — we
    # search the concatenated body for the leaf path's printable form so a new
    # leaf without a snapshot fails this test.
    body = "\n".join(p.read_text() for p in snapshot_dir.rglob("*.ambr"))

    missing = []
    for leaf in leaves:
        # Strip the root "tm" segment for the search pattern.
        path_str = " ".join(leaf[1:])
        if path_str and path_str not in body:
            missing.append(path_str)

    assert not missing, f"Leaf commands missing help snapshots: {missing}"
