"""Acceptance test: validation finding lifecycle driven via CliRunner.

No mocks — exercises the full DB+CLI stack including:
- create (single + batch)
- list with filters
- search by text
- clear by source
- push with validation array in the server payload
"""

from __future__ import annotations

import json
import threading
import uuid
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest
from click.testing import CliRunner

from tm_cli.main import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(result):
    """Assert exit_code 0 and return parsed JSON stdout."""
    assert result.exit_code == 0, (
        f"exit={result.exit_code}\n{result.output}\n{result.stderr}"
    )
    return json.loads(result.stdout)


def _ndjson(result):
    """Assert exit_code 0; return parsed NDJSON lines (skips empty/pagination)."""
    assert result.exit_code == 0, (
        f"exit={result.exit_code}\n{result.output}\n{result.stderr}"
    )
    return [
        json.loads(line)
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith('{"_pagination"')
    ]


# ---------------------------------------------------------------------------
# Stub WSGI server (mirrors test_diagram_push.py)
# ---------------------------------------------------------------------------


class _SilentHandler(WSGIRequestHandler):
    """Suppress per-request stderr noise during tests."""

    def log_message(self, format, *args):  # noqa: A002 – matches base signature
        return


def _make_app(captured: list[dict], *, server_uuid: str):
    def app(environ, start_response):
        method = environ.get("REQUEST_METHOD", "")
        path = environ.get("PATH_INFO", "")
        length = int(environ.get("CONTENT_LENGTH") or "0")
        body_bytes = environ["wsgi.input"].read(length) if length > 0 else b""
        try:
            body = json.loads(body_bytes) if body_bytes else None
        except json.JSONDecodeError:
            body = None
        captured.append({"method": method, "path": path, "body": body})

        if method == "POST" and path == "/api/agent/diagrams":
            payload = json.dumps({"id": server_uuid}).encode()
            start_response("201 Created", [("Content-Type", "application/json")])
            return [payload]
        if method == "PUT" and path.startswith("/api/agent/diagrams/"):
            remote_id = path.rsplit("/", 1)[-1]
            payload = json.dumps({"id": remote_id}).encode()
            start_response("200 OK", [("Content-Type", "application/json")])
            return [payload]
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"not found"]

    return app


@pytest.fixture
def stub_server():
    """Spin up an ephemeral WSGI stub and yield state shared with the test."""
    captured: list[dict] = []
    server_uuid = str(uuid.uuid4())
    app = _make_app(captured, server_uuid=server_uuid)
    server = make_server("127.0.0.1", 0, app, handler_class=_SilentHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"server": server, "captured": captured, "server_uuid": server_uuid}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Test 1: full lifecycle without HTTP
# ---------------------------------------------------------------------------


def test_finding_lifecycle(db_path) -> None:
    """Full create → list → filter → search → update → get → delete → clear lifecycle.

    Steps:
      1. Create a diagram and a node via CLI.
      2. Create an entity-level error (with code) and a diagram-level warning.
      3. List all findings — assert count=2.
      4. List with --severity error — assert only 1 error returned.
      5. Search by message text — assert correct match.
      6. Update the error finding's severity to warning.
      7. Get the updated finding — verify severity changed.
      8. Delete the updated finding — assert deleted=true.
      9. Clear remaining findings by source — assert cleared=1.
      10. List — assert empty.
    """
    runner = CliRunner()

    # 1. Diagram + node
    diagram = _ok(runner.invoke(cli, ["diagram", "create", "--name", "lifecycle-test"]))
    diagram_id = diagram["id"]

    node = _ok(
        runner.invoke(
            cli,
            [
                "node",
                "create",
                "process",
                "--diagram-id",
                diagram_id,
                "--name",
                "api-server",
                "--description",
                "The main API",
                "--trust-level",
                "authenticated",
            ],
        )
    )
    node_id = node["id"]

    # 2. Create findings
    finding_error = _ok(
        runner.invoke(
            cli,
            [
                "finding",
                "create",
                "--diagram-id",
                diagram_id,
                "--severity",
                "error",
                "--message",
                "trust_level must not be public on external endpoint",
                "--source",
                "stride-linter",
                "--entity-id",
                node_id,
                "--code",
                "STRIDE-T001",
            ],
        )
    )
    assert finding_error["severity"] == "error"
    assert finding_error["entity_id"] == node_id
    assert finding_error["code"] == "STRIDE-T001"
    finding_error_id = finding_error["id"]

    finding_warn = _ok(
        runner.invoke(
            cli,
            [
                "finding",
                "create",
                "--diagram-id",
                diagram_id,
                "--severity",
                "warning",
                "--message",
                "diagram is missing a trust boundary description",
                "--source",
                "completeness-check",
            ],
        )
    )
    assert finding_warn["severity"] == "warning"
    assert finding_warn["entity_id"] is None
    assert finding_warn["code"] is None

    # 3. List all — expect 2
    all_findings = _ndjson(
        runner.invoke(cli, ["finding", "list", "--diagram-id", diagram_id])
    )
    assert len(all_findings) == 2

    # 4. List with --severity error — expect only the error
    errors_only = _ndjson(
        runner.invoke(
            cli,
            ["finding", "list", "--diagram-id", diagram_id, "--severity", "error"],
        )
    )
    assert len(errors_only) == 1
    assert errors_only[0]["id"] == finding_error_id
    assert errors_only[0]["severity"] == "error"

    # 5. Search by message text — should match "trust_level" finding, not the other
    search_result = _ndjson(
        runner.invoke(
            cli,
            ["finding", "search", "trust_level", "--diagram-id", diagram_id],
        )
    )
    assert len(search_result) == 1
    assert "trust_level" in search_result[0]["message"]

    # 6. Update severity from error to warning
    updated = _ok(
        runner.invoke(
            cli,
            ["finding", "update", finding_error_id, "--severity", "warning"],
        )
    )
    assert updated["severity"] == "warning"
    assert updated["message"] == "trust_level must not be public on external endpoint"

    # 7. Get the finding — verify update applied
    fetched = _ok(runner.invoke(cli, ["finding", "get", finding_error_id]))
    assert fetched["severity"] == "warning"
    assert fetched["id"] == finding_error_id

    # 8. Delete the updated finding
    delete_result = _ok(
        runner.invoke(cli, ["finding", "delete", finding_error_id, "--yes"])
    )
    assert delete_result["deleted"] is True

    # 9. Clear remaining by source ("completeness-check")
    clear_result = _ok(
        runner.invoke(
            cli,
            [
                "finding",
                "clear",
                "--diagram-id",
                diagram_id,
                "--source",
                "completeness-check",
            ],
        )
    )
    assert clear_result["cleared"] == 1

    # 10. List — empty
    remaining = _ndjson(
        runner.invoke(cli, ["finding", "list", "--diagram-id", diagram_id])
    )
    assert remaining == []


# ---------------------------------------------------------------------------
# Test 2: push delivers validation array
# ---------------------------------------------------------------------------


def test_push_with_findings_delivers_validation_array(
    db_path, stub_server, monkeypatch
) -> None:
    """End-to-end: push sends findings in 'validation' array with correct shape.

    Steps:
      1. Create a diagram, a process node, a data store node, and a flow via CLI.
      2. Create one entity-level error targeting the process node.
      3. Create one diagram-level warning (no entity_id).
      4. Push via `tm diagram push`.
      5. Captured POST body has "validation" array with 2 entries.
      6. Entity-level entry has "guid" matching the node's deterministic guid.
      7. Diagram-level entry has no "guid" key.
      8. CLI output has error_count=1, warning_count=1.
    """
    from tm_cli.db.dfd_export import guid_for

    port = stub_server["server"].server_port
    captured = stub_server["captured"]

    monkeypatch.setenv("DFD_EDITOR_URL", f"http://127.0.0.1:{port}")

    runner = CliRunner()

    # 1. Diagram
    diagram = _ok(
        runner.invoke(cli, ["diagram", "create", "--name", "push-findings-test"])
    )
    diagram_id = diagram["id"]

    # Process node
    proc = _ok(
        runner.invoke(
            cli,
            [
                "node",
                "create",
                "process",
                "--diagram-id",
                diagram_id,
                "--name",
                "web-server",
                "--description",
                "handles HTTP",
                "--trust-level",
                "public",
            ],
        )
    )
    proc_id = proc["id"]

    # Data store node
    store = _ok(
        runner.invoke(
            cli,
            [
                "node",
                "create",
                "data-store",
                "--diagram-id",
                diagram_id,
                "--name",
                "main-db",
                "--description",
                "primary store",
                "--storage-type",
                "database",
                "--contains-pii",
                "--encryption-at-rest",
            ],
        )
    )
    store_id = store["id"]

    # Flow between them
    _ok(
        runner.invoke(
            cli,
            [
                "flow",
                "create",
                "--diagram-id",
                diagram_id,
                "--node1-id",
                proc_id,
                "--node2-id",
                store_id,
                "--name",
                "reads",
                "--protocol",
                "HTTPS",
                "--authenticated",
                "--encrypted",
            ],
        )
    )

    # 2. Entity-level error on the process node
    _ok(
        runner.invoke(
            cli,
            [
                "finding",
                "create",
                "--diagram-id",
                diagram_id,
                "--severity",
                "error",
                "--message",
                "web-server must not be public trust level",
                "--source",
                "stride-analyzer",
                "--entity-id",
                proc_id,
                "--code",
                "STRIDE-T001",
            ],
        )
    )

    # 3. Diagram-level warning
    _ok(
        runner.invoke(
            cli,
            [
                "finding",
                "create",
                "--diagram-id",
                diagram_id,
                "--severity",
                "warning",
                "--message",
                "diagram has no trust boundary defined",
                "--source",
                "completeness-check",
            ],
        )
    )

    # 4. Push
    push_result = _ok(
        runner.invoke(cli, ["diagram", "push", "--diagram-id", diagram_id])
    )

    # 5. Exactly one request captured (POST)
    assert len(captured) == 1
    body = captured[0]["body"]
    assert captured[0]["method"] == "POST"
    assert "validation" in body

    validation = body["validation"]
    assert len(validation) == 2

    # 6. Entity-level entry has "guid" matching the process node's guid
    entity_entries = [e for e in validation if "guid" in e]
    assert len(entity_entries) == 1
    expected_guid = guid_for(int(diagram_id), "nodes", int(proc_id))
    assert entity_entries[0]["guid"] == expected_guid
    assert entity_entries[0]["severity"] == "error"
    assert entity_entries[0]["code"] == "STRIDE-T001"

    # 7. Diagram-level entry has no "guid"
    diagram_entries = [e for e in validation if "guid" not in e]
    assert len(diagram_entries) == 1
    assert diagram_entries[0]["severity"] == "warning"
    assert "guid" not in diagram_entries[0]

    # 8. CLI output has correct counts
    assert push_result["error_count"] == 1
    assert push_result["warning_count"] == 1
