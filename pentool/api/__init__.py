"""API-слой pentool — публичный интерфейс между modules/ и TUI/CLI."""

from pentool.api.proxy_api     import ProxyAPI, InterceptedRequest, MatchReplaceRule
from pentool.api.repeater_api  import RepeaterAPI
from pentool.api.scanner_api   import ScannerAPI
from pentool.api.intruder_api  import IntruderAPI, IntruderConfig, IntruderAttack
from pentool.api.spider_api    import SpiderAPI
from pentool.api.target_api    import TargetAPI
# Decoder/Comparer/Sequencer — функциональные API без класса-обёртки
from pentool.api.decoder_api   import (  # noqa: F401
    OPERATIONS, OP_LABELS, DecoderChain,
    decode_op, decode_smart, encode_op, run_chain,
)
from pentool.api.comparer_api  import (  # noqa: F401
    compare, compare_lines, CompareStats, DiffLine, DiffResult,
)
from pentool.api.sequencer_api import (  # noqa: F401
    Sequencer, SequencerReport, token_entropy, charset_size,
)

__all__ = [
    # Proxy
    "ProxyAPI", "InterceptedRequest", "MatchReplaceRule",
    # Repeater
    "RepeaterAPI",
    # Scanner
    "ScannerAPI",
    # Intruder
    "IntruderAPI", "IntruderConfig", "IntruderAttack",
    # Spider
    "SpiderAPI",
    # Target
    "TargetAPI",
    # Decoder
    "OPERATIONS", "OP_LABELS", "DecoderChain",
    "decode_op", "decode_smart", "encode_op", "run_chain",
    # Comparer
    "compare", "compare_lines", "CompareStats", "DiffLine", "DiffResult",
    # Sequencer
    "Sequencer", "SequencerReport", "token_entropy", "charset_size",
]
