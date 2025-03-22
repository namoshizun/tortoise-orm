import operator
import datetime
import sqlite3
from decimal import Decimal
from typing import Callable, cast

from tortoise import Model
from tortoise.backends.base.executor import BaseExecutor
from tortoise.contrib.sqlite.regex import (
    insensitive_posix_sqlite_regexp,
    posix_sqlite_regexp,
)
from tortoise.fields import BigIntField, IntField, SmallIntField
from tortoise.filters import (
    insensitive_posix_regex,
    json_filter,
    posix_regex,
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


# Conversion for the cases where it's hard to know the
# related field, e.g. in raw queries, math or annotations.
sqlite3.register_adapter(Decimal, str)
sqlite3.register_adapter(datetime.date, lambda val: val.isoformat())
sqlite3.register_adapter(datetime.datetime, lambda val: val.isoformat(" "))


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


class SqliteExecutor(BaseExecutor):
    EXPLAIN_PREFIX = "EXPLAIN QUERY PLAN"
    DB_NATIVE = {bytes, str, int, float}
    FILTER_FUNC_OVERRIDE = {
        posix_regex: posix_sqlite_regexp,
        insensitive_posix_regex: insensitive_posix_sqlite_regexp,
        json_filter: sqlite_json_filter,
    }

    async def _process_insert_result(self, instance: Model, results: int) -> None:
        pk_field_object = self.model._meta.pk
        if (
            isinstance(pk_field_object, (SmallIntField, IntField, BigIntField))
            and pk_field_object.generated
        ):
            instance.pk = results

        # SQLite can only generate a single ROWID
        #   so if any other primary key, it won't generate what we want.
