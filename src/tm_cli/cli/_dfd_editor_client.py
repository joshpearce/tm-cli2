"""Stdlib HTTP client for the dfd_editor /api/agent/diagrams endpoints.

POST creates a diagram (server mints the UUID; we return it for local
persistence). PUT updates an existing diagram in place by UUID.

Redirects are NOT followed: a misconfigured server should fail loudly.
"""

# pattern: Imperative Shell

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

# ---------------------------------------------------------------------------
# Module-level redirect-suppressing opener (shared; OpenerDirector is
# thread-safe enough for a single-threaded CLI).
# ---------------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        # Returning None disables redirect following; urllib raises HTTPError instead.
        return None


_opener = urllib.request.build_opener(_NoRedirect())


# ---------------------------------------------------------------------------
# Public exception type
# ---------------------------------------------------------------------------


class DfdEditorError(Exception):
    """Raised when a request to dfd_editor fails (network, status, or shape)."""

    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message

    def __str__(self) -> str:
        if self.status is None:
            return self.message
        return f"HTTP {self.status}: {self.message}"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, limit: int = 1000) -> str:
    """Return ``text`` clipped to ``limit`` chars + a literal ``…(truncated)`` marker.

    The result length is therefore up to ``limit + len("…(truncated)")``; the
    budget bounds the *body* portion, not the final string. ``limit`` is a kwarg
    for forward-compat (e.g. tighter budgets for stderr-only contexts); current
    callers all use the default.
    """
    if len(text) > limit:
        return text[:limit] + "…(truncated)"
    return text


def _encode_body(body: dict) -> bytes:
    """Serialize ``body`` to compact UTF-8 JSON bytes."""
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def _do_request(
    url: str,
    method: str,
    body: dict,
    *,
    timeout: float,
) -> tuple[int, bytes]:
    """Execute an HTTP request and return ``(status, raw_bytes)``.

    Raises ``DfdEditorError`` on non-2xx status or connection errors.
    """
    data = _encode_body(body)
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )

    try:
        with _opener.open(req, timeout=timeout) as response:
            status: int = response.getcode()
            raw: bytes = response.read()
    except urllib.error.HTTPError as exc:
        body_bytes = exc.read()
        try:
            detail = body_bytes.decode("utf-8", errors="replace")
        except Exception:
            detail = repr(body_bytes)
        raise DfdEditorError(exc.code, _truncate(detail)) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise DfdEditorError(None, str(exc)) from exc

    # Defense-in-depth: HTTPError should have caught non-2xx already, but
    # guard in case the opener behaves unexpectedly.
    if not (200 <= status < 300):
        text = _truncate(raw.decode("utf-8", errors="replace"))
        raise DfdEditorError(status, text)

    return status, raw


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def post_diagram(server: str, body: dict, *, timeout: float = 30.0) -> str:
    """POST a new diagram to ``<server>/api/agent/diagrams``.

    On 2xx success, parse the JSON response and return the value of the
    ``id`` field as a string. The id MUST be a valid UUID.

    Raises ``DfdEditorError`` on:
      - non-2xx status (carries status + truncated body)
      - URLError / socket error / TimeoutError (status=None)
      - missing or non-UUID ``id`` in the response body
    """
    url = server.rstrip("/") + "/api/agent/diagrams"
    status, raw = _do_request(url, "POST", body, timeout=timeout)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DfdEditorError(status, f"invalid JSON in response: {exc}") from None

    if not isinstance(parsed, dict) or "id" not in parsed:
        raise DfdEditorError(
            status,
            f"response missing 'id' field: {_truncate(json.dumps(parsed))}",
        )

    raw_id = parsed["id"]
    if not isinstance(raw_id, str):
        raise DfdEditorError(
            status,
            f"'id' must be a string, got {type(raw_id).__name__}",
        )

    try:
        uuid.UUID(raw_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise DfdEditorError(
            status,
            f"'id' is not a valid UUID: {raw_id!r}",
        ) from exc

    return raw_id


def put_diagram(
    server: str,
    remote_id: str,
    body: dict,
    *,
    timeout: float = 30.0,
) -> None:
    """PUT a diagram update to ``<server>/api/agent/diagrams/<remote_id>``.

    On 2xx success, returns ``None`` (response body is unused on update).
    Raises ``DfdEditorError`` on non-2xx or connection errors.
    """
    # Defense-in-depth: percent-encode the path segment in case a caller passes
    # a remote_id that wasn't validated through ``post_diagram``'s UUID check.
    encoded_id = urllib.parse.quote(remote_id, safe="")
    url = server.rstrip("/") + "/api/agent/diagrams/" + encoded_id
    _do_request(url, "PUT", body, timeout=timeout)
