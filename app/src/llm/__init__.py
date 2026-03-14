from app.src.context import ChannelContext
from app.src.llm.gemini import GeminiBackend
from app.src.llm.openai import OpenAIBackend
from app.src.llm.local import LocalBackend


class LLMClient:
    """Factory — reads provider and returns the appropriate backend instance."""
    def __new__(cls, provider: str, config: dict, tools_config: dict, bot_nick: str = ""):
        if provider == 'gemini':
            context = ChannelContext(bot_nick)
            return GeminiBackend(config, tools_config, context)
        elif provider == 'openai':
            return OpenAIBackend(config, tools_config)
        elif provider == 'local':
            return LocalBackend(config)
        raise ValueError(f"Unknown provider: {provider}")
