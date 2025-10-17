"""LLM provider factory.

Creates LLM provider instances based on configuration.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

from src.services.llm.base import LLMProvider
from src.services.llm.claude import ClaudeAdapter
from src.services.llm.chatgpt import ChatGPTAdapter
from src.services.llm.gemini import GeminiAdapter
from src.services.llm.grok import GrokAdapter
from src.services.llm.dial import DialAdapter
from src.lib.config import get_config
from src.lib.logging import get_logger
from src.lib.constants import LLM_PROVIDERS_LITERAL

logger = get_logger(__name__)

class LLMProviderFactory:
    """Factory for creating LLM provider instances."""

    # Model name to (adapter_class, actual_model_id, api_key_type) mapping
    _model_registry = {
        "claude-sonnet": (ClaudeAdapter, "claude-sonnet-4-5-20250929", "anthropic"),
        "claude-opus": (ClaudeAdapter, "claude-opus-4-1-20250805", "anthropic"),
        "gemini-2.5-pro": (GeminiAdapter, "gemini-2.5-pro", "google"),
        "gemini-2.5-flash": (GeminiAdapter, "gemini-2.5-flash", "google"),
        "gpt-5": (ChatGPTAdapter, "gpt-5", "openai"),
        "gpt-5-mini": (ChatGPTAdapter, "gpt-5-mini", "openai"),
        "gpt-4.1": (ChatGPTAdapter, "gpt-4.1", "openai"),
        "gpt-4.1-mini": (ChatGPTAdapter, "gpt-4.1-mini", "openai"),
        "gpt-4o": (ChatGPTAdapter, "gpt-4o", "openai"),
        "o3": (ChatGPTAdapter, "o3", "openai"),
        "o3-mini": (ChatGPTAdapter, "o3-mini", "openai"),
        "o4-mini": (ChatGPTAdapter, "o4-mini", "openai"),
        "grok-4-fast-reasoning": (GrokAdapter, "grok-4-fast-reasoning", "x"),
        "grok-4-0709": (GrokAdapter, "grok-4-0709", "x"),
        "grok-3": (GrokAdapter, "grok-3", "x"),
        "grok-3-mini": (GrokAdapter, "grok-3-mini", "x"),
        "dial-gpt-4o": (DialAdapter, "gpt-4o", "dial"),
        "dial-gpt-4.1": (DialAdapter, "gpt-4.1-2025-04-14", "dial"),
        "dial-gpt-5": (DialAdapter, "gpt-5-2025-08-07", "dial"),
        "dial-gpt-5-chat": (DialAdapter, "gpt-5-chat-2025-08-07", "dial"),
        "dial-gpt-5-mini": (DialAdapter, "gpt-5-mini-2025-08-07", "dial"),
        "dial-gpt-o3": (DialAdapter, "o3-2025-04-16", "dial"),
        "dial-sonet-4.5": (DialAdapter, "anthropic.claude-sonnet-4-5-20250929-v1:0", "dial"),
        "dial-sonet-4.5-thinking": (DialAdapter, "anthropic.claude-sonnet-4-5-20250929-v1:0-with-thinking", "dial"),
        "dial-opus-4.1": (DialAdapter, "anthropic.claude-opus-4-1-20250805-v1:0", "dial"),
        "dial-opus-4.1-thinking": (DialAdapter, "anthropic.claude-opus-4-1-20250805-v1:0-with-thinking", "dial"),
        "dial-amazon-nova-pro": (DialAdapter, "amazon.nova-pro-v1", "dial"),
        "dial-amazon-titan": (DialAdapter, "amazon.titan-tg1-large", "dial"),
        "dial-gemini-2.5-pro": (DialAdapter, "gemini-2.5-pro", "dial"),
        "dial-gemini-2.5-flash": (DialAdapter, "gemini-2.5-flash", "dial"),
    }

    @classmethod
    def create(cls, provider_name: LLM_PROVIDERS_LITERAL = None) -> LLMProvider:
        """Create LLM provider instance.

        Args:
            provider_name: Model to use (claude-sonnet, gemini-2.5-pro, gpt-4o, etc.).
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
            provider_name = config.default_llm_provider

        # Validate provider name
        if provider_name not in cls._model_registry:
            raise ValueError(
                f"Invalid model: {provider_name}. "
                f"Must be one of: {', '.join(cls._model_registry.keys())}"
            )

        # Get adapter class, model ID, and API key type
        adapter_class, model_id, api_key_type = cls._model_registry[provider_name]

        # Get API key from config
        api_key_map = {
            "anthropic": config.anthropic_api_key,
            "openai": config.openai_api_key,
            "google": config.google_api_key,
            "x": config.x_api_key,
            "dial": config.dial_api_key,
        }

        api_key = api_key_map[api_key_type]

        if not api_key:
            api_key_env_map = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "google": "GOOGLE_API_KEY",
                "x": "X_API_KEY",
                "dial": "DIAL_API_KEY",
            }
            raise KeyError(
                f"API key not found: {api_key_env_map[api_key_type]}. "
                f"Set it in your environment or .env file."
            )

        # Create provider instance
        provider = adapter_class(api_key=api_key, model=model_id)

        logger.info(f"Created {provider_name} with model {model_id}")

        return provider

    @classmethod
    def get_available_providers(cls) -> list:
        """Get list of available model names.

        Returns:
            List of model names
        """
        return list(cls._model_registry.keys())

def get_provider(provider_name: LLM_PROVIDERS_LITERAL = None) -> LLMProvider:
    """Convenience function to get LLM provider.

    Args:
        provider_name: Provider to use (claude/chatgpt/gemini)

    Returns:
        LLMProvider instance
    """
    return LLMProviderFactory.create(provider_name)
