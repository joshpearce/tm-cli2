"""Tests for Observation read shape with linked entity ids.

Covers:
- tm observation get <id> includes node_ids/container_ids/flow_ids/data_item_ids
- Linking a node via EntityObservationRepository appears in node_ids on get
- Linking a node does NOT bleed into container_ids (kind mapping is correct)
- tm observation list populates the four *_ids fields on every row
- tm observation search populates the four *_ids fields on every row
- ObservationRepository.list() uses a single batched query (no N+1)
- tm schema observation includes the four *_ids properties
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tm_cli.db import (
    DiagramCreate,
    DiagramRepository,
    EntityObservationRepository,
    NodeRepository,
    ObservationCreate,
    ObservationRepository,
    ProcessNodeCreate,
    connect,
)
from tm_cli.main import cli

# ---------------------------------------------------------------------------
# get — four *_ids fields present
# ---------------------------------------------------------------------------


def test_observation_get_includes_all_ids_fields_empty(db_path: Path) -> None:
    """get returns all four *_ids fields as [] when observation has no links."""
    runner = CliRunner()

    create_result = runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--content",
            "check auth",
            "--observation-type",
            "todo",
        ],
    )
    assert create_result.exit_code == 0
    obs_id = json.loads(create_result.stdout)["id"]

    get_result = runner.invoke(cli, ["observation", "get", obs_id])
    assert get_result.exit_code == 0
    payload = json.loads(get_result.stdout)

    assert "node_ids" in payload, "node_ids missing from observation get"
    assert "container_ids" in payload, "container_ids missing from observation get"
    assert "flow_ids" in payload, "flow_ids missing from observation get"
    assert "data_item_ids" in payload, "data_item_ids missing from observation get"
    assert payload["node_ids"] == []
    assert payload["container_ids"] == []
    assert payload["flow_ids"] == []
    assert payload["data_item_ids"] == []


def test_observation_get_node_ids_populated_after_link(db_path: Path) -> None:
    """After linking a node via repo, get returns node_ids: ['<node_id_str>']."""
    runner = CliRunner()

    # Create the observation via CLI
    create_result = runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--content",
            "check auth",
            "--observation-type",
            "todo",
        ],
    )
    assert create_result.exit_code == 0
    obs_id_str = json.loads(create_result.stdout)["id"]
    obs_id = int(obs_id_str)

    # Create the diagram + node via DB (CLI commands for link don't exist yet)
    with connect() as conn:
        diagram_id = DiagramRepository(conn).create(DiagramCreate(name="test-diag")).id
        node = NodeRepository(conn).create(
            diagram_id,
            ProcessNodeCreate(
                name="auth-node", description="d", trust_level="public", assumptions=[]
            ),
        )
        EntityObservationRepository(conn).link(node.id, obs_id)

    # get must return the node in node_ids
    get_result = runner.invoke(cli, ["observation", "get", obs_id_str])
    assert get_result.exit_code == 0
    payload = json.loads(get_result.stdout)

    assert payload["node_ids"] == [str(node.id)]
    # Other three lists must be empty — the node must NOT appear in container_ids
    assert payload["container_ids"] == []
    assert payload["flow_ids"] == []
    assert payload["data_item_ids"] == []


def test_observation_get_node_does_not_appear_in_container_ids(db_path: Path) -> None:
    """A node-linked observation must not show node id in container_ids."""
    runner = CliRunner()

    create_result = runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--content",
            "kind-check",
            "--observation-type",
            "todo",
        ],
    )
    assert create_result.exit_code == 0
    obs_id_str = json.loads(create_result.stdout)["id"]
    obs_id = int(obs_id_str)

    with connect() as conn:
        diagram_id = DiagramRepository(conn).create(DiagramCreate(name="d")).id
        node = NodeRepository(conn).create(
            diagram_id,
            ProcessNodeCreate(
                name="p", description="d", trust_level="public", assumptions=[]
            ),
        )
        EntityObservationRepository(conn).link(node.id, obs_id)

    get_result = runner.invoke(cli, ["observation", "get", obs_id_str])
    assert get_result.exit_code == 0
    payload = json.loads(get_result.stdout)

    node_id_str = str(node.id)
    assert node_id_str not in payload["container_ids"]
    assert node_id_str not in payload["flow_ids"]
    assert node_id_str not in payload["data_item_ids"]


# ---------------------------------------------------------------------------
# list — four *_ids fields on every row
# ---------------------------------------------------------------------------


def test_observation_list_populates_ids_fields(db_path: Path) -> None:
    """tm observation list emits the four *_ids fields on every row."""
    runner = CliRunner()

    # Create two observations
    r1 = runner.invoke(
        cli,
        ["observation", "create", "--content", "obs-a", "--observation-type", "todo"],
    )
    r2 = runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--content",
            "obs-b",
            "--observation-type",
            "question",
        ],
    )
    assert r1.exit_code == 0
    assert r2.exit_code == 0

    list_result = runner.invoke(cli, ["observation", "list"])
    assert list_result.exit_code == 0
    lines = [line for line in list_result.stdout.splitlines() if line.strip()]
    rows = [json.loads(line) for line in lines]

    assert len(rows) == 2
    for row in rows:
        assert "node_ids" in row, f"node_ids missing: {row}"
        assert "container_ids" in row, f"container_ids missing: {row}"
        assert "flow_ids" in row, f"flow_ids missing: {row}"
        assert "data_item_ids" in row, f"data_item_ids missing: {row}"
        assert isinstance(row["node_ids"], list)
        assert isinstance(row["container_ids"], list)
        assert isinstance(row["flow_ids"], list)
        assert isinstance(row["data_item_ids"], list)


# ---------------------------------------------------------------------------
# search — four *_ids fields on every row
# ---------------------------------------------------------------------------


def test_observation_search_populates_ids_fields(db_path: Path) -> None:
    """tm observation search emits the four *_ids fields on every row."""
    runner = CliRunner()

    runner.invoke(
        cli,
        [
            "observation",
            "create",
            "--content",
            "search-target",
            "--observation-type",
            "todo",
        ],
    )

    search_result = runner.invoke(cli, ["observation", "search", "search-target"])
    assert search_result.exit_code == 0
    lines = [line for line in search_result.stdout.splitlines() if line.strip()]
    rows = [json.loads(line) for line in lines]

    assert len(rows) >= 1
    for row in rows:
        assert "node_ids" in row
        assert "container_ids" in row
        assert "flow_ids" in row
        assert "data_item_ids" in row


# ---------------------------------------------------------------------------
# N+1 prevention — single batched query for linked_ids_by_kind_for
# ---------------------------------------------------------------------------


def test_observation_list_uses_single_batched_query_for_links(db_path: Path) -> None:
    """list() must not issue N separate entity_observations queries.

    Uses sqlite3 set_trace_callback to count SQL statements that reference
    the entity_observations table. For N observations, the count must be
    exactly 1 (the single batched IN-query), not N.
    """
    n = 5
    with connect() as conn:
        obs_repo = ObservationRepository(conn)
        for i in range(n):
            obs_repo.create(
                ObservationCreate(content=f"obs-{i}", observation_type="todo")
            )

        # Trace SQL statements referencing entity_observations
        entity_obs_queries: list[str] = []

        def _tracer(statement: str) -> None:
            if "entity_observations" in statement:
                entity_obs_queries.append(statement)

        conn.set_trace_callback(_tracer)

        # This should produce exactly ONE batched query
        _ = obs_repo.list()

        conn.set_trace_callback(None)

    assert len(entity_obs_queries) == 1, (
        f"Expected exactly 1 entity_observations query, got {len(entity_obs_queries)}. "
        f"Queries: {entity_obs_queries}"
    )


# ---------------------------------------------------------------------------
# N+1 prevention — single batched query for search() (M7)
# ---------------------------------------------------------------------------


def test_observation_search_uses_single_batched_query_for_links(db_path: Path) -> None:
    """search() must not issue N separate entity_observations queries.

    Uses sqlite3 set_trace_callback to count SQL statements that reference
    the entity_observations table. For N observations, the count must be
    exactly 1 (the single batched IN-query), not N.
    """
    n = 5
    with connect() as conn:
        obs_repo = ObservationRepository(conn)
        for i in range(n):
            obs_repo.create(
                ObservationCreate(content=f"search-n1-{i}", observation_type="todo")
            )

        entity_obs_queries: list[str] = []

        def _tracer(statement: str) -> None:
            if "entity_observations" in statement:
                entity_obs_queries.append(statement)

        conn.set_trace_callback(_tracer)
        _ = obs_repo.search("search-n1")
        conn.set_trace_callback(None)

    assert len(entity_obs_queries) == 1, (
        f"Expected exactly 1 entity_observations query, got {len(entity_obs_queries)}. "
        f"Queries: {entity_obs_queries}"
    )


def test_observation_list_batched_query_count_independent_of_row_count(
    db_path: Path,
) -> None:
    """The number of entity_observations queries is always 1 regardless of row count.

    Creates 5 observations, links 3 different DFD-kind entities to each, then calls
    list() and asserts exactly 1 batched query is issued — not 5.
    """
    with connect() as conn:
        diagram_id = DiagramRepository(conn).create(DiagramCreate(name="d")).id
        # Create one entity of each of the three DFD kinds we'll link
        node = NodeRepository(conn).create(
            diagram_id,
            ProcessNodeCreate(
                name="p", description="d", trust_level="public", assumptions=[]
            ),
        )
        obs_repo = ObservationRepository(conn)
        eo_repo = EntityObservationRepository(conn)

        # Create 5 observations and link the node to each
        obs_ids: list[int] = []
        for i in range(5):
            obs = obs_repo.create(
                ObservationCreate(content=f"multi-{i}", observation_type="todo")
            )
            obs_ids.append(obs.id)
            eo_repo.link(node.id, obs.id)

        entity_obs_queries: list[str] = []

        def _tracer(statement: str) -> None:
            if "entity_observations" in statement:
                entity_obs_queries.append(statement)

        conn.set_trace_callback(_tracer)
        result = obs_repo.list()
        conn.set_trace_callback(None)

    assert len(result) == 5
    assert len(entity_obs_queries) == 1, (
        f"Expected exactly 1 batched query regardless of row count, "
        f"got {len(entity_obs_queries)}. Queries: {entity_obs_queries}"
    )


# ---------------------------------------------------------------------------
# tm schema observation reflects the new *_ids fields
# ---------------------------------------------------------------------------


def test_schema_observation_includes_ids_fields(db_path: Path) -> None:
    """tm schema observation read shape includes the four *_ids array fields."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "observation"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)

    read_schema = payload["read"]
    # The read schema should have a properties dict
    assert "properties" in read_schema, (
        f"Expected properties in read schema: {read_schema}"
    )

    props = read_schema["properties"]
    for field in ("node_ids", "container_ids", "flow_ids", "data_item_ids"):
        assert field in props, (
            f"Field {field!r} missing from schema observation read properties"
        )
        # Each field should be an array type
        field_schema = props[field]
        assert field_schema.get("type") == "array" or "items" in field_schema, (
            f"Expected {field!r} to be an array schema, got: {field_schema}"
        )
