"""Deterministic seed data for golden snapshot tests.

The seed populates a single canonical diagram named ``non-default`` so
default-diagram-fallback tests in Phase 4 don't accidentally pick it up.
Every row is addressable via the returned ``SeedIds`` mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from tm_cli.db import (
    ContainerRepository,
    ContainerVariantCreate,
    DataFlowCreate,
    DataFlowRepository,
    DataItemCreate,
    DataItemRepository,
    DataStoreNodeCreate,
    DiagramCreate,
    DiagramRepository,
    DocumentCreate,
    DocumentRepository,
    ExternalEntityNodeCreate,
    NodeRepository,
    ObservationCreate,
    ObservationRepository,
    ProcessComponentCreate,
    ProcessComponentRepository,
    ProcessNodeCreate,
    TermCreate,
    TermRepository,
    ThreatCatalogCreate,
    ThreatCatalogRepository,
    ThreatCreate,
    ThreatRepository,
    TrustBoundaryCreate,
    ValidationFindingCreate,
    ValidationFindingRepository,
    connect,
)


@dataclass
class SeedIds:
    diagram_id: int
    process_node_id: int
    external_entity_node_id: int
    data_store_node_id: int
    container_id: int
    trust_boundary_id: int
    data_flow_id: int
    data_item_with_parent_id: int
    data_item_without_parent_id: int
    document_ids: list[int] = field(default_factory=list)
    term_ids: list[int] = field(default_factory=list)
    observation_ids: list[int] = field(default_factory=list)
    process_component_ids: list[int] = field(default_factory=list)
    threat_catalog_ids: list[int] = field(default_factory=list)
    threat_ids: list[int] = field(default_factory=list)
    finding_ids: list[int] = field(default_factory=list)


def seed(db_path: Path) -> SeedIds:
    """Populate ``db_path`` with deterministic fixtures and return their ids."""

    with connect(db_path) as conn:
        diagrams = DiagramRepository(conn)
        nodes = NodeRepository(conn)
        containers = ContainerRepository(conn)
        flows = DataFlowRepository(conn)
        items = DataItemRepository(conn)
        documents = DocumentRepository(conn)
        terms = TermRepository(conn)
        observations = ObservationRepository(conn)

        diagram = diagrams.create(
            DiagramCreate(
                name="non-default", description="seed diagram", author="seeder"
            ),
        )
        process = nodes.create(
            diagram.id,
            ProcessNodeCreate(
                type="process",
                name="seed-process",
                description="A seeded process node.",
                trust_level="authenticated",
                assumptions=["seeded"],
            ),
        )
        external = nodes.create(
            diagram.id,
            ExternalEntityNodeCreate(
                type="external_entity",
                name="seed-external",
                description="A seeded external entity.",
                entity_type="user",
                out_of_scope=False,
            ),
        )
        store = nodes.create(
            diagram.id,
            DataStoreNodeCreate(
                type="data_store",
                name="seed-store",
                description="A seeded data store.",
                storage_type="database",
                contains_pii=True,
                encryption_at_rest=True,
            ),
        )
        container = containers.create(
            diagram.id,
            ContainerVariantCreate(
                type="container",
                name="seed-container",
                description="A seeded container.",
            ),
        )
        boundary = containers.create(
            diagram.id,
            TrustBoundaryCreate(
                type="trust_boundary",
                name="seed-boundary",
                description="A seeded trust boundary.",
                privilege_level="corporate",
            ),
        )
        flow = flows.create(
            diagram.id,
            DataFlowCreate(
                node1_id=process.id,
                node2_id=store.id,
                name="seed-flow",
                protocol="HTTPS",
                authenticated=True,
                encrypted=True,
            ),
        )
        item_with_parent = items.create(
            diagram.id,
            DataItemCreate(
                identifier="seed-item-1",
                name="item-with-parent",
                description="seeded data item",
                classification="pii",
                parent_node_id=process.id,
            ),
        )
        item_without_parent = items.create(
            diagram.id,
            DataItemCreate(
                identifier="seed-item-2",
                name="item-without-parent",
                description="seeded data item",
                classification="public",
            ),
        )

        components = ProcessComponentRepository(conn)
        comp1 = components.create(
            diagram.id,
            ProcessComponentCreate(
                parent_process_id=process.id,
                name="seed-controller",
                description="A seeded controller component.",
                component_type="controller",
            ),
        )
        comp2 = components.create(
            diagram.id,
            ProcessComponentCreate(
                parent_process_id=process.id,
                name="seed-service",
                description="A seeded service component.",
                component_type="service",
            ),
        )

        doc_ids = [
            documents.create(
                DocumentCreate(
                    title=f"Seed Doc {i}",
                    author="seeder",
                    content=f"Seeded document body {i}.",
                    last_updated=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            ).id
            for i in (1, 2)
        ]
        term_ids = [
            terms.create(
                TermCreate(term=f"seed-term-{i}", definition=f"definition {i}"),
            ).id
            for i in (1, 2, 3)
        ]
        obs_ids = [
            observations.create(
                ObservationCreate(
                    content=f"Seed observation {i}",
                    observation_type="todo",
                    status="open",
                ),
            ).id
            for i in (1, 2)
        ]

        threat_catalog_repo = ThreatCatalogRepository(conn)
        catalog1 = threat_catalog_repo.create(
            ThreatCatalogCreate(
                mitre_id="T1078",
                name="Valid Accounts",
                platforms="Windows, Linux, macOS",
                description="Adversaries may use valid accounts to gain access.",
            ),
            ["initial-access", "persistence"],
        )
        catalog2 = threat_catalog_repo.create(
            ThreatCatalogCreate(
                mitre_id="T1190",
                name="Exploit Public-Facing Application",
                platforms="Windows, Linux, Containers",
                description="Adversaries may exploit public-facing applications.",
            ),
            ["initial-access"],
        )

        threat_repo = ThreatRepository(conn)
        threat1 = threat_repo.create(
            ThreatCreate(
                threat_catalog_id=catalog1.id,
                title="Valid account abuse",
                scenario="Attacker uses compromised credentials",
                rating="high",
                description="Compromised credentials used for initial access.",
                mitre_reference="T1078",
                observed_mitigations="MFA enabled on all accounts.",
                recommendations="Enforce MFA and monitor login anomalies.",
            )
        )
        threat_repo.link_observation(threat1.id, obs_ids[0])
        threat_repo.link_entity(threat1.id, process.id)

        finding_repo = ValidationFindingRepository(conn)
        finding1 = finding_repo.create(
            diagram.id,
            ValidationFindingCreate(
                entity_id=process.id,
                severity="error",
                message="Missing encryption on data store connection",
                source="stride-analyzer",
                code="STRIDE-001",
            ),
        )
        finding2 = finding_repo.create(
            diagram.id,
            ValidationFindingCreate(
                entity_id=store.id,
                severity="warning",
                message="Data store has no backup policy documented",
                source="stride-analyzer",
                code="STRIDE-002",
            ),
        )
        finding3 = finding_repo.create(
            diagram.id,
            ValidationFindingCreate(
                severity="warning",
                message="Diagram is missing a description of trust boundaries",
                source="completeness-check",
            ),
        )

        return SeedIds(
            diagram_id=diagram.id,
            process_node_id=process.id,
            external_entity_node_id=external.id,
            data_store_node_id=store.id,
            container_id=container.id,
            trust_boundary_id=boundary.id,
            data_flow_id=flow.id,
            data_item_with_parent_id=item_with_parent.id,
            data_item_without_parent_id=item_without_parent.id,
            document_ids=doc_ids,
            term_ids=term_ids,
            observation_ids=obs_ids,
            process_component_ids=[comp1.id, comp2.id],
            threat_catalog_ids=[catalog1.id, catalog2.id],
            threat_ids=[threat1.id],
            finding_ids=[finding1.id, finding2.id, finding3.id],
        )
