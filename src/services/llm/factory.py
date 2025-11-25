"""LLM provider factory.

Creates LLM provider instances based on configuration.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

from src.lib.config import get_config
from src.lib.constants import LLM_PROVIDERS_LITERAL
from src.lib.logging import get_logger
from src.lib.server_config import get_multi_server_config
from src.services.llm.base import LLMProvider
from src.services.llm.chatgpt import ChatGPTAdapter
from src.services.llm.claude import ClaudeAdapter
from src.services.llm.deepseek import DeepSeekAdapter
from src.services.llm.dial import DialAdapter
from src.services.llm.gemini import GeminiAdapter
from src.services.llm.grok import GrokAdapter

logger = get_logger(__name__)


class LLMProviderFactory:
    """Factory for creating LLM provider instances."""

    # Model name to (adapter_class, actual_model_id, api_key_type) mapping
    _model_registry = {
        "claude-4.5-sonnet": (ClaudeAdapter, "claude-sonnet-4-5-20250929", "anthropic"),
        "claude-4.5-opus": (ClaudeAdapter, "claude-opus-4-5-20251101", "anthropic"),
        "claude-4.1-opus": (ClaudeAdapter, "claude-opus-4-1-20250805", "anthropic"),
        "claude-4.5-haiku": (ClaudeAdapter, "claude-haiku-4-5-20251001", "anthropic"),
        "gemini-3-pro-preview": (GeminiAdapter, "gemini-3-pro-preview", "google"),
        "gemini-2.5-pro": (GeminiAdapter, "gemini-2.5-pro", "google"),
        "gemini-2.5-flash": (GeminiAdapter, "gemini-2.5-flash", "google"),
        "gpt-5.1": (ChatGPTAdapter, "gpt-5.1", "openai"),
        "gpt-5.1-chat-latest": (ChatGPTAdapter, "gpt-5.1-chat-latest", "openai"),
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
        "deepseek-chat": (DeepSeekAdapter, "deepseek-chat", "deepseek"),
        "deepseek-reasoner": (DeepSeekAdapter, "deepseek-reasoner", "deepseek"),
        "dial-gpt-4o": (DialAdapter, "gpt-4o", "dial"),
        "dial-gpt-4.1": (DialAdapter, "gpt-4.1-2025-04-14", "dial"),
        "dial-gpt-5": (DialAdapter, "gpt-5-2025-08-07", "dial"),
        "dial-gpt-5-chat": (DialAdapter, "gpt-5-chat-2025-08-07", "dial"),
        "dial-gpt-5-mini": (DialAdapter, "gpt-5-mini-2025-08-07", "dial"),
        "dial-gpt-o3": (DialAdapter, "o3-2025-04-16", "dial"),
        "dial-sonet-4.5": (DialAdapter, "anthropic.claude-sonnet-4-5-20250929-v1:0", "dial"),
        "dial-sonet-4.5-thinking": (
            DialAdapter,
            "anthropic.claude-sonnet-4-5-20250929-v1:0-with-thinking",
            "dial",
        ),
        "dial-opus-4.1": (DialAdapter, "anthropic.claude-opus-4-1-20250805-v1:0", "dial"),
        "dial-opus-4.1-thinking": (
            DialAdapter,
            "anthropic.claude-opus-4-1-20250805-v1:0-with-thinking",
            "dial",
        ),
        "dial-amazon-nova-pro": (DialAdapter, "amazon.nova-pro-v1", "dial"),
        "dial-amazon-titan": (DialAdapter, "amazon.titan-tg1-large", "dial"),
        "dial-gemini-2.5-pro": (DialAdapter, "gemini-2.5-pro", "dial"),
        "dial-gemini-2.5-flash": (DialAdapter, "gemini-2.5-flash", "dial"),
    }

    @classmethod
    def create(
        cls, provider_name: LLM_PROVIDERS_LITERAL = None, guild_id: str | None = None
    ) -> LLMProvider:
        """Create LLM provider instance.

        Args:
            provider_name: Model to use (claude-sonnet, gemini-2.5-pro, gpt-4o, etc.).
                          If None, uses DEFAULT_LLM_PROVIDER from config.
            guild_id: Discord guild (server) ID for per-server API key resolution.
                     If None, uses global .env config only.

        Returns:
            LLMProvider instance

        Raises:
            ValueError: If provider name is invalid
            KeyError: If API key not found in environment
        """
        config = get_config()
        multi_server_config = get_multi_server_config()

        # Get server-specific config if guild_id provided
        server_config = multi_server_config.get_server_config(guild_id) if guild_id else None

        # Log config resolution for debugging
        if guild_id:
            if server_config:
                logger.debug(
                    f"Using server config for guild {guild_id} ({server_config.name if server_config.name else 'unnamed'})"
                )
            else:
                logger.debug(f"Guild {guild_id} not in servers.yaml, using global .env config")

        # Use default provider if not specified (check server override first)
        if provider_name is None:
            if server_config and server_config.llm_provider:
                provider_name = server_config.llm_provider
            else:
                provider_name = config.default_llm_provider

        # Validate provider name
        if provider_name not in cls._model_registry:
            raise ValueError(
                f"Invalid model: {provider_name}. "
                f"Must be one of: {', '.join(cls._model_registry.keys())}"
            )

        # Get adapter class, model ID, and API key type
        adapter_class, model_id, api_key_type = cls._model_registry[provider_name]

        # Resolve API key based on whether server is configured
        api_key = None

        if server_config:
            # Server defined in servers.yaml - use ONLY server keys (no .env fallback)
            server_api_key_map = {
                "anthropic": server_config.anthropic_api_key,
                "openai": server_config.openai_api_key,
                "google": server_config.google_api_key,
                "x": server_config.x_api_key,
                "dial": server_config.dial_api_key,
                "deepseek": server_config.deepseek_api_key,
            }
            api_key = server_api_key_map.get(api_key_type)
        else:
            # No server config - fall back to global .env keys
            global_api_key_map = {
                "anthropic": config.anthropic_api_key,
                "openai": config.openai_api_key,
                "google": config.google_api_key,
                "x": config.x_api_key,
                "dial": config.dial_api_key,
                "deepseek": config.deepseek_api_key,
            }
            api_key = global_api_key_map.get(api_key_type)

        # If API key is missing, return None instead of throwing
        # The bot will handle this gracefully and send a Discord message
        if not api_key:
            api_key_env_map = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "google": "GOOGLE_API_KEY",
                "x": "X_API_KEY",
                "dial": "DIAL_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
            }

            missing_key = api_key_env_map[api_key_type]

            logger.error(
                f"Missing API key for {provider_name}: {missing_key} "
                f"(guild_id: {guild_id}, server_config: {bool(server_config)})"
            )

            # Return None - let the bot handle this gracefully
            return None

        # Create provider instance
        provider = adapter_class(api_key=api_key, model=model_id)

        log_msg = f"Created {provider_name} with model {model_id}"
        if guild_id:
            guild_name = f" ({server_config.name})" if server_config and server_config.name else ""
            log_msg += f" for guild {guild_id}{guild_name}"
        logger.info(log_msg)

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
