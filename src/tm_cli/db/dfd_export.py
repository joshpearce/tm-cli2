# pattern: Functional Core
"""Pure adapter: tm-cli entities → dfd_editor push-body dict.

This module has zero side effects: no DB calls, no HTTP, no file IO.
Callers load entities through the existing repositories and pass them in.
"""

from __future__ import annotations

import uuid

from tm_cli.db.dfd_models import (
    ContainerVariant,
    DataFlow,
    DataItem,
    DataStoreNode,
    Diagram,
    ExternalEntityNode,
    ProcessNode,
    TrustBoundary,
    ValidationFinding,
)

# Stable namespace UUID for deterministic element UUIDs across re-pushes.
# Chosen once at random (uuid4) and hard-coded — DO NOT CHANGE.
# Changing this value rebuilds dfd_editor-side layout from scratch because
# every UUIDv5 derived from it would differ, breaking identity continuity.
NS_TM_DIAGRAM_PUSH = uuid.UUID("6537cad7-dabf-48fa-89e7-33f01cdf5f71")

_VALID_COLLECTIONS: frozenset[str] = frozenset(
    {"nodes", "containers", "data_flows", "data_items"}
)

_ENTITY_KIND_TO_COLLECTION: dict[str, str] = {
    "node": "nodes",
    "container": "containers",
    "data_flow": "data_flows",
    "data_item": "data_items",
}


def guid_for(diagram_int_id: int, collection: str, local_int_id: int) -> str:
    """Deterministic UUIDv5 for a tm-cli element.

    Same (diagram, collection, id) tuple always produces the same UUID,
    so dfd_editor-side layout survives re-pushes.
    """
    if collection not in _VALID_COLLECTIONS:
        raise ValueError(
            f"unknown collection {collection!r}; "
            f"must be one of {sorted(_VALID_COLLECTIONS)}"
        )
    key = f"{diagram_int_id}:{collection}:{local_int_id}"
    return str(uuid.uuid5(NS_TM_DIAGRAM_PUSH, key))


def to_dfd_editor_dict(
    diagram: Diagram,
    nodes: list[ProcessNode | ExternalEntityNode | DataStoreNode],
    containers: list[TrustBoundary | ContainerVariant],
    container_parents: dict[int, int],
    flows: list[DataFlow],
    items: list[DataItem],
    payloads_by_flow: dict[int, dict[int, list[int]]],
    findings: list[ValidationFinding] | None = None,
    entity_kinds: dict[int, str] | None = None,
) -> dict:
    """Convert already-loaded tm-cli entities to a dfd_editor Diagram-shaped dict.

    Parameters
    ----------
    diagram:
        The owning diagram row.
    nodes:
        All nodes belonging to the diagram, in desired output order.
    containers:
        All containers belonging to the diagram, in desired output order.
        The type annotation widens the plan's ``list[ContainerVariant]`` to
        ``list[TrustBoundary | ContainerVariant]`` because both concrete
        variants must be accepted — ``ContainerRepository`` returns either
        kind and both map to dfd_editor ``containers[]``.
    container_parents:
        Mapping of child entity int id → parent container int id.
    flows:
        All data flows belonging to the diagram, in desired output order.
    items:
        All data items belonging to the diagram, in desired output order.
    payloads_by_flow:
        Mapping of ``flow_id -> {1: [data_item_id, ...], 2: [...]}`` produced
        by ``DataFlowRepository.payloads_for_diagram``. Drives the
        ``node1_src_data_item_refs`` / ``node2_src_data_item_refs`` arrays on
        each emitted flow — without this, dfd_editor renders flows as
        directionless edges. Pass ``{}`` for a payload-less export. A flow
        absent from the dict (or with an empty list at an endpoint) emits an
        empty refs array for that endpoint.
    findings:
        Optional list of ``ValidationFinding`` rows for this diagram. When
        provided (and non-empty), a ``"validation"`` key is added to the
        output dict. Defaults to ``None`` so existing callers are unaffected.
    entity_kinds:
        Optional mapping of entity int id → kind string (``"node"``,
        ``"container"``, ``"data_flow"``, ``"data_item"``). Required for
        entity-level findings to resolve their GUIDs. If ``None``, entity
        findings are emitted without a ``"guid"`` key. Kinds not in
        ``_ENTITY_KIND_TO_COLLECTION`` (e.g. ``"process_component"``) are
        silently skipped.
    """
    did = diagram.id

    # --- meta ---
    meta = {
        "name": diagram.name,
        "description": diagram.description,
        "author": diagram.author,
        "created": diagram.created.isoformat(),  # non-nullable field
    }

    # --- nodes ---
    emitted_nodes: list[dict] = []
    for n in nodes:
        if isinstance(n, ProcessNode):
            emitted_nodes.append(
                {
                    "type": "process",
                    "guid": guid_for(did, "nodes", n.id),
                    "properties": {
                        "name": n.name,
                        "description": n.description,
                        "trust_level": n.trust_level,
                        "assumptions": n.assumptions,
                    },
                }
            )
        elif isinstance(n, ExternalEntityNode):
            emitted_nodes.append(
                {
                    "type": "external_entity",
                    "guid": guid_for(did, "nodes", n.id),
                    "properties": {
                        "name": n.name,
                        "description": n.description,
                        "entity_type": n.entity_type,
                        "out_of_scope": n.out_of_scope,
                    },
                }
            )
        elif isinstance(n, DataStoreNode):
            emitted_nodes.append(
                {
                    "type": "data_store",
                    "guid": guid_for(did, "nodes", n.id),
                    "properties": {
                        "name": n.name,
                        "description": n.description,
                        "storage_type": n.storage_type,
                        "contains_pii": n.contains_pii,
                        "encryption_at_rest": n.encryption_at_rest,
                    },
                }
            )
        else:
            raise TypeError(f"Unsupported node variant: {type(n).__name__}")

    # --- containers ---
    # Also build a lookup by int id for the children-population pass.
    emitted_containers: list[dict] = []
    container_by_id: dict[int, dict] = {}
    for c in containers:
        if isinstance(c, TrustBoundary):
            entry: dict = {
                "type": "trust_boundary",
                "guid": guid_for(did, "containers", c.id),
                "properties": {
                    "name": c.name,
                    "description": c.description,
                    "privilege_level": c.privilege_level,
                },
                "children": [],
            }
        elif isinstance(c, ContainerVariant):
            entry = {
                "type": "container",
                "guid": guid_for(did, "containers", c.id),
                "properties": {
                    "name": c.name,
                    "description": c.description,
                },
                "children": [],
            }
        else:
            raise TypeError(f"Unsupported container variant: {type(c).__name__}")
        emitted_containers.append(entry)
        container_by_id[c.id] = entry

    # --- populate container children ---
    # Build O(1) lookup: int id → collection name.
    # Node and container ids are guaranteed unique across both sets because they
    # share the `entity` master id table — so this merge never silently drops a key.
    child_collection: dict[int, str] = {n.id: "nodes" for n in nodes} | {
        c.id: "containers" for c in containers
    }

    # Accumulate children per parent before sorting, to avoid repeated list scans.
    parent_children: dict[int, list[str]] = {}
    for child_int_id, parent_int_id in container_parents.items():
        if child_int_id not in child_collection:
            raise ValueError(
                f"container_parents references unknown child id={child_int_id}"
            )
        if parent_int_id not in container_by_id:
            raise ValueError(
                "container_parents references unknown parent container "
                f"id={parent_int_id}"
            )
        child_guid = guid_for(did, child_collection[child_int_id], child_int_id)
        parent_children.setdefault(parent_int_id, []).append(child_guid)

    for parent_int_id, child_guids in parent_children.items():
        container_by_id[parent_int_id]["children"] = sorted(child_guids)

    # --- data_flows ---
    # Payload refs carry the only direction information dfd_editor sees: a
    # data_item attached to endpoint 1 means "originates at node1", endpoint 2
    # means "originates at node2". Empty refs => undirected/arrowless edge.
    def _refs(flow_id: int, endpoint: int) -> list[str]:
        ids = payloads_by_flow.get(flow_id, {}).get(endpoint, [])
        return [guid_for(did, "data_items", item_id) for item_id in ids]

    emitted_flows: list[dict] = [
        {
            "guid": guid_for(did, "data_flows", f.id),
            "node1": guid_for(did, "nodes", f.node1_id),
            "node2": guid_for(did, "nodes", f.node2_id),
            "properties": {
                "name": f.name,
                "protocol": f.protocol,
                "authenticated": f.authenticated,
                "encrypted": f.encrypted,
                "node1_src_data_item_refs": _refs(f.id, 1),
                "node2_src_data_item_refs": _refs(f.id, 2),
            },
        }
        for f in flows
    ]

    # --- data_items ---
    emitted_items: list[dict] = [
        {
            "guid": guid_for(did, "data_items", i.id),
            "parent": guid_for(did, "nodes", i.parent_node_id)
            if i.parent_node_id is not None
            else None,
            "identifier": i.identifier,
            "name": i.name,
            "description": i.description,
            "classification": i.classification,
        }
        for i in items
    ]

    result = {
        "meta": meta,
        "nodes": emitted_nodes,
        "containers": emitted_containers,
        "data_flows": emitted_flows,
        "data_items": emitted_items,
    }

    # --- validation findings ---
    if findings:
        emitted_validation: list[dict] = []
        for f in findings:
            entry: dict = {
                "severity": f.severity,
                "message": f.message,
            }
            if f.code is not None:
                entry["code"] = f.code
            if f.entity_id is not None and entity_kinds is not None:
                kind = entity_kinds.get(f.entity_id)
                if kind is not None:
                    collection = _ENTITY_KIND_TO_COLLECTION.get(kind)
                    if collection is not None:
                        entry["guid"] = guid_for(did, collection, f.entity_id)
            emitted_validation.append(entry)
        # Only include non-empty to avoid sending an empty array on clean diagrams
        result["validation"] = emitted_validation

    return result
