"""CLI-level tests for the `tm diagram push` command.

HTTP client functions are patched at the import site
(``tm_cli.cli.diagrams.post_diagram`` / ``put_diagram``).
WSGI integration is covered by the Step 5 acceptance test.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.cli._dfd_editor_client import DfdEditorError
from tm_cli.db import (
    ContainerRepository,
    ContainerVariantCreate,
    DiagramCreate,
    DiagramRepository,
    NodeRepository,
    ProcessNodeCreate,
    connect,
)
from tm_cli.main import cli

# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------

_DEFAULT_REMOTE_ID = "11111111-2222-3333-4444-555555555555"

_POST_SITE = "tm_cli.cli.diagrams.post_diagram"
_PUT_SITE = "tm_cli.cli.diagrams.put_diagram"


def _capture_post(captured: list, return_id: str = _DEFAULT_REMOTE_ID):
    def fake_post(server, body, *, timeout=30.0):
        captured.append({"server": server, "body": body, "timeout": timeout})
        return return_id

    return fake_post


def _capture_put(captured: list):
    def fake_put(server, remote_id, body, *, timeout=30.0):
        captured.append(
            {
                "server": server,
                "remote_id": remote_id,
                "body": body,
                "timeout": timeout,
            }
        )

    return fake_put


def _assert_not_called(name: str):
    def _bomb(*args, **kwargs):
        raise AssertionError(f"{name} should not have been called")

    return _bomb


def _raise_dfd_error(status, message):
    """Return a zero-arg callable that raises DfdEditorError when called."""

    def _raiser(*args, **kwargs):
        raise DfdEditorError(status, message)

    return _raiser


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_push_creates_remote_when_no_remote_id(db_path, monkeypatch) -> None:
    """POST path: first push mints a remote id and persists it."""
    remote_uuid = "66666666-7777-8888-9999-aaaaaaaaaaaa"
    captured: list = []

    monkeypatch.setenv("DFD_EDITOR_URL", "http://srv:9999")
    monkeypatch.setattr(_POST_SITE, _capture_post(captured, return_id=remote_uuid))
    monkeypatch.setattr(_PUT_SITE, _assert_not_called("put_diagram"))

    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "push"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)

    assert payload["operation"] == "created"
    assert payload["remote_id"] == remote_uuid
    assert isinstance(payload["diagram_id"], str)
    assert payload["server"] == "http://srv:9999"

    # Verify the POST body shape.
    assert len(captured) == 1
    body = captured[0]["body"]
    expected_keys = {"meta", "nodes", "containers", "data_flows", "data_items"}
    assert set(body.keys()) == expected_keys

    # Verify the remote id was persisted in the DB.
    with connect(db_path) as conn:
        diagram = DiagramRepository(conn).get(int(payload["diagram_id"]))
    assert diagram is not None
    assert diagram.dfd_editor_diagram_id == remote_uuid


def test_push_updates_when_remote_id_present(db_path, monkeypatch) -> None:
    """PUT path: subsequent push updates via the stored remote id."""
    existing_remote = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with connect(db_path) as conn:
        diagram = DiagramRepository(conn).create(DiagramCreate(name="my-diagram"))
        DiagramRepository(conn).set_remote_id(diagram.id, existing_remote)

    captured_put: list = []
    monkeypatch.setenv("DFD_EDITOR_URL", "http://srv:9999")
    monkeypatch.setattr(_POST_SITE, _assert_not_called("post_diagram"))
    monkeypatch.setattr(_PUT_SITE, _capture_put(captured_put))

    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "push", "--diagram-id", str(diagram.id)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)

    assert payload["operation"] == "updated"
    assert payload["remote_id"] == existing_remote

    assert len(captured_put) == 1
    call = captured_put[0]
    assert call["server"] == "http://srv:9999"
    assert call["remote_id"] == existing_remote
    assert isinstance(call["body"], dict)


def test_push_server_flag_overrides_env(db_path, monkeypatch) -> None:
    """--server flag takes precedence over DFD_EDITOR_URL env var."""
    captured: list = []

    monkeypatch.setenv("DFD_EDITOR_URL", "http://envserver")
    monkeypatch.setattr(_POST_SITE, _capture_post(captured))
    monkeypatch.setattr(_PUT_SITE, _assert_not_called("put_diagram"))

    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "push", "--server", "http://flagserver"])

    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    assert captured[0]["server"] == "http://flagserver"


def test_push_missing_server_exits_1(db_path, monkeypatch) -> None:
    """Exit 1 with user_error when neither --server nor DFD_EDITOR_URL is set."""
    monkeypatch.delenv("DFD_EDITOR_URL", raising=False)

    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "push"])

    assert result.exit_code == 1
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "user_error"
    hint = error.get("hint", "") + error.get("message", "")
    assert "DFD_EDITOR_URL" in hint or "--server" in hint


def test_push_http_error_exits_4(db_path, monkeypatch) -> None:
    """Exit 4 with system_error when the HTTP call raises DfdEditorError(503)."""
    monkeypatch.setenv("DFD_EDITOR_URL", "http://srv")
    monkeypatch.setattr(_POST_SITE, _raise_dfd_error(503, "service unavailable"))
    monkeypatch.setattr(_PUT_SITE, _assert_not_called("put_diagram"))

    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "push"])

    assert result.exit_code == 4
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "system_error"
    assert error["status"] == 503
    assert error["server"] == "http://srv"
    message = error["message"]
    assert "503" in message or "service unavailable" in message


def test_push_connection_error_exits_4(db_path, monkeypatch) -> None:
    """Exit 4 with system_error and null status on connection failure."""
    monkeypatch.setenv("DFD_EDITOR_URL", "http://srv")
    monkeypatch.setattr(_POST_SITE, _raise_dfd_error(None, "Connection refused"))
    monkeypatch.setattr(_PUT_SITE, _assert_not_called("put_diagram"))

    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "push"])

    assert result.exit_code == 4
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "system_error"
    assert error["status"] is None
    assert error["server"] == "http://srv"


def test_push_uses_default_diagram_when_diagram_id_omitted(
    db_path, monkeypatch
) -> None:
    """Omitting --diagram-id auto-creates a diagram named 'default'."""
    captured: list = []
    monkeypatch.setenv("DFD_EDITOR_URL", "http://srv")
    monkeypatch.setattr(_POST_SITE, _capture_post(captured))
    monkeypatch.setattr(_PUT_SITE, _assert_not_called("put_diagram"))

    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "push"])
    assert result.exit_code == 0, result.output

    with connect(db_path) as conn:
        diagrams = DiagramRepository(conn).list()

    assert len(diagrams) == 1
    assert diagrams[0].name == "default"


def test_push_with_explicit_diagram_id_uses_that_diagram(db_path, monkeypatch) -> None:
    """--diagram-id selects the specified diagram, not the default."""
    captured: list = []
    monkeypatch.setenv("DFD_EDITOR_URL", "http://srv")
    monkeypatch.setattr(_POST_SITE, _capture_post(captured))
    monkeypatch.setattr(_PUT_SITE, _assert_not_called("put_diagram"))

    with connect(db_path) as conn:
        non_default = DiagramRepository(conn).create(DiagramCreate(name="non-default"))
        DiagramRepository(conn).create(DiagramCreate(name="default"))

    runner = CliRunner()
    result = runner.invoke(
        cli, ["diagram", "push", "--diagram-id", str(non_default.id)]
    )
    assert result.exit_code == 0, result.output

    assert len(captured) == 1
    assert captured[0]["body"]["meta"]["name"] == "non-default"


def test_push_idempotent_element_uuids_across_create_and_update(
    db_path, monkeypatch
) -> None:
    """Element UUIDs are identical between the POST (create) and PUT (update) bodies."""
    monkeypatch.setenv("DFD_EDITOR_URL", "http://srv")

    with connect(db_path) as conn:
        diagram = DiagramRepository(conn).create(DiagramCreate(name="my-diagram"))
        NodeRepository(conn).create(
            diagram.id,
            ProcessNodeCreate(
                type="process",
                name="web-server",
                description="handles web traffic",
                trust_level="authenticated",
            ),
        )

    # --- First push: POST ---
    captured_post: list = []
    monkeypatch.setattr(_POST_SITE, _capture_post(captured_post))
    monkeypatch.setattr(_PUT_SITE, _assert_not_called("put_diagram"))

    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "push", "--diagram-id", str(diagram.id)])
    assert result.exit_code == 0, result.output

    guid_after_post = captured_post[0]["body"]["nodes"][0]["guid"]

    # --- Second push: PUT ---
    captured_put: list = []
    monkeypatch.setattr(_POST_SITE, _assert_not_called("post_diagram"))
    monkeypatch.setattr(_PUT_SITE, _capture_put(captured_put))

    result2 = runner.invoke(cli, ["diagram", "push", "--diagram-id", str(diagram.id)])
    assert result2.exit_code == 0, result2.output

    guid_after_put = captured_put[0]["body"]["nodes"][0]["guid"]

    assert guid_after_post == guid_after_put


def test_push_command_in_help(db_with_seed) -> None:
    """Smoke test: 'push' appears in `tm diagram --help` output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "--help"])
    assert result.exit_code == 0
    assert "push" in result.output


def test_push_body_populates_container_children(db_path, monkeypatch) -> None:
    """Regression-pin that container_parents wiring flows through the CLI seam.

    Without this, a future bug in `_load_container_parents` (wrong column,
    wrong join, swapped child/parent) would slip past every Step-4 test until
    the Step-5 acceptance test runs.
    """
    monkeypatch.setenv("DFD_EDITOR_URL", "http://srv")

    # Seed: one container with one process node placed inside it.
    with connect() as conn:
        diagram = DiagramRepository(conn).create(DiagramCreate(name="default"))
        diagram_id = diagram.id
        node = NodeRepository(conn).create(
            diagram_id,
            ProcessNodeCreate(
                name="worker", description="d", trust_level="public", assumptions=[]
            ),
        )
        container = ContainerRepository(conn).create(
            diagram_id,
            ContainerVariantCreate(name="parent", description="d"),
        )
        ContainerRepository(conn).set_parent(node.id, container.id)

    captured: list = []
    monkeypatch.setattr(_POST_SITE, _capture_post(captured))

    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "push"])
    assert result.exit_code == 0, result.stderr

    body = captured[0]["body"]
    # Find the parent container in the emitted body and assert its children list.
    parent = next(c for c in body["containers"] if c["properties"]["name"] == "parent")
    # Compute the expected child guid via the same deterministic helper.
    from tm_cli.db.dfd_export import guid_for

    expected_child_guid = guid_for(diagram_id, "nodes", node.id)
    assert parent["children"] == [expected_child_guid]


def test_push_includes_validation_findings(db_path, monkeypatch) -> None:
    """Push body carries a 'validation' array; entity-level findings have 'guid'.

    Seeds one entity-level error (attached to a process node) and one
    diagram-level warning (entity_id=None). Verifies:
    - 'validation' key appears in the captured request body.
    - Entity-level entry has 'guid' matching the node's deterministic guid.
    - Diagram-level entry has no 'guid'.
    - CLI output includes 'error_count' (1) and 'warning_count' (1).
    """
    from tm_cli.db import (
        DiagramCreate,
        DiagramRepository,
        NodeRepository,
        ProcessNodeCreate,
        ValidationFindingCreate,
        ValidationFindingRepository,
        connect,
    )
    from tm_cli.db.dfd_export import guid_for

    # --- seed ---
    with connect(db_path) as conn:
        diagram = DiagramRepository(conn).create(DiagramCreate(name="default"))
        diagram_id = diagram.id
        node = NodeRepository(conn).create(
            diagram_id,
            ProcessNodeCreate(
                name="web-server",
                description="handles web traffic",
                trust_level="authenticated",
            ),
        )
        finding_repo = ValidationFindingRepository(conn)
        # Entity-level error attached to the process node.
        finding_repo.create(
            diagram_id,
            ValidationFindingCreate(
                entity_id=node.id,
                severity="error",
                message="trust_level must not be public",
                source="linter",
                code="E001",
            ),
        )
        # Diagram-level warning (no entity).
        finding_repo.create(
            diagram_id,
            ValidationFindingCreate(
                entity_id=None,
                severity="warning",
                message="diagram has no author",
                source="linter",
            ),
        )

    captured: list = []
    monkeypatch.setenv("DFD_EDITOR_URL", "http://srv")
    monkeypatch.setattr(_POST_SITE, _capture_post(captured))
    monkeypatch.setattr(_PUT_SITE, _assert_not_called("put_diagram"))

    runner = CliRunner()
    result = runner.invoke(cli, ["diagram", "push", "--diagram-id", str(diagram_id)])
    assert result.exit_code == 0, result.output

    # --- body assertions ---
    body = captured[0]["body"]
    assert "validation" in body

    validation = body["validation"]
    assert len(validation) == 2

    # Entity-level entry must carry 'guid'.
    entity_entries = [e for e in validation if "guid" in e]
    assert len(entity_entries) == 1
    expected_guid = guid_for(diagram_id, "nodes", node.id)
    assert entity_entries[0]["guid"] == expected_guid
    assert entity_entries[0]["severity"] == "error"
    assert entity_entries[0]["code"] == "E001"

    # Diagram-level entry must NOT have 'guid'.
    diagram_entries = [e for e in validation if "guid" not in e]
    assert len(diagram_entries) == 1
    assert diagram_entries[0]["severity"] == "warning"

    # --- CLI output assertions ---
    payload = json.loads(result.stdout)
    assert payload["error_count"] == 1
    assert payload["warning_count"] == 1
