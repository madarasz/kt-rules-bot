"""Prompt template builder for assembling provider-specific prompts.

Loads base template and provider-specific overrides, assembles final prompt.
Handles both YAML overrides ({{PLACEHOLDER}}) and dynamic values (e.g., personality).
"""

from pathlib import Path
from typing import Literal

import yaml

from src.lib.logging import get_logger

logger = get_logger(__name__)

# Cache for assembled prompts (keyed by (provider_type, frozenset(dynamic_values)))
_PROMPT_CACHE: dict[tuple[str, frozenset], str] = {}

# Provider types
ProviderType = Literal["default", "gemini"]

# Dynamic placeholders replaced at runtime (not from YAML overrides)
DYNAMIC_PLACEHOLDERS = [
    "PERSONALITY_DESCRIPTION",
]


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

    def build_prompt(
        self, provider_type: ProviderType = "default", dynamic_values: dict[str, str] | None = None
    ) -> str:
        """Build prompt for specified provider type.

        Args:
            provider_type: Provider type ("default" or "gemini")
            dynamic_values: Optional dict of dynamic placeholder values (e.g., personality)

        Returns:
            Assembled prompt text

        Raises:
            FileNotFoundError: If override file not found
            ValueError: If required placeholder is missing in overrides or dynamic values
        """
        # Build cache key including dynamic values
        global _PROMPT_CACHE
        dynamic_values = dynamic_values or {}
        cache_key = (provider_type, frozenset(dynamic_values.items()))

        if cache_key in _PROMPT_CACHE:
            logger.debug(f"Using cached prompt for provider_type={provider_type}")
            return _PROMPT_CACHE[cache_key]

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

        # Replace all YAML override placeholders
        yaml_placeholders = [
            "QUOTE_EXTRACTION_PROTOCOL",
            "QUOTES_FIELD_DEFINITION",
            "QUOTE_CONSTRAINTS",
            "QUOTES_PERSONALITY_APPLICATION",
            "EXAMPLE_JSON",
        ]

        assembled = template
        for placeholder in yaml_placeholders:
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

        # Verify no YAML placeholders remain
        remaining_yaml = [p for p in yaml_placeholders if f"{{{{{p}}}}}" in assembled]
        if remaining_yaml:
            raise ValueError(
                f"YAML placeholders not replaced in template: {remaining_yaml}\n"
                f"Check override file: {overrides_file}"
            )

        # Replace dynamic placeholders
        for placeholder in DYNAMIC_PLACEHOLDERS:
            placeholder_pattern = f"{{{{{placeholder}}}}}"
            if placeholder_pattern in assembled:
                if placeholder not in dynamic_values:
                    raise ValueError(
                        f"Missing required dynamic placeholder: {placeholder}\n"
                        f"Provide it via dynamic_values parameter"
                    )
                assembled = assembled.replace(placeholder_pattern, dynamic_values[placeholder])

        # Verify no dynamic placeholders remain (that are expected to be replaced)
        remaining_dynamic = [
            p for p in DYNAMIC_PLACEHOLDERS if f"{{{{{p}}}}}" in assembled and p in dynamic_values
        ]
        if remaining_dynamic:
            raise ValueError(
                f"Dynamic placeholders not replaced in template: {remaining_dynamic}\n"
                f"Check dynamic_values parameter"
            )

        # Cache and return
        _PROMPT_CACHE[cache_key] = assembled
        logger.info(f"Built prompt for provider_type={provider_type} (length={len(assembled)})")
        return assembled

    def clear_cache(self) -> None:
        """Clear cached prompts (useful for testing)."""
        global _PROMPT_CACHE
        _PROMPT_CACHE.clear()
        logger.debug("Prompt cache cleared")


def build_prompt_for_provider(
    provider_type: ProviderType = "default", dynamic_values: dict[str, str] | None = None
) -> str:
    """Convenience function to build prompt with default paths.

    Args:
        provider_type: Provider type ("default" or "gemini")
        dynamic_values: Optional dict of dynamic placeholder values

    Returns:
        Assembled prompt text
    """
    from src.lib.constants import PROMPT_OVERRIDES_DIR, PROMPT_TEMPLATE_PATH

    builder = PromptBuilder(
        template_path=PROMPT_TEMPLATE_PATH,
        overrides_dir=PROMPT_OVERRIDES_DIR,
    )
    return builder.build_prompt(provider_type, dynamic_values)


def build_system_prompt(provider_type: ProviderType = "default") -> str:
    """Build complete system prompt with personality values injected.

    This is the unified entry point for system prompt generation.
    Loads personality values from personality module and injects them
    into the template via dynamic_values.

    Args:
        provider_type: Provider type ("default" or "gemini")

    Returns:
        Complete system prompt with all placeholders replaced

    Raises:
        FileNotFoundError: If template, override files, or personality files are missing
        ValueError: If override file is invalid or missing required placeholders
    """
    from src.lib.personality import get_personality_description

    # Load personality values
    dynamic_values = {
        "PERSONALITY_DESCRIPTION": get_personality_description(),
    }

    return build_prompt_for_provider(provider_type, dynamic_values)


# User prompt template section marker
_USER_PROMPT_SECTION_MARKER = "## User Prompt Template"


def build_user_prompt(
    user_query: str, context: list[str], chunk_ids: list[str] | None
) -> str:
    """Build user prompt with retrieved context using template.

    Loads the user prompt template from the same template file and replaces
    dynamic placeholders at runtime.

    Args:
        user_query: Sanitized user question
        context: Retrieved document chunks
        chunk_ids: List of chunk IDs (UUIDs) for attribution (can be None or empty)

    Returns:
        Formatted user prompt with context

    Raises:
        FileNotFoundError: If template file is missing
        ValueError: If user prompt section not found in template, or if
                    chunk_ids length doesn't match context length
    """
    from src.lib.constants import PROMPT_TEMPLATE_PATH

    # Handle empty context (e.g., hop evaluation or smalltalk)
    if not context:
        return f"User Question: {user_query}\n\nAnswer:"

    # Normalize chunk_ids
    chunk_ids = chunk_ids or []

    # Validate lengths match
    if len(chunk_ids) != len(context):
        raise ValueError(
            f"chunk_ids length ({len(chunk_ids)}) must match context length ({len(context)})"
        )

    # Load template file
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    template_path = project_root / PROMPT_TEMPLATE_PATH

    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")

    template_content = template_path.read_text(encoding="utf-8")

    # Extract user prompt section
    if _USER_PROMPT_SECTION_MARKER not in template_content:
        raise ValueError(
            f"User prompt section not found in template: {_USER_PROMPT_SECTION_MARKER}"
        )

    # Get content after the marker (skip the heading line)
    user_prompt_start = template_content.index(_USER_PROMPT_SECTION_MARKER)
    user_prompt_section = template_content[user_prompt_start:]

    # Skip the heading line itself
    lines = user_prompt_section.split("\n")
    user_prompt_template = "\n".join(lines[1:]).strip()

    # Build context text with chunk IDs
    context_text = "\n\n".join(
        [
            f"[CHUNK_{chunk_id[-8:]}]:\n{chunk}"
            for chunk_id, chunk in zip(chunk_ids, context, strict=True)
        ]
    )

    # Get example chunk ID (first chunk's short ID)
    example_chunk_id = chunk_ids[0][-8:] if chunk_ids else "CHUNK_ID"

    # Replace placeholders
    user_prompt = user_prompt_template
    user_prompt = user_prompt.replace("{{CONTEXT_TEXT}}", context_text)
    user_prompt = user_prompt.replace("{{USER_QUERY}}", user_query)
    user_prompt = user_prompt.replace("{{EXAMPLE_CHUNK_ID}}", example_chunk_id)

    return user_prompt
