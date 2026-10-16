"""Acceptance test: the canonical DFD workflow end-to-end through the CLI."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def _ok(result):
    """Helper: assert exit code 0 and parse JSON stdout."""
    assert result.exit_code == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def _ndjson(result):
    """Helper: assert exit code 0 and parse NDJSON stdout."""
    assert result.exit_code == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def test_full_dfd_workflow(db_path) -> None:
    """Build a small threat model from scratch through the CLI.

    Steps:
      1. Create a diagram.
      2. Add two process nodes and a data store.
      3. Connect them with a data flow.
      4. Add a data item and attach it as a payload.
      5. Place the process inside a trust boundary.
      6. Create a document and link it to the data flow.
      7. Verify everything via list-* / search / get.
    """
    runner = CliRunner()

    # 1. Diagram
    result = runner.invoke(
        cli, ["diagram", "create", "--name=tm", "--description=test"]
    )
    diagram = _ok(result)
    diagram_id = diagram["id"]

    # 2. Nodes
    proc_a = _ok(
        runner.invoke(
            cli,
            [
                "node",
                "create",
                "process",
                "--diagram-id",
                diagram_id,
                "--name=worker",
                "--description=background",
                "--trust-level=admin",
            ],
        )
    )
    store = _ok(
        runner.invoke(
            cli,
            [
                "node",
                "create",
                "data-store",
                "--diagram-id",
                diagram_id,
                "--name=db",
                "--description=primary",
                "--storage-type=database",
                "--contains-pii",
                "--encryption-at-rest",
            ],
        )
    )

    # 3. Flow (between worker and store)
    flow = _ok(
        runner.invoke(
            cli,
            [
                "flow",
                "create",
                "--diagram-id",
                diagram_id,
                "--node1-id",
                proc_a["id"],
                "--node2-id",
                store["id"],
                "--name=writes",
                "--protocol=HTTPS",
                "--authenticated",
                "--encrypted",
            ],
        )
    )
    # Endpoints canonicalized (smaller id first).
    assert int(flow["node1_id"]) < int(flow["node2_id"])

    # 4. Data item + payload
    item = _ok(
        runner.invoke(
            cli,
            [
                "data-item",
                "create",
                "--diagram-id",
                diagram_id,
                "--identifier=user-record",
                "--name=user-record-item",
                "--description=PII",
                "--classification=pii",
            ],
        )
    )
    payload_link = _ok(
        runner.invoke(
            cli,
            [
                "flow",
                "add-payload",
                flow["id"],
                "--data-item",
                item["id"],
                "--from",
                proc_a["id"],
            ],
        )
    )
    assert payload_link["linked"] is True

    # 5. Trust boundary + parent
    tb = _ok(
        runner.invoke(
            cli,
            [
                "container",
                "create",
                "trust-boundary",
                "--diagram-id",
                diagram_id,
                "--name=corp",
                "--description=corp network",
                "--privilege-level=corporate",
            ],
        )
    )
    parent_set = _ok(runner.invoke(cli, ["node", "set-parent", proc_a["id"], tb["id"]]))
    assert parent_set is not None  # Returns empty on success
    parent_of = _ok(runner.invoke(cli, ["node", "parent-of", proc_a["id"]]))
    assert parent_of["parent"]["id"] == tb["id"]

    # 6. Document + flow link
    doc = _ok(
        runner.invoke(
            cli,
            [
                "document",
                "create",
                "--title=Threat Notes",
                "--author=agent",
                "--content=...",
            ],
        )
    )
    link = _ok(runner.invoke(cli, ["flow", "link-document", flow["id"], doc["id"]]))
    assert link["linked"] is True

    # 7. Verify reverse views
    flows_for_doc = _ndjson(runner.invoke(cli, ["document", "list-flows", doc["id"]]))
    assert any(f["id"] == flow["id"] for f in flows_for_doc)

    payloads = _ndjson(runner.invoke(cli, ["flow", "list-payloads", flow["id"]]))
    assert any(p["id"] == item["id"] for p in payloads)

    children = _ndjson(runner.invoke(cli, ["container", "list-children", tb["id"]]))
    assert any(c["id"] == proc_a["id"] for c in children)

    # Search across nodes via the CLI.
    found = _ndjson(
        runner.invoke(
            cli,
            [
                "node",
                "search",
                "worker",
                "--diagram-id",
                diagram_id,
                "--type=process",
            ],
        )
    )
    assert any(n["id"] == proc_a["id"] for n in found)
