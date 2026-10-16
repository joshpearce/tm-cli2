from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tm_cli.db import (
    DocumentCreate,
    DocumentRepository,
    Term,
    TermCreate,
    TermRepository,
    TermUpdate,
    connect,
)
from tm_cli.db import connection as connection_module


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tm.db"
    monkeypatch.setenv("TM_DB_PATH", str(path))
    monkeypatch.setattr(connection_module, "_initialized_paths", set())
    return path


def _sample_doc(**overrides: object) -> DocumentCreate:
    base: dict[str, object] = {
        "last_updated": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        "title": "Hello",
        "author": "alice",
        "content": "body",
    }
    base.update(overrides)
    return DocumentCreate(**base)  # type: ignore[arg-type]


def test_create_assigns_id_and_last_updated(db_path: Path) -> None:
    before = datetime.now(UTC)
    with connect() as conn:
        repo = TermRepository(conn)
        term = repo.create(TermCreate(term="throughput", definition="ops/sec"))
    after = datetime.now(UTC)

    assert term.id == 1
    assert term.term == "throughput"
    assert term.definition == "ops/sec"
    slack = timedelta(seconds=1)
    assert before - slack <= term.last_updated <= after + slack


def test_create_duplicate_term_raises(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        repo.create(TermCreate(term="throughput", definition="ops/sec"))
        with pytest.raises(sqlite3.IntegrityError):
            repo.create(TermCreate(term="throughput", definition="duplicate"))


def test_get_returns_none_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        assert repo.get(999) is None


def test_get_returns_created_term(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        created = repo.create(TermCreate(term="latency", definition="ms"))
        fetched = repo.get(created.id)
    assert fetched is not None
    assert fetched.model_dump() == created.model_dump()


def test_get_by_term_returns_match(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        created = repo.create(TermCreate(term="latency", definition="ms"))
        fetched = repo.get_by_term("latency")
    assert fetched is not None
    assert fetched.id == created.id


def test_get_by_term_returns_none_for_unknown(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        assert repo.get_by_term("nope") is None


def test_update_partial_fields_bumps_last_updated(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        original = repo.create(TermCreate(term="latency", definition="ms"))

    with connect() as conn:
        repo = TermRepository(conn)
        updated = repo.update(original.id, TermUpdate(definition="milliseconds"))

    assert updated is not None
    assert updated.term == original.term
    assert updated.definition == "milliseconds"
    assert updated.last_updated >= original.last_updated


def test_update_returns_none_for_unknown_id(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        assert repo.update(42, TermUpdate(definition="x")) is None


def test_update_with_empty_patch_still_bumps_last_updated(
    db_path: Path,
) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        original = repo.create(TermCreate(term="latency", definition="ms"))

    with connect() as conn:
        repo = TermRepository(conn)
        touched = repo.update(original.id, TermUpdate())

    assert touched is not None
    assert touched.last_updated >= original.last_updated
    assert touched.term == original.term
    assert touched.definition == original.definition


def test_delete_returns_true_then_false(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        created = repo.create(TermCreate(term="latency", definition="ms"))
        assert repo.delete(created.id) is True
        assert repo.delete(created.id) is False
        assert repo.get(created.id) is None


def test_list_orders_by_id_and_supports_limit_offset(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        a = repo.create(TermCreate(term="a", definition="A"))
        b = repo.create(TermCreate(term="b", definition="B"))
        c = repo.create(TermCreate(term="c", definition="C"))

        all_terms = repo.list()
        assert all(isinstance(t, Term) for t in all_terms)
        assert [t.id for t in all_terms] == [a.id, b.id, c.id]

        page = repo.list(limit=2, offset=1)
        assert [t.term for t in page] == ["b", "c"]

        tail = repo.list(offset=2)
        assert [t.term for t in tail] == ["c"]


def test_link_is_idempotent(db_path: Path) -> None:
    with connect() as conn:
        doc = DocumentRepository(conn).create(_sample_doc())
        terms = TermRepository(conn)
        term = terms.create(TermCreate(term="t", definition="d"))

        terms.link(doc.id, term.id)
        terms.link(doc.id, term.id)

        count = conn.execute(
            "SELECT COUNT(*) FROM document_terms WHERE document_id = ? AND term_id = ?",
            (doc.id, term.id),
        ).fetchone()[0]
        assert count == 1


def test_unlink_returns_true_then_false(db_path: Path) -> None:
    with connect() as conn:
        doc = DocumentRepository(conn).create(_sample_doc())
        terms = TermRepository(conn)
        term = terms.create(TermCreate(term="t", definition="d"))
        terms.link(doc.id, term.id)

        assert terms.unlink(doc.id, term.id) is True
        assert terms.unlink(doc.id, term.id) is False


def test_documents_for_term_and_terms_for_document(db_path: Path) -> None:
    with connect() as conn:
        docs = DocumentRepository(conn)
        d1 = docs.create(_sample_doc(title="D1"))
        d2 = docs.create(_sample_doc(title="D2"))
        d3 = docs.create(_sample_doc(title="D3"))

        terms = TermRepository(conn)
        t_alpha = terms.create(TermCreate(term="alpha", definition="a"))
        t_beta = terms.create(TermCreate(term="beta", definition="b"))

        terms.link(d1.id, t_alpha.id)
        terms.link(d2.id, t_alpha.id)
        terms.link(d2.id, t_beta.id)
        # d3 has no terms

        alpha_docs = terms.documents_for_term(t_alpha.id)
        assert [d.title for d in alpha_docs] == ["D1", "D2"]

        beta_docs = terms.documents_for_term(t_beta.id)
        assert [d.title for d in beta_docs] == ["D2"]

        d2_terms = terms.terms_for_document(d2.id)
        assert [t.term for t in d2_terms] == ["alpha", "beta"]

        d3_terms = terms.terms_for_document(d3.id)
        assert d3_terms == []


def test_deleting_document_cascades_links_but_keeps_terms(
    db_path: Path,
) -> None:
    with connect() as conn:
        doc = DocumentRepository(conn).create(_sample_doc())
        terms = TermRepository(conn)
        term = terms.create(TermCreate(term="t", definition="d"))
        terms.link(doc.id, term.id)

        assert DocumentRepository(conn).delete(doc.id) is True

        assert terms.documents_for_term(term.id) == []
        assert terms.get(term.id) is not None


def test_deleting_term_cascades_links_but_keeps_documents(
    db_path: Path,
) -> None:
    with connect() as conn:
        docs = DocumentRepository(conn)
        doc = docs.create(_sample_doc())
        terms = TermRepository(conn)
        term = terms.create(TermCreate(term="t", definition="d"))
        terms.link(doc.id, term.id)

        assert terms.delete(term.id) is True

        assert terms.terms_for_document(doc.id) == []
        assert docs.get(doc.id) is not None


def test_search_no_args_returns_all_in_id_order(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        a = repo.create(TermCreate(term="alpha", definition="A"))
        b = repo.create(TermCreate(term="beta", definition="B"))
        assert [t.id for t in repo.search()] == [a.id, b.id]


def test_search_matches_term_and_definition(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        repo.create(TermCreate(term="latency", definition="response time"))
        repo.create(TermCreate(term="throughput", definition="ops per second"))
        repo.create(TermCreate(term="cache", definition="latency reduction"))

        hits = repo.search(text="latency")
        assert {t.term for t in hits} == {"latency", "cache"}


def test_search_multi_token_ands(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        repo.create(TermCreate(term="cache hit", definition="fast"))
        repo.create(TermCreate(term="cache miss", definition="slow"))
        hits = repo.search(text="cache hit")
        assert [t.term for t in hits] == ["cache hit"]


def test_search_case_insensitive(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        created = repo.create(TermCreate(term="Latency", definition="MS"))
        hits = repo.search(text="LATENCY")
        assert [t.id for t in hits] == [created.id]


def test_search_escapes_wildcards(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        target = repo.create(TermCreate(term="50%_off", definition="discount"))
        decoy = repo.create(TermCreate(term="50xoff", definition="discount"))
        hits = repo.search(text="50%_")
        ids = {t.id for t in hits}
        assert target.id in ids
        assert decoy.id not in ids


def test_search_pagination(db_path: Path) -> None:
    with connect() as conn:
        repo = TermRepository(conn)
        ids = [
            repo.create(TermCreate(term=f"term{i}", definition="match")).id
            for i in range(4)
        ]
        page1 = repo.search(text="match", limit=2)
        page2 = repo.search(text="match", limit=2, offset=2)
        assert [t.id for t in page1] == ids[:2]
        assert [t.id for t in page2] == ids[2:]
