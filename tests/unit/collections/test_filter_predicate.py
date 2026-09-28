"""Тесты FilterPredicate/FilterSpec — все операторы, комбинирование, граничные случаи.

Цель: 100% покрытие логики фильтрации.
"""

from __future__ import annotations

import pytest

from pentool.collections.filter_predicate import (
    FilterOp,
    FilterPredicate,
    FilterSpec,
)


# ─── FilterOp.EQ ─────────────────────────────────────────────────────────────


class TestEq:
    def test_match(self):
        p = FilterPredicate("method", FilterOp.EQ, "GET")
        assert p.apply({"method": "GET"})

    def test_no_match(self):
        p = FilterPredicate("method", FilterOp.EQ, "GET")
        assert not p.apply({"method": "POST"})

    def test_none_field(self):
        p = FilterPredicate("method", FilterOp.EQ, "GET")
        assert not p.apply({})

    def test_sql(self):
        p = FilterPredicate("method", FilterOp.EQ, "GET")
        clause, params = p.to_sql()
        assert clause == "method = ?"
        assert params == ["GET"]


# ─── FilterOp.NEQ ────────────────────────────────────────────────────────────


class TestNeq:
    def test_match(self):
        p = FilterPredicate("status_code", FilterOp.NEQ, 404)
        assert p.apply({"status_code": 200})

    def test_no_match(self):
        p = FilterPredicate("status_code", FilterOp.NEQ, 404)
        assert not p.apply({"status_code": 404})

    def test_sql(self):
        p = FilterPredicate("status_code", FilterOp.NEQ, 404)
        clause, _ = p.to_sql()
        assert "!=" in clause


# ─── FilterOp.GT / GTE / LT / LTE ───────────────────────────────────────────


class TestGt:
    def test_match(self):
        assert FilterPredicate("length", FilterOp.GT, 100).apply({"length": 101})
        assert not FilterPredicate("length", FilterOp.GT, 100).apply({"length": 100})
        assert not FilterPredicate("length", FilterOp.GT, 100).apply({"length": 99})

    def test_sql(self):
        clause, params = FilterPredicate("length", FilterOp.GT, 100).to_sql()
        assert ">" in clause
        assert params == [100]


class TestGte:
    def test_match(self):
        assert FilterPredicate("length", FilterOp.GTE, 100).apply({"length": 100})
        assert not FilterPredicate("length", FilterOp.GTE, 100).apply({"length": 99})

    def test_sql(self):
        clause, _ = FilterPredicate("length", FilterOp.GTE, 100).to_sql()
        assert ">=" in clause


class TestLt:
    def test_match(self):
        assert FilterPredicate("length", FilterOp.LT, 100).apply({"length": 99})
        assert not FilterPredicate("length", FilterOp.LT, 100).apply({"length": 100})

    def test_sql(self):
        clause, _ = FilterPredicate("length", FilterOp.LT, 100).to_sql()
        assert "<" in clause and ">=" not in clause


class TestLte:
    def test_match(self):
        assert FilterPredicate("length", FilterOp.LTE, 100).apply({"length": 100})
        assert not FilterPredicate("length", FilterOp.LTE, 100).apply({"length": 101})

    def test_sql(self):
        clause, _ = FilterPredicate("length", FilterOp.LTE, 100).to_sql()
        assert "<=" in clause


# ─── FilterOp.BETWEEN ────────────────────────────────────────────────────────


class TestBetween:
    def test_match(self):
        p = FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299))
        assert p.apply({"status_code": 200})
        assert p.apply({"status_code": 250})
        assert p.apply({"status_code": 299})
        assert not p.apply({"status_code": 199})
        assert not p.apply({"status_code": 300})
        assert not p.apply({"status_code": 100})

    def test_sql(self):
        p = FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299))
        clause, params = p.to_sql()
        assert "BETWEEN" in clause
        assert params == [200, 299]

    def test_none_field(self):
        assert not FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299)).apply({})


# ─── FilterOp.LIKE ───────────────────────────────────────────────────────────


class TestLike:
    def test_match_substring(self):
        p = FilterPredicate("host", FilterOp.LIKE, "example")
        assert p.apply({"host": "www.example.com"})
        assert p.apply({"host": "example.com"})
        assert p.apply({"host": "notexample.org"})  # substring
        assert not p.apply({"host": "exampl"})

    def test_case_insensitive(self):
        p = FilterPredicate("host", FilterOp.LIKE, "Example")
        assert p.apply({"host": "www.example.com"})

    def test_sql(self):
        p = FilterPredicate("host", FilterOp.LIKE, "example")
        clause, params = p.to_sql()
        assert "LIKE" in clause
        assert params == ["%example%"]

    def test_empty_host(self):
        assert not FilterPredicate("host", FilterOp.LIKE, "example").apply({})


# ─── FilterOp.STARTS ─────────────────────────────────────────────────────────


class TestStarts:
    def test_match(self):
        p = FilterPredicate("host", FilterOp.STARTS, "api")
        assert p.apply({"host": "api.example.com"})
        assert not p.apply({"host": "www.api.com"})

    def test_sql(self):
        p = FilterPredicate("host", FilterOp.STARTS, "api")
        clause, params = p.to_sql()
        assert "LIKE" in clause
        assert params == ["api%"]


# ─── FilterOp.IN ─────────────────────────────────────────────────────────────


class TestIn:
    def test_match(self):
        p = FilterPredicate("method", FilterOp.IN, ["GET", "POST"])
        assert p.apply({"method": "GET"})
        assert p.apply({"method": "POST"})
        assert not p.apply({"method": "PUT"})

    def test_sql(self):
        p = FilterPredicate("method", FilterOp.IN, ["GET", "POST"])
        clause, params = p.to_sql()
        assert "IN" in clause
        assert params == ["GET", "POST"]

    def test_hosts_special(self):
        """field='hosts' + IN разворачивается в OR для портов."""
        p = FilterPredicate("hosts", FilterOp.IN, ["example.com", "test.org"])
        clause, params = p.to_sql()
        assert clause == (
            "((host = ? OR host LIKE ?) OR (host = ? OR host LIKE ?))"
        )
        assert params == [
            "example.com", "example.com:%",
            "test.org", "test.org:%",
        ]

    def test_single_value(self):
        """IN с одним значением."""
        p = FilterPredicate("method", FilterOp.IN, "GET")
        clause, params = p.to_sql()
        assert params == ["GET"]


# ─── FilterOp.REGEX ──────────────────────────────────────────────────────────


class TestRegex:
    def test_match(self):
        p = FilterPredicate("payload", FilterOp.REGEX, r"admin")
        assert p.apply({"payload": "user=admin"})
        assert not p.apply({"payload": "user=guest"})

    def test_invalid_regex(self):
        p = FilterPredicate("payload", FilterOp.REGEX, r"[invalid")
        assert not p.apply({"payload": "test"})  # не падает

    def test_sql(self):
        p = FilterPredicate("payload", FilterOp.REGEX, r"admin")
        clause, _ = p.to_sql()
        assert "REGEXP" in clause


# ─── FilterOp.IS_NULL / NOT_NULL ─────────────────────────────────────────────


class TestIsNull:
    def test_missing_key(self):
        assert FilterPredicate("comment", FilterOp.IS_NULL, None).apply({})

    def test_empty_string(self):
        assert FilterPredicate("comment", FilterOp.IS_NULL, None).apply({"comment": ""})

    def test_not_null(self):
        assert not FilterPredicate("comment", FilterOp.IS_NULL, None).apply({"comment": "hello"})

    def test_sql(self):
        clause, params = FilterPredicate("comment", FilterOp.IS_NULL, None).to_sql()
        assert "IS NULL" in clause
        assert params == []


class TestNotNull:
    def test_match(self):
        assert FilterPredicate("comment", FilterOp.NOT_NULL, None).apply({"comment": "hello"})
        assert not FilterPredicate("comment", FilterOp.NOT_NULL, None).apply({"comment": ""})
        assert not FilterPredicate("comment", FilterOp.NOT_NULL, None).apply({})

    def test_sql(self):
        clause, params = FilterPredicate("comment", FilterOp.NOT_NULL, None).to_sql()
        assert "IS NOT NULL" in clause


# ─── FilterOp.HAS (tags) ─────────────────────────────────────────────────────


class TestHas:
    def test_match(self):
        p = FilterPredicate("tags", FilterOp.HAS, "important")
        assert p.apply({"tags": "important"})
        assert p.apply({"tags": "important,urgent"})
        assert p.apply({"tags": "urgent,important"})
        assert not p.apply({"tags": "unimportant"})

    def test_sql(self):
        p = FilterPredicate("tags", FilterOp.HAS, "important")
        clause, params = p.to_sql()
        assert "OR" in clause
        assert "important" in str(params)

    def test_no_tags(self):
        assert not FilterPredicate("tags", FilterOp.HAS, "important").apply({})


# ─── FilterOp.FTS ────────────────────────────────────────────────────────────


class TestFts:
    def test_sql_empty(self):
        p = FilterPredicate("fts", FilterOp.FTS, "test query")
        clause, params = p.to_sql()
        assert clause == ""
        assert params == []


# ─── FilterSpec — комбинирование ─────────────────────────────────────────────


class TestFilterSpecSql:
    def test_empty(self):
        s = FilterSpec()
        clause, params = s.to_sql()
        assert clause == ""
        assert params == []

    def test_and_combines_predicates(self):
        s = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "example"),
            FilterPredicate("method", FilterOp.IN, ["GET"]),
        ])
        clause, params = s.to_sql()
        assert "AND" in clause
        assert "host LIKE ?" in clause
        assert "method IN" in clause

    def test_or_logic(self):
        s = FilterSpec(
            predicates=[
                FilterPredicate("status_code", FilterOp.EQ, 200),
                FilterPredicate("status_code", FilterOp.EQ, 404),
            ],
            logic="OR",
        )
        clause, _ = s.to_sql()
        assert "OR" in clause

    def test_fts_excluded_from_sql(self):
        s = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "example"),
            FilterPredicate("fts", FilterOp.FTS, "search term"),
        ])
        clause, _ = s.to_sql()
        assert "fts" not in clause
        assert s.fts_query == "search term"

    def test_no_predicates(self):
        s = FilterSpec(predicates=[])
        assert s.is_empty

    def test_is_empty(self):
        assert not FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "x"),
        ]).is_empty


class TestFilterSpecApply:
    def test_empty(self):
        rows = [{"host": "a"}, {"host": "b"}]
        assert FilterSpec().apply(rows) == rows

    def test_and_filter(self):
        s = FilterSpec(predicates=[
            FilterPredicate("method", FilterOp.EQ, "GET"),
            FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299)),
        ])
        rows = [
            {"method": "GET", "status_code": 200},
            {"method": "POST", "status_code": 200},
            {"method": "GET", "status_code": 404},
        ]
        result = s.apply(rows)
        assert len(result) == 1
        assert result[0]["method"] == "GET"

    def test_or_filter(self):
        s = FilterSpec(
            predicates=[
                FilterPredicate("method", FilterOp.EQ, "GET"),
                FilterPredicate("method", FilterOp.EQ, "POST"),
            ],
            logic="OR",
        )
        rows = [
            {"method": "GET"},
            {"method": "POST"},
            {"method": "PUT"},
        ]
        assert len(s.apply(rows)) == 2

    def test_unknown_operator(self):
        s = FilterSpec(predicates=[
            FilterPredicate("x", "unknown_op", "v"),  # type: ignore[arg-type]
        ])
        assert s.apply([{"x": "v"}]) == []  # apply returns False for unknown op

    def test_empty_predicates(self):
        assert FilterSpec(predicates=[]).apply([{"a": 1}]) == [{"a": 1}]

    def test_none_value_applied(self):
        """Проверка что apply не падает на None."""
        assert not FilterPredicate("host", FilterOp.EQ, "x").apply({"host": None})


# ─── FilterSpec — сериализация ──────────────────────────────────────────────


class TestFilterSpecSerialization:
    def test_roundtrip(self):
        spec = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "example"),
            FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299)),
            FilterPredicate("method", FilterOp.IN, ["GET", "POST"]),
        ])
        d = spec.to_dict()
        spec2 = FilterSpec.from_dict(d)
        assert len(spec2.predicates) == 3
        assert spec2.logic == "AND"
        # SQL должен совпадать
        assert spec.to_sql() == spec2.to_sql()

    def test_empty_to_dict(self):
        d = FilterSpec().to_dict()
        assert d == {"logic": "AND", "predicates": []}

    def test_empty_from_dict(self):
        spec = FilterSpec.from_dict({"logic": "AND", "predicates": []})
        assert spec.is_empty


# ─── Граничные случаи ────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_none_field_in_row(self):
        """Поле есть, но значение None — apply должен вернуть False."""
        p = FilterPredicate("status_code", FilterOp.EQ, 200)
        assert not p.apply({"status_code": None})

    def test_wrong_type_in_row(self):
        """Поле есть, но тип не тот — EQ сравнивает, может вернуть False."""
        p = FilterPredicate("status_code", FilterOp.EQ, 200)
        assert not p.apply({"status_code": "200"})  # int vs str

    def test_like_with_none(self):
        assert not FilterPredicate("host", FilterOp.LIKE, "x").apply({"host": None})

    def test_between_outside(self):
        p = FilterPredicate("x", FilterOp.BETWEEN, (10, 20))
        assert not p.apply({"x": 5})
        assert not p.apply({"x": 25})


# ─── Комбинирование 5+ фильтров (симуляция реального сценария) ──────────────


class TestFiveFiltersAnd:
    """Сценарий: пользователь применил Host + Method + Status + Search + Scope.

    AND-логика — все условия должны выполниться одновременно.
    """

    def test_all_match(self):
        s = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "example"),
            FilterPredicate("method", FilterOp.IN, ["GET"]),
            FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299)),
            FilterPredicate("is_websocket", FilterOp.EQ, False),
        ])
        row = {
            "host": "www.example.com",
            "method": "GET",
            "status_code": 200,
            "is_websocket": False,
        }
        assert all(p.apply(row) for p in s.predicates)

    def test_no_match_because_host(self):
        s = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "example"),
            FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299)),
        ])
        row = {"host": "other.com", "status_code": 200}
        assert not all(p.apply(row) for p in s.predicates)

    def test_sql_generation_for_five(self):
        s = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "example"),
            FilterPredicate("method", FilterOp.IN, ["GET"]),
            FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299)),
            FilterPredicate("is_websocket", FilterOp.EQ, False),
        ])
        clause, params = s.to_sql()
        # BETWEEN содержит " AND " внутри — считаем по кол-ву предикатов
        assert clause.startswith("WHERE")
        assert "host LIKE" in clause
        assert "method IN" in clause
        assert "status_code BETWEEN" in clause
        assert "is_websocket" in clause
        assert len(params) == 5


class TestScopeAndCommentsTogether:
    """Сценарий: scope_only=True + has_comment=True.

    Ожидается: строки, которые входят в scope И имеют комментарий.
    На уровне apply: host в списке И comment не пустой.
    """

    def test_scope_sql(self):
        """scope_only → разворачивается в OR с портами. Проверяем SQL."""
        s = FilterSpec(predicates=[
            FilterPredicate("hosts", FilterOp.IN, ["example.com", "test.org"]),
            FilterPredicate("comment", FilterOp.NOT_NULL, None),
        ])
        clause, params = s.to_sql()
        assert "(host = ? OR host LIKE ?)" in clause
        assert "comment IS NOT NULL" in clause
        assert "example.com" in str(params)
        assert "test.org" in str(params)

    def test_scope_in_apply_treats_as_regular_in(self):
        """apply для 'hosts' работает как обычный IN (сравнение точное)."""
        # Это не SQL-ветка — in-memory apply не обрабатывает hosts специально
        p = FilterPredicate("hosts", FilterOp.IN, ["example.com"])
        assert p.apply({"hosts": "example.com"})
        assert not p.apply({"hosts": "other.com"})

    def test_comment_not_null_apply(self):
        assert FilterPredicate("comment", FilterOp.NOT_NULL, None).apply(
            {"comment": "fixed"}
        )
        assert not FilterPredicate("comment", FilterOp.NOT_NULL, None).apply(
            {"comment": ""}
        )


# ─── FTS комбинации ─────────────────────────────────────────────────────────


class TestFtsCombination:
    def test_fts_with_other_predicates(self):
        """FTS исключается из SQL, но доступен через .fts_query."""
        s = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "example"),
            FilterPredicate("fts", FilterOp.FTS, "login admin"),
        ])
        sql_clause, sql_params = s.to_sql()
        assert "host LIKE" in sql_clause
        assert s.fts_query == "login admin"
        # SQL содержит только host, FTS отдельно
        assert len(sql_params) == 1

    def test_only_fts(self):
        s = FilterSpec(predicates=[
            FilterPredicate("fts", FilterOp.FTS, "search term"),
        ])
        clause, params = s.to_sql()
        assert clause == ""
        assert params == []
        assert s.fts_query == "search term"