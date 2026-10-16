"""Tests for document↔term junction commands (link-term, unlink-term, list-terms)."""

from __future__ import annotations

import json

from click.testing import CliRunner

from tm_cli.main import cli


def test_link_term_creates_link(db_with_seed, snapshot) -> None:
    """AC3.1: link-term creates a link and returns linked=true."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    doc_id = seed_ids.document_ids[0]
    term_id = seed_ids.term_ids[0]

    result = runner.invoke(cli, ["document", "link-term", str(doc_id), str(term_id)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["linked"] is True
    assert payload["doc_id"] == str(doc_id)
    assert payload["term_id"] == str(term_id)

    # Verify the link was created by listing terms
    list_result = runner.invoke(cli, ["document", "list-terms", str(doc_id)])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 1
    parsed_lines = [json.loads(line) for line in lines]
    term_ids = [obj["id"] for obj in parsed_lines]
    assert str(term_id) in term_ids

    assert payload == snapshot


def test_relink_returns_already_linked(db_with_seed) -> None:
    """AC3.2: relinking same pair returns linked=false with reason='already_linked'."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    doc_id = seed_ids.document_ids[0]
    term_id = seed_ids.term_ids[0]

    # First link
    first_result = runner.invoke(
        cli, ["document", "link-term", str(doc_id), str(term_id)]
    )
    assert first_result.exit_code == 0
    first_payload = json.loads(first_result.stdout)
    assert first_payload["linked"] is True

    # Second link (same pair)
    second_result = runner.invoke(
        cli, ["document", "link-term", str(doc_id), str(term_id)]
    )
    assert second_result.exit_code == 0
    second_payload = json.loads(second_result.stdout)
    assert second_payload["linked"] is False
    assert second_payload["reason"] == "already_linked"


def test_unlink_term_removes_link(db_with_seed, snapshot) -> None:
    """AC3.3: unlink-term removes the link; term no longer in list-terms."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    doc_id = seed_ids.document_ids[0]
    term_id = seed_ids.term_ids[0]

    # Link first
    link_result = runner.invoke(
        cli, ["document", "link-term", str(doc_id), str(term_id)]
    )
    assert link_result.exit_code == 0

    # Verify it's linked
    verify_result = runner.invoke(cli, ["document", "list-terms", str(doc_id)])
    assert verify_result.exit_code == 0
    verify_lines = [line for line in verify_result.stdout.splitlines() if line.strip()]
    assert len(verify_lines) >= 1

    # Unlink
    unlink_result = runner.invoke(
        cli, ["document", "unlink-term", str(doc_id), str(term_id)]
    )
    assert unlink_result.exit_code == 0
    unlink_payload = json.loads(unlink_result.stdout)
    assert unlink_payload["unlinked"] is True
    assert unlink_payload["doc_id"] == str(doc_id)
    assert unlink_payload["term_id"] == str(term_id)

    # Verify it's no longer linked
    final_result = runner.invoke(cli, ["document", "list-terms", str(doc_id)])
    assert final_result.exit_code == 0
    final_lines = [line for line in final_result.stdout.splitlines() if line.strip()]
    # Should be empty or at least not contain this term
    final_parsed = [json.loads(line) for line in final_lines]
    term_ids = [obj.get("id") for obj in final_parsed]
    assert str(term_id) not in term_ids

    assert unlink_payload == snapshot


def test_unlink_nonexistent_link_returns_not_linked(db_with_seed) -> None:
    """Unlink when not linked returns unlinked=false with reason='not_linked'."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    doc_id = seed_ids.document_ids[0]
    term_id = seed_ids.term_ids[0]

    # Unlink without ever linking
    result = runner.invoke(cli, ["document", "unlink-term", str(doc_id), str(term_id)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["unlinked"] is False
    assert payload["reason"] == "not_linked"


def test_link_term_unknown_doc_id_exits_3_fk(db_with_seed) -> None:
    """AC5.4: linking to unknown doc_id exits 3 with error.constraint='foreign_key'."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    term_id = seed_ids.term_ids[0]

    result = runner.invoke(cli, ["document", "link-term", "9999", str(term_id)])
    assert result.exit_code == 3
    stderr = result.output
    payload = json.loads(stderr)
    assert payload.get("error", {}).get("constraint") == "foreign_key"


def test_link_term_unknown_term_id_exits_3_fk(db_with_seed) -> None:
    """AC5.4: linking to unknown term_id exits 3 with error.constraint='foreign_key'."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    doc_id = seed_ids.document_ids[0]

    result = runner.invoke(cli, ["document", "link-term", str(doc_id), "9999"])
    assert result.exit_code == 3
    stderr = result.output
    payload = json.loads(stderr)
    assert payload.get("error", {}).get("constraint") == "foreign_key"


def test_list_terms_returns_ndjson(db_with_seed, snapshot) -> None:
    """AC3.1: list-terms returns NDJSON of Term rows."""
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    doc_id = seed_ids.document_ids[0]
    term_id_1 = seed_ids.term_ids[0]
    term_id_2 = seed_ids.term_ids[1]

    # Link two terms
    runner.invoke(cli, ["document", "link-term", str(doc_id), str(term_id_1)])
    runner.invoke(cli, ["document", "link-term", str(doc_id), str(term_id_2)])

    # List terms
    result = runner.invoke(cli, ["document", "list-terms", str(doc_id)])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) >= 2
    parsed_lines = [json.loads(line) for line in lines]

    # Verify structure
    for obj in parsed_lines:
        assert "id" in obj
        assert "term" in obj
        assert "definition" in obj

    assert parsed_lines == snapshot


def test_list_terms_for_missing_doc_exits_2(db_path) -> None:
    """AC1.5: list-terms for missing doc_id exits 2."""
    runner = CliRunner()
    result = runner.invoke(cli, ["document", "list-terms", "9999"])
    assert result.exit_code == 2
    stderr = result.output
    payload = json.loads(stderr)
    assert payload.get("error", {}).get("code") == "not_found"
