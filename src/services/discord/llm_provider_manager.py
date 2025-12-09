"""LLM provider management for per-server configuration."""

from src.lib.logging import get_logger
from src.lib.server_config import get_multi_server_config
from src.services.llm.factory import LLMProviderFactory

logger = get_logger(__name__)


class LLMProviderManager:
    """Manages LLM provider creation for per-server configurations."""

    # Maps provider prefix to required API key name
    PROVIDER_TO_KEY = {
        "claude": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "gpt": "OPENAI_API_KEY",
        "o3": "OPENAI_API_KEY",
        "o4": "OPENAI_API_KEY",
        "grok": "X_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "dial": "DIAL_API_KEY",
        "mistral": "MISTRAL_API_KEY",
    }

    def __init__(self, llm_factory: LLMProviderFactory):
        """Initialize provider manager.

        Args:
            llm_factory: LLM provider factory instance
        """
        self.llm_factory = llm_factory

    def create_provider(self, guild_id: str | None, correlation_id: str) -> tuple:
        """Create LLM provider for a guild, handling errors.

        Args:
            guild_id: Discord guild ID (None for DMs)
            correlation_id: Correlation ID for logging

        Returns:
            Tuple of (llm_provider, error_message)
            If successful: (provider, None)
            If failed: (None, error_message)
        """
        try:
            llm = self.llm_factory.create(guild_id=guild_id)

            if llm is None:
                error_message = self._get_missing_key_error(guild_id)
                logger.warning(
                    "LLM provider creation failed",
                    extra={"correlation_id": correlation_id, "guild_id": guild_id},
                )
                return None, error_message

            return llm, None

        except Exception as e:
            logger.error(
                f"Error creating LLM provider: {e}",
                extra={"correlation_id": correlation_id, "guild_id": guild_id},
                exc_info=True,
            )
            return None, "❌ Failed to create LLM provider. Please check server configuration."

    def _get_missing_key_error(self, guild_id: str | None) -> str:
        """Get error message for missing API key.

        Args:
            guild_id: Discord guild ID (None for DMs)

        Returns:
            Error message string
        """
        multi_server_config = get_multi_server_config()
        server_config = multi_server_config.get_server_config(guild_id) if guild_id else None

        if server_config:
            # Extract provider type from llm_provider (e.g., "claude-4.5-sonnet" → "claude")
            provider_type = server_config.llm_provider.split("-")[0].lower()
            missing_key = self.PROVIDER_TO_KEY.get(provider_type, "API_KEY")
            return f"❌ Missing API key: {missing_key}"
        else:
            return "❌ Missing Discord server configuration."
