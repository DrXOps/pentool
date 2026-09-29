"""Unit tests for Proxy HTTP-history filter — FilterSpec-based composition."""

from __future__ import annotations

from pentool.collections.filter_predicate import FilterOp, FilterPredicate, FilterSpec


class TestFilterSpecComposition:
    """Build_history_filters is removed — FilterSpec composition is done directly
    in ProxyScreen._reload_table by appending FilterPredicate to the spec."""

    def test_add_comment_predicate_to_spec(self):
        spec = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "example.com"),
        ])
        spec.predicates.append(FilterPredicate("comment", FilterOp.NOT_NULL, None))
        assert len(spec.predicates) == 2

    def test_empty_spec_with_comment(self):
        spec = FilterSpec(predicates=[
            FilterPredicate("comment", FilterOp.NOT_NULL, None),
        ])
        assert not spec.is_empty
        where, params = spec.to_sql()
        assert "NOT_NULL" not in where
        assert "COALESCE(comment, '') != ''" in where

    def test_fts_not_in_sql(self):
        spec = FilterSpec(predicates=[
            FilterPredicate("host", FilterOp.LIKE, "x"),
            FilterPredicate("fts", FilterOp.FTS, "test query"),
        ])
        where, params = spec.to_sql()
        assert "LIKE" in where
        assert spec.fts_query == "test query"