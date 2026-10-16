"""Unit tests for _dfd_editor_client HTTP wrapper."""

from __future__ import annotations

import io
import urllib.error

import pytest

from tm_cli.cli import _dfd_editor_client as client
from tm_cli.cli._dfd_editor_client import DfdEditorError

_VALID_UUID = "11111111-2222-3333-4444-555555555555"
_POST_RESPONSE = f'{{"id": "{_VALID_UUID}", "diagram": {{}}}}'.encode()
_PUT_RESPONSE = b'{"diagram": {}}'


class _FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self._status = status
        self._buf = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._buf.getvalue()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_open(response_or_exc, *, captured: list):
    """Return a fake `_opener.open` that records the call and responds."""

    def fake_open(req, timeout=30.0):
        captured.append({"req": req, "timeout": timeout})
        if isinstance(response_or_exc, BaseException):
            raise response_or_exc
        if isinstance(response_or_exc, type) and issubclass(
            response_or_exc, BaseException
        ):
            raise response_or_exc()
        return response_or_exc

    return fake_open


def _patch(monkeypatch, response_or_exc, captured: list):
    """Patch _opener.open and register calls into captured."""
    monkeypatch.setattr(
        client._opener,
        "open",
        _make_fake_open(response_or_exc, captured=captured),
    )


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


def test_post_diagram_returns_uuid_on_201(monkeypatch):
    captured: list = []
    _patch(monkeypatch, _FakeResponse(201, _POST_RESPONSE), captured)

    result = client.post_diagram("http://localhost:5050", {"meta": None})

    assert result == _VALID_UUID
    req = captured[0]["req"]
    assert req.full_url == "http://localhost:5050/api/agent/diagrams"
    assert req.get_method() == "POST"
    assert req.data == b'{"meta":null}'
    assert req.get_header("Content-type") == "application/json"


def test_post_diagram_strips_trailing_slash_on_server(monkeypatch):
    captured: list = []
    _patch(monkeypatch, _FakeResponse(201, _POST_RESPONSE), captured)

    result = client.post_diagram("http://localhost:5050/", {"meta": None})

    assert result == _VALID_UUID
    req = captured[0]["req"]
    assert "//" not in req.full_url.replace("http://", "").replace("https://", "")
    assert req.full_url == "http://localhost:5050/api/agent/diagrams"


def test_put_diagram_returns_none_on_200(monkeypatch):
    captured: list = []
    _patch(monkeypatch, _FakeResponse(200, _PUT_RESPONSE), captured)

    result = client.put_diagram("http://x", "abc-uuid", {"foo": "bar"})

    assert result is None
    req = captured[0]["req"]
    assert req.full_url == "http://x/api/agent/diagrams/abc-uuid"
    assert req.get_method() == "PUT"


def test_put_diagram_percent_encodes_remote_id(monkeypatch):
    """Defense-in-depth: a remote_id containing URL metacharacters must not break out
    of the path segment. The wrapper percent-encodes ``/`` (and any other unsafe char)
    rather than concatenating raw."""
    captured: list = []
    _patch(monkeypatch, _FakeResponse(200, _PUT_RESPONSE), captured)

    client.put_diagram("http://x", "weird/id with space", {})

    req = captured[0]["req"]
    assert req.full_url == "http://x/api/agent/diagrams/weird%2Fid%20with%20space"


# ---------------------------------------------------------------------------
# HTTP error paths
# ---------------------------------------------------------------------------


def test_post_non_2xx_raises_with_status_and_truncated_body(monkeypatch):
    body = b"validation failed: " + b"x" * 2000
    exc = urllib.error.HTTPError(
        url="http://x/api/agent/diagrams",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=io.BytesIO(body),
    )
    _patch(monkeypatch, exc, [])

    with pytest.raises(DfdEditorError) as info:
        client.post_diagram("http://x", {"k": "v"})

    e = info.value
    assert e.status == 400
    assert "validation failed:" in e.message
    assert len(e.message) <= 1000 + len("…(truncated)")


def test_put_non_2xx_raises_with_status(monkeypatch):
    exc = urllib.error.HTTPError(
        url="http://x/api/agent/diagrams/missing",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=io.BytesIO(b"not found"),
    )
    _patch(monkeypatch, exc, [])

    with pytest.raises(DfdEditorError) as info:
        client.put_diagram("http://x", "missing", {})

    assert info.value.status == 404


# ---------------------------------------------------------------------------
# Network / OS error paths
# ---------------------------------------------------------------------------


def test_connection_error_raises_with_status_none(monkeypatch):
    _patch(monkeypatch, urllib.error.URLError("Connection refused"), [])

    with pytest.raises(DfdEditorError) as info:
        client.post_diagram("http://x", {})

    e = info.value
    assert e.status is None
    assert "Connection refused" in e.message


def test_socket_timeout_raises_with_status_none(monkeypatch):
    _patch(monkeypatch, TimeoutError("timed out"), [])

    with pytest.raises(DfdEditorError) as info:
        client.post_diagram("http://x", {})

    e = info.value
    assert e.status is None
    assert "timed out" in e.message


def test_oserror_raises_with_status_none(monkeypatch):
    _patch(monkeypatch, OSError("dns failure"), [])

    with pytest.raises(DfdEditorError) as info:
        client.post_diagram("http://x", {})

    e = info.value
    assert e.status is None
    assert "dns failure" in e.message


# ---------------------------------------------------------------------------
# Response parsing error paths
# ---------------------------------------------------------------------------


def test_post_invalid_json_raises_dfd_editor_error(monkeypatch):
    _patch(monkeypatch, _FakeResponse(201, b"not json"), [])

    with pytest.raises(DfdEditorError) as info:
        client.post_diagram("http://x", {})

    e = info.value
    assert e.status == 201
    assert "invalid JSON" in e.message


def test_post_missing_id_field_raises_dfd_editor_error(monkeypatch):
    _patch(monkeypatch, _FakeResponse(201, b'{"oops": "no id here"}'), [])

    with pytest.raises(DfdEditorError) as info:
        client.post_diagram("http://x", {})

    e = info.value
    assert e.status == 201
    assert "id" in e.message


def test_post_non_uuid_id_raises_dfd_editor_error(monkeypatch):
    _patch(monkeypatch, _FakeResponse(201, b'{"id": "not-a-uuid"}'), [])

    with pytest.raises(DfdEditorError) as info:
        client.post_diagram("http://x", {})

    assert "not a valid UUID" in info.value.message


def test_post_non_string_id_raises_dfd_editor_error(monkeypatch):
    _patch(monkeypatch, _FakeResponse(201, b'{"id": 42}'), [])

    with pytest.raises(DfdEditorError) as info:
        client.post_diagram("http://x", {})

    assert "int" in info.value.message


# ---------------------------------------------------------------------------
# Redirect handling
# ---------------------------------------------------------------------------


def test_redirect_raises_as_dfd_editor_error(monkeypatch):
    exc = urllib.error.HTTPError(
        url="http://x/api/agent/diagrams",
        code=302,
        msg="Found",
        hdrs={"Location": "http://elsewhere"},
        fp=io.BytesIO(b""),
    )
    _patch(monkeypatch, exc, [])

    with pytest.raises(DfdEditorError) as info:
        client.post_diagram("http://x", {})

    assert info.value.status == 302


def test_opener_uses_no_redirect_handler():
    assert any(isinstance(h, client._NoRedirect) for h in client._opener.handlers)


# ---------------------------------------------------------------------------
# Timeout forwarding
# ---------------------------------------------------------------------------


def test_default_timeout_passed_through(monkeypatch):
    captured: list = []
    _patch(monkeypatch, _FakeResponse(201, _POST_RESPONSE), captured)

    client.post_diagram("http://x", {})
    assert captured[0]["timeout"] == 30.0

    captured.clear()
    _patch(monkeypatch, _FakeResponse(201, _POST_RESPONSE), captured)
    client.post_diagram("http://x", {}, timeout=5.0)
    assert captured[0]["timeout"] == 5.0


# ---------------------------------------------------------------------------
# Body serialization
# ---------------------------------------------------------------------------


def test_body_serialization_compact(monkeypatch):
    captured: list = []
    _patch(monkeypatch, _FakeResponse(201, _POST_RESPONSE), captured)

    client.post_diagram("http://x", {"a": 1, "b": [1, 2, 3]})

    assert captured[0]["req"].data == b'{"a":1,"b":[1,2,3]}'


def test_post_url_construction_no_trailing_slash(monkeypatch):
    captured: list = []
    _patch(monkeypatch, _FakeResponse(201, _POST_RESPONSE), captured)

    client.post_diagram("http://localhost:5050", {})

    url = captured[0]["req"].full_url
    assert url.endswith("/api/agent/diagrams")
    assert "//" not in url.replace("http://", "")
