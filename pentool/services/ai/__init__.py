"""AI-сервис: промпт-реестр, провайдер, фабрика."""

from pentool.services.ai.factory import (  # noqa: F401
    ai_setup_required,
    get_active_backend,
    get_ai,
    is_ai_running,
    start_ai,
    stop_ai,
)
from pentool.services.ai.prompts import REGISTRY, AITask  # noqa: F401
from pentool.services.ai.provider import AIBackend, MCPBackend  # noqa: F401
