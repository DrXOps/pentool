"""Feature flags и лимиты для лицензионной модели Pentool."""

from enum import Enum
from dataclasses import dataclass


class FeatureStatus(str, Enum):
    """Статус фичи."""
    STABLE = "stable"    # Стабильная, готова к production
    BETA = "beta"        # Стабильная, но в beta-тестировании
    ALPHA = "alpha"      # Экспериментальная, может быть нестабильной


@dataclass
class Feature:
    """Описание одной фичи."""
    name: str
    description: str
    status: FeatureStatus
    required_plan: str  # "free", "lite", "medium", "full"


# ═══════════════════════════════════════════════════════════════════════
# FEATURE CONSTANTS — строковые идентификаторы для require_feature
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
# FEATURES — доступность фич по планам
# ═══════════════════════════════════════════════════════════════════════

FEATURES = {
    # ────────────────────────────────────────────────────────────────────
    # FREE PLAN — базовые инструменты
    # ────────────────────────────────────────────────────────────────────
    "proxy": Feature(
        "proxy",
        "HTTP/HTTPS Proxy с перехватом",
        FeatureStatus.STABLE,
        "free"
    ),
    "repeater": Feature(
        "repeater",
        "Repeater — повтор и модификация запросов",
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
        "Decoder — кодирование/декодирование данных",
        FeatureStatus.STABLE,
        "free"
    ),
    "comparer": Feature(
        "comparer",
        "Comparer — сравнение запросов/ответов",
        FeatureStatus.STABLE,
        "free"
    ),
    "httpql": Feature(
        "httpql",
        "HTTPQL — фильтрация истории запросов",
        FeatureStatus.BETA,
        "free"
    ),

    # ────────────────────────────────────────────────────────────────────
    # LITE PLAN — расширенные возможности
    # ────────────────────────────────────────────────────────────────────
    "scanner_extended": Feature(
        "scanner_extended",
        "Scanner — расширенные проверки безопасности",
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
        "Spider — автоматическое сканирование сайта",
        FeatureStatus.BETA,
        "lite"
    ),
    "match_replace": Feature(
        "match_replace",
        "Match & Replace — авто-модификация запросов",
        FeatureStatus.BETA,
        "lite"
    ),
    "target_scope": Feature(
        "target_scope",
        "Target Scope — управление областью тестирования",
        FeatureStatus.STABLE,
        "lite"
    ),

    # ────────────────────────────────────────────────────────────────────
    # MEDIUM PLAN — профессиональные инструменты
    # ────────────────────────────────────────────────────────────────────
    "oob_detection": Feature(
        "oob_detection",
        "Out-of-Band детекция уязвимостей",
        FeatureStatus.ALPHA,
        "medium"
    ),
    "websocket_intercept": Feature(
        "websocket_intercept",
        "WebSocket перехват и модификация",
        FeatureStatus.ALPHA,
        "medium"
    ),
    "plugins": Feature(
        "plugins",
        "Система плагинов",
        FeatureStatus.ALPHA,
        "medium"
    ),
    "sequencer": Feature(
        "sequencer",
        "Sequencer — анализ случайности токенов",
        FeatureStatus.BETA,
        "medium"
    ),
    "passive_scanner": Feature(
        "passive_scanner",
        "Passive Scanner — фоновый анализ трафика",
        FeatureStatus.BETA,
        "medium"
    ),
    "turbo_mode": Feature(
        "turbo_mode",
        "Turbo Mode Intruder (10x ускорение)",
        FeatureStatus.BETA,
        "medium"
    ),

    # ────────────────────────────────────────────────────────────────────
    # FULL PLAN — enterprise возможности
    # ────────────────────────────────────────────────────────────────────
    "ai_analysis": Feature(
        "ai_analysis",
        "AI-анализ уязвимостей (GPT-4)",
        FeatureStatus.ALPHA,
        "full"
    ),
    "pro_reports": Feature(
        "pro_reports",
        "PRO отчёты (HTML/PDF/JSON)",
        FeatureStatus.ALPHA,
        "full"
    ),
    "collaboration": Feature(
        "collaboration",
        "Совместная работа над проектами",
        FeatureStatus.ALPHA,
        "full"
    ),
    "api_access": Feature(
        "api_access",
        "REST API для автоматизации",
        FeatureStatus.BETA,
        "full"
    ),
    "custom_scanner_checks": Feature(
        "custom_scanner_checks",
        "Кастомные проверки Scanner",
        FeatureStatus.ALPHA,
        "full"
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# LIMITS — лимиты по планам
# ═══════════════════════════════════════════════════════════════════════

LIMITS = {
    # История запросов
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

    # Проекты
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
# PLAN NAMES — человекочитаемые названия планов
# ═══════════════════════════════════════════════════════════════════════

PLAN_NAMES = {
    "free": "Free",
    "lite": "Lite",
    "medium": "Medium",
    "full": "Full (PRO)",
}


PLAN_DESCRIPTIONS = {
    "free": "Базовые инструменты для тестирования",
    "lite": "Расширенные возможности для профессионалов",
    "medium": "Продвинутые инструменты + плагины",
    "full": "Enterprise функции + AI + API",
}


# ═══════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def has_feature(feature_name: str, plan: str) -> bool:
    """Проверить, доступна ли фича для указанного плана.

    Args:
        feature_name: Название фичи (ключ из FEATURES)
        plan: Название плана ("free", "lite", "medium", "full")

    Returns:
        True если фича доступна для этого плана
    """
    feature = FEATURES.get(feature_name)
    if not feature:
        return False

    # Порядок планов от младшего к старшему
    plan_order = ["free", "lite", "medium", "full"]

    # Если текущий план >= требуемого плана, фича доступна
    try:
        current_level = plan_order.index(plan.lower())
        required_level = plan_order.index(feature.required_plan)
        return current_level >= required_level
    except (ValueError, AttributeError):
        return False


def get_limit(limit_name: str, plan: str, default: int = 0) -> int | list:
    limits = LIMITS.get(limit_name, {})
    return limits.get(plan.lower(), default)


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
