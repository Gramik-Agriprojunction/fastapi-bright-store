from app.core.config import Settings
from app.integrations.ai.contracts import AIClient, AIResponse


class DisabledAIClient:
    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AIResponse:
        raise RuntimeError("AI integration is not configured")


def get_ai_client(settings: Settings) -> AIClient:
    """Return the configured provider adapter.

    Provider SDKs belong in adapter modules and should never leak into
    domain services or API endpoints.
    """
    if settings.ai_provider == "none":
        return DisabledAIClient()
    raise ValueError(f"Unsupported AI provider: {settings.ai_provider}")
