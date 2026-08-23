"""AI task prompt registry.

Each AITask defines:
- name — unique task identifier
- system_prompt — system prompt for the LLM
- expected_json_schema — optional JSON schema for response validation
- max_tokens — max response tokens
- temperature — generation temperature
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AITask:
    """One AI task definition (prompt + parameters)."""

    name: str
    system_prompt: str
    expected_json_schema: dict[str, Any] | None = None
    max_tokens: int = 1024
    temperature: float = 0.3


# ── Task registry ───────────────────────────────────────────────────────────
REGISTRY: dict[str, AITask] = {}


def _register(task: AITask) -> None:
    REGISTRY[task.name] = task


# === 1. WAF bypass: generate obfuscated XSS payloads ===
_register(AITask(
    name="xss_waf_bypass",
    system_prompt=(
        "You are a penetration tester. Your task is to generate obfuscated XSS payloads "
        "that bypass WAF. Analyze the provided context: detected WAF type, "
        "filtered characters/keywords, and the original payload. "
        "Return a JSON array of objects with:\n"
        "- payload: the obfuscated payload string\n"
        "- technique: short description of the bypass technique\n"
        "- expected_tag: expected reflection marker (substring to check against)\n\n"
        "Do not include any text outside the JSON."
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

# === 2. AI check selection: choose relevant checks for the target ===
_register(AITask(
    name="choose_checks",
    system_prompt=(
        "You are a penetration tester. Analyze the target data (URL, technology stack, "
        "forms, parameters, JS files) and select the most relevant checks from the "
        "available list. Return a JSON array of objects:\n"
        "- check_name: the check name (exactly from the provided list)\n"
        "- priority: \"high\" | \"medium\" | \"low\"\n"
        "- reason: why this check is relevant\n\n"
        "If there is not enough data, return an empty array. Do not invent checks "
        "that are not in the list."
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

# === 3. AI crawling: discover non-obvious endpoints ===
_register(AITask(
    name="crawl_endpoints",
    system_prompt=(
        "You are a penetration tester. Analyze the provided web application data: "
        "base URL, already discovered links, forms, JS fragments, API paths. "
        "Try to find non-obvious endpoints, hidden parameters, "
        "undocumented APIs, path-traversal candidates, potential "
        "GraphQL introspection points.\n\n"
        "Return ONLY a compact JSON array. NO explanations, NO markdown, "
        "NO text around the JSON. Each object format:\n"
        '{"method":"GET","path":"/admin","params":"","confidence":"high",'
        '"reason":"admin panel"}\n'
        "Allowed methods: GET | POST | PUT | DELETE. "
        "confidence: high | medium | low. path is required, starts with \"/\".\n\n"
        "Full response example:\n"
        '[{"method":"GET","path":"/api/user","params":"id=1","confidence":"high","reason":"api"},{"method":"POST","path":"/graphql","params":"","confidence":"medium","reason":"graphql"}]\n\n'
        "Do not make up obviously non-existent paths. Only reasonable guesses. "
        "If no suitable endpoints exist, return an empty array []."
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
    temperature=0.1,
))

# === 4. Finding analysis: classify TP vs FP ===
_register(AITask(
    name="finding_analysis",
    system_prompt=(
        "You are a penetration tester. Analyze the discovered vulnerability and determine: "
        "whether it is a true positive (TP) or false positive (FP). "
        "Consider request/response context, escaping, Content-Type, "
        "WAF blocking. Return JSON:\n"
        "- is_vulnerable: true | false\n"
        "- confidence: 0.0–1.0\n"
        "- reason: brief justification"
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