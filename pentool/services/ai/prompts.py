"""Промпт-реестр AI-задач.

Каждая задача (AITask) содержит:
- name — уникальное имя задачи
- system_prompt — системный промпт для LLM
- expected_json_schema — ожидаемая JSON-схема ответа (опционально)
- max_tokens — макс. токенов в ответе
- temperature — температура генерации
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AITask:
    """Описание одной AI-задачи (промпт + параметры)."""

    name: str
    system_prompt: str
    expected_json_schema: dict[str, Any] | None = None
    max_tokens: int = 1024
    temperature: float = 0.3


# ── Реестр задач ────────────────────────────────────────────────────────────
REGISTRY: dict[str, AITask] = {}


def _register(task: AITask) -> None:
    REGISTRY[task.name] = task


# === 1. WAF-bypass: генерация обфусцированных XSS-payload'ов ===
_register(AITask(
    name="xss_waf_bypass",
    system_prompt=(
        "Ты — пентестер. Цель — сгенерировать обфусцированные XSS-payload'ы, "
        "которые обходят WAF. Анализируй переданный контекст: какой WAF обнаружен, "
        "какие символы/ключевые слова фильтруются, какой исходный payload. "
        "Верни JSON-массив объектов с полями:\n"
        "- payload: строка с обфусцированным payload'ом\n"
        "- technique: краткое описание техники обхода\n"
        "- expected_tag: ожидаемый маркер отражения (подстрока, по которой проверять)\n\n"
        "Не добавляй лишнего текста вне JSON."
    ),
    expected_json_schema={
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "payload": {"type": "string"},
                "technique": {"type": "string"},
                "expected_tag": {"type": "string"},
            },
            "required": ["payload", "technique", "expected_tag"],
        },
    },
    max_tokens=2048,
    temperature=0.7,
))

# === 2. AI-выбор чеков: какие чеки релевантны для цели ===
_register(AITask(
    name="choose_checks",
    system_prompt=(
        "Ты — пентестер. Проанализируй переданные данные о цели (URL, технологии, "
        "формы, параметры, JS-файлы) и выбери наиболее релевантные чеки из списка "
        "доступных. Верни JSON-массив объектов:\n"
        "- check_name: имя чека (строго из предоставленного списка)\n"
        "- priority: \"high\" | \"medium\" | \"low\"\n"
        "- reason: почему этот чек релевантен\n\n"
        "Если данных недостаточно — верни пустой массив. Не придумывай чеков, "
        "которых нет в списке."
    ),
    expected_json_schema={
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "check_name": {"type": "string"},
                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                "reason": {"type": "string"},
            },
            "required": ["check_name", "priority", "reason"],
        },
    },
    max_tokens=1024,
    temperature=0.2,
))

# === 3. AI-краулинг: поиск неочевидных эндпоинтов ===
_register(AITask(
    name="crawl_endpoints",
    system_prompt=(
        "Ты — пентестер. Проанализируй переданные данные о веб-приложении: "
        "базовый URL, уже найденные ссылки, формы, JS-фрагменты, API-пути. "
        "Попробуй найти неочевидные эндпоинты, скрытые параметры, "
        "недокументированные API, path-traversal кандидаты, возможные точки "
        "GraphQL-интроспекции.\n\n"
        "Верни JSON-массив объектов:\n"
        "- method: \"GET\" | \"POST\" | \"PUT\" | \"DELETE\"\n"
        "- path: предполагаемый путь\n"
        "- params: строка параметров (если есть)\n"
        "- confidence: \"high\" | \"medium\" | \"low\"\n"
        "- reason: почему этот эндпоинт может существовать\n\n"
        "Не выдумывай очевидно несуществующие пути. Только обоснованные догадки."
    ),
    expected_json_schema={
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "method": {"type": "string"},
                "path": {"type": "string"},
                "params": {"type": "string"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "reason": {"type": "string"},
            },
            "required": ["method", "path", "reason"],
        },
    },
    max_tokens=2048,
    temperature=0.4,
))

# === 4. Анализ находок (перенос из ai_analyzer) ===
_register(AITask(
    name="finding_analysis",
    system_prompt=(
        "Ты — пентестер. Проанализируй найденную уязвимость и определи: "
        "является ли она истинным срабатыванием (TP) или ложным (FP). "
        "Учитывай контекст запроса/ответа, экранирование, Content-Type, "
        "WAF-блокировку. Верни JSON:\n"
        "- is_vulnerable: true | false\n"
        "- confidence: 0.0–1.0\n"
        "- reason: краткое обоснование"
    ),
    expected_json_schema={
        "type": "object",
        "properties": {
            "is_vulnerable": {"type": "boolean"},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["is_vulnerable", "confidence", "reason"],
    },
    max_tokens=512,
    temperature=0.1,
))
