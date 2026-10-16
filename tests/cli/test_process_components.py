"""Golden snapshots for tm process-component JSON output on all verbs."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_seeded_components(db_with_seed, snapshot) -> None:
    """AC1.1: list returns NDJSON with seeded process components."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    runner = CliRunner()
    result = runner.invoke(
        cli, ["process-component", "list", "--diagram-id", str(diagram_id)]
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines == snapshot


def test_list_filtered_by_component_type(db_with_seed, snapshot) -> None:
    """AC2.5: list with --component-type filter returns only matching components."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "process-component",
            "list",
            "--diagram-id",
            str(diagram_id),
            "--component-type",
            "controller",
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Only the seeded component with component_type="controller" should match
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines[0]["component_type"] == "controller"
    assert parsed_lines == snapshot


def test_list_filtered_by_parent_process_id(db_with_seed, snapshot) -> None:
    """AC2.5: list with --parent-process-id filter returns only matching components."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    process_id = seed_ids.process_node_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "process-component",
            "list",
            "--diagram-id",
            str(diagram_id),
            "--parent-process-id",
            str(process_id),
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Both seeded components have the same parent_process_id
    assert len(lines) == 2
    parsed_lines = [json.loads(line) for line in lines]
    for comp in parsed_lines:
        assert comp["parent_process_id"] == str(process_id)
    assert parsed_lines == snapshot


def test_list_filtered_by_component_type_and_parent_process(
    db_with_seed, snapshot
) -> None:
    """AC2.5: combining filters AND-combines constraints."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    process_id = seed_ids.process_node_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "process-component",
            "list",
            "--diagram-id",
            str(diagram_id),
            "--component-type",
            "service",
            "--parent-process-id",
            str(process_id),
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Only the seeded component with both service type AND parent should match
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert parsed_lines[0]["component_type"] == "service"
    assert parsed_lines[0]["parent_process_id"] == str(process_id)
    assert parsed_lines == snapshot


def test_get_returns_component(db_with_seed, snapshot) -> None:
    """AC1.2: get returns the full process component object."""
    db_path, seed_ids = db_with_seed
    component_id = seed_ids.process_component_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["process-component", "get", str(component_id)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "id" in payload
    assert payload["name"] == "seed-controller"
    assert payload == snapshot


def test_get_not_found(db_with_seed) -> None:
    """AC1.5: get with missing id exits 2."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["process-component", "get", "99999"])
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("code") == "not_found"


def test_create_returns_new_component(db_with_seed, snapshot) -> None:
    """AC1.3: create with explicit flags works."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    parent_process_id = seed_ids.process_node_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "process-component",
            "create",
            "--diagram-id",
            str(diagram_id),
            "--parent-process-id",
            str(parent_process_id),
            "--name",
            "new-component",
            "--description",
            "A new component",
            "--component-type",
            "handler",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["name"] == "new-component"
    assert parsed["description"] == "A new component"
    assert parsed["component_type"] == "handler"
    assert parsed["parent_process_id"] == str(parent_process_id)
    assert parsed["diagram_id"] == str(diagram_id)
    assert isinstance(parsed["id"], str)
    assert parsed == snapshot


def test_create_stdin_batch(db_with_seed, snapshot) -> None:
    """AC1.3: create via --stdin with a JSON array creates multiple components."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    parent_process_id = seed_ids.process_node_id
    runner = CliRunner()

    batch_input = json.dumps(
        [
            {
                "parent_process_id": parent_process_id,
                "name": "batch-component-1",
                "description": "First batch component",
                "component_type": "controller",
            },
            {
                "parent_process_id": parent_process_id,
                "name": "batch-component-2",
                "description": "Second batch component",
                "component_type": "service",
            },
        ]
    )

    result = runner.invoke(
        cli,
        [
            "process-component",
            "create",
            "--diagram-id",
            str(diagram_id),
            "--stdin",
        ],
        input=batch_input,
    )
    assert result.exit_code == 0
    # Batch create returns a JSON array, not NDJSON
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "batch-component-1"
    assert parsed[1]["name"] == "batch-component-2"
    assert parsed == snapshot


def test_create_dry_run(db_with_seed, snapshot) -> None:
    """AC1.3: create with --dry-run validates but doesn't persist."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    parent_process_id = seed_ids.process_node_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "process-component",
            "create",
            "--diagram-id",
            str(diagram_id),
            "--parent-process-id",
            str(parent_process_id),
            "--name",
            "dry-run-component",
            "--description",
            "This should not be persisted",
            "--component-type",
            "service",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["dry_run"] is True
    assert parsed["would_create"]["name"] == "dry-run-component"
    assert parsed == snapshot

    # Verify it wasn't persisted
    list_result = runner.invoke(
        cli, ["process-component", "list", "--diagram-id", str(diagram_id)]
    )
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    parsed_list = [json.loads(line) for line in lines]
    assert not any(comp["name"] == "dry-run-component" for comp in parsed_list)


def test_update_returns_updated(db_with_seed, snapshot) -> None:
    """AC1.4: update returns the full updated process component."""
    db_path, seed_ids = db_with_seed
    component_id = seed_ids.process_component_ids[0]
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "process-component",
            "update",
            str(component_id),
            "--name",
            "updated-controller",
            "--component-type",
            "service",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["name"] == "updated-controller"
    assert parsed["component_type"] == "service"
    assert parsed == snapshot


def test_update_missing_id_exits_2(db_with_seed) -> None:
    """AC1.6: update with missing id exits 2."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli, ["process-component", "update", "99999", "--name", "new"]
    )
    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload.get("error", {}).get("code") == "not_found"


def test_delete(db_with_seed) -> None:
    """AC1.7: delete returns deleted: true."""
    db_path, seed_ids = db_with_seed
    component_id = seed_ids.process_component_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["process-component", "delete", str(component_id)])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["deleted"] is True
    assert parsed["id"] == str(component_id)

    # Verify it's gone
    get_result = runner.invoke(cli, ["process-component", "get", str(component_id)])
    assert get_result.exit_code == 2


def test_search_matches_name(db_with_seed, snapshot) -> None:
    """AC2.6: search matches component name."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["process-component", "search", "controller", "--diagram-id", str(diagram_id)],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    parsed_lines = [json.loads(line) for line in lines]
    # Should match seed-controller
    assert any("controller" in comp["name"].lower() for comp in parsed_lines)
    assert parsed_lines == snapshot


def test_search_with_component_type_filter(db_with_seed, snapshot) -> None:
    """AC2.6: search with --component-type filter."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "process-component",
            "search",
            "seed",
            "--diagram-id",
            str(diagram_id),
            "--component-type",
            "service",
        ],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    parsed_lines = [json.loads(line) for line in lines]
    # Should only match seed-service, not seed-controller
    for comp in parsed_lines:
        assert comp["component_type"] == "service"
    assert parsed_lines == snapshot


def test_set_parent(db_with_seed, snapshot) -> None:
    """AC3.8: set-parent moves component to a different process."""
    db_path, seed_ids = db_with_seed
    diagram_id = seed_ids.diagram_id
    component_id = seed_ids.process_component_ids[0]
    runner = CliRunner()

    # Create a second process node
    from tm_cli.db import NodeRepository, ProcessNodeCreate, connect

    with connect(db_path) as conn:
        nodes = NodeRepository(conn)
        second_process = nodes.create(
            diagram_id,
            ProcessNodeCreate(
                type="process",
                name="second-process",
                description="Second process for set-parent test",
                trust_level="public",
            ),
        )

    # Move the component to the new parent
    result = runner.invoke(
        cli,
        [
            "process-component",
            "set-parent",
            str(component_id),
            str(second_process.id),
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["parent_process_id"] == str(second_process.id)
    assert parsed["id"] == str(component_id)
    assert parsed == snapshot

    # Verify with get
    get_result = runner.invoke(cli, ["process-component", "get", str(component_id)])
    assert get_result.exit_code == 0
    get_payload = json.loads(get_result.stdout)
    assert get_payload["parent_process_id"] == str(second_process.id)


def test_link_document(db_with_seed) -> None:
    """Link a document to a process component."""
    db_path, seed_ids = db_with_seed
    component_id = seed_ids.process_component_ids[0]
    doc_id = seed_ids.document_ids[0]
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["process-component", "link-document", str(component_id), str(doc_id)],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["linked"] is True
    assert parsed["component_id"] == str(component_id)
    assert parsed["document_id"] == str(doc_id)

    # Idempotent: second call says already_linked
    result2 = runner.invoke(
        cli,
        ["process-component", "link-document", str(component_id), str(doc_id)],
    )
    assert result2.exit_code == 0
    parsed2 = json.loads(result2.stdout)
    assert parsed2["linked"] is False
    assert parsed2["reason"] == "already_linked"


def test_unlink_document(db_with_seed) -> None:
    """Unlink a document from a process component."""
    db_path, seed_ids = db_with_seed
    component_id = seed_ids.process_component_ids[0]
    doc_id = seed_ids.document_ids[0]
    runner = CliRunner()

    # Link first
    runner.invoke(
        cli,
        ["process-component", "link-document", str(component_id), str(doc_id)],
    )
    # Unlink
    result = runner.invoke(
        cli,
        ["process-component", "unlink-document", str(component_id), str(doc_id)],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["unlinked"] is True

    # Second unlink says not_linked
    result2 = runner.invoke(
        cli,
        ["process-component", "unlink-document", str(component_id), str(doc_id)],
    )
    parsed2 = json.loads(result2.stdout)
    assert parsed2["unlinked"] is False
    assert parsed2["reason"] == "not_linked"


def test_list_documents(db_with_seed) -> None:
    """List documents linked to a process component."""
    db_path, seed_ids = db_with_seed
    component_id = seed_ids.process_component_ids[0]
    doc_id = seed_ids.document_ids[0]
    runner = CliRunner()

    # Link a document
    runner.invoke(
        cli,
        ["process-component", "link-document", str(component_id), str(doc_id)],
    )
    result = runner.invoke(
        cli,
        ["process-component", "list-documents", str(component_id)],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    parsed = json.loads(lines[0])
    assert parsed["id"] == str(doc_id)


def test_link_observation(db_with_seed) -> None:
    """Link an observation to a process component."""
    db_path, seed_ids = db_with_seed
    component_id = seed_ids.process_component_ids[0]
    obs_id = seed_ids.observation_ids[0]
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["process-component", "link-observation", str(component_id), str(obs_id)],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["linked"] is True

    # Idempotent
    result2 = runner.invoke(
        cli,
        ["process-component", "link-observation", str(component_id), str(obs_id)],
    )
    parsed2 = json.loads(result2.stdout)
    assert parsed2["linked"] is False
    assert parsed2["reason"] == "already_linked"


def test_list_observations(db_with_seed) -> None:
    """List observations linked to a process component."""
    db_path, seed_ids = db_with_seed
    component_id = seed_ids.process_component_ids[0]
    obs_id = seed_ids.observation_ids[0]
    runner = CliRunner()

    # Link first
    runner.invoke(
        cli,
        ["process-component", "link-observation", str(component_id), str(obs_id)],
    )
    result = runner.invoke(
        cli,
        ["process-component", "list-observations", str(component_id)],
    )
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    parsed = json.loads(lines[0])
    assert parsed["id"] == str(obs_id)
