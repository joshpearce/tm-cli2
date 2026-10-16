# pattern: Functional Core
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tm_cli.db._validators import validate_kebab_case

TrustLevel = Literal["public", "authenticated", "admin", "system"]
ExternalEntityType = Literal["user", "service", "system", "device"]
StorageType = Literal["database", "cache", "file", "queue", "bucket"]
PrivilegeLevel = Literal["internet", "dmz", "corporate", "restricted"]
Classification = Literal["unclassified", "pii", "secret", "public", "internal"]
SourceEndpoint = Literal[1, 2]
NodeType = Literal["process", "external_entity", "data_store"]
ContainerType = Literal["trust_boundary", "container"]
ComponentType = Literal[
    "controller",
    "service",
    "filter",
    "repository",
    "utility",
    "client",
    "handler",
    "interceptor",
    "configuration",
]


class DiagramCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    author: str | None = None

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str | None) -> str | None:
        return validate_kebab_case(v) if v is not None else v


class DiagramUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    author: str | None = None

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str | None) -> str | None:
        return validate_kebab_case(v) if v is not None else v


class Diagram(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    description: str | None
    author: str | None
    created: datetime
    dfd_editor_diagram_id: str | None = None


class ProcessNodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["process"] = "process"
    name: str
    description: str
    trust_level: TrustLevel
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str) -> str:
        return validate_kebab_case(v)


class ExternalEntityNodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["external_entity"] = "external_entity"
    name: str
    description: str
    entity_type: ExternalEntityType
    out_of_scope: bool = False

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str) -> str:
        return validate_kebab_case(v)


class DataStoreNodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["data_store"] = "data_store"
    name: str
    description: str
    storage_type: StorageType
    contains_pii: bool
    encryption_at_rest: bool

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str) -> str:
        return validate_kebab_case(v)


NodeCreate = Annotated[
    ProcessNodeCreate | ExternalEntityNodeCreate | DataStoreNodeCreate,
    Field(discriminator="type"),
]


class ProcessNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["process"]
    id: int
    name: str
    description: str
    trust_level: TrustLevel
    assumptions: list[str]


class ExternalEntityNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["external_entity"]
    id: int
    name: str
    description: str
    entity_type: ExternalEntityType
    out_of_scope: bool


class DataStoreNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["data_store"]
    id: int
    name: str
    description: str
    storage_type: StorageType
    contains_pii: bool
    encryption_at_rest: bool


Node = Annotated[
    ProcessNode | ExternalEntityNode | DataStoreNode,
    Field(discriminator="type"),
]


class ProcessNodeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    trust_level: TrustLevel | None = None
    assumptions: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str | None) -> str | None:
        return validate_kebab_case(v) if v is not None else v


class ExternalEntityNodeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    entity_type: ExternalEntityType | None = None
    out_of_scope: bool | None = None

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str | None) -> str | None:
        return validate_kebab_case(v) if v is not None else v


class DataStoreNodeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    storage_type: StorageType | None = None
    contains_pii: bool | None = None
    encryption_at_rest: bool | None = None

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str | None) -> str | None:
        return validate_kebab_case(v) if v is not None else v


NodeUpdate = ProcessNodeUpdate | ExternalEntityNodeUpdate | DataStoreNodeUpdate


class TrustBoundaryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["trust_boundary"] = "trust_boundary"
    name: str
    description: str
    privilege_level: PrivilegeLevel

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str) -> str:
        return validate_kebab_case(v)


class ContainerVariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["container"] = "container"
    name: str
    description: str

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str) -> str:
        return validate_kebab_case(v)


ContainerCreate = Annotated[
    TrustBoundaryCreate | ContainerVariantCreate,
    Field(discriminator="type"),
]


class TrustBoundary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["trust_boundary"]
    id: int
    name: str
    description: str
    privilege_level: PrivilegeLevel


class ContainerVariant(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["container"]
    id: int
    name: str
    description: str


Container = Annotated[
    TrustBoundary | ContainerVariant,
    Field(discriminator="type"),
]


class TrustBoundaryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    privilege_level: PrivilegeLevel | None = None

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str | None) -> str | None:
        return validate_kebab_case(v) if v is not None else v


class ContainerVariantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str | None) -> str | None:
        return validate_kebab_case(v) if v is not None else v


ContainerUpdate = TrustBoundaryUpdate | ContainerVariantUpdate


class DataFlowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node1_id: int
    node2_id: int
    name: str
    protocol: str
    authenticated: bool
    encrypted: bool

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str) -> str:
        return validate_kebab_case(v)


class DataFlowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    protocol: str | None = None
    authenticated: bool | None = None
    encrypted: bool | None = None

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str | None) -> str | None:
        return validate_kebab_case(v) if v is not None else v


class DataFlow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node1_id: int
    node2_id: int
    name: str
    protocol: str
    authenticated: bool
    encrypted: bool


class DataItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str
    name: str
    description: str
    classification: Classification = "unclassified"
    parent_node_id: int | None = None

    @field_validator("name", "identifier")
    @classmethod
    def _name_kebab(cls, v: str) -> str:
        return validate_kebab_case(v)


class DataItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str | None = None
    name: str | None = None
    description: str | None = None
    classification: Classification | None = None
    parent_node_id: int | None = None

    @field_validator("name", "identifier")
    @classmethod
    def _name_kebab(cls, v: str | None) -> str | None:
        return validate_kebab_case(v) if v is not None else v


class DataItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    identifier: str
    name: str
    description: str
    classification: Classification
    parent_node_id: int | None


class ProcessComponentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_process_id: int
    name: str
    description: str
    component_type: ComponentType

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str) -> str:
        return validate_kebab_case(v)


class ProcessComponentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    component_type: ComponentType | None = None
    parent_process_id: int | None = None

    @field_validator("name")
    @classmethod
    def _name_kebab(cls, v: str | None) -> str | None:
        return validate_kebab_case(v) if v is not None else v


class ProcessComponent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_process_id: int
    name: str
    description: str
    component_type: ComponentType


FindingSeverity = Literal["error", "warning"]


class ValidationFindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: int | None = None
    severity: FindingSeverity
    message: str
    source: str
    code: str | None = None


class ValidationFindingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: FindingSeverity | None = None
    message: str | None = None
    source: str | None = None
    code: str | None = None


class ValidationFinding(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    diagram_id: int
    entity_id: int | None
    severity: FindingSeverity
    message: str
    source: str
    code: str | None
    created: datetime
