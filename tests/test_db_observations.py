from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from tm_cli.db import (
    Observation,
    ObservationCreate,
    ObservationRepository,
    ObservationUpdate,
    connect,
)
from tm_cli.db import connection as connection_module


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tm.db"
    monkeypatch.setenv("TM_DB_PATH", str(path))
    monkeypatch.setattr(connection_module, "_initialized_paths", set())
    return path


def test_create_assigns_id_and_last_updated(db_path: Path) -> None:
    before = datetime.now(UTC)
    with connect() as conn:
        repo = ObservationRepository(conn)
        obs = repo.create(
            ObservationCreate(
                content="auth flow may be vulnerable to replay",
                observation_type="potential_threat",
            )
        )
    after = datetime.now(UTC)

    assert obs.id == 1
    assert obs.content == "auth flow may be vulnerable to replay"
    assert obs.observation_type == "potential_threat"
    assert obs.status == "open"
    slack = timedelta(seconds=1)
    assert before - slack <= obs.last_updated <= after + slack


def test_create_accepts_explicit_closed_status(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        obs = repo.create(
            ObservationCreate(
                content="resolved upstream",
                observation_type="todo",
                status="closed",
            )
        )
    assert obs.status == "closed"


def test_pydantic_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        ObservationCreate(content="x", observation_type="bogus")  # type: ignore[arg-type]


def test_pydantic_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        ObservationCreate(
            content="x",
            observation_type="todo",
            status="archived",  # type: ignore[arg-type]
        )


def test_db_check_constraint_rejects_unknown_type(db_path: Path) -> None:
    """Defense in depth: even raw SQL bypassing Pydantic must fail."""
    with pytest.raises(sqlite3.IntegrityError):
        with connect() as conn:
            conn.execute(
                "INSERT INTO observations "
                "(content, observation_type, last_updated) VALUES (?, ?, ?)",
                ("x", "bogus", datetime.now(UTC)),
            )


def test_db_check_constraint_rejects_unknown_status(db_path: Path) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        with connect() as conn:
            conn.execute(
                "INSERT INTO observations "
                "(content, observation_type, status, last_updated) "
                "VALUES (?, ?, ?, ?)",
                ("x", "todo", "archived", datetime.now(UTC)),
            )


def test_update_can_close_an_observation(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        original = repo.create(ObservationCreate(content="c", observation_type="todo"))
        assert original.status == "open"

    with connect() as conn:
        repo = ObservationRepository(conn)
        closed = repo.update(original.id, ObservationUpdate(status="closed"))

    assert closed is not None
    assert closed.status == "closed"
    assert closed.last_updated >= original.last_updated


def test_exists_returns_true_for_known_id(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        obs = repo.create(ObservationCreate(content="c", observation_type="todo"))
        assert repo.exists(obs.id) is True


def test_exists_returns_false_for_missing_id(db_path: Path) -> None:
    with connect() as conn:
        assert ObservationRepository(conn).exists(999) is False


def test_get_returns_none_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        assert ObservationRepository(conn).get(999) is None


def test_get_returns_created_observation(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        created = repo.create(
            ObservationCreate(content="why no MFA?", observation_type="question")
        )
        fetched = repo.get(created.id)
    assert fetched is not None
    assert fetched.model_dump() == created.model_dump()


def test_update_partial_fields_bumps_last_updated(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        original = repo.create(
            ObservationCreate(content="check session timeout", observation_type="todo")
        )

    with connect() as conn:
        repo = ObservationRepository(conn)
        updated = repo.update(
            original.id,
            ObservationUpdate(observation_type="question"),
        )

    assert updated is not None
    assert updated.content == original.content
    assert updated.observation_type == "question"
    assert updated.last_updated >= original.last_updated


def test_update_returns_none_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        assert repo.update(42, ObservationUpdate(content="x")) is None


def test_update_with_empty_patch_still_bumps_last_updated(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        original = repo.create(ObservationCreate(content="c", observation_type="todo"))

    with connect() as conn:
        repo = ObservationRepository(conn)
        touched = repo.update(original.id, ObservationUpdate())

    assert touched is not None
    assert touched.last_updated >= original.last_updated
    assert touched.content == original.content
    assert touched.observation_type == original.observation_type


def test_delete_returns_true_then_false(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        created = repo.create(ObservationCreate(content="c", observation_type="todo"))
        assert repo.delete(created.id) is True
        assert repo.delete(created.id) is False
        assert repo.get(created.id) is None


def test_list_orders_by_id_and_supports_limit_offset(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        a = repo.create(ObservationCreate(content="A", observation_type="todo"))
        b = repo.create(ObservationCreate(content="B", observation_type="question"))
        c = repo.create(
            ObservationCreate(content="C", observation_type="potential_threat")
        )

        all_obs = repo.list()
        assert all(isinstance(o, Observation) for o in all_obs)
        assert [o.id for o in all_obs] == [a.id, b.id, c.id]

        page = repo.list(limit=2, offset=1)
        assert [o.content for o in page] == ["B", "C"]


def test_list_filters_by_observation_type(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        repo.create(ObservationCreate(content="a", observation_type="todo"))
        repo.create(ObservationCreate(content="b", observation_type="question"))
        repo.create(ObservationCreate(content="c", observation_type="todo"))

        todos = repo.list(observation_type="todo")
        assert [o.content for o in todos] == ["a", "c"]

        questions = repo.list(observation_type="question")
        assert [o.content for o in questions] == ["b"]

        missing = repo.list(observation_type="incomplete_information")
        assert missing == []


def test_list_filters_by_status(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        repo.create(ObservationCreate(content="a", observation_type="todo"))
        repo.create(
            ObservationCreate(content="b", observation_type="todo", status="closed")
        )
        repo.create(ObservationCreate(content="c", observation_type="todo"))

        opens = repo.list(status="open")
        assert [o.content for o in opens] == ["a", "c"]

        closed = repo.list(status="closed")
        assert [o.content for o in closed] == ["b"]


def test_list_filters_by_type_and_status_together(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        repo.create(ObservationCreate(content="t-open", observation_type="todo"))
        repo.create(
            ObservationCreate(
                content="t-closed", observation_type="todo", status="closed"
            )
        )
        repo.create(ObservationCreate(content="q-open", observation_type="question"))

        result = repo.list(observation_type="todo", status="open")
        assert [o.content for o in result] == ["t-open"]


def test_all_four_observation_types_round_trip(db_path: Path) -> None:
    types = (
        "potential_threat",
        "incomplete_information",
        "question",
        "todo",
    )
    with connect() as conn:
        repo = ObservationRepository(conn)
        for t in types:
            obs = repo.create(ObservationCreate(content=t, observation_type=t))  # type: ignore[arg-type]
            assert obs.observation_type == t


def test_search_no_args_returns_all_in_id_order(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        a = repo.create(ObservationCreate(content="alpha", observation_type="todo"))
        b = repo.create(ObservationCreate(content="beta", observation_type="question"))
        assert [o.id for o in repo.search()] == [a.id, b.id]


def test_search_text_matches_content(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        repo.create(
            ObservationCreate(
                content="replay attack", observation_type="potential_threat"
            )
        )
        repo.create(
            ObservationCreate(content="missing rate limit", observation_type="todo")
        )

        hits = repo.search(text="replay")
        assert len(hits) == 1
        assert hits[0].content == "replay attack"


def test_search_multi_token_ands_in_content(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        repo.create(
            ObservationCreate(
                content="replay attack found",
                observation_type="potential_threat",
            )
        )
        repo.create(
            ObservationCreate(
                content="replay only", observation_type="potential_threat"
            )
        )

        hits = repo.search(text="replay attack")
        assert len(hits) == 1


def test_search_text_combined_with_filters(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        target = repo.create(
            ObservationCreate(
                content="auth replay attack",
                observation_type="potential_threat",
                status="open",
            )
        )
        repo.create(
            ObservationCreate(
                content="auth replay attack",
                observation_type="potential_threat",
                status="closed",
            )
        )
        repo.create(
            ObservationCreate(
                content="auth replay attack",
                observation_type="todo",
                status="open",
            )
        )

        hits = repo.search(
            text="replay",
            observation_type="potential_threat",
            status="open",
        )
        assert [o.id for o in hits] == [target.id]


def test_search_case_insensitive(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        created = repo.create(
            ObservationCreate(content="MiXeD CaSe", observation_type="todo")
        )
        hits = repo.search(text="mixed")
        assert [o.id for o in hits] == [created.id]


def test_search_escapes_wildcards(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        target = repo.create(
            ObservationCreate(content="100% reproducible", observation_type="todo")
        )
        decoy = repo.create(
            ObservationCreate(content="100x faster", observation_type="todo")
        )
        hits = repo.search(text="100%")
        ids = {o.id for o in hits}
        assert target.id in ids
        assert decoy.id not in ids


def test_search_pagination(db_path: Path) -> None:
    with connect() as conn:
        repo = ObservationRepository(conn)
        ids = [
            repo.create(
                ObservationCreate(content=f"hit {i}", observation_type="todo")
            ).id
            for i in range(4)
        ]
        page1 = repo.search(text="hit", limit=2)
        page2 = repo.search(text="hit", limit=2, offset=2)
        assert [o.id for o in page1] == ids[:2]
        assert [o.id for o in page2] == ids[2:]
