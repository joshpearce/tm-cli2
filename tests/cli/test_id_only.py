"""Tests for the global ``--id-only`` root flag.

Each case is numbered to match the plan (cli-ergonomics.md, Step 2,
lines 131-144).

HTTP client functions are patched at the import site for the push case,
mirroring the pattern used in ``tests/cli/test_diagram_push.py``.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from tm_cli.cli._output import _id_only_value
from tm_cli.db import (
    DiagramCreate,
    DiagramRepository,
    NodeRepository,
    ProcessNodeCreate,
    connect,
)
from tm_cli.main import cli

# ---------------------------------------------------------------------------
# Patch-site constants — mirror test_diagram_push.py exactly.
# ---------------------------------------------------------------------------

_POST_SITE = "tm_cli.cli.diagrams.post_diagram"
_PUT_SITE = "tm_cli.cli.diagrams.put_diagram"

_FIXED_REMOTE_UUID = "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb"


def _capture_post(captured: list, return_id: str = _FIXED_REMOTE_UUID):
    def fake_post(server, body, *, timeout=30.0):
        captured.append({"server": server, "body": body})
        return return_id

    return fake_post


def _assert_not_called(name: str):
    def _bomb(*args, **kwargs):
        raise AssertionError(f"{name} should not have been called")

    return _bomb


# ---------------------------------------------------------------------------
# Case 1: diagram create → stdout is bare id
# ---------------------------------------------------------------------------


def test_id_only_diagram_create(db_path) -> None:
    """--id-only diagram create --name x → stdout is exactly '<id>\\n', exit 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--id-only", "diagram", "create", "--name", "x"])

    assert result.exit_code == 0, result.output
    stdout = result.stdout.strip()
    # Must be a plain integer string — no JSON braces, no extra whitespace.
    assert stdout.isdigit(), f"expected bare int id, got: {stdout!r}"


# ---------------------------------------------------------------------------
# Case 2: diagram list → ids one per line, no _pagination footer
# ---------------------------------------------------------------------------


def test_id_only_diagram_list_no_pagination_footer(db_path) -> None:
    """--id-only diagram list --limit 2 → two ids, no _pagination footer line."""
    runner = CliRunner()

    # Create two diagrams so the list is full (len == limit) — this is when
    # the _pagination footer would normally fire.
    r1 = runner.invoke(cli, ["diagram", "create", "--name", "alpha"])
    r2 = runner.invoke(cli, ["diagram", "create", "--name", "beta"])
    assert r1.exit_code == 0, r1.output
    assert r2.exit_code == 0, r2.output
    id1 = str(json.loads(r1.stdout)["id"])
    id2 = str(json.loads(r2.stdout)["id"])

    result = runner.invoke(cli, ["--id-only", "diagram", "list", "--limit", "2"])

    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    # Exactly two id lines — no _pagination footer.
    assert len(lines) == 2, f"expected 2 id lines, got {lines!r}"
    assert set(lines) == {id1, id2}
    # Confirm the _pagination key is absent from every line.
    for ln in lines:
        assert "_pagination" not in ln, f"pagination footer leaked into: {ln!r}"


# ---------------------------------------------------------------------------
# Case 3: diagram update → stdout is bare id
# ---------------------------------------------------------------------------


def test_id_only_diagram_update(db_path) -> None:
    """--id-only diagram update <id> --name y → stdout is the id, exit 0."""
    runner = CliRunner()

    create_result = runner.invoke(cli, ["diagram", "create", "--name", "before"])
    assert create_result.exit_code == 0, create_result.output
    diagram_id = json.loads(create_result.stdout)["id"]

    result = runner.invoke(
        cli,
        ["--id-only", "diagram", "update", str(diagram_id), "--name", "after"],
    )

    assert result.exit_code == 0, result.output
    stdout = result.stdout.strip()
    assert stdout == str(diagram_id), f"expected {diagram_id!r}, got {stdout!r}"


# ---------------------------------------------------------------------------
# Case 4: diagram delete --yes → stdout is the id from {"deleted": ..., "id": ...}
# ---------------------------------------------------------------------------


def test_id_only_diagram_delete(db_path) -> None:
    """--id-only diagram delete <id> --yes → stdout is the id, exit 0."""
    runner = CliRunner()

    create_result = runner.invoke(cli, ["diagram", "create", "--name", "to-delete"])
    assert create_result.exit_code == 0, create_result.output
    diagram_id = json.loads(create_result.stdout)["id"]

    result = runner.invoke(
        cli,
        ["--id-only", "diagram", "delete", str(diagram_id), "--yes"],
    )

    assert result.exit_code == 0, result.output
    stdout = result.stdout.strip()
    # The delete payload is {"deleted": true, "id": "<id>"}.  --id-only should
    # print the bare id extracted from the "id" key.
    assert stdout == str(diagram_id), f"expected {diagram_id!r}, got {stdout!r}"


# ---------------------------------------------------------------------------
# Case 5: diagram push → stdout is the *local* diagram_id (not the remote UUID)
# ---------------------------------------------------------------------------


def test_id_only_diagram_push_emits_local_diagram_id(db_path, monkeypatch) -> None:
    """--id-only diagram push → stdout is the local integer diagram_id, not the UUID.

    Regression-pins the "first *_id-suffixed key in insertion order" rule:
    the push payload is {"diagram_id": ..., "remote_id": ..., ...} so
    diagram_id wins (it ends in _id and comes before remote_id, which also ends
    in _id but has value = UUID not an integer id).
    """
    # Create a diagram and one process node (push needs content to be useful).
    with connect(db_path) as conn:
        diagram = DiagramRepository(conn).create(DiagramCreate(name="push-me"))
        NodeRepository(conn).create(
            diagram.id,
            ProcessNodeCreate(
                name="worker",
                description="desc",
                trust_level="public",
            ),
        )

    captured: list = []
    monkeypatch.setattr(
        _POST_SITE, _capture_post(captured, return_id=_FIXED_REMOTE_UUID)
    )
    monkeypatch.setattr(_PUT_SITE, _assert_not_called("put_diagram"))

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--id-only",
            "diagram",
            "push",
            "--server",
            "http://stub",
            "--diagram-id",
            str(diagram.id),
        ],
    )

    assert result.exit_code == 0, result.output
    stdout = result.stdout.strip()
    # Must be the local integer diagram id, not the remote UUID.
    assert stdout == str(diagram.id), f"expected {diagram.id!r}, got {stdout!r}"
    assert stdout != _FIXED_REMOTE_UUID, "got remote UUID instead of local id"
    # POST was called exactly once.
    assert len(captured) == 1


# ---------------------------------------------------------------------------
# Case 6: schema document → fallback to JSON (no id-bearing key)
# ---------------------------------------------------------------------------


def test_id_only_schema_document_falls_back_to_json(db_path) -> None:
    """--id-only schema document → JSON fallback because schema has no id field.

    Regression-pins the non-crashing fallback for payloads without any
    id-bearing key.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["--id-only", "schema", "document"])

    assert result.exit_code == 0, result.output
    # Output must be parseable JSON.
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"expected JSON fallback, stdout was: {result.stdout!r}"
        ) from exc
    # The schema document payload should have the standard schema keys.
    assert "properties" in payload or "read" in payload or "create" in payload, (
        f"unexpected schema shape: {list(payload.keys())}"
    )


# ---------------------------------------------------------------------------
# Case 7: --id-only + --json together → bare id wins (--id-only takes precedence)
# ---------------------------------------------------------------------------


def test_id_only_wins_over_json_flag(db_path) -> None:
    """--id-only --json diagram create --name x → bare id, not a JSON object."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--id-only", "--json", "diagram", "create", "--name", "combo"]
    )

    assert result.exit_code == 0, result.output
    stdout = result.stdout.strip()
    # Must NOT start with '{' (which would indicate JSON was emitted).
    assert not stdout.startswith("{"), f"got JSON instead of bare id: {stdout!r}"
    # Must be a plain integer string.
    assert stdout.isdigit(), f"expected bare int id, got: {stdout!r}"


# ---------------------------------------------------------------------------
# Unit tests for _id_only_value (M5 — direct import, no CliRunner needed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload, expected",
    [
        # 1. Bare `id` key wins.
        ({"id": 5}, "5"),
        # 2. Bare `id` wins over *_id-suffixed key when both present.
        ({"id": "5", "diagram_id": "9"}, "5"),
        # 3. First *_id-suffixed key in insertion order wins when no bare `id`.
        ({"a_id": "1", "b_id": "2"}, "1"),
        # 4. No id-bearing key → None.
        ({"foo": "bar"}, None),
        # 5. Non-dict payload → None.
        (["a", "b"], None),
        # 6. Zero id is valid — don't treat 0 as falsy.
        ({"id": 0}, "0"),
    ],
)
def test_id_only_value_unit(payload, expected) -> None:
    """Pin the _id_only_value field-resolution contract directly."""
    assert _id_only_value(payload) == expected
