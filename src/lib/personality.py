"""Personality configuration loader.

Loads personality settings from YAML descriptor files based on PERSONALITY env variable.
Each personality defines:
- Description file (injected into system prompt)
- Short answer example phrase
- Afterword example phrase
- Acknowledgements file path
- Disclaimers file path
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PersonalityConfig:
    """Personality configuration loaded from YAML."""

    name: str
    description_file: str
    short_answer_example: str
    afterword_example: str
    acknowledgements_file: str
    disclaimers_file: str


# Cached personality config (loaded once)
_PERSONALITY_CACHE: PersonalityConfig | None = None


def load_personality(personality_name: str) -> PersonalityConfig:
    """Load personality configuration from YAML file.

    Args:
        personality_name: Name of personality (e.g., "necron")

    Returns:
        PersonalityConfig with all settings

    Raises:
        FileNotFoundError: If personality directory or YAML file not found
        ValueError: If YAML is invalid or missing required fields
    """
    # Get project root (assumes this file is at src/lib/personality.py)
    project_root = Path(__file__).parent.parent.parent
    personality_dir = project_root / "personality" / personality_name
    yaml_file = personality_dir / "personality.yaml"

    if not personality_dir.exists():
        raise FileNotFoundError(
            f"Personality directory not found: {personality_dir}\n"
            f"Available personalities should be in personality/ folder"
        )

    if not yaml_file.exists():
        raise FileNotFoundError(
            f"Personality YAML not found: {yaml_file}\n"
            f"Each personality must have a personality.yaml file"
        )

    # Load and parse YAML
    try:
        with open(yaml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {yaml_file}: {e}") from e

    # Validate required fields
    required_fields = [
        "description_file",
        "short_answer_example",
        "afterword_example",
        "acknowledgements_file",
        "disclaimers_file",
    ]
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise ValueError(
            f"Missing required fields in {yaml_file}: {', '.join(missing)}"
        )

    # Validate that referenced files exist
    for field in ["description_file", "acknowledgements_file", "disclaimers_file"]:
        file_path = project_root / data[field]
        if not file_path.exists():
            logger.warning(
                f"Personality file not found: {file_path} (referenced in {yaml_file})"
            )

    return PersonalityConfig(
        name=personality_name,
        description_file=data["description_file"],
        short_answer_example=data["short_answer_example"],
        afterword_example=data["afterword_example"],
        acknowledgements_file=data["acknowledgements_file"],
        disclaimers_file=data["disclaimers_file"],
    )


def get_personality() -> PersonalityConfig:
    """Get current personality configuration (cached).

    Loads personality based on Config.personality setting.

    Returns:
        PersonalityConfig instance

    Raises:
        FileNotFoundError: If personality files not found
        ValueError: If personality YAML is invalid
    """
    global _PERSONALITY_CACHE

    if _PERSONALITY_CACHE is not None:
        return _PERSONALITY_CACHE

    # Import here to avoid circular dependency
    from src.lib.config import get_config

    config = get_config()
    _PERSONALITY_CACHE = load_personality(config.personality)
    return _PERSONALITY_CACHE


def get_personality_description() -> str:
    """Get personality description content for system prompt.

    Returns:
        Content of personality description file
    """
    personality = get_personality()
    project_root = Path(__file__).parent.parent.parent
    description_path = project_root / personality.description_file

    return description_path.read_text(encoding="utf-8")


def get_short_answer_example() -> str:
    """Get short answer example phrase for system prompt.

    Returns:
        Short answer example string
    """
    return get_personality().short_answer_example


def get_afterword_example() -> str:
    """Get afterword example phrase for system prompt.

    Returns:
        Afterword example string
    """
    return get_personality().afterword_example


def get_acknowledgements_path() -> str:
    """Get path to acknowledgements file.

    Returns:
        Relative path to acknowledgements file
    """
    return get_personality().acknowledgements_file


def get_disclaimers_path() -> str:
    """Get path to disclaimers file.

    Returns:
        Relative path to disclaimers file
    """
    return get_personality().disclaimers_file
