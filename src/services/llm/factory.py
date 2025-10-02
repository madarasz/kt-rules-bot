"""LLM provider factory.

Creates LLM provider instances based on configuration.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

from typing import Literal

from src.services.llm.base import LLMProvider
from src.services.llm.claude import ClaudeAdapter
from src.services.llm.chatgpt import ChatGPTAdapter
from src.services.llm.gemini import GeminiAdapter
from src.lib.config import get_config
from src.lib.logging import get_logger

logger = get_logger(__name__)

ProviderName = Literal["claude", "chatgpt", "gemini"]


class LLMProviderFactory:
    """Factory for creating LLM provider instances."""

    _providers = {
        "claude": ClaudeAdapter,
        "chatgpt": ChatGPTAdapter,
        "gemini": GeminiAdapter,
    }

    @classmethod
    def create(cls, provider_name: ProviderName = None) -> LLMProvider:
        """Create LLM provider instance.

        Args:
            provider_name: Provider to use (claude/chatgpt/gemini).
                          If None, uses DEFAULT_LLM_PROVIDER from config.

        Returns:
            LLMProvider instance

        Raises:
            ValueError: If provider name is invalid
            KeyError: If API key not found in environment
        """
        config = get_config()

        # Use default provider if not specified
        if provider_name is None:
            provider_name = config.get("DEFAULT_LLM_PROVIDER", "claude")

        # Validate provider name
        if provider_name not in cls._providers:
            raise ValueError(
                f"Invalid provider: {provider_name}. "
                f"Must be one of: {', '.join(cls._providers.keys())}"
            )

        # Get API key from environment
        api_key_map = {
            "claude": "ANTHROPIC_API_KEY",
            "chatgpt": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
        }

        api_key_env = api_key_map[provider_name]
        api_key = config.get(api_key_env)

        if not api_key:
            raise KeyError(
                f"API key not found: {api_key_env}. "
                f"Set it in your environment or .env file."
            )

        # Get model from config or use defaults
        model_defaults = {
            "claude": "claude-3-sonnet-20240229",
            "chatgpt": "gpt-4-turbo",
            "gemini": "gemini-1.5-pro",
        }

        model = config.get(f"{provider_name.upper()}_MODEL", model_defaults[provider_name])

        # Create provider instance
        provider_class = cls._providers[provider_name]
        provider = provider_class(api_key=api_key, model=model)

        logger.info(f"Created {provider_name} provider with model {model}")

        return provider

    @classmethod
    def get_available_providers(cls) -> list:
        """Get list of available provider names.

        Returns:
            List of provider names
        """
        return list(cls._providers.keys())


def get_provider(provider_name: ProviderName = None) -> LLMProvider:
    """Convenience function to get LLM provider.

    Args:
        provider_name: Provider to use (claude/chatgpt/gemini)

    Returns:
        LLMProvider instance
    """
    return LLMProviderFactory.create(provider_name)
