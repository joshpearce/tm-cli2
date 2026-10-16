from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ObservationType = Literal[
    "potential_threat",
    "incomplete_information",
    "question",
    "todo",
]

ObservationStatus = Literal["open", "closed"]


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_updated: datetime
    title: str
    author: str
    content: str


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_updated: datetime | None = None
    title: str | None = None
    author: str | None = None
    content: str | None = None


class Document(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_updated: datetime
    last_imported: datetime
    title: str
    author: str
    content: str


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_updated: datetime
    last_imported: datetime
    title: str
    author: str


class TermCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    definition: str


class TermUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str | None = None
    definition: str | None = None


class Term(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    term: str
    definition: str
    last_updated: datetime


class ObservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    observation_type: ObservationType
    status: ObservationStatus = "open"


class ObservationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    observation_type: ObservationType | None = None
    status: ObservationStatus | None = None


class Observation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    observation_type: ObservationType
    status: ObservationStatus
    last_updated: datetime
    node_ids: list[int] = Field(default_factory=list)
    container_ids: list[int] = Field(default_factory=list)
    flow_ids: list[int] = Field(default_factory=list)
    data_item_ids: list[int] = Field(default_factory=list)
    process_component_ids: list[int] = Field(default_factory=list)


ThreatRating = Literal["low", "medium", "high"]


class Tactic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ThreatCatalogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mitre_id: str
    name: str
    platforms: str
    description: str


class ThreatCatalogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mitre_id: str
    name: str
    platforms: str
    description: str
    tactics: list[str] = Field(default_factory=list)


class ThreatCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threat_catalog_id: int | None = None
    title: str
    scenario: str
    rating: ThreatRating
    description: str
    mitre_reference: str
    observed_mitigations: str
    recommendations: str


class ThreatUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threat_catalog_id: int | None = None
    title: str | None = None
    scenario: str | None = None
    rating: ThreatRating | None = None
    description: str | None = None
    mitre_reference: str | None = None
    observed_mitigations: str | None = None
    recommendations: str | None = None


class Threat(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    threat_catalog_id: int | None = None
    title: str
    scenario: str
    rating: ThreatRating
    description: str
    mitre_reference: str
    observed_mitigations: str
    recommendations: str
    last_updated: datetime
    observation_ids: list[int] = Field(default_factory=list)
    entity_ids: list[int] = Field(default_factory=list)
