from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AIResponse:
    content: str
    model: str | None = None
    usage: dict[str, int] | None = None


class AIClient(Protocol):
    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> AIResponse:
        """Generate a response without exposing provider-specific details."""
