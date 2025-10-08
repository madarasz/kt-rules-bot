"""Configuration management for the application.

Loads environment variables and provides validated Config dataclass.
Based on specs/001-we-are-building/tasks.md T026
"""

from dataclasses import dataclass
from typing import Literal, Optional
from pathlib import Path
import os
from dotenv import load_dotenv

from src.lib.constants import EMBEDDING_MODEL


LLMProvider = Literal[
    "claude-sonnet",
    "claude-opus",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gpt-5",
    "gpt-5-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "o3",
    "o3-mini",
    "o4-mini",
]


@dataclass
class Config:
    """Application configuration."""

    # Discord
    discord_bot_token: str

    # LLM Providers
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None

    # LLM Selection
    default_llm_provider: LLMProvider = os.getenv("DEFAULT_LLM_PROVIDER", "gpt-4.1") 

    # RAG Configuration
    vector_db_path: str = "./data/chroma_db"
    embedding_model: str = EMBEDDING_MODEL

    # Logging
    log_level: str = "INFO"

    # GDPR
    retention_days: int = 7

    # Performance
    max_concurrent_users: int = 5
    response_timeout_seconds: int = 30

    def validate(self) -> None:
        """Validate configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        # Discord token required
        if not self.discord_bot_token:
            raise ValueError("DISCORD_BOT_TOKEN is required")

        # At least one LLM provider API key required
        has_provider = any(
            [
                self.anthropic_api_key,
                self.openai_api_key,
                self.google_api_key,
            ]
        )
        if not has_provider:
            raise ValueError("At least one LLM provider API key is required")

        # Validate default provider has API key
        provider_key_mapping = {
            "claude-sonnet": self.anthropic_api_key,
            "claude-opus": self.anthropic_api_key,
            "gemini-2.5-pro": self.google_api_key,
            "gemini-2.5-flash": self.google_api_key,
            "gpt-5": self.openai_api_key,
            "gpt-5-mini": self.openai_api_key,
            "gpt-4.1": self.openai_api_key,
            "gpt-4.1-mini": self.openai_api_key,
            "gpt-4o": self.openai_api_key,
            "o3": self.openai_api_key,
            "o3-mini": self.openai_api_key,
            "o4-mini": self.openai_api_key,
        }

        if not provider_key_mapping.get(self.default_llm_provider):
            raise ValueError(
                f"API key for default model '{self.default_llm_provider}' is missing"
            )

        # Validate log level
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_levels:
            raise ValueError(
                f"log_level must be one of: {', '.join(valid_levels)}"
            )

        # Validate retention days
        if self.retention_days < 1 or self.retention_days > 30:
            raise ValueError("retention_days must be between 1 and 30")

        # Validate concurrent users
        if self.max_concurrent_users < 1:
            raise ValueError("max_concurrent_users must be at least 1")

        # Validate timeout
        if self.response_timeout_seconds < 5:
            raise ValueError("response_timeout_seconds must be at least 5")

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "Config":
        """Load configuration from environment variables.

        Args:
            env_file: Optional path to .env file

        Returns:
            Config instance

        Raises:
            ValueError: If configuration is invalid
        """
        # Load .env file if specified
        if env_file:
            load_dotenv(env_file)
        else:
            # Try to load from default locations
            for path in ["config/.env", ".env"]:
                if Path(path).exists():
                    load_dotenv(path)
                    break

        config = cls(
            # Discord
            discord_bot_token=os.getenv("DISCORD_BOT_TOKEN", ""),
            # LLM Providers
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            # LLM Selection
            default_llm_provider=os.getenv("DEFAULT_LLM_PROVIDER", "claude-sonnet"),  # type: ignore
            # RAG
            vector_db_path=os.getenv("VECTOR_DB_PATH", "./data/chroma_db"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            # Logging
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            # GDPR
            retention_days=int(os.getenv("RETENTION_DAYS", "7")),
            # Performance
            max_concurrent_users=int(os.getenv("MAX_CONCURRENT_USERS", "5")),
            response_timeout_seconds=int(
                os.getenv("RESPONSE_TIMEOUT_SECONDS", "30")
            ),
        )

        config.validate()
        return config


# Global config instance (loaded on import)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global config instance.

    Returns:
        Config instance
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_config(config: Config) -> None:
    """Set global config instance (for testing).

    Args:
        config: Config instance
    """
    global _config
    _config = config
