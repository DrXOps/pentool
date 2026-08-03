"""DecoderAPI — public Decoder/Encoder interface for TUI."""

from __future__ import annotations

# Re-export everything public from modules/decoder
from pentool.modules.decoder import (  # noqa: F401
    OP_LABELS,
    OPERATIONS,
    DecoderChain,
    decode_op,
    decode_smart,
    encode_op,
    run_chain,
)
from pentool.modules.decoder import (
    _detect_encoding as detect_encoding,  # expose as public API
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
