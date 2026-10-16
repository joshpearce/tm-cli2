"""Golden snapshots for tm document JSON output on all verbs."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_ndjson_when_piped(db_with_seed, snapshot) -> None:
    """AC1.1, AC4.1: list returns NDJSON, one parseable object per line."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "list"])
    assert result.exit_code == 0
    # NDJSON: every non-empty line is a parseable object.
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == len(seed_ids.document_ids)
    parsed_lines = [json.loads(line) for line in lines]
    for obj in parsed_lines:
        json.loads(json.dumps(obj))
    assert parsed_lines == snapshot


def test_list_no_pagination_footer_when_under_limit(db_with_seed) -> None:
    """AC1.8, AC4.5: no pagination footer when result count < limit."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "list", "--limit", "50"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # 2 seeded docs + no footer
    assert len(lines) == 2
    # Last line should not be a pagination footer
    last = json.loads(lines[-1])
    assert "_pagination" not in last


def test_list_emits_pagination_footer_when_full_page(db_with_seed) -> None:
    """AC4.5: pagination footer when len(rows) == limit."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "list", "--limit", "2"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # 2 docs + 1 footer
    assert len(lines) == 3
    last = json.loads(lines[-1])
    assert last == {
        "_pagination": {
            "next_offset": 2,
            "returned": 2,
        }
    }


def test_list_no_json_remains_ndjson(db_with_seed) -> None:
    """AC4.3: --no-json does NOT pretty-print NDJSON output (indent is malformed)."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["--no-json", "document", "list"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Still 2 docs (no footer because we're under the limit)
    assert len(lines) == 2
    # Each line should be parseable JSON and NOT indented
    for line in lines:
        obj = json.loads(line)
        assert isinstance(obj, dict)
    # Verify no indentation by checking no lines start with whitespace
    for line in result.stdout.splitlines():
        if line.strip():
            assert not line.startswith(" ") and not line.startswith("\t")


def test_get_returns_full_object_with_content(db_with_seed, snapshot) -> None:
    """AC1.2, AC4.2: get returns compact JSON including content & last_imported."""
    db_path, seed_ids = db_with_seed
    doc_id = seed_ids.document_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "get", str(doc_id)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "id" in payload
    assert "content" in payload
    assert "last_imported" in payload
    assert payload == snapshot


def test_get_no_json_indents_two_spaces(db_with_seed) -> None:
    """AC4.3: --no-json indents with 2 spaces."""
    db_path, seed_ids = db_with_seed
    doc_id = seed_ids.document_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["--no-json", "document", "get", str(doc_id)])
    assert result.exit_code == 0
    # Should start with { followed by newline and 2 spaces
    assert result.stdout.startswith("{\n  ")


def test_id_fields_are_strings(db_with_seed) -> None:
    """AC4.4: id field is a JSON string."""
    db_path, seed_ids = db_with_seed
    doc_id = seed_ids.document_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "get", str(doc_id)])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert isinstance(parsed["id"], str)


def test_create_with_named_flags_returns_new_row(db_path: Path, snapshot) -> None:
    """AC1.3: create with named flags returns the new row as single JSON object."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "document",
            "create",
            "--title",
            "Test Doc",
            "--author",
            "Test Author",
            "--content",
            "Test content body",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["title"] == "Test Doc"
    assert parsed["author"] == "Test Author"
    assert parsed["content"] == "Test content body"
    assert isinstance(parsed["id"], str)
    assert "last_imported" in parsed
    assert "last_updated" in parsed
    assert parsed == snapshot


def test_create_dry_run_does_not_write(db_path: Path) -> None:
    """AC6.4: --dry-run validates but does not write."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "document",
            "create",
            "--title",
            "Dry Run Doc",
            "--author",
            "Author",
            "--content",
            "Content",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload.get("dry_run") is True
    assert "would_create" in payload
    # Verify nothing was written
    list_result = runner.invoke(cli, ["document", "list"])
    assert list_result.exit_code == 0
    assert list_result.stdout.strip() == ""


def test_update_returns_full_row(db_with_seed, snapshot) -> None:
    """AC1.4: update with valid patch returns the resulting full Document."""
    db_path, seed_ids = db_with_seed
    doc_id = seed_ids.document_ids[0]
    runner = CliRunner()
    result = runner.invoke(
        cli, ["document", "update", str(doc_id), "--title", "Updated Title"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["title"] == "Updated Title"
    assert parsed == snapshot


def test_update_dry_run_does_not_modify(db_with_seed) -> None:
    """AC6.5: --dry-run does not modify database."""
    db_path, seed_ids = db_with_seed
    doc_id = seed_ids.document_ids[0]
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "document",
            "update",
            str(doc_id),
            "--title",
            "Would Be Updated",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload.get("dry_run") is True
    assert "would_update" in payload
    # Verify the original title is still there
    get_result = runner.invoke(cli, ["document", "get", str(doc_id)])
    assert get_result.exit_code == 0
    original = json.loads(get_result.stdout)
    assert original["title"] == "Seed Doc 1"


def test_delete_existing_returns_deleted_true(db_with_seed) -> None:
    """AC6.2: delete existing id returns deleted=true and exits 0."""
    db_path, seed_ids = db_with_seed
    doc_id = seed_ids.document_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "delete", str(doc_id)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["deleted"] is True
    assert payload["id"] == str(doc_id)


def test_delete_missing_returns_deleted_false(db_with_seed) -> None:
    """AC6.3: delete missing id is idempotent: returns deleted=false, exits 0."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "delete", "9999"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["deleted"] is False
    assert payload["id"] == "9999"
    assert payload["reason"] == "not_found"


def test_search_case_insensitive_single_token(db_with_seed, snapshot) -> None:
    """AC2.1: search matches case-insensitively across searchable columns."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "search", "seed"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Should match both "Seed Doc 1" and "Seed Doc 2"
    assert len(lines) == 2
    parsed_lines = [json.loads(line) for line in lines]
    for obj in parsed_lines:
        assert "seed" in obj["title"].lower()
    assert parsed_lines == snapshot


def test_search_multi_token_and(db_with_seed, snapshot) -> None:
    """AC2.2: multi-token search AND-combines tokens."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "search", "seed 1"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Should match only "Seed Doc 1" (both "seed" and "1" present)
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert "Seed Doc 1" in parsed_lines[0]["title"]
    assert parsed_lines == snapshot


def test_stdin_single_object_creates_one_row(db_path: Path, snapshot) -> None:
    """AC7.1: --stdin with single JSON object creates one row."""
    runner = CliRunner()
    body = json.dumps(
        {
            "last_updated": "2026-01-02T03:04:05+00:00",
            "title": "ViaStdin",
            "author": "agent",
            "content": "...body...",
        }
    )
    result = runner.invoke(cli, ["document", "create", "--stdin"], input=body)
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["title"] == "ViaStdin"
    assert isinstance(parsed["id"], str)
    assert parsed == snapshot


def test_stdin_array_creates_n_rows_in_order(db_path: Path, snapshot) -> None:
    """AC7.2: --stdin with array creates N rows in input order, returns array."""
    runner = CliRunner()
    body = json.dumps(
        [
            {
                "last_updated": "2026-01-01T00:00:00+00:00",
                "title": "First",
                "author": "a",
                "content": "c1",
            },
            {
                "last_updated": "2026-01-01T00:00:00+00:00",
                "title": "Second",
                "author": "b",
                "content": "c2",
            },
        ]
    )
    result = runner.invoke(cli, ["document", "create", "--stdin"], input=body)
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["title"] == "First"
    assert parsed[1]["title"] == "Second"
    # Verify ids are in ascending order (integers as strings)
    id1, id2 = int(parsed[0]["id"]), int(parsed[1]["id"])
    assert id1 < id2
    assert parsed == snapshot


def test_json_fields_projection_on_get(db_with_seed) -> None:
    """AC4.6 (extension): --json projects fields on single-object output."""
    db_path, seed_ids = db_with_seed
    doc_id = seed_ids.document_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "get", str(doc_id), "--json", "id,title"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert set(parsed.keys()) == {"id", "title"}


def test_json_fields_projection_on_list(db_with_seed) -> None:
    """AC4.6 (extension): --json projects fields on list output."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "list", "--json", "id,title"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    for line in lines:
        obj = json.loads(line)
        # _pagination footer won't be included in projection
        if "_pagination" not in obj:
            assert set(obj.keys()) == {"id", "title"}
