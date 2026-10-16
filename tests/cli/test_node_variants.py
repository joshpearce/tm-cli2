"""Tests for polymorphic node create/update + type-mismatch validation."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_create_process_returns_process_node(db_with_seed) -> None:
    """AC1.3, AC8.1: create process returns a process node."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "create",
            "process",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "worker",
            "--description",
            "background process",
            "--trust-level",
            "admin",
            "--assumption",
            "always-up",
            "--assumption",
            "ipv4-only",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "process"
    assert payload["name"] == "worker"
    assert payload["trust_level"] == "admin"
    assert payload["assumptions"] == ["always-up", "ipv4-only"]


def test_create_external_entity_returns_external_entity_node(db_with_seed) -> None:
    """AC1.3, AC8.1: create external-entity returns an external entity node."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "create",
            "external-entity",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "external-user",
            "--description",
            "external user",
            "--entity-type",
            "user",
            "--out-of-scope",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "external_entity"
    assert payload["name"] == "external-user"
    assert payload["entity_type"] == "user"
    assert payload["out_of_scope"] is True


def test_create_data_store_returns_data_store_node(db_with_seed) -> None:
    """AC1.3, AC8.1: create data-store returns a data store node."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "create",
            "data-store",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "data-store",
            "--description",
            "data store",
            "--storage-type",
            "database",
            "--contains-pii",
            "--no-encryption-at-rest",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "data_store"
    assert payload["name"] == "data-store"
    assert payload["storage_type"] == "database"
    assert payload["contains_pii"] is True
    assert payload["encryption_at_rest"] is False


def test_create_with_invalid_trust_level_exits_1(db_with_seed) -> None:
    """AC1.7: invalid trust_level choice exits 1 with user_error."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "create",
            "process",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "p",
            "--description",
            "d",
            "--trust-level",
            "bogus",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"


def test_create_data_store_missing_required_bool_exits_1(db_with_seed) -> None:
    """AC5.1: missing required boolean flag exits 1."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "create",
            "data-store",
            "--diagram-id",
            str(seed_ids.diagram_id),
            "--name",
            "ds",
            "--description",
            "d",
            "--storage-type",
            "cache",
            "--contains-pii",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"


def test_update_process_returns_updated_process_node(db_with_seed) -> None:
    """AC1.4, AC8.2: update process updates and returns the node."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "update",
            "process",
            str(seed_ids.process_node_id),
            "--trust-level",
            "system",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "process"
    assert payload["trust_level"] == "system"
    assert payload["id"] == str(seed_ids.process_node_id)


def test_update_external_entity_returns_updated_node(db_with_seed) -> None:
    """AC1.4, AC8.2: update external-entity updates and returns the node."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "update",
            "external-entity",
            str(seed_ids.external_entity_node_id),
            "--out-of-scope",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "external_entity"
    assert payload["out_of_scope"] is True
    assert payload["id"] == str(seed_ids.external_entity_node_id)


def test_update_data_store_returns_updated_node(db_with_seed) -> None:
    """AC1.4, AC8.2: update data-store updates and returns the node."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "update",
            "data-store",
            str(seed_ids.data_store_node_id),
            "--no-contains-pii",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["type"] == "data_store"
    assert payload["contains_pii"] is False
    assert payload["id"] == str(seed_ids.data_store_node_id)


def test_update_process_against_data_store_exits_1_with_hint(
    db_with_seed,
) -> None:
    """AC8.3: updating process against a data store exits 1 with friendly hint."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "update",
            "process",
            str(seed_ids.data_store_node_id),
            "--trust-level",
            "system",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
    hint = payload["error"].get("hint", "")
    assert "tm node update data-store" in hint
    assert str(seed_ids.data_store_node_id) in hint


def test_update_missing_id_exits_2(db_with_seed) -> None:
    """AC1.6: update with nonexistent id exits 2 (NotFoundError)."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "node",
            "update",
            "process",
            "99999",
            "--trust-level",
            "admin",
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "not_found"


def test_update_no_fields_exits_1(db_with_seed) -> None:
    """Edge case: update with no fields provided exits 1."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["node", "update", "process", str(seed_ids.process_node_id)],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "user_error"
