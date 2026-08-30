"""Unit tests for payload-set serialization helpers (Этап 6)."""

from __future__ import annotations

from pentool.tui.widgets.payload_serialization import serialize_payloads, deserialize_payloads
from pentool.modules.intruder import (
    CharPayloadSource,
    ChainedPayloadSource,
    NumericPayloadSource,
)


class TestSerialize:
    def test_plain_list_is_identity(self):
        assert serialize_payloads([["a", "b"]]) == [["a", "b"]]

    def test_numeric_source(self):
        src = NumericPayloadSource(0, 10, 2)
        out = serialize_payloads([src])
        assert out[0] == {"__numeric__": True, "start": 0, "end": 10, "step": 2}

    def test_char_source(self):
        src = CharPayloadSource("ab", 1, 3)
        out = serialize_payloads([src])
        assert out[0]["__charset__"] == "ab"
        assert out[0]["min_len"] == 1
        assert out[0]["max_len"] == 3

    def test_file_source_serializes_meta_not_contents(self, tmp_path):
        p = tmp_path / "list.txt"
        p.write_text("a\nb\nc\n")
        from pentool.modules.intruder import FilePayloadSource
        src = FilePayloadSource(str(p))
        src.set_count(3)
        out = serialize_payloads([src])
        assert out[0] == {"__file__": str(p), "count": 3}

    def test_chained_serializes_recursively(self):
        out = serialize_payloads([ChainedPayloadSource(NumericPayloadSource(0, 5, 1))])
        assert "__chained__" in out[0]
        assert out[0]["__chained__"][0]["__numeric__"] is True


class TestDeserialize:
    def test_round_trip_plain(self):
        assert deserialize_payloads([["x", "y"]]) == [["x", "y"]]

    def test_round_trip_numeric(self):
        out = deserialize_payloads([{"__numeric__": True, "start": 0, "end": 9, "step": 1}])
        assert isinstance(out[0], NumericPayloadSource)
        assert out[0].start == 0 and out[0].end == 9 and out[0].step == 1

    def test_round_trip_char(self):
        out = deserialize_payloads([{"__charset__": "ab", "min_len": 2, "max_len": 4}])
        assert isinstance(out[0], CharPayloadSource)
        assert (out[0].charset, out[0].min_len, out[0].max_len) == ("ab", 2, 4)

    def test_round_trip_chained_numeric(self):
        raw = [{"__chained__": [{"__numeric__": True, "start": 4, "end": 6, "step": 1}]}]
        out = deserialize_payloads(raw)
        assert isinstance(out[0], ChainedPayloadSource)
        # reconstituted chain has an inner NumericPayloadSource
        inner = list(out[0]._sources)
        assert isinstance(inner[0], NumericPayloadSource)

    def test_bad_entry_becomes_empty_list(self):
        out = deserialize_payloads([None, 42, "x"])
        assert out == [[], [], []]
