"""Unit-тесты для pentool/modules/comparer.py."""

from __future__ import annotations

import pytest
from pentool.modules.comparer import (
    CompareStats,
    DiffLine,
    DiffResult,
    compare,
    compare_bytes,
    compare_lines,
)


class TestCompareBasic:
    def test_identical_texts(self):
        result = compare("hello\nworld", "hello\nworld")
        assert result.stats.equal_lines == 2
        assert result.stats.added_lines == 0
        assert result.stats.removed_lines == 0
        assert result.stats.similarity == 1.0

    def test_empty_left(self):
        result = compare("", "hello\nworld")
        assert result.stats.added_lines == 2
        assert result.stats.removed_lines == 0

    def test_empty_right(self):
        result = compare("hello\nworld", "")
        assert result.stats.removed_lines == 2
        assert result.stats.added_lines == 0

    def test_both_empty(self):
        result = compare("", "")
        assert result.stats.total_left == 0
        assert result.stats.total_right == 0

    def test_added_lines(self):
        result = compare("line1\nline2", "line1\nline2\nline3")
        assert result.stats.added_lines >= 1

    def test_removed_lines(self):
        result = compare("line1\nline2\nline3", "line1\nline2")
        assert result.stats.removed_lines >= 1


class TestDiffLines:
    def test_equal_tag(self):
        result = compare("same\ntext", "same\ntext")
        tags = {dl.tag for dl in result.lines}
        assert "equal" in tags

    def test_insert_tag(self):
        result = compare("a\nb", "a\nb\nc")
        tags = {dl.tag for dl in result.lines}
        assert "insert" in tags

    def test_delete_tag(self):
        result = compare("a\nb\nc", "a\nb")
        tags = {dl.tag for dl in result.lines}
        assert "delete" in tags

    def test_replace_tag(self):
        result = compare("line1\nold line\nline3", "line1\nnew line\nline3")
        tags = {dl.tag for dl in result.lines}
        assert "replace" in tags or "delete" in tags or "insert" in tags

    def test_diff_line_fields(self):
        result = compare("a", "b")
        assert all(isinstance(dl, DiffLine) for dl in result.lines)
        for dl in result.lines:
            assert dl.tag in ("equal", "insert", "delete", "replace")

    def test_no_orphan_lines(self):
        """Каждая строка diff должна иметь хотя бы один непустой текст."""
        result = compare("foo\nbar\nbaz", "foo\nqux\nbaz")
        for dl in result.lines:
            assert dl.left != "" or dl.right != ""


class TestSimilarity:
    def test_similarity_identical(self):
        result = compare("hello world", "hello world")
        assert result.stats.similarity == 1.0

    def test_similarity_different(self):
        result = compare("aaaa\nbbbb", "cccc\ndddd")
        assert result.stats.similarity < 0.5

    def test_similarity_pct(self):
        result = compare("same\ntext", "same\ntext")
        assert result.stats.similarity_pct == 100


class TestRichText:
    def test_rich_text_returns_string(self):
        result = compare("a\nb", "a\nc")
        text = result.rich_text()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_rich_text_contains_markup(self):
        result = compare("old", "new")
        text = result.rich_text()
        # Должен содержать rich markup для цветов
        assert "[green]" in text or "[red]" in text or "[dim]" in text


class TestCompareLines:
    def test_compare_lines_list(self):
        left = ["line1", "line2", "line3"]
        right = ["line1", "changed", "line3"]
        result = compare_lines(left, right)
        assert result.stats.total_left == 3
        assert result.stats.total_right == 3

    def test_compare_lines_empty_lists(self):
        result = compare_lines([], [])
        assert result.stats.total_left == 0
        assert result.stats.total_right == 0


class TestCompareBytes:
    def test_compare_bytes_identical(self):
        data = b"hello\nworld"
        result = compare_bytes(data, data)
        assert result.stats.similarity == 1.0

    def test_compare_bytes_different(self):
        result = compare_bytes(b"aaa", b"bbb")
        assert result.stats.similarity < 1.0

    def test_compare_bytes_with_non_utf8(self):
        # Не должно бросать исключение
        result = compare_bytes(b"\xff\xfe", b"\x00\x01")
        assert isinstance(result, DiffResult)


class TestCompareStats:
    def test_stats_fields(self):
        result = compare("a\nb\nc", "a\nd\nc")
        s = result.stats
        assert isinstance(s.total_left, int)
        assert isinstance(s.total_right, int)
        assert isinstance(s.equal_lines, int)
        assert isinstance(s.added_lines, int)
        assert isinstance(s.removed_lines, int)
        assert isinstance(s.changed_lines, int)
        assert 0.0 <= s.similarity <= 1.0

    def test_stats_similarity_pct_range(self):
        result = compare("a", "b")
        assert 0 <= result.stats.similarity_pct <= 100
