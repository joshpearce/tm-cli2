"""Golden snapshots for tm term JSON output on all verbs."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_seeded_terms_as_ndjson(db_with_seed, snapshot) -> None:
    """AC1.1: list returns NDJSON, one parseable object per line."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["term", "list"])
    assert result.exit_code == 0
    # NDJSON: every non-empty line is a parseable object.
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == len(seed_ids.term_ids)
    parsed_lines = [json.loads(line) for line in lines]
    for obj in parsed_lines:
        json.loads(json.dumps(obj))
    assert parsed_lines == snapshot


def test_get_returns_full_term(db_with_seed, snapshot) -> None:
    """AC1.2: get returns full Term object."""
    db_path, seed_ids = db_with_seed
    term_id = seed_ids.term_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["term", "get", str(term_id)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "id" in payload
    assert "term" in payload
    assert "definition" in payload
    assert "last_updated" in payload
    assert payload == snapshot


def test_create_with_named_flags_returns_new_row(db_path: Path, snapshot) -> None:
    """AC1.3: create with named flags returns the new row as single JSON object."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "term",
            "create",
            "--term",
            "alpha",
            "--definition",
            "First letter of Greek alphabet",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["term"] == "alpha"
    assert parsed["definition"] == "First letter of Greek alphabet"
    assert isinstance(parsed["id"], str)
    assert "last_updated" in parsed
    assert parsed == snapshot


def test_update_returns_updated_row(db_with_seed, snapshot) -> None:
    """AC1.4: update with valid patch returns the resulting full Term."""
    db_path, seed_ids = db_with_seed
    term_id = seed_ids.term_ids[0]
    runner = CliRunner()
    result = runner.invoke(
        cli, ["term", "update", str(term_id), "--definition", "Updated definition"]
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["definition"] == "Updated definition"
    assert parsed == snapshot


def test_get_missing_id_exits_2(db_path: Path) -> None:
    """AC1.5: get of missing id exits 2 with error.code = 'not_found'."""
    runner = CliRunner()
    result = runner.invoke(cli, ["term", "get", "9999"])
    assert result.exit_code == 2
    stderr = result.output  # CliRunner captures both stdout and stderr
    payload = json.loads(stderr)
    assert payload.get("error", {}).get("code") == "not_found"


def test_update_missing_id_exits_2(db_path: Path) -> None:
    """AC1.6: update of missing id exits 2 with error.code = 'not_found'."""
    runner = CliRunner()
    result = runner.invoke(cli, ["term", "update", "9999", "--definition", "x"])
    assert result.exit_code == 2
    stderr = result.output
    payload = json.loads(stderr)
    assert payload.get("error", {}).get("code") == "not_found"


def test_search_case_insensitive(db_with_seed, snapshot) -> None:
    """AC2.1: search matches case-insensitively across searchable columns."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["term", "search", "SEED"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Should match all three seed-term-1/2/3
    assert len(lines) == 3
    parsed_lines = [json.loads(line) for line in lines]
    for obj in parsed_lines:
        assert "seed" in obj["term"].lower()
    assert parsed_lines == snapshot


def test_search_multi_token_and(db_with_seed, snapshot) -> None:
    """AC2.2: multi-token search AND-combines tokens."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["term", "search", "seed 1"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # Should match only seed-term-1 (both "seed" and "1" present)
    assert len(lines) == 1
    parsed_lines = [json.loads(line) for line in lines]
    assert "seed-term-1" in parsed_lines[0]["term"]
    assert parsed_lines == snapshot


def test_create_duplicate_term_exits_3_unique(db_with_seed) -> None:
    """AC5.3: UNIQUE constraint violation exits 3 with error.constraint = 'unique'."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "term",
            "create",
            "--term",
            "seed-term-1",
            "--definition",
            "duplicate attempt",
        ],
    )
    assert result.exit_code == 3
    stderr = result.output
    payload = json.loads(stderr)
    assert payload.get("error", {}).get("constraint") == "unique"


def test_if_not_exists_returns_existing_with_created_false(
    db_with_seed, snapshot
) -> None:
    """AC6.1: --if-not-exists returns existing row with created=false."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "term",
            "create",
            "--if-not-exists",
            "--term",
            "seed-term-1",
            "--definition",
            "different definition",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["created"] is False
    # Should return original definition, not the new one
    assert "definition 1" in parsed["definition"]
    assert parsed == snapshot


def test_if_not_exists_creates_when_absent(db_path: Path, snapshot) -> None:
    """AC6.1: --if-not-exists creates when term is absent."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "term",
            "create",
            "--if-not-exists",
            "--term",
            "fresh-term",
            "--definition",
            "brand new",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["created"] is True
    assert parsed["term"] == "fresh-term"
    assert parsed == snapshot


def test_list_documents_for_term_returns_linked_docs(db_with_seed, snapshot) -> None:
    """Reverse junction: list-documents returns linked document summaries."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    doc_id = seed_ids.document_ids[0]
    term_id = seed_ids.term_ids[0]

    # First, link a term to a document
    link_result = runner.invoke(
        cli, ["document", "link-term", str(doc_id), str(term_id)]
    )
    assert link_result.exit_code == 0

    # Now list documents for that term
    result = runner.invoke(cli, ["term", "list-documents", str(term_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    parsed_lines = [json.loads(line) for line in lines]
    # At least the linked document should appear
    assert any(doc.get("id") == str(doc_id) for doc in parsed_lines)
    assert parsed_lines == snapshot


def test_list_documents_for_missing_term_exits_2(db_path: Path) -> None:
    """AC1.5 (reverse): list-documents for missing term exits 2."""
    runner = CliRunner()
    result = runner.invoke(cli, ["term", "list-documents", "9999"])
    assert result.exit_code == 2
    stderr = result.output
    payload = json.loads(stderr)
    assert payload.get("error", {}).get("code") == "not_found"
