"""Configuration management for the application.

Loads environment variables and provides validated Config dataclass.
Based on specs/001-we-are-building/tasks.md T026
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from src.lib.constants import DEFAULT_LLM_PROVIDER, EMBEDDING_MODEL, LLM_PROVIDERS_LITERAL


@dataclass
class Config:
    """Application configuration."""

    # Discord
    discord_bot_token: str

    # LLM Providers
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    x_api_key: str | None = None
    dial_api_key: str | None = None
    deepseek_api_key: str | None = None

    # LLM Selection
    default_llm_provider: LLM_PROVIDERS_LITERAL = os.getenv(
        "DEFAULT_LLM_PROVIDER", DEFAULT_LLM_PROVIDER
    )  # type: ignore[assignment, arg-type]

    # RAG Configuration
    vector_db_path: str = "./data/chroma_db"
    embedding_model: str = EMBEDDING_MODEL
    rag_hop_evaluation_model: LLM_PROVIDERS_LITERAL | None = (
        None  # Model for multi-hop RAG evaluation (defaults to constant)
    )

    # Logging
    log_level: str = "INFO"

    # Bot Personality
    personality: str = "necron"

    # GDPR
    retention_days: int = 7

    # Performance
    max_concurrent_users: int = 5
    response_timeout_seconds: int = 30

    # Analytics Database (optional)
    enable_analytics_db: bool = False
    analytics_db_path: str = "./data/analytics.db"
    analytics_retention_days: int = 30
    admin_dashboard_password: str = ""

    # Multi-Server Configuration (optional)
    server_config_path: str = "./config/servers.yaml"

    def validate(self) -> None:
        """Validate configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        # Discord token required
        if not self.discord_bot_token:
            raise ValueError("DISCORD_BOT_TOKEN is required")

        # Validate default provider has API key

        # Validate log level
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of: {', '.join(valid_levels)}")

        # Validate retention days
        if self.retention_days < 1 or self.retention_days > 30:
            raise ValueError("retention_days must be between 1 and 30")

        # Validate concurrent users
        if self.max_concurrent_users < 1:
            raise ValueError("max_concurrent_users must be at least 1")

        # Validate timeout
        if self.response_timeout_seconds < 5:
            raise ValueError("response_timeout_seconds must be at least 5")

        # Validate personality directory exists
        personality_dir = Path(f"personality/{self.personality}")
        if not personality_dir.exists():
            raise ValueError(
                f"Personality directory not found: {personality_dir}\n"
                f"Available personalities should be in personality/ folder"
            )

        # Validate personality.yaml exists
        personality_file = personality_dir / "personality.yaml"
        if not personality_file.exists():
            raise ValueError(
                f"Personality configuration not found: {personality_file}\n"
                f"Each personality must have a personality.yaml file"
            )

        # Validate analytics DB settings
        if self.enable_analytics_db and not self.admin_dashboard_password:
            raise ValueError("ADMIN_DASHBOARD_PASSWORD is required when ENABLE_ANALYTICS_DB=true")

        if self.analytics_retention_days < 1:
            raise ValueError("analytics_retention_days must be at least 1")

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "Config":
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
            x_api_key=os.getenv("X_API_KEY"),
            dial_api_key=os.getenv("DIAL_API_KEY"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            # LLM Selection
            default_llm_provider=os.getenv("DEFAULT_LLM_PROVIDER", DEFAULT_LLM_PROVIDER),  # type: ignore
            # RAG
            vector_db_path=os.getenv("VECTOR_DB_PATH", "./data/chroma_db"),
            embedding_model=os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL),
            rag_hop_evaluation_model=os.getenv("RAG_HOP_EVALUATION_MODEL"),  # type: ignore
            # Logging
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            # Bot Personality
            personality=os.getenv("PERSONALITY", "necron"),
            # GDPR
            retention_days=int(os.getenv("RETENTION_DAYS", "7")),
            # Performance
            max_concurrent_users=int(os.getenv("MAX_CONCURRENT_USERS", "5")),
            response_timeout_seconds=int(os.getenv("RESPONSE_TIMEOUT_SECONDS", "30")),
            # Analytics Database
            enable_analytics_db=os.getenv("ENABLE_ANALYTICS_DB", "false").lower() == "true",
            analytics_db_path=os.getenv("ANALYTICS_DB_PATH", "./data/analytics.db"),
            analytics_retention_days=int(os.getenv("ANALYTICS_RETENTION_DAYS", "30")),
            admin_dashboard_password=os.getenv("ADMIN_DASHBOARD_PASSWORD", ""),
            # Multi-Server Configuration
            server_config_path=os.getenv("SERVER_CONFIG_PATH", "./config/servers.yaml"),
        )

        config.validate()
        return config


# Global config instance (loaded on import)
_config: Config | None = None


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


def load_config() -> Config:
    """Load config from environment (alias for get_config).

    Returns:
        Config instance
    """
    return get_config()
