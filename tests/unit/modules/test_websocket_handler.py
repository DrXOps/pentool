"""Unit tests: modules/websocket_handler.py — RFC 6455 frame parsing/building."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pentool.modules.websocket_handler import WebSocketHandler


class TestParseFrame:
    def test_too_short_returns_none(self):
        assert WebSocketHandler.parse_frame(b"\x81") is None
        assert WebSocketHandler.parse_frame(b"") is None

    def test_simple_text_unmasked(self):
        frame = b"\x81\x03abc"  # FIN+text, len 3, payload "abc"
        opcode, fin, payload, consumed = WebSocketHandler.parse_frame(frame)
        assert opcode == 0x1
        assert fin is True
        assert payload == b"abc"
        assert consumed == len(frame)

    def test_continuation_not_final(self):
        frame = b"\x00\x02hi"  # continuation, no FIN
        opcode, fin, payload, _ = WebSocketHandler.parse_frame(frame)
        assert fin is False
        assert opcode == 0x0

    def test_length_126_extended(self):
        # payload 200 bytes → 126 extended length (2 bytes big-endian)
        payload = b"a" * 200
        frame = b"\x81\x7e" + (200).to_bytes(2, "big") + payload
        opcode, fin, payload_out, consumed = WebSocketHandler.parse_frame(frame)
        assert len(payload_out) == 200
        assert consumed == len(frame)

    def test_length_126_insufficient_header(self):
        frame = b"\x81\x7e\x03"  # claims 126-extended but missing length bytes
        assert WebSocketHandler.parse_frame(frame) is None

    def test_length_127_extended64(self):
        payload = b"b" * 70000  # > 65535 → 8-byte length
        frame = b"\x81\x7f" + (70000).to_bytes(8, "big") + payload
        opcode, fin, payload_out, consumed = WebSocketHandler.parse_frame(frame)
        assert len(payload_out) == 70000
        assert consumed == len(frame)

    def test_length_127_insufficient_header(self):
        frame = b"\x81\x7f\x01" + b"\x00" * 5  # missing full 8-byte length
        assert WebSocketHandler.parse_frame(frame) is None

    def test_masked_frame_unmasks(self):
        mask_key = b"\x01\x02\x03\x04"
        raw = b"hello"
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(raw))
        frame = b"\x81\x85" + mask_key + masked
        opcode, fin, payload, consumed = WebSocketHandler.parse_frame(frame)
        assert payload == b"hello"
        assert consumed == len(frame)

    def test_masked_insufficient_mask_key(self):
        frame = b"\x81\x80\x01\x02"  # claims masked but fewer than 4 mask key bytes
        assert WebSocketHandler.parse_frame(frame) is None

    def test_insufficient_payload_bytes(self):
        frame = b"\x81\x05ab"  # claims 5 payload bytes, has 2
        assert WebSocketHandler.parse_frame(frame) is None

    def test_parse_frame_roundtrip_masked(self):
        data = b"The quick brown fox jumps over the lazy dog"
        built = WebSocketHandler.build_frame(0x1, data, mask=True)
        opcode, fin, payload, _ = WebSocketHandler.parse_frame(built)
        assert opcode == 0x1
        assert payload == data


class TestBuildFrame:
    def test_short_payload(self):
        frame = WebSocketHandler.build_frame(0x1, b"xyz")
        assert frame == b"\x81\x03xyz"

    def test_binary_opcode(self):
        frame = WebSocketHandler.build_frame(0x2, b"\x00\x01")
        assert frame[0] == 0x82

    def test_medium_payload_two_byte_length(self):
        frame = WebSocketHandler.build_frame(0x1, b"a" * 300)
        assert frame[1] == 126
        assert frame[2:4] == (300).to_bytes(2, "big")

    def test_large_payload_eight_byte_length(self):
        frame = WebSocketHandler.build_frame(0x2, b"b" * 70000)
        assert frame[1] == 127
        assert frame[2:10] == (70000).to_bytes(8, "big")

    def test_masked_frame_has_mask_and_unmaskable(self):
        with patch("os.urandom", return_value=b"\xde\xad\xbe\xef"):
            frame = WebSocketHandler.build_frame(0x1, b"abcd", mask=True)
        assert (frame[1] & 0x80) != 0
        # mask key present, payload unmaskable back to "abcd"
        mask_key = frame[2:6]
        payload = frame[6:]
        unmasked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        assert unmasked == b"abcd"
        # roundtrip via parse
        _, _, parsed, _ = WebSocketHandler.parse_frame(frame)
        assert parsed == b"abcd"
