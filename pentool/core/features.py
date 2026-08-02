"""Feature flags and limits for the Pentool licensing model."""

from enum import Enum
from dataclasses import dataclass


class FeatureStatus(str, Enum):
    """Feature status."""
    STABLE = "stable"    # Stable, ready for production
    BETA = "beta"        # Stable, but in beta testing
    ALPHA = "alpha"      # Experimental, may be unstable


@dataclass
class Feature:
    """Description of a single feature."""
    name: str
    description: str
    status: FeatureStatus
    required_plan: str  # "free", "lite", "medium", "full"


# ═══════════════════════════════════════════════════════════════════════
# FEATURE CONSTANTS — string identifiers for require_feature
# ═══════════════════════════════════════════════════════════════════════

# Scanner PRO checks
FEATURE_SCANNER_ADVANCED_WAF = "scanner_advanced_waf"
FEATURE_SCANNER_OOB = "scanner_oob"
FEATURE_SCANNER_SSRF_PORTSCAN = "scanner_ssrf_portscan"
FEATURE_SCANNER_SQLI_UNION = "scanner_sqli_union"
FEATURE_SCANNER_SQLI_OOB = "scanner_sqli_oob"
FEATURE_SCANNER_LFI_LOG_POISON = "scanner_lfi_log_poison"
FEATURE_SCANNER_XSS_STORED = "scanner_xss_stored"
FEATURE_SCANNER_DOM_XSS_ACTIVE = "scanner_dom_xss_active"
FEATURE_SCANNER_DESER = "scanner_deser"
FEATURE_SCANNER_SMUGGLING = "scanner_smuggling"
FEATURE_SCANNER_FILE_UPLOAD = "scanner_file_upload"
FEATURE_SCANNER_IDOR = "scanner_idor"
FEATURE_SCANNER_PROMPT_INJECT = "scanner_prompt_inject"
FEATURE_SCANNER_RCE_OOB = "scanner_rce_oob"

# AI features
FEATURE_AI_ANALYSIS = "ai_analysis"
FEATURE_AI_STRATEGY = "ai_strategy"

# Reports
FEATURE_REPORTS_PRO = "pro_reports"


# ═══════════════════════════════════════════════════════════════════════
# FEATURES — feature availability by plan
# ═══════════════════════════════════════════════════════════════════════

FEATURES = {
    # ────────────────────────────────────────────────────────────────────
    # FREE PLAN — basic tools
    # ────────────────────────────────────────────────────────────────────
    "proxy": Feature(
        "proxy",
        "HTTP/HTTPS Proxy with interception",
        FeatureStatus.STABLE,
        "free"
    ),
    "repeater": Feature(
        "repeater",
        "Repeater — replay and modify requests",
        FeatureStatus.STABLE,
        "free"
    ),
    "intruder_basic": Feature(
        "intruder_basic",
        "Intruder (Sniper, Battering Ram)",
        FeatureStatus.BETA,
        "free"
    ),
    "decoder": Feature(
        "decoder",
        "Decoder — encode/decode data",
        FeatureStatus.STABLE,
        "free"
    ),
    "comparer": Feature(
        "comparer",
        "Comparer — compare requests/responses",
        FeatureStatus.STABLE,
        "free"
    ),
    "httpql": Feature(
        "httpql",
        "HTTPQL — filter request history",
        FeatureStatus.BETA,
        "free"
    ),

    # ────────────────────────────────────────────────────────────────────
    # LITE PLAN — extended capabilities
    # ────────────────────────────────────────────────────────────────────
    "scanner_extended": Feature(
        "scanner_extended",
        "Scanner — extended security checks",
        FeatureStatus.ALPHA,
        "lite"
    ),
    "intruder_all_types": Feature(
        "intruder_all_types",
        "Intruder (Pitchfork, Cluster Bomb)",
        FeatureStatus.ALPHA,
        "lite"
    ),
    "spider": Feature(
        "spider",
        "Spider — automatic site crawling",
        FeatureStatus.BETA,
        "lite"
    ),
    "match_replace": Feature(
        "match_replace",
        "Match & Replace — auto-modify requests",
        FeatureStatus.BETA,
        "lite"
    ),
    "target_scope": Feature(
        "target_scope",
        "Target Scope — manage testing scope",
        FeatureStatus.STABLE,
        "lite"
    ),

    # ────────────────────────────────────────────────────────────────────
    # MEDIUM PLAN — professional tools
    # ────────────────────────────────────────────────────────────────────
    "oob_detection": Feature(
        "oob_detection",
        "Out-of-Band vulnerability detection",
        FeatureStatus.ALPHA,
        "medium"
    ),
    "websocket_intercept": Feature(
        "websocket_intercept",
        "WebSocket interception and modification",
        FeatureStatus.ALPHA,
        "medium"
    ),
    "plugins": Feature(
        "plugins",
        "Plugin system",
        FeatureStatus.ALPHA,
        "medium"
    ),
    "sequencer": Feature(
        "sequencer",
        "Sequencer — token randomness analysis",
        FeatureStatus.BETA,
        "medium"
    ),
    "passive_scanner": Feature(
        "passive_scanner",
        "Passive Scanner — background traffic analysis",
        FeatureStatus.BETA,
        "medium"
    ),
    "turbo_mode": Feature(
        "turbo_mode",
        "Turbo Mode Intruder (10x speed)",
        FeatureStatus.BETA,
        "medium"
    ),

    # ────────────────────────────────────────────────────────────────────
    # FULL PLAN — enterprise capabilities
    # ────────────────────────────────────────────────────────────────────
    "ai_analysis": Feature(
        "ai_analysis",
        "AI vulnerability analysis (GPT-4)",
        FeatureStatus.ALPHA,
        "full"
    ),
    "pro_reports": Feature(
        "pro_reports",
        "PRO reports (HTML/PDF/JSON)",
        FeatureStatus.ALPHA,
        "full"
    ),
    "collaboration": Feature(
        "collaboration",
        "Collaborative project work",
        FeatureStatus.ALPHA,
        "full"
    ),
    "api_access": Feature(
        "api_access",
        "REST API for automation",
        FeatureStatus.BETA,
        "full"
    ),
    "custom_scanner_checks": Feature(
        "custom_scanner_checks",
        "Custom Scanner checks",
        FeatureStatus.ALPHA,
        "full"
    ),
    "payloads_pro": Feature(
        "payloads_pro",
        "PRO payload sets for Intruder/Scanner",
        FeatureStatus.ALPHA,
        "full"
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# LIMITS — limits by plan
# ═══════════════════════════════════════════════════════════════════════

LIMITS = {
    # Request history
    "history_max_entries": {
        "free": 500,
        "lite": 5000,
        "medium": 50000,
        "full": -1,  # unlimited
    },

    # Intruder
    "intruder_max_threads": {
        "free": 10,
        "lite": 20,
        "medium": 50,
        "full": 100,
    },
    "intruder_max_requests": {
        "free": 1000,
        "lite": 10000,
        "medium": 100000,
        "full": -1,  # unlimited
    },

    # Scanner
    "scanner_max_depth": {
        "free": 2,
        "lite": 5,
        "medium": 10,
        "full": -1,  # unlimited
    },
    "scanner_max_pages": {
        "free": 20,
        "lite": 100,
        "medium": 1000,
        "full": -1,  # unlimited
    },
    "scanner_threads": {
        "free": 5,
        "lite": 10,
        "medium": 20,
        "full": 50,
    },

    # Spider
    "spider_max_depth": {
        "free": 2,
        "lite": 5,
        "medium": 10,
        "full": -1,  # unlimited
    },
    "spider_max_pages": {
        "free": 50,
        "lite": 200,
        "medium": 1000,
        "full": -1,  # unlimited
    },

    # Projects
    "projects_max": {
        "free": 5,
        "lite": 20,
        "medium": 100,
        "full": -1,  # unlimited
    },

    # Export
    "export_formats": {
        "free": ["txt"],
        "lite": ["txt", "csv", "json"],
        "medium": ["txt", "csv", "json", "html"],
        "full": ["txt", "csv", "json", "html", "pdf"],
    },
}


# ═══════════════════════════════════════════════════════════════════════
# PLAN NAMES — human-readable plan names
# ═══════════════════════════════════════════════════════════════════════

PLAN_NAMES = {
    "free": "Free",
    "lite": "Lite",
    "medium": "Medium",
    "full": "Full (PRO)",
    "pro": "PRO",
    "enterprise": "Enterprise",
}


PLAN_DESCRIPTIONS = {
    "free": "Basic tools for testing",
    "lite": "Extended capabilities for professionals",
    "medium": "Advanced tools + plugins",
    "full": "Enterprise features + AI + API",
    "pro": "Full PRO license — all features",
    "enterprise": "Enterprise license — all features + custom integrations",
}


# ═══════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def has_feature(feature_name: str, plan: str) -> bool:
    """Check if a feature is available for the given plan.

    Args:
        feature_name: Feature name (key from FEATURES)
        plan: Plan name ("free", "lite", "medium", "full")

    Returns:
        True if the feature is available for this plan
    """
    feature = FEATURES.get(feature_name)
    if not feature:
        return False

    # Plan order from lowest to highest
    plan_order = ["free", "lite", "medium", "full", "pro", "enterprise"]

    # If current plan >= required plan, feature is available
    try:
        current_level = plan_order.index(plan.lower())
        required_level = plan_order.index(feature.required_plan)
        return current_level >= required_level
    except (ValueError, AttributeError):
        return False


def get_limit(limit_name: str, plan: str, default: int = 0) -> int | list:
    limits = LIMITS.get(limit_name, {})
    plan_l = plan.lower()
    # pro/enterprise inherit "full" limits if not explicitly defined
    if plan_l not in limits and plan_l in ("pro", "enterprise"):
        return limits.get("full", default)
    return limits.get(plan_l, default)


def get_feature_status(feature_name: str) -> str:
    feature = FEATURES.get(feature_name)
    return feature.status.value if feature else "unknown"


def get_features_for_plan(plan: str) -> list[Feature]:
    return [
        feature
        for feature in FEATURES.values()
        if has_feature(feature.name, plan)
    ]


def get_plan_info(plan: str) -> dict:
    features = get_features_for_plan(plan)

    return {
        "plan": plan,
        "name": PLAN_NAMES.get(plan, plan.capitalize()),
        "description": PLAN_DESCRIPTIONS.get(plan, ""),
        "features_count": len(features),
        "features": [
            {
                "name": f.name,
                "description": f.description,
                "status": f.status.value,
            }
            for f in features
        ],
        "limits": {
            limit_name: get_limit(limit_name, plan)
            for limit_name in LIMITS.keys()
        },
    }
