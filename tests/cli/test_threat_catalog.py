"""Golden snapshots for tm threat-catalog JSON output on all verbs."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from click.testing import CliRunner

from tm_cli.main import cli


def test_list_returns_seeded_entries(db_with_seed, snapshot) -> None:
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["threat-catalog", "list"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == len(seed_ids.threat_catalog_ids)
    parsed = [json.loads(line) for line in lines]
    assert parsed == snapshot


def test_get_returns_entry_with_tactics(db_with_seed, snapshot) -> None:
    db_path, seed_ids = db_with_seed
    catalog_id = seed_ids.threat_catalog_ids[0]
    runner = CliRunner()
    result = runner.invoke(cli, ["threat-catalog", "get", str(catalog_id)])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert "tactics" in parsed
    assert len(parsed["tactics"]) >= 1
    assert parsed == snapshot


def test_search_returns_matching_entries(db_with_seed, snapshot) -> None:
    db_path, seed_ids = db_with_seed
    runner = CliRunner()
    result = runner.invoke(cli, ["threat-catalog", "search", "Valid"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["name"] == "Valid Accounts"
    assert parsed == snapshot


def test_import_dir(db_with_seed, tmp_path: Path) -> None:
    db_path, seed_ids = db_with_seed
    md_dir = tmp_path / "mitre"
    md_dir.mkdir()
    (md_dir / "lateral-movement-extracted.md").write_text(
        textwrap.dedent("""\
        ### T9001: Test Technique
        **Platforms:** Linux
        **Description:** A test technique for import.
        """)
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["threat-catalog", "import-dir", str(md_dir)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["processed"] == 1
    assert payload["tactics"] == 1
    assert payload["files"] == 1
