"""Tests for entity↔document links (all four DFD kinds + reverse views)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli


def test_node_link_unlink_list_round_trip(db_with_seed) -> None:
    """AC3.9: node link-document / list-documents / unlink-document round trip."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    node_id = seed_ids.process_node_id
    doc_id = seed_ids.document_ids[0]

    # Link: first time should return linked: true
    link_result = runner.invoke(
        cli, ["node", "link-document", str(node_id), str(doc_id)]
    )
    assert link_result.exit_code == 0
    payload = json.loads(link_result.stdout)
    assert payload["linked"] is True
    assert payload["node_id"] == str(node_id)
    assert payload["document_id"] == str(doc_id)

    # List should include the doc
    list_result = runner.invoke(cli, ["node", "list-documents", str(node_id)])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    docs = [json.loads(line) for line in lines]
    assert any(d["id"] == str(doc_id) for d in docs)

    # Relink: second time should return linked: false with reason
    relink_result = runner.invoke(
        cli, ["node", "link-document", str(node_id), str(doc_id)]
    )
    assert relink_result.exit_code == 0
    payload = json.loads(relink_result.stdout)
    assert payload["linked"] is False
    assert payload.get("reason") == "already_linked"

    # Unlink
    unlink_result = runner.invoke(
        cli, ["node", "unlink-document", str(node_id), str(doc_id)]
    )
    assert unlink_result.exit_code == 0
    payload = json.loads(unlink_result.stdout)
    assert payload["unlinked"] is True
    assert payload["node_id"] == str(node_id)
    assert payload["document_id"] == str(doc_id)

    # List should now be empty
    list_after = runner.invoke(cli, ["node", "list-documents", str(node_id)])
    assert list_after.exit_code == 0
    lines = [line for line in list_after.stdout.splitlines() if line.strip()]
    assert all(d["id"] != str(doc_id) for d in [json.loads(line) for line in lines])


def test_container_link_unlink_list_round_trip(db_with_seed) -> None:
    """AC3.9: container link-document / list-documents / unlink-document round trip."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    container_id = seed_ids.trust_boundary_id
    doc_id = seed_ids.document_ids[0]

    # Link: first time should return linked: true
    link_result = runner.invoke(
        cli, ["container", "link-document", str(container_id), str(doc_id)]
    )
    assert link_result.exit_code == 0
    payload = json.loads(link_result.stdout)
    assert payload["linked"] is True
    assert payload["container_id"] == str(container_id)
    assert payload["document_id"] == str(doc_id)

    # List should include the doc
    list_result = runner.invoke(cli, ["container", "list-documents", str(container_id)])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    docs = [json.loads(line) for line in lines]
    assert any(d["id"] == str(doc_id) for d in docs)

    # Relink: second time should return linked: false with reason
    relink_result = runner.invoke(
        cli, ["container", "link-document", str(container_id), str(doc_id)]
    )
    assert relink_result.exit_code == 0
    payload = json.loads(relink_result.stdout)
    assert payload["linked"] is False
    assert payload.get("reason") == "already_linked"

    # Unlink
    unlink_result = runner.invoke(
        cli, ["container", "unlink-document", str(container_id), str(doc_id)]
    )
    assert unlink_result.exit_code == 0
    payload = json.loads(unlink_result.stdout)
    assert payload["unlinked"] is True

    # List should now be empty
    list_after = runner.invoke(cli, ["container", "list-documents", str(container_id)])
    assert list_after.exit_code == 0
    lines = [line for line in list_after.stdout.splitlines() if line.strip()]
    docs = [json.loads(line) for line in lines]
    assert all(d["id"] != str(doc_id) for d in docs)


def test_flow_link_unlink_list_round_trip(db_with_seed) -> None:
    """AC3.9: flow link-document / list-documents / unlink-document round trip."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    flow_id = seed_ids.data_flow_id
    doc_id = seed_ids.document_ids[0]

    # Link: first time should return linked: true
    link_result = runner.invoke(
        cli, ["flow", "link-document", str(flow_id), str(doc_id)]
    )
    assert link_result.exit_code == 0
    payload = json.loads(link_result.stdout)
    assert payload["linked"] is True
    assert payload["flow_id"] == str(flow_id)
    assert payload["document_id"] == str(doc_id)

    # List should include the doc
    list_result = runner.invoke(cli, ["flow", "list-documents", str(flow_id)])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    docs = [json.loads(line) for line in lines]
    assert any(d["id"] == str(doc_id) for d in docs)

    # Relink: second time should return linked: false with reason
    relink_result = runner.invoke(
        cli, ["flow", "link-document", str(flow_id), str(doc_id)]
    )
    assert relink_result.exit_code == 0
    payload = json.loads(relink_result.stdout)
    assert payload["linked"] is False
    assert payload.get("reason") == "already_linked"

    # Unlink
    unlink_result = runner.invoke(
        cli, ["flow", "unlink-document", str(flow_id), str(doc_id)]
    )
    assert unlink_result.exit_code == 0
    payload = json.loads(unlink_result.stdout)
    assert payload["unlinked"] is True

    # List should now be empty
    list_after = runner.invoke(cli, ["flow", "list-documents", str(flow_id)])
    assert list_after.exit_code == 0
    lines = [line for line in list_after.stdout.splitlines() if line.strip()]
    docs = [json.loads(line) for line in lines]
    assert all(d["id"] != str(doc_id) for d in docs)


def test_data_item_link_unlink_list_round_trip(db_with_seed) -> None:
    """AC3.9: data-item link-document / list-documents / unlink-document round trip."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    item_id = seed_ids.data_item_with_parent_id
    doc_id = seed_ids.document_ids[0]

    # Link: first time should return linked: true
    link_result = runner.invoke(
        cli, ["data-item", "link-document", str(item_id), str(doc_id)]
    )
    assert link_result.exit_code == 0
    payload = json.loads(link_result.stdout)
    assert payload["linked"] is True
    assert payload["item_id"] == str(item_id)
    assert payload["document_id"] == str(doc_id)

    # List should include the doc
    list_result = runner.invoke(cli, ["data-item", "list-documents", str(item_id)])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    docs = [json.loads(line) for line in lines]
    assert any(d["id"] == str(doc_id) for d in docs)

    # Relink: second time should return linked: false with reason
    relink_result = runner.invoke(
        cli, ["data-item", "link-document", str(item_id), str(doc_id)]
    )
    assert relink_result.exit_code == 0
    payload = json.loads(relink_result.stdout)
    assert payload["linked"] is False
    assert payload.get("reason") == "already_linked"

    # Unlink
    unlink_result = runner.invoke(
        cli, ["data-item", "unlink-document", str(item_id), str(doc_id)]
    )
    assert unlink_result.exit_code == 0
    payload = json.loads(unlink_result.stdout)
    assert payload["unlinked"] is True

    # List should now be empty
    list_after = runner.invoke(cli, ["data-item", "list-documents", str(item_id)])
    assert list_after.exit_code == 0
    lines = [line for line in list_after.stdout.splitlines() if line.strip()]
    docs = [json.loads(line) for line in lines]
    assert all(d["id"] != str(doc_id) for d in docs)


def test_document_list_nodes_returns_linked_node(db_with_seed) -> None:
    """AC3.10: document list-nodes returns the node with type discriminator."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    node_id = seed_ids.process_node_id
    doc_id = seed_ids.document_ids[0]

    # Link node to document
    runner.invoke(cli, ["node", "link-document", str(node_id), str(doc_id)])

    # List nodes for document
    result = runner.invoke(cli, ["document", "list-nodes", str(doc_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    nodes = [json.loads(line) for line in lines]
    found = next((n for n in nodes if n["id"] == str(node_id)), None)
    assert found is not None
    assert found["type"] == "process"


def test_document_list_containers_returns_linked_container(db_with_seed) -> None:
    """AC3.10: document list-containers with type discriminator."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    container_id = seed_ids.trust_boundary_id
    doc_id = seed_ids.document_ids[0]

    # Link container to document
    runner.invoke(cli, ["container", "link-document", str(container_id), str(doc_id)])

    # List containers for document
    result = runner.invoke(cli, ["document", "list-containers", str(doc_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    containers = [json.loads(line) for line in lines]
    found = next((c for c in containers if c["id"] == str(container_id)), None)
    assert found is not None
    assert found["type"] == "trust_boundary"


def test_document_list_flows_returns_linked_flow(db_with_seed) -> None:
    """AC3.10: document list-flows returns the flow."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    flow_id = seed_ids.data_flow_id
    doc_id = seed_ids.document_ids[0]

    # Link flow to document
    runner.invoke(cli, ["flow", "link-document", str(flow_id), str(doc_id)])

    # List flows for document
    result = runner.invoke(cli, ["document", "list-flows", str(doc_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    flows = [json.loads(line) for line in lines]
    found = next((f for f in flows if f["id"] == str(flow_id)), None)
    assert found is not None


def test_document_list_items_returns_linked_item(db_with_seed) -> None:
    """AC3.10: document list-items returns the data item."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    item_id = seed_ids.data_item_with_parent_id
    doc_id = seed_ids.document_ids[0]

    # Link item to document
    runner.invoke(cli, ["data-item", "link-document", str(item_id), str(doc_id)])

    # List items for document
    result = runner.invoke(cli, ["document", "list-items", str(doc_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    items = [json.loads(line) for line in lines]
    found = next((i for i in items if i["id"] == str(item_id)), None)
    assert found is not None


def test_link_document_unknown_entity_exits_3_fk(db_with_seed) -> None:
    """AC5.4: linking to missing entity exits 3 with constraint=foreign_key."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    doc_id = seed_ids.document_ids[0]

    result = runner.invoke(cli, ["node", "link-document", "99999", str(doc_id)])
    assert result.exit_code == 3
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("constraint") == "foreign_key"


def test_link_document_unknown_doc_exits_3_fk(db_with_seed) -> None:
    """AC5.4: linking missing document exits 3 with constraint=foreign_key."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()

    node_id = seed_ids.process_node_id

    result = runner.invoke(cli, ["node", "link-document", str(node_id), "99999"])
    assert result.exit_code == 3
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("constraint") == "foreign_key"


def test_document_list_nodes_for_missing_doc_exits_2(db_path: Path) -> None:
    """AC1.5: list-nodes for missing document exits 2 with not_found."""
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "list-nodes", "99999"])
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("code") == "not_found"
