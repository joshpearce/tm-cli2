"""Tests for tm schema and tm commands introspection."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_schema_no_arg_lists_entity_names(db_path) -> None:
    """AC10.2: tm schema with no argument lists available entity names."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "entities" in payload
    entities = payload["entities"]
    assert len(entities) == 8
    assert "document" in entities
    assert "term" in entities
    assert "observation" in entities
    assert "diagram" in entities
    assert "node" in entities
    assert "container" in entities
    assert "flow" in entities
    assert "data-item" in entities


def test_schema_document_returns_triple_plus_summary(db_path) -> None:
    """AC10.1: tm schema document returns read/create/update/summary schemas."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "document"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "read" in payload
    assert "create" in payload
    assert "update" in payload
    assert "summary" in payload
    # Each should be a JSON Schema dict with properties or $ref
    for key in ["read", "create", "update", "summary"]:
        schema = payload[key]
        assert isinstance(schema, dict)
        assert "properties" in schema or "$ref" in schema or "oneOf" in schema


def test_schema_node_returns_discriminated_union(db_path) -> None:
    """AC10.1: tm schema node with oneOf and discriminator."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "node"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    # The read schema should be a discriminated union
    read_schema = payload["read"]
    assert "oneOf" in read_schema
    assert "discriminator" in read_schema
    assert read_schema["discriminator"]["propertyName"] == "type"
    # Create schema should also have oneOf
    create_schema = payload["create"]
    assert "oneOf" in create_schema


def test_schema_all_returns_dict_keyed_by_entity(db_path) -> None:
    """AC10.3: tm schema --all returns all entities keyed by name."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "--all"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    # All 8 entity names should be keys
    assert "document" in payload
    assert "term" in payload
    assert "observation" in payload
    assert "diagram" in payload
    assert "node" in payload
    assert "container" in payload
    assert "flow" in payload
    assert "data-item" in payload
    # Each entity should have read/create/update schemas at minimum
    for entity_name, entity_schemas in payload.items():
        assert isinstance(entity_schemas, dict)
        assert "read" in entity_schemas


def test_schema_unknown_entity_exits_1(db_path) -> None:
    """AC5.1: tm schema with unknown entity exits 1 with user_error."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "bogus"])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("code") == "user_error"


def test_commands_json_root_has_expected_subgroups(db_path) -> None:
    """AC10.4: tm commands lists all entity groups and introspection commands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.stdout)
    assert tree["name"] == "tm"
    subcommands = {cmd["name"] for cmd in tree["subcommands"]}
    # Should have all 8 entity groups + schema + commands
    assert "document" in subcommands
    assert "term" in subcommands
    assert "observation" in subcommands
    assert "diagram" in subcommands
    assert "node" in subcommands
    assert "container" in subcommands
    assert "flow" in subcommands
    assert "data-item" in subcommands
    assert "schema" in subcommands
    assert "commands" in subcommands


def test_commands_json_every_leaf_has_options_and_arguments_keys(db_path) -> None:
    """AC10.4: every node in commands tree has options and arguments keys."""

    def _walk(node):
        yield node
        for sub in node.get("subcommands", []):
            yield from _walk(sub)

    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.stdout)

    for node in _walk(tree):
        assert "options" in node, f"{node['name']} missing 'options'"
        assert "arguments" in node, f"{node['name']} missing 'arguments'"
        assert isinstance(node["options"], list)
        assert isinstance(node["arguments"], list)


def test_commands_json_includes_hidden_diagram_id_for_dfd_create(db_path) -> None:
    """AC9.5: every DFD create command includes hidden diagram_id option.

    DFD create commands are those under:
    - tm node create <variant> (process, external-entity, data-store)
    - tm container create <variant> (trust-boundary, container)
    - tm flow create (no variants)
    - tm data-item create (no variants)

    Each must have a diagram_id option with hidden=True.
    """

    def _walk_all_leaves(node, path):
        """Walk tree and yield all leaves with their paths."""
        if not node.get("subcommands"):
            yield (path + [node["name"]], node)
            return
        for sub in node.get("subcommands", []):
            yield from _walk_all_leaves(sub, path + [node["name"]])

    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.stdout)

    # Collect all leaf commands that are DFD creates or DFD create variants
    dfd_create_entities = {"node", "container", "flow", "data-item"}
    diagram_id_commands = []

    for path, node in _walk_all_leaves(tree, []):
        # Find all leaves under DFD create commands
        # Pattern: [tm, entity, create] or [tm, entity, create, variant]
        if len(path) >= 3:
            entity = path[1]
            create_cmd = path[2]

            # Is this directly a DFD create command?
            if entity in dfd_create_entities and create_cmd == "create":
                diagram_ids = [
                    opt
                    for opt in node.get("options", [])
                    if opt["name"] == "diagram_id"
                ]
                if diagram_ids:
                    diagram_id_commands.append((path, diagram_ids[0]))

            # Or is this a variant under a DFD create command?
            is_variant = (
                len(path) >= 4
                and entity in dfd_create_entities
                and create_cmd == "create"
            )
            if is_variant:
                diagram_ids = [
                    opt
                    for opt in node.get("options", [])
                    if opt["name"] == "diagram_id"
                ]
                if diagram_ids:
                    diagram_id_commands.append((path, diagram_ids[0]))

    # Verify we found at least 7 DFD create commands
    found_count = len(diagram_id_commands)
    found_paths = [" ".join(p) for p, _ in diagram_id_commands]
    assert found_count >= 7, (
        f"Expected at least 7 DFD create commands with diagram_id, "
        f"found {found_count}: {found_paths}"
    )

    # Verify all diagram_id options are hidden
    for path, diagram_id_opt in diagram_id_commands:
        path_str = " ".join(path)
        assert diagram_id_opt.get("hidden") is True, (
            f"diagram_id option not hidden in {path_str}"
        )


def test_commands_json_for_flow_update_omits_endpoint_options(db_path) -> None:
    """AC11.3: flow update command does not expose node1_id / node2_id options."""

    def _find_command(node, path):
        """Navigate tree by path."""
        if not path:
            return node
        for sub in node.get("subcommands", []):
            if sub["name"] == path[0]:
                return _find_command(sub, path[1:])
        return None

    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.stdout)

    flow_update = _find_command(tree, ["flow", "update"])
    assert flow_update is not None
    option_names = {opt["name"] for opt in flow_update.get("options", [])}
    assert "node1_id" not in option_names
    assert "node2_id" not in option_names


def test_commands_json_golden_snapshot(db_path, snapshot) -> None:
    """AC10.5: tm commands --json output is pinned by golden snapshot."""
    runner = CliRunner()
    result = runner.invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.stdout)
    assert tree == snapshot
