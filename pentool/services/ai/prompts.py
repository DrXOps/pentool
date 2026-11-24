"""AI task prompt registry.

Each AITask defines:
- name — unique task identifier
- system_prompt — system prompt for the LLM
- expected_json_schema — optional JSON schema for response validation
- max_tokens — max response tokens
- temperature — generation temperature
"""

from __future__ import annotations

from dataclasses import dataclass
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
_register(
    AITask(
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
    )
)

# === 2. AI check selection: choose relevant checks for the target ===
_register(
    AITask(
        name="choose_checks",
        system_prompt=(
            "You are a penetration tester. Analyze the target data (URL, technology stack, "
            "forms, parameters, JS files) and select the most relevant checks from the "
            "available list. Return a JSON array of objects:\n"
            "- check_name: the check name (exactly from the provided list)\n"
            '- priority: "high" | "medium" | "low"\n'
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
    )
)

# === 3. AI crawling: discover non-obvious endpoints ===
_register(
    AITask(
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
            'confidence: high | medium | low. path is required, starts with "/".\n\n'
            "Full response example:\n"
            '[{"method":"GET","path":"/api/user","params":"id=1","confidence":"high","reason":"api"},'
            '{"method":"POST","path":"/graphql","params":"","confidence":"medium","reason":"graphql"}]\n\n'
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
    )
)

# === 4. Finding analysis: classify TP vs FP ===
_register(
    AITask(
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
    )
)

# === 5. AI payload generation: context-aware payloads ===
_register(
    AITask(
        name="generate_payloads",
        system_prompt=(
            "You are a penetration tester. Given a target URL, a parameter name, "
            "its current value, and the detected technology stack, generate up to 10 "
            "realistic vulnerability-specific payloads tailored to this exact context. "
            "The goal is to find reflected XSS, SQL injection, or other injection points.\n\n"
            "Rules:\n"
            "- Payloads must be context-aware: if the parameter expects a number, "
            "use numeric variants; if it expects a string with HTML, use HTML variants.\n"
            "- Do NOT include generic test payloads — only ones that stand a realistic "
            "chance of triggering a vulnerability in the given tech stack.\n"
            "- If the context is unclear, provide a mix of common injection types.\n\n"
            "Return a JSON array of objects. NO text outside JSON:\n"
            '- {{"payload": "...", "description": "short context note", "confidence": "high"}}\n'
            "confidence: high | medium | low."
        ),
        expected_json_schema={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "payload": {"type": "string"},
                    "description": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["payload", "description", "confidence"],
            },
        },
        max_tokens=1024,
        temperature=0.3,
    )
)

# === 6. Parameter prioritization: which params to scan first ===
_register(
    AITask(
        name="prioritize_params",
        system_prompt=(
            "You are a penetration tester. Given a list of URL parameters, their current "
            "values, and the technology stack, rank them by how likely they are to be "
            "vulnerable. Consider: reflecting input, database interaction, file paths, "
            "admin functionality.\n\n"
            "Return a JSON array of objects, ordered by priority (highest first):\n"
            '- {{"param": "search", "priority": "high", "reason": "reflects user input"}}\n'
            "priority: high | medium | low."
        ),
        expected_json_schema={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "param": {"type": "string"},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reason": {"type": "string"},
                },
                "required": ["param", "priority", "reason"],
            },
        },
        max_tokens=512,
        temperature=0.1,
    )
)

# === 7. Discovery: subdomains and endpoints (Recon) ===
# One task serves both jobs because the Recon modules build their own instruction text
# (``pro/pentool/modules/ai_discovery/prompts.py``) and pass it through ``context``.
# Before this task existed every Recon AI call ended with "unknown task 'discovery'",
# MCPBackend returned None, and the AI half of Recon never produced a candidate.
# Kept after the migration below: end users can run a PRO package older than this
# client, and those builds still ask for the catch-all name.
_register(
    AITask(
        name="discovery",
        system_prompt=(
            "You are a web security testing assistant. Follow the instruction block in the "
            "context and answer with exactly what it asks for: a JSON array, no markdown, "
            "no commentary. For subdomains return their names; for endpoints return objects "
            'with "method" and "path".'
        ),
        expected_json_schema={"type": "array"},
        max_tokens=1024,
        temperature=0.4,
    )
)

# === 8. Discovery, one task per question ===
# Recon used to keep its prompt text inside the PRO package, so the registry — the
# contract every ``generate()`` call is checked against — did not know these tasks and
# the same wording lived in two repositories. The texts belong here; callers pass
# structured context only.
_register(
    AITask(
        name="discovery_subdomains",
        system_prompt=(
            "You are a web security testing assistant. Given a domain, suggest subdomains "
            "that plausibly exist: common service names (api, admin, dev, staging, mail, "
            "vpn, cdn, static, docs) and names typical for the domain's industry.\n"
            "Return ONLY a JSON array of strings like "
            '["api.example.com", "admin.example.com"], at most 50, no markdown.'
        ),
        expected_json_schema={"type": "array", "items": {"type": "string"}},
        max_tokens=768,
        temperature=0.4,
    )
)

_register(
    AITask(
        name="discovery_endpoints",
        system_prompt=(
            "You are a web security testing assistant. Given a target URL, its technology "
            "stack and already known paths, suggest paths that probably exist but are not "
            "linked from the visible pages (framework routes, API versions, admin panels).\n"
            "Return ONLY a JSON array of objects, at most 20, no markdown:\n"
            '[{"method": "GET", "path": "/api/v1/users", "reason": "REST API"}]'
        ),
        expected_json_schema={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "path": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["method", "path"],
            },
        },
        max_tokens=1024,
        temperature=0.3,
    )
)

_register(
    AITask(
        name="discovery_params",
        system_prompt=(
            "You are a web security testing assistant. Given endpoints of a target, suggest "
            "query parameters that might enable hidden functionality, debug modes or admin "
            "features.\n"
            "Return ONLY a JSON array of [param, value] pairs, no explanation: "
            '[["debug", "1"], ["admin", "true"]]'
        ),
        expected_json_schema={
            "type": "array",
            "items": {"type": "array", "items": {"type": "string"}},
        },
        max_tokens=512,
        temperature=0.4,
    )
)

_register(
    AITask(
        name="discovery_param_fuzz",
        system_prompt=(
            "You are a web security testing assistant. Given endpoints of a target, suggest "
            "query parameters worth fuzzing for hidden functionality.\n"
            "Return ONLY a JSON array of [param, value, description] triples, no "
            'explanation: [["debug", "1", "turns on debug output"]]'
        ),
        expected_json_schema={
            "type": "array",
            "items": {"type": "array", "items": {"type": "string"}},
        },
        max_tokens=768,
        temperature=0.4,
    )
)
