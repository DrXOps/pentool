"""AI-сервис: промпт-реестр, провайдер, фабрика."""

from pentool.services.ai.prompts import AITask, REGISTRY  # noqa: F401
from pentool.services.ai.provider import AIBackend, MCPBackend  # noqa: F401
from pentool.services.ai.factory import get_ai, ai_setup_required  # noqa: F401
