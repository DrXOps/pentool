"""Feature catalogue and limits for the Pentool licensing model.

**This module is the single source of truth for what a plan buys.** It must match the
code, not the marketing: every entry in `FEATURES` is checked somewhere in the
application with `LicenseInfo.has_feature(...)`, and every such check has an entry here.
`tests/unit/core/test_feature_catalogue.py` enforces that both directions stay true.

Plans are `free`, `pro` and `enterprise`. There is no `team` plan and no
`lite`/`medium`/`full` tiers — earlier revisions of this file invented them, which made
the site and support answers promise features that did not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: Plans ordered from least to most capable. `has_feature` compares positions here.
PLAN_ORDER = ("free", "pro", "enterprise")


class FeatureStatus(str, Enum):
    """Maturity of a feature, shown in the licence portal and the UI."""

    STABLE = "stable"  # ready for production
    BETA = "beta"  # works, still being hardened
    ALPHA = "alpha"  # experimental, may change or break


@dataclass(frozen=True)
class Feature:
    """Description of a single gated feature."""

    name: str
    description: str
    status: FeatureStatus
    required_plan: str  # "pro" | "enterprise"


# ═══════════════════════════════════════════════════════════════════════
# FEATURE IDENTIFIERS — the exact strings passed to has_feature()
# ═══════════════════════════════════════════════════════════════════════

#: Unlocks the vulnerability Scanner module (server-side check list included).
FEATURE_SCANNER_PRO = "scanner_pro"
#: Unlocks the Reconnaissance module (subdomains, endpoints, real IP, param fuzz).
FEATURE_AI_DISCOVERY = "ai_discovery"
#: AI analysis of scanner findings (requires a configured AI backend).
FEATURE_AI_ANALYSIS = "ai_analysis"
#: Scanner reports: single-finding and bulk HTML (Bug Bounty template).
FEATURE_REPORTS_PRO = "reports_pro"
#: Smart Payloads and the PRO payload sets for Intruder.
FEATURE_PAYLOADS_PRO = "payloads_pro"


# ═══════════════════════════════════════════════════════════════════════
# FEATURES — everything a PRO key actually unlocks
# ═══════════════════════════════════════════════════════════════════════

FEATURES: dict[str, Feature] = {
    FEATURE_SCANNER_PRO: Feature(
        FEATURE_SCANNER_PRO,
        "Vulnerability Scanner module — 21 active and passive checks",
        FeatureStatus.BETA,
        "pro",
    ),
    FEATURE_AI_DISCOVERY: Feature(
        FEATURE_AI_DISCOVERY,
        "Reconnaissance — subdomains, endpoints, real IP behind CDN, parameter fuzzing",
        FeatureStatus.BETA,
        "pro",
    ),
    FEATURE_AI_ANALYSIS: Feature(
        FEATURE_AI_ANALYSIS,
        "AI analysis of scanner findings",
        FeatureStatus.ALPHA,
        "pro",
    ),
    FEATURE_REPORTS_PRO: Feature(
        FEATURE_REPORTS_PRO,
        "Reports — single finding and bulk HTML (Bug Bounty template)",
        FeatureStatus.BETA,
        "pro",
    ),
    FEATURE_PAYLOADS_PRO: Feature(
        FEATURE_PAYLOADS_PRO,
        "Smart Payloads and PRO payload sets for Intruder",
        FeatureStatus.BETA,
        "pro",
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# LIMITS — only limits the code enforces (or at least displays as input bounds)
# ═══════════════════════════════════════════════════════════════════════

#: `IntruderScreen._apply_license_limits` reads these: FREE is capped at 5 threads
#: and a 100 ms minimum delay, PRO allows up to 200 threads and no delay floor.
LIMITS: dict[str, dict[str, int]] = {
    "intruder_max_threads": {"free": 5, "pro": 200, "enterprise": 200},
    "intruder_min_delay_ms": {"free": 100, "pro": 0, "enterprise": 0},
}


# ═══════════════════════════════════════════════════════════════════════
# PLAN NAMES — human-readable labels
# ═══════════════════════════════════════════════════════════════════════

PLAN_NAMES = {
    "free": "Free",
    "pro": "PRO",
    "enterprise": "Enterprise",
}

PLAN_DESCRIPTIONS = {
    "free": "Open-source core: proxy, repeater, intruder, decoder, comparer, sequencer, spider",
    "pro": "Free plus Scanner, Recon, AI analysis, Smart Payloads and HTML reports",
    "enterprise": "Everything in PRO, for organisations that need custom arrangements",
}


# ═══════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════


def has_feature(feature_name: str, plan: str) -> bool:
    """Return True if *plan* includes *feature_name*.

    Unknown features and unknown plans return False: a licence that names a feature
    this build does not know about must not unlock anything.
    """
    feature = FEATURES.get(feature_name)
    if feature is None:
        return False
    plan_key = (plan or "").lower()
    try:
        return PLAN_ORDER.index(plan_key) >= PLAN_ORDER.index(feature.required_plan)
    except ValueError:
        return False


def get_limit(limit_name: str, plan: str, default: int = 0) -> int:
    """Return the numeric limit for *plan*, falling back to *default*."""
    limits = LIMITS.get(limit_name, {})
    plan_key = (plan or "").lower()
    # `pro` and `enterprise` share the paid limits; a future tier may add its own row.
    if plan_key not in limits and plan_key in ("pro", "enterprise"):
        plan_key = "pro"
    return int(limits.get(plan_key, default))


def get_feature_status(feature_name: str) -> str:
    """Return the maturity of a feature as a string (`stable`/`beta`/`alpha`)."""
    feature = FEATURES.get(feature_name)
    return feature.status.value if feature else "unknown"


def get_features_for_plan(plan: str) -> list[Feature]:
    """Return every feature unlocked by *plan*."""
    return [feature for feature in FEATURES.values() if has_feature(feature.name, plan)]


def get_plan_info(plan: str) -> dict:
    """Return a JSON-friendly description of a plan (used by the licence portal)."""
    features = get_features_for_plan(plan)
    return {
        "plan": plan,
        "name": PLAN_NAMES.get(plan, plan.capitalize()),
        "description": PLAN_DESCRIPTIONS.get(plan, ""),
        "features_count": len(features),
        "features": [
            {
                "name": feature.name,
                "description": feature.description,
                "status": feature.status.value,
            }
            for feature in features
        ],
        "limits": {limit_name: get_limit(limit_name, plan) for limit_name in LIMITS},
    }
