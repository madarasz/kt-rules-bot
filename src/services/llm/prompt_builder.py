"""Prompt template builder for assembling provider-specific prompts.

Loads base template and provider-specific overrides, assembles final prompt.
"""

from pathlib import Path
from typing import Literal

import yaml

from src.lib.logging import get_logger

logger = get_logger(__name__)

# Cache for assembled prompts (keyed by provider_type)
_PROMPT_CACHE: dict[str, str] = {}

# Provider types
ProviderType = Literal["default", "gemini"]


class PromptBuilder:
    """Builds provider-specific prompts from template + overrides."""

    def __init__(self, template_path: str, overrides_dir: str):
        """Initialize prompt builder.

        Args:
            template_path: Path to base prompt template (relative to project root)
            overrides_dir: Directory containing override YAML files (relative to project root)
        """
        # Locate project root (assuming this file is at src/services/llm/prompt_builder.py)
        current_file = Path(__file__)
        self.project_root = current_file.parent.parent.parent.parent

        self.template_path = self.project_root / template_path
        self.overrides_dir = self.project_root / overrides_dir

        # Validate paths
        if not self.template_path.exists():
            raise FileNotFoundError(
                f"Prompt template not found: {self.template_path}\n"
                f"Expected location: {template_path}"
            )
        if not self.overrides_dir.exists():
            raise FileNotFoundError(
                f"Overrides directory not found: {self.overrides_dir}\n"
                f"Expected location: {overrides_dir}"
            )

        logger.debug(f"PromptBuilder initialized: template={template_path}, overrides={overrides_dir}")

    def build_prompt(self, provider_type: ProviderType = "default") -> str:
        """Build prompt for specified provider type.

        Args:
            provider_type: Provider type ("default" or "gemini")

        Returns:
            Assembled prompt text

        Raises:
            FileNotFoundError: If override file not found
            ValueError: If required placeholder is missing in overrides
        """
        # Check cache
        global _PROMPT_CACHE
        if provider_type in _PROMPT_CACHE:
            logger.debug(f"Using cached prompt for provider_type={provider_type}")
            return _PROMPT_CACHE[provider_type]

        # Load template
        template = self.template_path.read_text(encoding="utf-8")

        # Load overrides
        overrides_file = self.overrides_dir / f"{provider_type}-overrides.yaml"
        if not overrides_file.exists():
            raise FileNotFoundError(
                f"Overrides file not found: {overrides_file}\n"
                f"Expected: {provider_type}-overrides.yaml"
            )

        with overrides_file.open("r", encoding="utf-8") as f:
            overrides = yaml.safe_load(f)

        if not isinstance(overrides, dict):
            raise ValueError(f"Invalid overrides file: {overrides_file} (must be YAML dict)")

        # Replace all placeholders
        placeholders = [
            "QUOTE_EXTRACTION_PROTOCOL",
            "QUOTES_FIELD_DEFINITION",
            "QUOTE_CONSTRAINTS",
            "QUOTES_PERSONALITY_APPLICATION",
            "EXAMPLE_JSON",
        ]

        assembled = template
        for placeholder in placeholders:
            if placeholder not in overrides:
                raise ValueError(
                    f"Missing required placeholder in overrides: {placeholder}\n"
                    f"File: {overrides_file}"
                )

            # Replace {{PLACEHOLDER}} with override content
            replacement = overrides[placeholder]
            if replacement is None:
                replacement = ""  # Handle null values as empty strings

            assembled = assembled.replace(f"{{{{{placeholder}}}}}", replacement)

        # Verify no placeholders remain
        remaining = [p for p in placeholders if f"{{{{{p}}}}}" in assembled]
        if remaining:
            raise ValueError(
                f"Placeholders not replaced in template: {remaining}\n"
                f"Check override file: {overrides_file}"
            )

        # Cache and return
        _PROMPT_CACHE[provider_type] = assembled
        logger.info(f"Built prompt for provider_type={provider_type} (length={len(assembled)})")
        return assembled

    def clear_cache(self) -> None:
        """Clear cached prompts (useful for testing)."""
        global _PROMPT_CACHE
        _PROMPT_CACHE.clear()
        logger.debug("Prompt cache cleared")


def build_prompt_for_provider(provider_type: ProviderType = "default") -> str:
    """Convenience function to build prompt with default paths.

    Args:
        provider_type: Provider type ("default" or "gemini")

    Returns:
        Assembled prompt text
    """
    from src.lib.constants import PROMPT_OVERRIDES_DIR, PROMPT_TEMPLATE_PATH

    builder = PromptBuilder(
        template_path=PROMPT_TEMPLATE_PATH,
        overrides_dir=PROMPT_OVERRIDES_DIR,
    )
    return builder.build_prompt(provider_type)
