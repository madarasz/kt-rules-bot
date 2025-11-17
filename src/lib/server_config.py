"""Per-server configuration management for multi-server deployments.

Allows different Discord servers to use different LLM API keys, with fallback to global .env config.
Each server is identified by its Discord guild ID.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.lib.constants import LLM_PROVIDERS_LITERAL
from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ServerConfig:
    """Configuration overrides for a specific Discord server.

    Any field not set will fall back to the global .env configuration.
    """

    guild_id: str
    llm_provider: LLM_PROVIDERS_LITERAL  # REQUIRED: LLM model for this server
    name: str | None = None  # Human-readable name (for documentation)

    # LLM Provider API Keys (optional overrides)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    x_api_key: str | None = None
    dial_api_key: str | None = None
    deepseek_api_key: str | None = None

    # RAG Configuration (optional override)
    rag_hop_evaluation_model: LLM_PROVIDERS_LITERAL | None = None  # Model for multi-hop RAG evaluation

    def validate(self) -> None:
        """Validate server configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        if not self.llm_provider:
            raise ValueError(
                f"Server {self.guild_id} ({self.name if self.name else 'unnamed'}): "
                f"llm_provider is required in servers.yaml"
            )


class MultiServerConfig:
    """Manages per-server configuration with fallback to global config."""

    def __init__(self, config_path: str = "config/servers.yaml"):
        """Initialize multi-server config loader.

        Args:
            config_path: Path to servers.yaml file
        """
        self.config_path = Path(config_path)
        self.servers: dict[str, ServerConfig] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load server configurations from YAML file.

        If file doesn't exist or is invalid, logs warning and continues with empty config.
        """
        if not self.config_path.exists():
            logger.info(f"Server config not found at {self.config_path}, using .env only")
            return

        logger.info(f"Loading server config from {self.config_path}")

        try:
            with open(self.config_path) as f:
                data = yaml.safe_load(f)

            if not data or 'servers' not in data:
                logger.warning(f"No 'servers' section in {self.config_path}")
                return

            for guild_id, server_data in data['servers'].items():
                if not isinstance(server_data, dict):
                    logger.warning(f"Invalid config for guild {guild_id}, skipping")
                    continue

                # Convert guild_id to string (YAML may parse as int)
                guild_id_str = str(guild_id)

                # Check for required llm_provider field
                llm_provider = server_data.get('llm_provider')
                if not llm_provider:
                    logger.error(
                        f"Guild {guild_id_str} ({server_data.get('name', 'unnamed')}): "
                        f"llm_provider is required but not found in servers.yaml. Skipping this server."
                    )
                    continue

                try:
                    server_config = ServerConfig(
                        guild_id=guild_id_str,
                        llm_provider=llm_provider,
                        name=server_data.get('name'),
                        anthropic_api_key=server_data.get('anthropic_api_key'),
                        openai_api_key=server_data.get('openai_api_key'),
                        google_api_key=server_data.get('google_api_key'),
                        x_api_key=server_data.get('x_api_key'),
                        dial_api_key=server_data.get('dial_api_key'),
                        deepseek_api_key=server_data.get('deepseek_api_key'),
                        rag_hop_evaluation_model=server_data.get('rag_hop_evaluation_model'),
                    )

                    # Validate the config
                    server_config.validate()

                    self.servers[guild_id_str] = server_config
                    logger.info(
                        f"Loaded server config for guild {guild_id_str} "
                        f"({server_config.name if server_config.name else 'unnamed'}): "
                        f"using {server_config.llm_provider}"
                    )
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to load config for guild {guild_id_str}: {e}")
                    continue

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse {self.config_path}: {e}")
        except Exception as e:
            logger.error(f"Error loading server config: {e}")

    def get_server_config(self, guild_id: str | None) -> ServerConfig | None:
        """Get configuration for a specific Discord server.

        Args:
            guild_id: Discord guild (server) ID, or None for DMs

        Returns:
            ServerConfig if found, None otherwise (will fall back to .env)
        """
        if not guild_id:
            return None

        return self.servers.get(str(guild_id))

    def has_server_config(self, guild_id: str | None) -> bool:
        """Check if a server has specific configuration.

        Args:
            guild_id: Discord guild ID

        Returns:
            True if server has custom config, False otherwise
        """
        if not guild_id:
            return False
        return str(guild_id) in self.servers

    def list_configured_servers(self) -> list[str]:
        """Get list of all configured guild IDs.

        Returns:
            List of guild IDs with custom configurations
        """
        return list(self.servers.keys())


# Global instance (loaded on import, similar to Config)
_multi_server_config: MultiServerConfig | None = None


def get_multi_server_config() -> MultiServerConfig:
    """Get global multi-server config instance.

    Returns:
        MultiServerConfig instance
    """
    global _multi_server_config
    if _multi_server_config is None:
        _multi_server_config = MultiServerConfig()
    return _multi_server_config


def set_multi_server_config(config: MultiServerConfig) -> None:
    """Set global multi-server config instance (for testing).

    Args:
        config: MultiServerConfig instance
    """
    global _multi_server_config
    _multi_server_config = config
