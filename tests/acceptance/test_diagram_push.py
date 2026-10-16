"""Acceptance test: tm diagram push against a real in-process WSGI server.

No mocks of urlopen or _dfd_editor_client — the CLI talks to an actual HTTP
server running in a daemon thread on a kernel-assigned ephemeral port.
"""

from __future__ import annotations

import json
import threading
import uuid
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest
from click.testing import CliRunner

from tm_cli.db import (
    ContainerRepository,
    DataFlowCreate,
    DataFlowRepository,
    DataItemCreate,
    DataItemRepository,
    DataStoreNodeCreate,
    DiagramCreate,
    DiagramRepository,
    NodeRepository,
    ProcessNodeCreate,
    TrustBoundaryCreate,
    connect,
)
from tm_cli.main import cli


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


def _seed_diagram(db_path) -> int:
    """Seed one process node, one data store, one flow, one data item, and one
    container (trust boundary with the process node as a child) into a fresh
    diagram named ``push-test``.

    Returns the diagram int id.
    """
    with connect(db_path) as conn:
        diagram = DiagramRepository(conn).create(
            DiagramCreate(
                name="push-test",
                description="acceptance test diagram",
                author="tester",
            )
        )
        did = diagram.id

        node_repo = NodeRepository(conn)
        proc = node_repo.create(
            did,
            ProcessNodeCreate(
                type="process",
                name="api-server",
                description="Main API",
                trust_level="authenticated",
            ),
        )
        store = node_repo.create(
            did,
            DataStoreNodeCreate(
                type="data_store",
                name="main-db",
                description="Primary database",
                storage_type="database",
                contains_pii=True,
                encryption_at_rest=True,
            ),
        )

        DataFlowRepository(conn).create(
            did,
            DataFlowCreate(
                node1_id=proc.id,
                node2_id=store.id,
                name="writes",
                protocol="HTTPS",
                authenticated=True,
                encrypted=True,
            ),
        )

        DataItemRepository(conn).create(
            did,
            DataItemCreate(
                identifier="user-record",
                name="user-record",
                description="PII data",
                classification="pii",
                parent_node_id=proc.id,
            ),
        )

        boundary = ContainerRepository(conn).create(
            did,
            TrustBoundaryCreate(
                type="trust_boundary",
                name="corp-network",
                description="Corporate network boundary",
                privilege_level="corporate",
            ),
        )

        # Place the process node inside the trust boundary.
        ContainerRepository(conn).set_parent(proc.id, boundary.id)

    return did


def test_push_create_then_update_preserves_element_uuids(
    db_path, stub_server, monkeypatch
) -> None:
    """Full create-then-update cycle through a real in-process HTTP server.

    1. Seed a small diagram.
    2. First push: CLI POSTs, server mints a UUID, CLI persists it locally.
    3. Verify the local row reflects the server UUID.
    4. Second push: CLI PUTs to the same path, element UUIDs are byte-identical.
    """
    port = stub_server["server"].server_port
    captured = stub_server["captured"]
    server_uuid = stub_server["server_uuid"]

    monkeypatch.setenv("DFD_EDITOR_URL", f"http://127.0.0.1:{port}")

    diagram_id = _seed_diagram(db_path)
    runner = CliRunner()

    # --- First push: expect POST ---
    result1 = runner.invoke(cli, ["diagram", "push", "--diagram-id", str(diagram_id)])
    assert result1.exit_code == 0, (
        f"first push failed:\n{result1.output}\n{result1.stderr}"
    )

    assert len(captured) == 1
    req1 = captured[0]
    assert req1["method"] == "POST"
    assert req1["path"] == "/api/agent/diagrams"

    body1 = req1["body"]
    assert isinstance(body1, dict)
    # Top-level shape matches dfd_editor Diagram doc.
    for key in ("meta", "nodes", "containers", "data_flows", "data_items"):
        assert key in body1, f"missing key {key!r} in first push body"

    # Check emit output.
    out1 = json.loads(result1.output)
    assert out1["operation"] == "created"
    assert out1["remote_id"] == server_uuid

    # --- Verify local persistence ---
    with connect(db_path) as conn:
        diagram = DiagramRepository(conn).get(diagram_id)
    assert diagram is not None
    assert diagram.dfd_editor_diagram_id == server_uuid

    # --- Second push: expect PUT ---
    result2 = runner.invoke(cli, ["diagram", "push", "--diagram-id", str(diagram_id)])
    assert result2.exit_code == 0, (
        f"second push failed:\n{result2.output}\n{result2.stderr}"
    )

    assert len(captured) == 2
    req2 = captured[1]
    assert req2["method"] == "PUT"
    assert req2["path"] == f"/api/agent/diagrams/{server_uuid}"

    body_post = body1
    body_put = req2["body"]
    assert isinstance(body_put, dict)

    # Element UUIDs must be byte-identical across all four collections.
    for collection in ("nodes", "containers", "data_flows", "data_items"):
        guids_first = [el["guid"] for el in body_post[collection]]
        guids_second = [el["guid"] for el in body_put[collection]]
        assert guids_first == guids_second, f"{collection} guids drifted between pushes"
        assert guids_first, f"{collection} should be non-empty in seed"

    # The trust boundary should contain exactly the process node's guid in its children.
    process_guid = next(
        n["guid"] for n in body_post["nodes"] if n["properties"]["name"] == "api-server"
    )
    boundary = next(
        c for c in body_post["containers"] if c["properties"]["name"] == "corp-network"
    )
    assert boundary["children"] == [process_guid]

    # The seeded data item's parent field must equal the process node's guid.
    data_item = body_post["data_items"][0]
    assert data_item["parent"] == process_guid

    # Check emit output.
    out2 = json.loads(result2.output)
    assert out2["operation"] == "updated"
    assert out2["remote_id"] == server_uuid
