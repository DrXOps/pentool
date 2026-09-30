"""Тесты HttpStorage._build_where — FilterSpec → SQL WHERE.

Проверяет что _build_where корректно транслирует FilterSpec в SQL.
"""

from __future__ import annotations

from pentool.collections.filter_predicate import FilterOp, FilterPredicate, FilterSpec
from pentool.storage.http_storage import HttpStorage


def _build_where(spec: FilterSpec | None) -> tuple[str, list]:
    """Вызывает _build_where через HttpStorage."""
    return HttpStorage._build_where(None, spec)


class TestBuildWhereEmpty:
    def test_none(self):
        clause, params = _build_where(None)
        assert clause == ""
        assert params == []

    def test_empty_spec(self):
        clause, params = _build_where(FilterSpec())
        assert clause == ""
        assert params == []


class TestBuildWhereSingle:
    def test_host_like(self):
        s = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "example"),
        ])
        clause, params = _build_where(s)
        assert "host LIKE ?" in clause
        assert params == ["%example%"]

    def test_method_in(self):
        s = FilterSpec(predicates=[
            FilterPredicate("method", FilterOp.IN, ["GET", "POST"]),
        ])
        clause, params = _build_where(s)
        assert "method IN (?,?)" in clause
        assert params == ["GET", "POST"]

    def test_status_between(self):
        s = FilterSpec(predicates=[
            FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299)),
        ])
        clause, params = _build_where(s)
        assert "BETWEEN ? AND ?" in clause
        assert params == [200, 299]

    def test_color_eq(self):
        s = FilterSpec(predicates=[
            FilterPredicate("color", FilterOp.EQ, "red"),
        ])
        clause, params = _build_where(s)
        assert "color = ?" in clause
        assert params == ["red"]

    def test_is_websocket_false(self):
        s = FilterSpec(predicates=[
            FilterPredicate("is_websocket", FilterOp.EQ, False),
        ])
        clause, params = _build_where(s)
        assert "is_websocket = ?" in clause
        assert params == [False]

    def test_comment_not_null(self):
        s = FilterSpec(predicates=[
            FilterPredicate("comment", FilterOp.NOT_NULL, None),
        ])
        clause, params = _build_where(s)
        assert "COALESCE(comment, '') != ''" in clause
        assert params == []

    def test_has_params_true(self):
        s = FilterSpec(predicates=[
            FilterPredicate("has_params", FilterOp.EQ, True),
        ])
        clause, params = _build_where(s)
        assert "has_params = ?" in clause
        assert params == [1]

    def test_hosts_in_with_ports(self):
        """scope — разворачивается в OR с портами."""
        s = FilterSpec(predicates=[
            FilterPredicate("hosts", FilterOp.IN, ["example.com"]),
        ])
        clause, params = _build_where(s)
        assert "host = ? OR host LIKE ?" in clause
        assert "example.com" in params
        assert "example.com:%" in params

    def test_mime_type_like(self):
        s = FilterSpec(predicates=[
            FilterPredicate("mime_type", FilterOp.LIKE, "text"),
        ])
        clause, params = _build_where(s)
        assert "mime_type LIKE ?" in clause
        assert params == ["%text%"]


class TestBuildWhereCombined:
    """Полный сценарий: 5 фильтров одновременно."""

    def test_http_history_default(self):
        """Host + Method + Status + Scope — симуляция HTTP History."""
        s = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "example"),
            FilterPredicate("method", FilterOp.IN, ["GET"]),
            FilterPredicate("status_code", FilterOp.BETWEEN, (200, 299)),
            FilterPredicate("is_websocket", FilterOp.EQ, False),
        ])
        clause, params = _build_where(s)
        assert clause.count("?") == 5  # LIKE + IN + BETWEEN(2) + EQ
        assert "host LIKE" in clause
        assert "method IN" in clause
        assert "status_code BETWEEN" in clause
        assert "is_websocket" in clause

    def test_scope_and_comment(self):
        """Scope + Comments — два дополнительных фильтра."""
        s = FilterSpec(predicates=[
            FilterPredicate("hosts", FilterOp.IN, ["example.com", "test.org"]),
            FilterPredicate("comment", FilterOp.NOT_NULL, None),
            FilterPredicate("is_websocket", FilterOp.EQ, False),
        ])
        clause, params = _build_where(s)
        assert "(host = ? OR host LIKE ?)" in clause
        assert "COALESCE(comment, '') != ''" in clause
        assert "is_websocket = ?" in clause
        # NOT_NULL — без params (COALESCE), остальные 4 params: 2 scope host/ LIKE + websocket
        # + 2 для scope (host = ?, host LIKE ? для каждого из 2 хостов)
        assert len(params) == 5

    def test_color_and_has_params(self):
        s = FilterSpec(predicates=[
            FilterPredicate("color", FilterOp.EQ, "red"),
            FilterPredicate("has_params", FilterOp.EQ, True),
        ])
        clause, _ = _build_where(s)
        assert "color = ?" in clause
        assert "has_params = ?" in clause