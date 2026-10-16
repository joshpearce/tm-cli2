"""Unit tests for CLI option helpers (sort, field projection, id stringification)."""

from __future__ import annotations

from types import SimpleNamespace

from tm_cli.cli._options import apply_sort, parse_json_fields
from tm_cli.cli._output import _stringify_ids, project_fields


def test_apply_sort_default_id_ascending() -> None:
    rows = [SimpleNamespace(id=3), SimpleNamespace(id=1), SimpleNamespace(id=2)]
    assert [r.id for r in apply_sort(rows, sort_field="id", order="asc")] == [1, 2, 3]


def test_apply_sort_descending() -> None:
    rows = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    assert [r.id for r in apply_sort(rows, sort_field="id", order="desc")] == [2, 1]


def test_apply_sort_missing_field_goes_last() -> None:
    rows = [
        SimpleNamespace(name="b"),
        SimpleNamespace(other="x"),
        SimpleNamespace(name="a"),
    ]
    sorted_rows = apply_sort(rows, sort_field="name", order="asc")
    names = [getattr(r, "name", None) for r in sorted_rows]
    assert names == ["a", "b", None]


def test_parse_json_fields_none() -> None:
    assert parse_json_fields(None) is None


def test_parse_json_fields_strips_and_splits() -> None:
    assert parse_json_fields("id, name , author") == ["id", "name", "author"]


def test_project_fields_dict() -> None:
    assert project_fields({"a": 1, "b": 2, "c": 3}, ["a", "c"]) == {"a": 1, "c": 3}


def test_project_fields_list() -> None:
    rows = [{"a": 1, "b": 2}, {"a": 10, "b": 20}]
    assert project_fields(rows, ["a"]) == [{"a": 1}, {"a": 10}]


def test_project_fields_missing_silently_dropped() -> None:
    assert project_fields({"a": 1}, ["a", "missing"]) == {"a": 1}


# ---------------------------------------------------------------------------
# _stringify_ids — plural *_ids fields
# ---------------------------------------------------------------------------


def test_stringify_ids_empty_list_unchanged() -> None:
    assert _stringify_ids({"node_ids": []}) == {"node_ids": []}


def test_stringify_ids_int_elements_become_strings() -> None:
    assert _stringify_ids({"node_ids": [5, 10]}) == {"node_ids": ["5", "10"]}


def test_stringify_ids_bool_not_stringified() -> None:
    # isinstance(True, int) is True, but booleans must be left as-is.
    result = _stringify_ids({"node_ids": [True]})
    # True should NOT be converted to "True"; it falls through to _stringify_ids(True)
    # which returns the scalar unchanged.
    assert result == {"node_ids": [True]}


def test_stringify_ids_nested_dict_element_recurses() -> None:
    # Non-int elements fall through to recursive _stringify_ids call.
    result = _stringify_ids({"node_ids": [{"id": 5}]})
    assert result == {"node_ids": [{"id": "5"}]}


def test_stringify_ids_scalar_id_field_unchanged() -> None:
    # Existing scalar _id behaviour: {"id": 5} -> {"id": "5"}
    assert _stringify_ids({"id": 5}) == {"id": "5"}


def test_stringify_ids_scalar_id_suffix_unchanged() -> None:
    assert _stringify_ids({"node_id": 7}) == {"node_id": "7"}


def test_stringify_ids_multiple_ids_fields_all_stringified() -> None:
    payload = {
        "node_ids": [1, 2],
        "container_ids": [],
        "flow_ids": [3],
        "data_item_ids": [4, 5],
    }
    result = _stringify_ids(payload)
    assert result == {
        "node_ids": ["1", "2"],
        "container_ids": [],
        "flow_ids": ["3"],
        "data_item_ids": ["4", "5"],
    }
