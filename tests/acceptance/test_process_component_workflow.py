"""Acceptance test: process-component workflow end-to-end through the CLI."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def _ok(result):
    """Helper: assert exit code 0 and parse JSON stdout."""
    assert result.exit_code == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def _ndjson(result):
    """Helper: assert exit code 0 and parse NDJSON stdout."""
    assert result.exit_code == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def test_full_process_component_workflow(db_path) -> None:
    """Build process components from scratch through the CLI.

    Steps:
      1. Create a diagram.
      2. Create a process node.
      3. Create two process components (controller + service) with different types.
      4. List components, verify both appear, filter by --component-type and
         --parent-process-id.
      5. Get a component by id, verify fields.
      6. Update a component's name and type.
      7. Search by text, verify matches.
      8. Create a document, link it to a component, list documents for the
         component.
      9. Create an observation, link it to a component, list observations for the
         component.
      10. Create a second process node, use set-parent to move a component.
      11. Verify entity get resolves the component with kind=process_component.
      12. Delete a component, verify it's gone.
      13. Delete the parent process node, verify cascade deletes remaining
          components.
    """
    runner = CliRunner()

    # 1. Diagram
    result = runner.invoke(
        cli, ["diagram", "create", "--name=app", "--description=application"]
    )
    diagram = _ok(result)
    diagram_id = diagram["id"]

    # 2. Process node
    process_a = _ok(
        runner.invoke(
            cli,
            [
                "node",
                "create",
                "process",
                "--diagram-id",
                diagram_id,
                "--name=api-server",
                "--description=main API process",
                "--trust-level=authenticated",
            ],
        )
    )
    process_a_id = process_a["id"]

    # 3. Create two process components
    controller = _ok(
        runner.invoke(
            cli,
            [
                "process-component",
                "create",
                "--diagram-id",
                diagram_id,
                "--name=user-controller",
                "--description=handles user requests",
                "--component-type=controller",
                "--parent-process-id",
                process_a_id,
            ],
        )
    )
    controller_id = controller["id"]
    assert controller["name"] == "user-controller"
    assert controller["component_type"] == "controller"
    assert controller["parent_process_id"] == process_a_id

    service = _ok(
        runner.invoke(
            cli,
            [
                "process-component",
                "create",
                "--diagram-id",
                diagram_id,
                "--name=auth-service",
                "--description=authentication service",
                "--component-type=service",
                "--parent-process-id",
                process_a_id,
            ],
        )
    )
    service_id = service["id"]
    assert service["name"] == "auth-service"
    assert service["component_type"] == "service"

    # 4. List components, verify both appear
    all_components = _ndjson(
        runner.invoke(cli, ["process-component", "list", "--diagram-id", diagram_id])
    )
    assert len(all_components) == 2
    assert any(c["id"] == controller_id for c in all_components)
    assert any(c["id"] == service_id for c in all_components)

    # Filter by component-type
    controllers = _ndjson(
        runner.invoke(
            cli,
            [
                "process-component",
                "list",
                "--diagram-id",
                diagram_id,
                "--component-type=controller",
            ],
        )
    )
    assert len(controllers) == 1
    assert controllers[0]["id"] == controller_id

    # Filter by parent-process-id
    process_components = _ndjson(
        runner.invoke(
            cli,
            [
                "process-component",
                "list",
                "--diagram-id",
                diagram_id,
                "--parent-process-id",
                process_a_id,
            ],
        )
    )
    assert len(process_components) == 2

    # 5. Get a component by id, verify fields
    fetched_controller = _ok(
        runner.invoke(cli, ["process-component", "get", controller_id])
    )
    assert fetched_controller["id"] == controller_id
    assert fetched_controller["name"] == "user-controller"
    assert fetched_controller["description"] == "handles user requests"
    assert fetched_controller["component_type"] == "controller"
    assert fetched_controller["parent_process_id"] == process_a_id

    # 6. Update a component's name and type
    updated = _ok(
        runner.invoke(
            cli,
            [
                "process-component",
                "update",
                controller_id,
                "--name=user-request-controller",
                "--component-type=handler",
            ],
        )
    )
    assert updated["name"] == "user-request-controller"
    assert updated["component_type"] == "handler"
    assert updated["id"] == controller_id

    # 7. Search by text, verify matches
    search_results = _ndjson(
        runner.invoke(
            cli,
            ["process-component", "search", "auth", "--diagram-id", diagram_id],
        )
    )
    assert len(search_results) == 1
    assert search_results[0]["id"] == service_id

    search_controller = _ndjson(
        runner.invoke(
            cli,
            ["process-component", "search", "Controller", "--diagram-id", diagram_id],
        )
    )
    assert any(c["id"] == controller_id for c in search_controller)

    # 8. Create a document, link it to a component, list documents
    doc = _ok(
        runner.invoke(
            cli,
            [
                "document",
                "create",
                "--title=Component Design",
                "--author=architect",
                "--content=Design notes for components",
            ],
        )
    )
    doc_id = doc["id"]

    link_result = _ok(
        runner.invoke(
            cli, ["process-component", "link-document", controller_id, doc_id]
        )
    )
    assert link_result["linked"] is True
    assert link_result["component_id"] == controller_id
    assert link_result["document_id"] == doc_id

    docs_for_component = _ndjson(
        runner.invoke(cli, ["process-component", "list-documents", controller_id])
    )
    assert any(d["id"] == doc_id for d in docs_for_component)

    # 9. Create an observation, link it to a component, list observations
    obs = _ok(
        runner.invoke(
            cli,
            [
                "observation",
                "create",
                "--observation-type=potential_threat",
                "--status=open",
                "--content=Input validation needed in controller",
            ],
        )
    )
    obs_id = obs["id"]

    obs_link_result = _ok(
        runner.invoke(
            cli, ["process-component", "link-observation", controller_id, obs_id]
        )
    )
    assert obs_link_result["linked"] is True
    assert obs_link_result["component_id"] == controller_id
    assert obs_link_result["observation_id"] == obs_id

    obs_for_component = _ndjson(
        runner.invoke(cli, ["process-component", "list-observations", controller_id])
    )
    assert any(o["id"] == obs_id for o in obs_for_component)

    # 10. Create a second process node, use set-parent to move a component
    process_b = _ok(
        runner.invoke(
            cli,
            [
                "node",
                "create",
                "process",
                "--diagram-id",
                diagram_id,
                "--name=background-worker",
                "--description=async worker process",
                "--trust-level=authenticated",
            ],
        )
    )
    process_b_id = process_b["id"]

    moved = _ok(
        runner.invoke(
            cli, ["process-component", "set-parent", service_id, process_b_id]
        )
    )
    assert moved["id"] == service_id
    assert moved["parent_process_id"] == process_b_id

    # 11. Verify entity get resolves the component with kind=process_component
    entity_result = _ok(runner.invoke(cli, ["entity", "get", controller_id]))
    assert entity_result["kind"] == "process_component"
    assert entity_result["id"] == controller_id
    assert entity_result["name"] == "user-request-controller"

    # 12. Delete a component, verify it's gone
    delete_result = _ok(
        runner.invoke(cli, ["process-component", "delete", controller_id, "--yes"])
    )
    assert delete_result["deleted"] is True
    assert delete_result["id"] == controller_id

    # Verify it no longer appears in list
    after_delete = _ndjson(
        runner.invoke(cli, ["process-component", "list", "--diagram-id", diagram_id])
    )
    assert not any(c["id"] == controller_id for c in after_delete)
    assert len(after_delete) == 1  # Only service remains

    # 13. Delete the parent process node, verify cascade deletes remaining components
    # First delete process_a (which has no components now)
    _ok(runner.invoke(cli, ["node", "delete", process_a_id, "--yes"]))

    # Now delete process_b, which has the service component
    _ok(runner.invoke(cli, ["node", "delete", process_b_id, "--yes"]))

    # Verify all components are gone
    final_components = _ndjson(
        runner.invoke(cli, ["process-component", "list", "--diagram-id", diagram_id])
    )
    assert len(final_components) == 0
