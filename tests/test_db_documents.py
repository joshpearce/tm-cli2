from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tm_cli.db import (
    DocumentCreate,
    DocumentRepository,
    DocumentSummary,
    DocumentUpdate,
    connect,
    init_schema,
)
from tm_cli.db import connection as connection_module


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tm.db"
    monkeypatch.setenv("TM_DB_PATH", str(path))
    monkeypatch.setattr(connection_module, "_initialized_paths", set())
    return path


def _sample_create(**overrides: object) -> DocumentCreate:
    base: dict[str, object] = {
        "last_updated": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        "title": "Hello",
        "author": "alice",
        "content": "body",
    }
    base.update(overrides)
    return DocumentCreate(**base)  # type: ignore[arg-type]


def test_create_assigns_id_and_last_imported(db_path: Path) -> None:
    before = datetime.now(UTC)
    with connect() as conn:
        repo = DocumentRepository(conn)
        doc = repo.create(_sample_create())
    after = datetime.now(UTC)

    assert doc.id == 1
    assert doc.title == "Hello"
    assert doc.author == "alice"
    assert doc.content == "body"
    assert doc.last_updated == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    slack = timedelta(seconds=1)
    assert before - slack <= doc.last_imported <= after + slack


def test_get_returns_none_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        assert repo.get(999) is None


def test_get_returns_created_document(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        created = repo.create(_sample_create())
        fetched = repo.get(created.id)
    assert fetched is not None
    assert fetched.model_dump() == created.model_dump()


def test_update_partial_fields_bumps_last_imported(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        original = repo.create(_sample_create())
        updated = repo.update(original.id, DocumentUpdate(title="Updated"))

    assert updated is not None
    assert updated.title == "Updated"
    assert updated.author == original.author
    assert updated.content == original.content
    assert updated.last_updated == original.last_updated
    assert updated.last_imported >= original.last_imported


def test_update_returns_none_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        assert repo.update(42, DocumentUpdate(title="x")) is None


def test_update_with_empty_patch_still_bumps_last_imported(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        original = repo.create(_sample_create())

    with connect() as conn:
        repo = DocumentRepository(conn)
        touched = repo.update(original.id, DocumentUpdate())

    assert touched is not None
    assert touched.last_imported >= original.last_imported
    assert touched.title == original.title


def test_delete_returns_true_then_false(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        created = repo.create(_sample_create())
        assert repo.delete(created.id) is True
        assert repo.delete(created.id) is False
        assert repo.get(created.id) is None


def test_list_orders_by_id_and_supports_limit_offset(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        a = repo.create(_sample_create(title="A"))
        b = repo.create(_sample_create(title="B"))
        c = repo.create(_sample_create(title="C"))

        all_docs = repo.list()
        assert all(isinstance(d, DocumentSummary) for d in all_docs)
        assert [d.id for d in all_docs] == [a.id, b.id, c.id]

        page = repo.list(limit=2, offset=1)
        assert [d.title for d in page] == ["B", "C"]

        tail = repo.list(offset=2)
        assert [d.title for d in tail] == ["C"]


def test_list_omits_content(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        repo.create(_sample_create(content="x" * 10_000))
        summaries = repo.list()

    assert len(summaries) == 1
    summary = summaries[0]
    assert "content" not in DocumentSummary.model_fields
    assert not hasattr(summary, "content")


def test_init_schema_is_idempotent(db_path: Path) -> None:
    with connect() as conn:
        init_schema(conn)
        init_schema(conn)
        repo = DocumentRepository(conn)
        repo.create(_sample_create())


def test_connect_raises_when_env_var_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TM_DB_PATH", raising=False)
    with pytest.raises(RuntimeError, match="TM_DB_PATH"):
        with connect():
            pass


def test_search_no_args_returns_all_in_id_order(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        a = repo.create(_sample_create(title="A"))
        b = repo.create(_sample_create(title="B"))
        c = repo.create(_sample_create(title="C"))

        results = repo.search()
        assert [d.id for d in results] == [a.id, b.id, c.id]


def test_search_single_token_matches_text_columns(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        repo.create(_sample_create(title="Alpha", content="x"))
        repo.create(_sample_create(title="Other", author="alpha-author"))
        repo.create(_sample_create(title="Other", content="contains alpha here"))
        repo.create(_sample_create(title="Beta"))

        results = repo.search(text="alpha")
        assert len(results) == 3
        assert all("Beta" not in r.title for r in results)


def test_search_no_match_returns_empty(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        repo.create(_sample_create(title="Alpha"))
        assert repo.search(text="zzznope") == []


def test_search_multi_token_ands(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        repo.create(_sample_create(title="foo bar baz"))
        only_foo = repo.create(_sample_create(title="foo only"))
        repo.create(_sample_create(title="other", content="foo and bar together"))

        ids = {d.id for d in repo.search(text="foo bar")}
        assert only_foo.id not in ids
        assert len(ids) == 2


def test_search_is_case_insensitive(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        created = repo.create(_sample_create(title="Mixed Case Title"))
        results = repo.search(text="MIXED case")
        assert [d.id for d in results] == [created.id]


def test_search_escapes_like_wildcards(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        target = repo.create(_sample_create(title="100% complete"))
        decoy = repo.create(_sample_create(title="100x complete"))

        results = repo.search(text="100%")
        ids = [d.id for d in results]
        assert target.id in ids
        assert decoy.id not in ids


def test_search_underscore_is_escaped(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        target = repo.create(_sample_create(title="snake_case"))
        decoy = repo.create(_sample_create(title="snakeXcase"))

        results = repo.search(text="snake_")
        ids = [d.id for d in results]
        assert target.id in ids
        assert decoy.id not in ids


def test_search_pagination_is_stable(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        ids = [
            repo.create(_sample_create(title=f"hit {i}", content="match")).id
            for i in range(5)
        ]

        page1 = repo.search(text="match", limit=2)
        page2 = repo.search(text="match", limit=2, offset=2)
        page3 = repo.search(text="match", limit=2, offset=4)
        assert [d.id for d in page1] == ids[:2]
        assert [d.id for d in page2] == ids[2:4]
        assert [d.id for d in page3] == ids[4:]


def test_search_whitespace_only_text_returns_all(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        a = repo.create(_sample_create(title="A"))
        b = repo.create(_sample_create(title="B"))
        results = repo.search(text="   ")
        assert [d.id for d in results] == [a.id, b.id]


def test_search_returns_summary_not_full_document(db_path: Path) -> None:
    with connect() as conn:
        repo = DocumentRepository(conn)
        repo.create(_sample_create(title="hit", content="x" * 10_000))
        results = repo.search(text="hit")
        assert len(results) == 1
        assert isinstance(results[0], DocumentSummary)
        assert not hasattr(results[0], "content")
