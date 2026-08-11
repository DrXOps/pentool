"""Unit tests: lazy payload loading support in pentool/modules/intruder.py.

Covers FilePayloadSource, _lazy_cartesian_product, count_lines_with_progress,
ProcessedPayloads, and IntruderAttack._count_total()/run() no longer
materializing the full combination set — see the "Загрузка файлов
пейлоадов до 30ГБ" requirement.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _write_payload_file(tmp_path: Path, lines: list[str], name: str = "payloads.txt") -> str:
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


class TestFilePayloadSource:
    def test_iterates_lines(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource
        path = _write_payload_file(tmp_path, ["admin", "root", "guest"])
        source = FilePayloadSource(path)
        assert list(source) == ["admin", "root", "guest"]

    def test_skips_blank_and_comment_lines(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource
        path = _write_payload_file(tmp_path, ["admin", "", "# comment", "  ", "root"])
        source = FilePayloadSource(path)
        assert list(source) == ["admin", "root"]

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource
        path = _write_payload_file(tmp_path, ["  admin  ", "root\t"])
        source = FilePayloadSource(path)
        assert list(source) == ["admin", "root"]

    def test_repeated_iteration_reopens_file(self, tmp_path: Path) -> None:
        """Needed by Pitchfork's zip() and cartesian product re-iteration."""
        from pentool.modules.intruder import FilePayloadSource
        path = _write_payload_file(tmp_path, ["a", "b", "c"])
        source = FilePayloadSource(path)
        assert list(source) == ["a", "b", "c"]
        assert list(source) == ["a", "b", "c"]  # second pass, not exhausted

    def test_len_counts_lazily_and_caches(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource
        path = _write_payload_file(tmp_path, ["a", "b", "c", "d"])
        source = FilePayloadSource(path)
        assert source.cached_count is None
        assert source.is_count_known is False
        assert len(source) == 4
        assert source.is_count_known is True
        assert source.cached_count == 4

    def test_set_count_avoids_rescan(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource
        path = _write_payload_file(tmp_path, ["a", "b"])
        source = FilePayloadSource(path)
        source.set_count(999)  # deliberately wrong, to prove no rescan happens
        assert len(source) == 999
        assert source.is_count_known is True

    def test_bool_true_for_nonempty(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource
        path = _write_payload_file(tmp_path, ["a"])
        assert bool(FilePayloadSource(path)) is True

    def test_bool_false_for_empty_file(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource
        path = _write_payload_file(tmp_path, [])
        assert bool(FilePayloadSource(path)) is False

    def test_head_returns_first_n_only(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource
        path = _write_payload_file(tmp_path, [f"p{i}" for i in range(100)])
        source = FilePayloadSource(path)
        head = source.head(5)
        assert head == ["p0", "p1", "p2", "p3", "p4"]

    def test_head_does_not_force_count(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource
        path = _write_payload_file(tmp_path, [f"p{i}" for i in range(50)])
        source = FilePayloadSource(path)
        source.head(3)
        assert source.cached_count is None

    def test_missing_file_iteration_raises(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource
        source = FilePayloadSource(str(tmp_path / "nonexistent.txt"))
        with pytest.raises(OSError):
            list(source)


class TestCountLinesWithProgress:
    def test_counts_qualifying_lines(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import count_lines_with_progress
        path = _write_payload_file(tmp_path, ["a", "", "# skip", "b", "c"])
        assert count_lines_with_progress(path) == 3

    def test_progress_callback_fires_with_final_totals(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import count_lines_with_progress
        path = _write_payload_file(tmp_path, [f"p{i}" for i in range(10)])
        calls = []
        count_lines_with_progress(path, on_progress=lambda c, b, t: calls.append((c, b, t)))
        assert calls  # at least the final call fired
        last_count, last_bytes, last_total = calls[-1]
        assert last_count == 10
        assert last_bytes == last_total


class TestLazyCartesianProduct:
    def test_matches_itertools_product_two_sets(self) -> None:
        import itertools
        from pentool.modules.intruder import _lazy_cartesian_product
        a, b = ["x", "y"], ["1", "2"]
        assert list(_lazy_cartesian_product(a, b)) == list(itertools.product(a, b))

    def test_matches_itertools_product_three_sets(self) -> None:
        import itertools
        from pentool.modules.intruder import _lazy_cartesian_product
        sets = [["a", "b"], ["x", "y"], ["1", "2", "3"]]
        assert list(_lazy_cartesian_product(*sets)) == list(itertools.product(*sets))

    def test_single_set(self) -> None:
        from pentool.modules.intruder import _lazy_cartesian_product
        assert list(_lazy_cartesian_product(["a", "b", "c"])) == [("a",), ("b",), ("c",)]

    def test_empty_input_yields_nothing(self) -> None:
        from pentool.modules.intruder import _lazy_cartesian_product
        assert list(_lazy_cartesian_product()) == []

    def test_works_with_file_backed_sets(self, tmp_path: Path) -> None:
        """The whole point — a FilePayloadSource set must not need to be
        materialized to compute a cartesian product over it."""
        from pentool.modules.intruder import FilePayloadSource, _lazy_cartesian_product
        path_a = _write_payload_file(tmp_path, ["a", "b"], name="a.txt")
        path_b = _write_payload_file(tmp_path, ["1", "2"], name="b.txt")
        source_a = FilePayloadSource(path_a)
        source_b = FilePayloadSource(path_b)
        combos = list(_lazy_cartesian_product(source_a, source_b))
        assert combos == [("a", "1"), ("a", "2"), ("b", "1"), ("b", "2")]


class TestProcessedPayloads:
    def test_applies_function_lazily(self) -> None:
        from pentool.modules.intruder import ProcessedPayloads
        calls = []

        def apply(p, ops):
            calls.append(p)
            return p.upper()

        wrapped = ProcessedPayloads(["a", "b", "c"], [], apply)
        assert calls == []  # nothing applied yet — lazy
        result = list(wrapped)
        assert result == ["A", "B", "C"]
        assert calls == ["a", "b", "c"]

    def test_len_delegates_to_source(self, tmp_path: Path) -> None:
        from pentool.modules.intruder import FilePayloadSource, ProcessedPayloads
        path = _write_payload_file(tmp_path, ["a", "b", "c"])
        source = FilePayloadSource(path)
        wrapped = ProcessedPayloads(source, [], lambda p, ops: p)
        assert len(wrapped) == 3

    def test_bool_true_for_nonempty_source(self) -> None:
        from pentool.modules.intruder import ProcessedPayloads
        assert bool(ProcessedPayloads(["a"], [], lambda p, ops: p)) is True

    def test_bool_false_for_empty_source(self) -> None:
        from pentool.modules.intruder import ProcessedPayloads
        assert bool(ProcessedPayloads([], [], lambda p, ops: p)) is False


class TestCountTotalDoesNotMaterialize:
    """_count_total() must derive from set sizes, not by walking the full
    (potentially enormous) combination iterator."""

    def test_sniper_count_total(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="§a§ §b§ §c§",
            attack_type=AttackType.SNIPER,
            payload_sets=[["x", "y"]],
        )
        attack = IntruderAttack(config)
        # 3 positions x 2 payloads = 6
        assert attack._count_total() == 6

    def test_cluster_bomb_count_total_with_file_backed_set(self, tmp_path: Path) -> None:
        """The core regression case: computing the total for a Cluster Bomb
        attack over a FilePayloadSource must use its cached/streamed len(),
        not iterate the (potentially huge) cartesian product."""
        from pentool.modules.intruder import (
            AttackType, FilePayloadSource, IntruderAttack, IntruderConfig,
        )
        path = _write_payload_file(tmp_path, ["a", "b", "c"])
        source = FilePayloadSource(path)
        config = IntruderConfig(
            template="§a§ §b§",
            attack_type=AttackType.CLUSTER_BOMB,
            payload_sets=[["x", "y"], source],
        )
        attack = IntruderAttack(config)
        assert attack._count_total() == 6  # 2 * 3

    def test_empty_payload_sets_count_total_zero(self) -> None:
        from pentool.modules.intruder import IntruderAttack, IntruderConfig, AttackType
        config = IntruderConfig(
            template="§a§",
            attack_type=AttackType.SNIPER,
            payload_sets=[],
        )
        attack = IntruderAttack(config)
        assert attack._count_total() == 0


class TestRunDoesNotMaterializeCombinations:
    """run() must not build `list(self._get_iterator())` up front — verified
    indirectly by confirming attacks over large-ish payload sets still
    complete correctly and results/progress line up, exercising the
    lazy task_iter path end-to-end."""

    @pytest.mark.asyncio
    async def test_run_completes_with_file_backed_payload_set(self, tmp_path: Path, monkeypatch) -> None:
        from pentool.modules.intruder import (
            AttackType, FilePayloadSource, IntruderAttack, IntruderConfig, IntruderResult,
        )

        path = _write_payload_file(tmp_path, ["p1", "p2", "p3"])
        source = FilePayloadSource(path)
        config = IntruderConfig(
            template="GET /§FUZZ§ HTTP/1.1\r\nHost: example.com",
            attack_type=AttackType.BATTERING_RAM,
            payload_sets=[source],
            threads=2,
        )
        attack = IntruderAttack(config)

        async def _fake_send_request(req_num, payload_values, request_raw, client=None):
            return IntruderResult(
                id=str(req_num), attack_id=attack.attack_id, request_number=req_num,
                payload_values=payload_values, request_raw=request_raw,
                response_status=200, response_length=2, response_time_ms=1,
            )

        monkeypatch.setattr(attack, "_send_request", _fake_send_request)

        results = []
        progress_calls = []
        await attack.run(
            on_result=lambda r: results.append(r),
            on_progress=lambda done, total: progress_calls.append((done, total)),
        )

        assert len(results) == 3
        assert attack.total_requests == 3
        # Final progress call reports completion
        assert progress_calls[-1] == (3, 3)
