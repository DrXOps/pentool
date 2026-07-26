"""DecoderAPI — public Decoder/Encoder interface for TUI."""

from __future__ import annotations

# Re-export everything public from modules/decoder
from pentool.modules.decoder import (  # noqa: F401
    OPERATIONS,
    OP_LABELS,
    DecoderChain,
    _detect_encoding as detect_encoding,  # expose as public API
    decode_op,
    decode_smart,
    encode_op,
    run_chain,
)

__all__ = [
    "OPERATIONS",
    "OP_LABELS",
    "DecoderChain",
    "detect_encoding",
    "decode_op",
    "decode_smart",
    "encode_op",
    "run_chain",
]
