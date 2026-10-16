"""Unit tests for the pure dfd_export builder (`to_dfd_editor_dict`).

All tests construct Pydantic models directly — no DB required — except for the
dfd_editor schema contract test which also uses direct construction.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tm_cli.db.dfd_export import NS_TM_DIAGRAM_PUSH, guid_for, to_dfd_editor_dict
from tm_cli.db.dfd_models import (
    ContainerVariant,
    DataFlow,
    DataItem,
    DataStoreNode,
    Diagram,
    ExternalEntityNode,
    ProcessNode,
    TrustBoundary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _diagram(id: int = 1) -> Diagram:
    return Diagram(
        id=id,
        name="test-diagram",
        description="a test diagram",
        author="tester",
        created=_EPOCH,
        dfd_editor_diagram_id=None,
    )


def _process(id: int = 10) -> ProcessNode:
    return ProcessNode(
        type="process",
        id=id,
        name="my-process",
        description="does processing",
        trust_level="public",
        assumptions=[],
    )


def _external(id: int = 20) -> ExternalEntityNode:
    return ExternalEntityNode(
        type="external_entity",
        id=id,
        name="a-user",
        description="an external user",
        entity_type="user",
        out_of_scope=False,
    )


def _store(id: int = 30) -> DataStoreNode:
    return DataStoreNode(
        type="data_store",
        id=id,
        name="main-db",
        description="primary database",
        storage_type="database",
        contains_pii=True,
        encryption_at_rest=True,
    )


def _boundary(id: int = 40) -> TrustBoundary:
    return TrustBoundary(
        type="trust_boundary",
        id=id,
        name="corp-boundary",
        description="corporate trust boundary",
        privilege_level="corporate",
    )


def _container(id: int = 50) -> ContainerVariant:
    return ContainerVariant(
        type="container",
        id=id,
        name="service-group",
        description="logical grouping",
    )


def _flow(id: int = 60, node1_id: int = 10, node2_id: int = 30) -> DataFlow:
    return DataFlow(
        id=id,
        node1_id=node1_id,
        node2_id=node2_id,
        name="proc-to-store",
        protocol="HTTPS",
        authenticated=True,
        encrypted=True,
    )


def _item_with_parent(id: int = 70, parent_node_id: int = 30) -> DataItem:
    return DataItem(
        id=id,
        identifier="DI-001",
        name="user-record",
        description="sensitive user data",
        classification="pii",
        parent_node_id=parent_node_id,
    )


def _item_without_parent(id: int = 80) -> DataItem:
    return DataItem(
        id=id,
        identifier="DI-002",
        name="audit-log",
        description="system audit events",
        classification="internal",
        parent_node_id=None,
    )


# ---------------------------------------------------------------------------
# guid_for tests
# ---------------------------------------------------------------------------


def test_guid_for_deterministic() -> None:
    g1 = guid_for(1, "nodes", 5)
    g2 = guid_for(1, "nodes", 5)
    assert g1 == g2

    assert guid_for(1, "nodes", 5) != guid_for(1, "nodes", 6)
    assert guid_for(1, "nodes", 5) != guid_for(1, "containers", 5)
    assert guid_for(1, "nodes", 5) != guid_for(2, "nodes", 5)


def test_guid_for_rejects_unknown_collection() -> None:
    with pytest.raises(ValueError, match="nope"):
        guid_for(1, "nope", 1)


def test_guid_for_returns_uuid_string() -> None:
    result = guid_for(1, "nodes", 5)
    # Must be parseable as UUID.
    parsed = uuid.UUID(result)
    assert str(parsed) == result
    # Must match the expected UUIDv5 computation.
    expected = str(uuid.uuid5(NS_TM_DIAGRAM_PUSH, "1:nodes:5"))
    assert result == expected


# ---------------------------------------------------------------------------
# to_dfd_editor_dict — field placement
# ---------------------------------------------------------------------------


def test_to_dfd_editor_dict_per_type_field_placement() -> None:
    """Variant-specific fields must live under 'properties', not at the root."""
    diagram = _diagram()
    proc = _process(10)
    ext = _external(20)
    store = _store(30)
    boundary = _boundary(40)
    container = _container(50)
    flow = _flow(60, node1_id=10, node2_id=30)
    item_with = _item_with_parent(70, parent_node_id=30)
    item_without = _item_without_parent(80)

    # proc is inside boundary; boundary is inside container.
    container_parents = {proc.id: boundary.id, boundary.id: container.id}

    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[proc, ext, store],
        containers=[boundary, container],
        container_parents=container_parents,
        flows=[flow],
        items=[item_with, item_without],
        payloads_by_flow={},
    )

    # Top-level keys
    assert set(doc.keys()) == {
        "meta",
        "nodes",
        "containers",
        "data_flows",
        "data_items",
    }

    # --- nodes ---
    for node_dict in doc["nodes"]:
        assert set(node_dict.keys()) == {"type", "guid", "properties"}
        props = node_dict["properties"]
        # Variant fields must be under properties, not at root.
        assert "name" in props
        assert "description" in props
        assert "trust_level" not in node_dict  # process-only
        assert "entity_type" not in node_dict  # external_entity-only
        assert "storage_type" not in node_dict  # data_store-only
        assert "contains_pii" not in node_dict
        assert "encryption_at_rest" not in node_dict
        assert "out_of_scope" not in node_dict
        assert "assumptions" not in node_dict

    # Spot-check each type's variant field is inside properties.
    proc_dict = next(d for d in doc["nodes"] if d["type"] == "process")
    assert "trust_level" in proc_dict["properties"]
    assert "assumptions" in proc_dict["properties"]

    ext_dict = next(d for d in doc["nodes"] if d["type"] == "external_entity")
    assert "entity_type" in ext_dict["properties"]
    assert "out_of_scope" in ext_dict["properties"]

    store_dict = next(d for d in doc["nodes"] if d["type"] == "data_store")
    assert "storage_type" in store_dict["properties"]
    assert "contains_pii" in store_dict["properties"]
    assert "encryption_at_rest" in store_dict["properties"]

    # --- containers ---
    for container_dict in doc["containers"]:
        assert set(container_dict.keys()) == {"type", "guid", "properties", "children"}
        props = container_dict["properties"]
        assert "name" in props
        assert "description" in props
        assert "privilege_level" not in container_dict  # must be under properties

    boundary_dict = next(c for c in doc["containers"] if c["type"] == "trust_boundary")
    assert "privilege_level" in boundary_dict["properties"]

    # --- flows ---
    for flow_dict in doc["data_flows"]:
        assert set(flow_dict.keys()) == {"guid", "node1", "node2", "properties"}
        props = flow_dict["properties"]
        assert props["node1_src_data_item_refs"] == []
        assert props["node2_src_data_item_refs"] == []
        assert "name" in props
        assert "protocol" in props
        assert "authenticated" in props
        assert "encrypted" in props
        # These must NOT be at root.
        assert "name" not in flow_dict
        assert "protocol" not in flow_dict

    # --- data_items ---
    for item_dict in doc["data_items"]:
        assert set(item_dict.keys()) == {
            "guid",
            "parent",
            "identifier",
            "name",
            "description",
            "classification",
        }


# ---------------------------------------------------------------------------
# to_dfd_editor_dict — children populated and sorted
# ---------------------------------------------------------------------------


def test_to_dfd_editor_dict_children_populated_and_sorted() -> None:
    """Parent container's children list is sorted by UUID string, ascending."""
    diagram = _diagram(id=99)

    # Three nodes whose UUID-string order differs from insertion order.
    n1 = _process(id=11)
    n2 = _process(id=22)
    n3 = _process(id=33)

    # Create two containers: parent holds n1, n2, n3; other_container holds nothing.
    parent = _boundary(id=41)
    other = _container(id=51)

    container_parents = {
        n1.id: parent.id,
        n2.id: parent.id,
        n3.id: parent.id,
    }

    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[n1, n2, n3],
        containers=[parent, other],
        container_parents=container_parents,
        flows=[],
        items=[],
        payloads_by_flow={},
    )

    parent_dict = next(c for c in doc["containers"] if c["type"] == "trust_boundary")
    other_dict = next(c for c in doc["containers"] if c["type"] == "container")

    assert other_dict["children"] == []

    children = parent_dict["children"]
    assert len(children) == 3

    # Precompute expected guids to verify sorting.
    expected_guids = sorted(
        [
            guid_for(99, "nodes", n1.id),
            guid_for(99, "nodes", n2.id),
            guid_for(99, "nodes", n3.id),
        ]
    )
    assert children == expected_guids
    assert children == sorted(children)


# ---------------------------------------------------------------------------
# to_dfd_editor_dict — payload refs (flow direction)
# ---------------------------------------------------------------------------


def test_to_dfd_editor_dict_populates_payload_refs_per_endpoint() -> None:
    """`payloads_by_flow` drives the two nodeN_src_data_item_refs arrays.

    Direction is the only thing dfd_editor sees about who-talks-to-whom: a
    data_item ref under `node1_src_data_item_refs` means "originates at
    node1". An empty array on both sides is what makes a flow render as a
    directionless edge — exactly the bug this parameter exists to prevent.
    """
    diagram = _diagram(id=1)
    proc = _process(10)
    store = _store(30)
    flow = _flow(60, node1_id=10, node2_id=30)
    item_req = _item_with_parent(70, parent_node_id=10)  # request payload (node1 → )
    item_resp = _item_with_parent(71, parent_node_id=30)  # response payload ( ← node2)

    # node1 (proc, id=10) sends item 70; node2 (store, id=30) sends item 71.
    payloads_by_flow = {flow.id: {1: [item_req.id], 2: [item_resp.id]}}

    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[proc, store],
        containers=[],
        container_parents={},
        flows=[flow],
        items=[item_req, item_resp],
        payloads_by_flow=payloads_by_flow,
    )

    flow_dict = doc["data_flows"][0]
    props = flow_dict["properties"]
    assert props["node1_src_data_item_refs"] == [
        guid_for(diagram.id, "data_items", item_req.id)
    ]
    assert props["node2_src_data_item_refs"] == [
        guid_for(diagram.id, "data_items", item_resp.id)
    ]


def test_to_dfd_editor_dict_missing_flow_in_payloads_emits_empty_refs() -> None:
    """A flow absent from payloads_by_flow gets two empty refs arrays.

    Locks in the back-compatible shape for payload-less exports (callers can
    legitimately pass `{}` and every flow ships with empty refs).
    """
    diagram = _diagram()
    proc = _process(10)
    store = _store(30)
    flow = _flow(60, node1_id=10, node2_id=30)

    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[proc, store],
        containers=[],
        container_parents={},
        flows=[flow],
        items=[],
        payloads_by_flow={},
    )

    props = doc["data_flows"][0]["properties"]
    assert props["node1_src_data_item_refs"] == []
    assert props["node2_src_data_item_refs"] == []


# ---------------------------------------------------------------------------
# to_dfd_editor_dict — cross-ref validation is NOT performed
# ---------------------------------------------------------------------------


def test_to_dfd_editor_dict_does_not_validate_cross_refs() -> None:
    """to_dfd_editor_dict does not validate that flow/item node refs exist in nodes.

    This is by design: validation is a server-side concern (dfd_editor enforces
    referential integrity on POST/PUT). The builder is purely structural — it
    maps local int ids to deterministic UUIDv5 guids without checking consistency.
    Callers are expected to load a consistent entity set via the repositories.
    """
    diagram = _diagram(id=1)

    # A flow whose node2_id (999) is NOT present in the nodes list.
    missing_node_id = 999
    orphan_flow = _flow(id=60, node1_id=10, node2_id=missing_node_id)

    # Must not raise even though missing_node_id has no corresponding node row.
    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[_process(10)],  # node 999 is intentionally absent
        containers=[],
        container_parents={},
        flows=[orphan_flow],
        items=[],
        payloads_by_flow={},
    )

    # The emitted flow must still contain the deterministic UUIDv5 for the missing id.
    expected_missing_guid = guid_for(diagram.id, "nodes", missing_node_id)
    flow_dict = doc["data_flows"][0]
    assert flow_dict["node2"] == expected_missing_guid


# ---------------------------------------------------------------------------
# to_dfd_editor_dict — determinism
# ---------------------------------------------------------------------------


def test_to_dfd_editor_dict_children_order_independent_of_parent_dict() -> None:
    """container_parents dict order does not affect emitted children-array order.

    Specifically: two dicts with identical entries but different insertion order
    produce byte-identical JSON, proving that children sorting is driven by the
    deterministic UUIDv5 guids rather than by the dict's iteration sequence.
    """
    diagram = _diagram()
    nodes = [_process(10), _external(20), _store(30)]
    containers = [_boundary(40), _container(50)]
    flows = [_flow(60, node1_id=10, node2_id=30)]
    items = [_item_with_parent(70), _item_without_parent(80)]

    # Two container_parents dicts with the same content but different iteration order.
    pairs = [(10, 40), (40, 50)]
    parents_forward = dict(pairs)
    parents_reversed = dict(reversed(pairs))

    doc1 = to_dfd_editor_dict(
        diagram, nodes, containers, parents_forward, flows, items, {}
    )
    doc2 = to_dfd_editor_dict(
        diagram, nodes, containers, parents_reversed, flows, items, {}
    )

    assert json.dumps(doc1, sort_keys=True) == json.dumps(doc2, sort_keys=True)


# ---------------------------------------------------------------------------
# to_dfd_editor_dict — data item parent handling
# ---------------------------------------------------------------------------


def test_to_dfd_editor_dict_data_item_parent_handling() -> None:
    """Items with parent emit the node's guid; items without parent emit None."""
    diagram = _diagram()
    store = _store(30)
    item_with = _item_with_parent(70, parent_node_id=store.id)
    item_without = _item_without_parent(80)

    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[store],
        containers=[],
        container_parents={},
        flows=[],
        items=[item_with, item_without],
        payloads_by_flow={},
    )

    by_id = {d["identifier"]: d for d in doc["data_items"]}

    # Item with parent: parent field must be the node's guid.
    expected_parent_guid = guid_for(diagram.id, "nodes", store.id)
    assert by_id["DI-001"]["parent"] == expected_parent_guid

    # Item without parent: parent field must be None.
    assert by_id["DI-002"]["parent"] is None


# ---------------------------------------------------------------------------
# dfd_editor schema contract
# ---------------------------------------------------------------------------


def _find_dfd_editor_server_dir() -> Path | None:
    """Locate dfd_editor's server/ directory.

    Checks ``DFD_EDITOR_PATH`` env var first (accepts either the repo root or
    the ``server/`` subdirectory directly), then falls back to the conventional
    sibling checkout at ``/Users/josh/code/dfd_editor/server``.
    Returns the directory containing ``schema.py``, or ``None`` if not found.
    """
    candidates: list[Path] = []

    env_path = os.environ.get("DFD_EDITOR_PATH")
    if env_path:
        p = Path(env_path)
        candidates.append(p / "server")  # treat as repo root
        candidates.append(p)  # treat as server/ directly

    candidates.append(Path("/Users/josh/code/dfd_editor/server"))

    for candidate in candidates:
        if (candidate / "schema.py").is_file():
            return candidate

    return None


def test_to_dfd_editor_dict_validates_against_dfd_editor_schema() -> None:
    """to_dfd_editor_dict output validates against dfd_editor's Diagram model.

    This test is skipped when dfd_editor is not available locally.  Set the
    ``DFD_EDITOR_PATH`` env var to the dfd_editor repo root (or its ``server/``
    subdirectory) to run it on other machines.  Without it, the test falls back
    to ``/Users/josh/code/dfd_editor/server`` and skips if that path is absent.
    """
    server_dir = _find_dfd_editor_server_dir()
    if server_dir is None:
        pytest.skip(
            "dfd_editor schema not found: "
            "set DFD_EDITOR_PATH or check out alongside tm-cli",
            allow_module_level=False,
        )

    sys.path.insert(0, str(server_dir))
    try:
        from schema import Diagram as DfdEditorDiagram  # type: ignore[import]
    finally:
        sys.path.pop(0)

    # Build a non-trivial document with one of each entity kind.
    diagram = _diagram()
    proc = _process(10)
    store = _store(30)
    boundary = _boundary(40)
    container = _container(50)
    flow = _flow(60, node1_id=proc.id, node2_id=store.id)
    item_with = _item_with_parent(70, parent_node_id=store.id)
    item_without = _item_without_parent(80)

    # proc is inside boundary; boundary is inside container.
    container_parents = {proc.id: boundary.id, boundary.id: container.id}

    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[proc, store],
        containers=[boundary, container],
        container_parents=container_parents,
        flows=[flow],
        items=[item_with, item_without],
        payloads_by_flow={},
    )

    # Must not raise.
    validated = DfdEditorDiagram.model_validate(doc)

    # Node UUIDs are valid and correspond to the expected guids.
    node_guids = {str(n.guid) for n in validated.nodes}
    assert guid_for(diagram.id, "nodes", proc.id) in node_guids
    assert guid_for(diagram.id, "nodes", store.id) in node_guids

    # Both flow endpoints must reference existing nodes (belt-and-braces:
    # dfd_editor's model validator already enforces this, but we lock it in
    # as an explicit assertion).
    node_guids_uuid = {n.guid for n in validated.nodes}
    for dfd_flow in validated.data_flows:
        assert dfd_flow.node1 in node_guids_uuid and dfd_flow.node2 in node_guids_uuid

    # Data item with parent: parent UUID matches the node's guid.
    items_with_parent = [di for di in validated.data_items if di.parent is not None]
    assert len(items_with_parent) == 1
    assert str(items_with_parent[0].parent) == guid_for(diagram.id, "nodes", store.id)


# ---------------------------------------------------------------------------
# to_dfd_editor_dict — validation findings
# ---------------------------------------------------------------------------


def _finding(
    *,
    id: int = 100,
    diagram_id: int = 1,
    entity_id: int | None = None,
    severity: str = "error",
    message: str = "something is broken",
    source: str = "linter",
    code: str | None = None,
):
    from tm_cli.db.dfd_models import ValidationFinding

    return ValidationFinding(
        id=id,
        diagram_id=diagram_id,
        entity_id=entity_id,
        severity=severity,
        message=message,
        source=source,
        code=code,
        created=_EPOCH,
    )


def test_to_dfd_editor_dict_no_findings_omits_validation_key() -> None:
    """Calling without findings must NOT emit a 'validation' key (backward compat)."""
    diagram = _diagram()
    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[],
        containers=[],
        container_parents={},
        flows=[],
        items=[],
        payloads_by_flow={},
        # findings omitted entirely
    )
    assert "validation" not in doc


def test_to_dfd_editor_dict_empty_findings_omits_validation_key() -> None:
    """Passing findings=[] must NOT emit a 'validation' key."""
    diagram = _diagram()
    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[],
        containers=[],
        container_parents={},
        flows=[],
        items=[],
        payloads_by_flow={},
        findings=[],
    )
    assert "validation" not in doc


def test_to_dfd_editor_dict_findings_with_entity_guid() -> None:
    """Entity-level finding resolves to the node's deterministic guid."""
    diagram = _diagram(id=1)
    node = _process(id=10)
    finding = _finding(entity_id=node.id, severity="error", message="bad process")

    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[node],
        containers=[],
        container_parents={},
        flows=[],
        items=[],
        payloads_by_flow={},
        findings=[finding],
        entity_kinds={node.id: "node"},
    )

    assert "validation" in doc
    entries = doc["validation"]
    assert len(entries) == 1
    expected_guid = guid_for(diagram.id, "nodes", node.id)
    assert entries[0]["guid"] == expected_guid


def test_to_dfd_editor_dict_findings_diagram_level() -> None:
    """Diagram-level finding (entity_id=None) must NOT have a 'guid' key."""
    diagram = _diagram()
    finding = _finding(entity_id=None, severity="warning", message="missing author")

    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[],
        containers=[],
        container_parents={},
        flows=[],
        items=[],
        payloads_by_flow={},
        findings=[finding],
    )

    assert "validation" in doc
    entries = doc["validation"]
    assert len(entries) == 1
    assert "guid" not in entries[0]


def test_to_dfd_editor_dict_findings_includes_code_when_present() -> None:
    """Finding with code='E001' must include 'code' in the emitted entry."""
    diagram = _diagram()
    finding = _finding(code="E001")

    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[],
        containers=[],
        container_parents={},
        flows=[],
        items=[],
        payloads_by_flow={},
        findings=[finding],
    )

    entries = doc["validation"]
    assert len(entries) == 1
    assert entries[0]["code"] == "E001"


def test_to_dfd_editor_dict_findings_omits_code_when_none() -> None:
    """Finding with code=None must NOT include a 'code' key in the emitted entry."""
    diagram = _diagram()
    finding = _finding(code=None)

    doc = to_dfd_editor_dict(
        diagram=diagram,
        nodes=[],
        containers=[],
        container_parents={},
        flows=[],
        items=[],
        payloads_by_flow={},
        findings=[finding],
    )

    entries = doc["validation"]
    assert len(entries) == 1
    assert "code" not in entries[0]
