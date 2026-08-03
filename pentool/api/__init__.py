"""Pentool API layer — public interface between modules/ and TUI/CLI."""
import pkgutil
__path__ = pkgutil.extend_path(__path__, __name__)

from pentool.api.comparer_api import (  # noqa: F401
    CompareStats,
    DiffLine,
    DiffResult,
    compare,
    compare_lines,
)

# Decoder/Comparer/Sequencer — functional APIs without a wrapper class
from pentool.api.decoder_api import (  # noqa: F401
    OP_LABELS,
    OPERATIONS,
    DecoderChain,
    decode_op,
    decode_smart,
    encode_op,
    run_chain,
)
from pentool.api.intruder_api import IntruderAPI, IntruderAttack, IntruderConfig
from pentool.api.proxy_api import InterceptedRequest, MatchReplaceRule, ProxyAPI
from pentool.api.repeater_api import RepeaterAPI
from pentool.api.sequencer_api import (  # noqa: F401
    Sequencer,
    SequencerReport,
    charset_size,
    token_entropy,
)
from pentool.api.spider_api import SpiderAPI
from pentool.api.target_api import TargetAPI

# Scanner is a PRO-only module (see docs on licensing/trial). Its source
# ships separately (downloaded via 'pentool license trial'/'activate' into
# ~/.pentool/pro/) and is absent on a bare `pip install pentool`. Import it
# defensively so the rest of the app (FREE modules, TUI shell) still works
# without it — callers should check `SCANNER_AVAILABLE` before using
# `ScannerAPI`.
try:
    from pentool.api.scanner_api import ScannerAPI  # noqa: F401
    SCANNER_AVAILABLE = True
except ImportError:
    ScannerAPI = None  # type: ignore[assignment,misc]
    SCANNER_AVAILABLE = False

__all__ = [
    # Proxy
    "ProxyAPI", "InterceptedRequest", "MatchReplaceRule",
    # Repeater
    "RepeaterAPI",
    # Scanner (PRO — may be None, see SCANNER_AVAILABLE)
    "ScannerAPI", "SCANNER_AVAILABLE",
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
