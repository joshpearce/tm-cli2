"""Unit tests for the kebab-case validator."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tm_cli.db._validators import validate_kebab_case
from tm_cli.db.dfd_models import (
    ContainerVariantCreate,
    DataFlowCreate,
    DataFlowUpdate,
    DataItemCreate,
    DataItemUpdate,
    DataStoreNodeCreate,
    DiagramCreate,
    DiagramUpdate,
    ExternalEntityNodeCreate,
    ProcessComponentCreate,
    ProcessComponentUpdate,
    ProcessNodeCreate,
    ProcessNodeUpdate,
    TrustBoundaryCreate,
)

# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


class TestValidateKebabCase:
    @pytest.mark.parametrize(
        "value",
        [
            "a",
            "foo",
            "foo-bar",
            "v2-thing",
            "my-threat-model",
            "x1",
            "abc-123-def",
        ],
    )
    def test_valid(self, value: str) -> None:
        assert validate_kebab_case(value) == value

    @pytest.mark.parametrize(
        "value",
        [
            "Foo",
            "FOO",
            "foo_bar",
            "foo--bar",
            "-foo",
            "foo-",
            "foo bar",
            "123-foo",
            "",
            "a" * 129,
        ],
    )
    def test_invalid(self, value: str) -> None:
        with pytest.raises(ValueError):
            validate_kebab_case(value)

    def test_max_length_boundary(self) -> None:
        assert validate_kebab_case("a" * 128) == "a" * 128
        with pytest.raises(ValueError, match="too long"):
            validate_kebab_case("a" * 129)


# ---------------------------------------------------------------------------
# Pydantic model integration tests
# ---------------------------------------------------------------------------


class TestCreateModelsRejectBadNames:
    """Every Create model with a required ``name`` must reject non-kebab values."""

    def test_process_node(self) -> None:
        with pytest.raises(ValidationError):
            ProcessNodeCreate(name="Bad_Name", description="d", trust_level="public")

    def test_external_entity_node(self) -> None:
        with pytest.raises(ValidationError):
            ExternalEntityNodeCreate(
                name="Bad Name", description="d", entity_type="user"
            )

    def test_data_store_node(self) -> None:
        with pytest.raises(ValidationError):
            DataStoreNodeCreate(
                name="BadName",
                description="d",
                storage_type="database",
                contains_pii=False,
                encryption_at_rest=False,
            )

    def test_trust_boundary(self) -> None:
        with pytest.raises(ValidationError):
            TrustBoundaryCreate(name="BAD", description="d", privilege_level="internet")

    def test_container_variant(self) -> None:
        with pytest.raises(ValidationError):
            ContainerVariantCreate(name="has space", description="d")

    def test_data_flow(self) -> None:
        with pytest.raises(ValidationError):
            DataFlowCreate(
                node1_id=1,
                node2_id=2,
                name="Under_Score",
                protocol="HTTPS",
                authenticated=True,
                encrypted=True,
            )

    def test_data_item_name(self) -> None:
        with pytest.raises(ValidationError):
            DataItemCreate(identifier="ok", name="Not Kebab", description="d")

    def test_data_item_identifier(self) -> None:
        with pytest.raises(ValidationError):
            DataItemCreate(identifier="Not Kebab", name="ok", description="d")

    def test_process_component(self) -> None:
        with pytest.raises(ValidationError):
            ProcessComponentCreate(
                parent_process_id=1,
                name="camelCase",
                description="d",
                component_type="controller",
            )


class TestCreateModelsAcceptGoodNames:
    def test_process_node(self) -> None:
        m = ProcessNodeCreate(name="good-name", description="d", trust_level="public")
        assert m.name == "good-name"

    def test_data_item(self) -> None:
        m = DataItemCreate(identifier="my-id", name="my-name", description="d")
        assert m.identifier == "my-id"
        assert m.name == "my-name"


class TestUpdateModelsAllowNone:
    """Update models have optional name; None must pass without validation."""

    def test_process_node_update_none(self) -> None:
        m = ProcessNodeUpdate()
        assert m.name is None

    def test_process_node_update_rejects_bad(self) -> None:
        with pytest.raises(ValidationError):
            ProcessNodeUpdate(name="Bad_Name")

    def test_data_flow_update_none(self) -> None:
        m = DataFlowUpdate()
        assert m.name is None

    def test_data_item_update_none(self) -> None:
        m = DataItemUpdate()
        assert m.name is None
        assert m.identifier is None

    def test_data_item_update_rejects_bad_identifier(self) -> None:
        with pytest.raises(ValidationError):
            DataItemUpdate(identifier="Bad Id")

    def test_process_component_update_none(self) -> None:
        m = ProcessComponentUpdate()
        assert m.name is None


class TestDiagramNameOptional:
    """Diagram name is optional even on create."""

    def test_none_allowed(self) -> None:
        m = DiagramCreate(name=None)
        assert m.name is None

    def test_omitted_allowed(self) -> None:
        m = DiagramCreate()
        assert m.name is None

    def test_good_name(self) -> None:
        m = DiagramCreate(name="my-diagram")
        assert m.name == "my-diagram"

    def test_bad_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DiagramCreate(name="Bad Name")

    def test_update_none(self) -> None:
        m = DiagramUpdate()
        assert m.name is None

    def test_update_bad_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DiagramUpdate(name="Bad_Name")
