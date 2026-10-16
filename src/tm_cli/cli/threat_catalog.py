"""tm threat-catalog — MITRE ATT&CK catalog import and lookup."""

from __future__ import annotations

import re
from pathlib import Path

import click

from tm_cli.cli._errors import NotFoundError
from tm_cli.cli._options import (
    apply_sort,
    json_fields_option,
    list_options,
    parse_json_fields,
)
from tm_cli.cli._output import emit, project_fields
from tm_cli.db import (
    ThreatCatalogCreate,
    ThreatCatalogRepository,
    connect,
)

_TECHNIQUE_RE = re.compile(r"^### (T\d+(?:\.\d+)?): (.+)$")
_PLATFORMS_RE = re.compile(r"^\*\*Platforms?:\*\*\s*(.+)$")
_DESCRIPTION_RE = re.compile(r"^\*\*Description:\*\*\s*(.+)$")


def _tactic_from_filename(filename: str) -> str:
    """Derive tactic name from filename like ``initial-access-extracted.md``."""
    stem = Path(filename).stem
    for suffix in ("-extracted-part1", "-extracted-part2", "-extracted"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _parse_techniques(
    text: str, tactic: str
) -> list[tuple[ThreatCatalogCreate, list[str]]]:
    """Parse markdown into (create-model, tactic-list) pairs."""
    results: list[tuple[ThreatCatalogCreate, list[str]]] = []
    current_id: str | None = None
    current_name: str | None = None
    current_platforms: str | None = None
    current_description: str | None = None

    for line in text.splitlines():
        m = _TECHNIQUE_RE.match(line)
        if m:
            if current_id and current_name and current_platforms is not None:
                results.append(
                    (
                        ThreatCatalogCreate(
                            mitre_id=current_id,
                            name=current_name,
                            platforms=current_platforms or "",
                            description=current_description or "",
                        ),
                        [tactic],
                    )
                )
            current_id = m.group(1)
            current_name = m.group(2).strip()
            current_platforms = None
            current_description = None
            continue

        pm = _PLATFORMS_RE.match(line)
        if pm and current_id:
            current_platforms = pm.group(1).strip()
            continue

        dm = _DESCRIPTION_RE.match(line)
        if dm and current_id:
            current_description = dm.group(1).strip()
            continue

    if current_id and current_name and current_platforms is not None:
        results.append(
            (
                ThreatCatalogCreate(
                    mitre_id=current_id,
                    name=current_name,
                    platforms=current_platforms or "",
                    description=current_description or "",
                ),
                [tactic],
            )
        )

    return results


@click.group(name="threat-catalog")
def threat_catalog_group() -> None:
    """Manage MITRE ATT&CK threat catalog entries."""


@threat_catalog_group.command(name="import-dir")
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.pass_context
def import_dir(ctx, path) -> None:
    """Import extracted MITRE techniques from markdown files in PATH."""
    dir_path = Path(path)
    md_files = sorted(dir_path.glob("*.md"))
    if not md_files:
        emit(ctx, {"processed": 0, "tactics": 0, "files": 0})
        return

    total_processed = 0
    tactics_seen: set[str] = set()

    with connect() as conn:
        repo = ThreatCatalogRepository(conn)
        for md_file in md_files:
            tactic = _tactic_from_filename(md_file.name)
            tactics_seen.add(tactic)
            text = md_file.read_text()
            techniques = _parse_techniques(text, tactic)
            for create_model, tactic_names in techniques:
                repo.create(create_model, tactic_names)
                total_processed += 1

    emit(
        ctx,
        {
            "processed": total_processed,
            "tactics": len(tactics_seen),
            "files": len(md_files),
        },
    )


@threat_catalog_group.command(name="list")
@list_options
@json_fields_option
@click.pass_context
def list_catalog(ctx, *, limit, offset, sort_field, order, json_fields) -> None:
    """List threat catalog entries."""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = ThreatCatalogRepository(conn).list(limit=limit, offset=offset)
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)


@threat_catalog_group.command(name="get")
@click.argument("catalog_id", type=click.INT)
@json_fields_option
@click.pass_context
def get_catalog(ctx, catalog_id, *, json_fields) -> None:
    """Fetch a threat catalog entry by id."""
    with connect() as conn:
        row = ThreatCatalogRepository(conn).get(catalog_id)
    if row is None:
        raise NotFoundError(
            f"Threat catalog id={catalog_id} not found", id=str(catalog_id)
        )
    fields = parse_json_fields(json_fields)
    payload = project_fields(row.model_dump(mode="json"), fields)
    emit(ctx, payload)


@threat_catalog_group.command(name="search")
@click.argument("text", nargs=-1, required=False)
@list_options
@json_fields_option
@click.pass_context
def search_catalog(ctx, text, *, limit, offset, sort_field, order, json_fields) -> None:
    """Search threat catalog entries by text."""
    text_str = " ".join(text).strip() if text else ""
    fields = parse_json_fields(json_fields)
    with connect() as conn:
        rows = ThreatCatalogRepository(conn).search(
            text=text_str if text_str else None,
            limit=limit,
            offset=offset,
        )
    sorted_rows = apply_sort(rows, sort_field=sort_field, order=order)
    projected = [project_fields(r.model_dump(mode="json"), fields) for r in sorted_rows]
    emit(ctx, projected, list_mode=True, limit=limit, offset=offset)
