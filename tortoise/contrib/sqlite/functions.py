import operator
from typing import Callable, cast
from tortoise.filters import (
    get_json_filter_operator,
    between_and,
    contains,
    ends_with,
    insensitive_contains,
    insensitive_ends_with,
    insensitive_exact,
    insensitive_starts_with,
    is_in,
    is_null,
    not_equal,
    not_in,
    not_null,
    starts_with,
)
from pypika_tortoise.terms import Criterion, Term, BasicCriterion, ValueWrapper
from pypika_tortoise.enums import JSONOperators
from pypika_tortoise.terms import Function


class Random(Function):
    """
    Generate random number.

    :samp:`Random()`
    """

    def __init__(self, alias=None) -> None:
        super().__init__("RANDOM", alias=alias)


operator_keywords: dict[str, Callable[..., Criterion]] = {
    "not": not_equal,
    "isnull": is_null,
    "not_isnull": not_null,
    "in": is_in,
    "not_in": not_in,
    "gte": cast(Callable[..., Criterion], operator.ge),
    "gt": cast(Callable[..., Criterion], operator.gt),
    "lte": cast(Callable[..., Criterion], operator.le),
    "lt": cast(Callable[..., Criterion], operator.lt),
    "range": between_and,
    "contains": contains,
    "startswith": starts_with,
    "endswith": ends_with,
    "iexact": insensitive_exact,
    "icontains": insensitive_contains,
    "istartswith": insensitive_starts_with,
    "iendswith": insensitive_ends_with,
}


def _get_json_path(key_parts: list[str | int]) -> Criterion:
    """
    Recursively build a JSON path from a list of key parts, e.g. ['a', 'b', 'c'] -> 'a'->'b'->>'c'
    """
    if len(key_parts) == 2:
        left = key_parts.pop(0)
        right = key_parts.pop(0)
        return BasicCriterion(JSONOperators.GET_TEXT_VALUE, ValueWrapper(left), ValueWrapper(right))

    left = key_parts.pop(0)
    return BasicCriterion(
        JSONOperators.GET_JSON_VALUE, ValueWrapper(left), _get_json_path(key_parts)
    )


def sqlite_json_filter(field: Term, value: dict) -> Criterion:
    key_parts, filter_value, operator_ = get_json_filter_operator(value, operator_keywords)

    if len(key_parts) == 1:
        json_path = ValueWrapper(f"$.{key_parts.pop(0)}")
        json_operator = JSONOperators.GET_TEXT_VALUE
    else:
        json_path = _get_json_path(key_parts)
        json_operator = JSONOperators.GET_JSON_VALUE

    criterion = BasicCriterion(json_operator, field, json_path)
    return operator_(criterion, filter_value)
