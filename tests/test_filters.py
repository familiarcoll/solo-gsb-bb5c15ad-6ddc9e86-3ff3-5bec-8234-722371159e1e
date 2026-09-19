"""Unit tests for the declarative filter DSL (validation + evaluation)."""

from __future__ import annotations

import pytest

from app.filters import FilterError, evaluate_filter, validate_filter


def v(node):
    return validate_filter(node)


@pytest.mark.parametrize(
    "node",
    [
        {"op": "eq", "path": "a", "value": 1},
        {"op": "in", "path": "a", "values": []},
        {"op": "exists", "path": "a"},
        {"op": "all", "filters": [{"op": "exists", "path": "a"}]},
        {"op": "any", "filters": [{"op": "exists", "path": "a"}]},
        {"op": "not", "filter": {"op": "exists", "path": "a"}},
    ],
)
def test_valid_operators_accepted(node):
    assert v(node) is node


def test_eq_matches_nested_and_array_paths():
    f = v({"op": "eq", "path": "order.items.0.sku", "value": "X1"})
    assert evaluate_filter(f, {"order": {"items": [{"sku": "X1"}]}})
    assert not evaluate_filter(f, {"order": {"items": [{"sku": "X2"}]}})
    assert not evaluate_filter(f, {"order": {"items": []}})
    assert not evaluate_filter(f, None)


def test_eq_requires_present_path_null_is_a_value():
    f = v({"op": "eq", "path": "a", "value": None})
    assert evaluate_filter(f, {"a": None})
    assert not evaluate_filter(f, {})


def test_bool_not_equal_to_int():
    f = v({"op": "eq", "path": "a", "value": 1})
    assert not evaluate_filter(f, {"a": True})
    assert evaluate_filter(f, {"a": 1})


def test_in_matches_any_candidate():
    f = v({"op": "in", "path": "type", "values": ["paid", "shipped"]})
    assert evaluate_filter(f, {"type": "shipped"})
    assert not evaluate_filter(f, {"type": "cancelled"})
    assert not evaluate_filter(f, {})


def test_exists_semantics():
    f = v({"op": "exists", "path": "user.email"})
    assert evaluate_filter(f, {"user": {"email": None}})
    assert not evaluate_filter(f, {"user": {}})
    assert not evaluate_filter(f, {})
    assert not evaluate_filter(f, {"user": []})


def test_all_any_not_composition():
    payload = {"type": "x", "n": 5, "flag": True}
    all_f = v(
        {
            "op": "all",
            "filters": [
                {"op": "eq", "path": "type", "value": "x"},
                {"op": "in", "path": "n", "values": [4, 5]},
            ],
        }
    )
    assert evaluate_filter(all_f, payload)
    assert not evaluate_filter(all_f, {"type": "x", "n": 9})

    any_f = v(
        {
            "op": "any",
            "filters": [
                {"op": "eq", "path": "type", "value": "z"},
                {"op": "exists", "path": "flag"},
            ],
        }
    )
    assert evaluate_filter(any_f, payload)

    not_f = v({"op": "not", "filter": {"op": "exists", "path": "ghost"}})
    assert evaluate_filter(not_f, payload)
    assert not evaluate_filter(not_f, {"ghost": 1})


def test_none_filter_matches_everything():
    assert evaluate_filter(None, {"a": 1})
    assert evaluate_filter(None, None)
    assert evaluate_filter(None, {})


def test_exactly_five_levels_allowed_sixth_rejected():
    node = {"op": "exists", "path": "a"}
    for _ in range(4):
        node = {"op": "not", "filter": node}
    v(node)  # depth 5: fine

    too_deep = {"op": "not", "filter": node}  # depth 6
    with pytest.raises(FilterError, match="nesting"):
        v(too_deep)


@pytest.mark.parametrize(
    "node",
    [
        {"op": "regex", "path": "a"},
        {"op": "EQ", "path": "a", "value": 1},
        {"op": 42},
        {"path": "a", "value": 1},
        "not a node",
    ],
)
def test_unknown_operator_rejected(node):
    with pytest.raises(FilterError, match="operator"):
        v(node)


def test_empty_combinators_rejected():
    with pytest.raises(FilterError, match="non-empty"):
        v({"op": "all", "filters": []})
    with pytest.raises(FilterError, match="non-empty"):
        v({"op": "any", "filters": []})


@pytest.mark.parametrize(
    "node",
    [
        {"op": "all", "filters": "nope"},
        {"op": "not"},
        {"op": "not", "filter": "nope"},
        {"op": "eq", "path": "a"},
        {"op": "in", "path": "a"},
        {"op": "in", "path": "a", "values": "x"},
        {"op": "exists"},
        {"op": "exists", "path": ""},
        {"op": "exists", "path": "a..b"},
        {"op": "exists", "path": "a."},
        {"op": "eq", "path": "a", "value": 1, "extra": 2},
    ],
)
def test_malformed_nodes_rejected(node):
    with pytest.raises(FilterError):
        v(node)
