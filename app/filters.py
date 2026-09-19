"""Declarative payload filters for subscriptions.

A filter is a JSON object tree describing a predicate evaluated against an
event payload:

* ``{"op": "eq", "path": "a.b", "value": 42}``
* ``{"op": "in", "path": "type", "values": ["x", "y"]}``
* ``{"op": "exists", "path": "user.id"}``
* ``{"op": "all", "filters": [<node>, ...]}``  (AND)
* ``{"op": "any", "filters": [<node>, ...]}``  (OR)
* ``{"op": "not", "filter": <node>}``          (negation)

Paths are dot-separated lookups into nested objects/arrays (all-digit
segments index arrays). ``validate_filter`` rejects unknown operators,
empty combinators, malformed paths and trees deeper than ``MAX_DEPTH``
nodes; ``evaluate_filter`` evaluates a validated tree (``None`` means
"no filter", i.e. every event matches).
"""

from __future__ import annotations

from typing import Any

MAX_DEPTH = 5
MAX_PATH_LEN = 1024

LEAF_OPS = frozenset({"eq", "in", "exists"})
COMPOSITE_OPS = frozenset({"all", "any", "not"})
KNOWN_OPS = LEAF_OPS | COMPOSITE_OPS


class FilterError(ValueError):
    """Raised when a filter tree fails declarative validation."""


# Sentinel for "the path does not exist in the payload" (distinct from an
# explicit JSON null, which is a present value).
_MISSING = object()


# ------------------------------------------------------------- validation

def validate_filter(node: Any, depth: int = 1) -> dict[str, Any]:
    """Validate a filter tree, returning it unchanged on success."""
    if depth > MAX_DEPTH:
        raise FilterError(
            f"filter nesting must not exceed {MAX_DEPTH} levels"
        )
    if not isinstance(node, dict):
        raise FilterError("filter node must be a JSON object")

    op = node.get("op")
    if not isinstance(op, str) or op not in KNOWN_OPS:
        raise FilterError(f"unknown filter operator: {op!r}")

    if op == "eq":
        _require_path(node)
        if "value" not in node:
            raise FilterError("'eq' filter requires a 'value' key")
        _reject_extra(node, {"op", "path", "value"})
    elif op == "in":
        _require_path(node)
        if not isinstance(node.get("values"), list):
            raise FilterError("'in' filter requires a 'values' list")
        _reject_extra(node, {"op", "path", "values"})
    elif op == "exists":
        _require_path(node)
        _reject_extra(node, {"op", "path"})
    elif op in ("all", "any"):
        children = node.get("filters")
        if not isinstance(children, list) or not children:
            raise FilterError(
                f"'{op}' filter requires a non-empty 'filters' list"
            )
        _reject_extra(node, {"op", "filters"})
        for child in children:
            validate_filter(child, depth + 1)
    else:  # op == "not"
        if "filter" not in node:
            raise FilterError("'not' filter requires a nested 'filter' key")
        _reject_extra(node, {"op", "filter"})
        validate_filter(node["filter"], depth + 1)

    return node


def _require_path(node: dict[str, Any]) -> None:
    path = node.get("path")
    op = node.get("op")
    if not isinstance(path, str) or not path:
        raise FilterError(f"'{op}' filter requires a non-empty 'path'")
    if len(path) > MAX_PATH_LEN:
        raise FilterError(f"'path' must be at most {MAX_PATH_LEN} characters")
    if any(segment == "" for segment in path.split(".")):
        raise FilterError(f"invalid path {path!r}: empty segment")


def _reject_extra(node: dict[str, Any], allowed: set[str]) -> None:
    extra = set(node) - allowed
    if extra:
        raise FilterError(
            f"unexpected keys for {node.get('op')!r}: {sorted(extra)}"
        )


# ------------------------------------------------------------- evaluation

def evaluate_filter(node: dict[str, Any] | None, payload: Any) -> bool:
    """Return True when ``payload`` passes the filter.

    ``None`` represents an unfiltered subscription and matches everything,
    including subscriptions created before filters existed.
    """
    if node is None:
        return True

    op = node["op"]
    if op == "eq":
        actual = _resolve(payload, node["path"])
        return actual is not _MISSING and _json_equal(actual, node["value"])
    if op == "in":
        actual = _resolve(payload, node["path"])
        return actual is not _MISSING and any(
            _json_equal(actual, candidate) for candidate in node["values"]
        )
    if op == "exists":
        return _resolve(payload, node["path"]) is not _MISSING
    if op == "all":
        return all(evaluate_filter(child, payload) for child in node["filters"])
    if op == "any":
        return any(evaluate_filter(child, payload) for child in node["filters"])
    # op == "not"
    return not evaluate_filter(node["filter"], payload)


def _resolve(payload: Any, path: str) -> Any:
    current = payload
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return _MISSING
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index >= len(current):
                return _MISSING
            current = current[index]
        else:
            return _MISSING
    return current


def _json_equal(left: Any, right: Any) -> bool:
    # JSON booleans are not numbers: True must not equal 1 (Python says ==).
    if isinstance(left, bool) or isinstance(right, bool):
        return (
            isinstance(left, bool)
            and isinstance(right, bool)
            and bool(left) == bool(right)
        )
    return left == right
