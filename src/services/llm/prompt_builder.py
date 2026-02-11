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

# Module-level template cache (loaded once)
_TEMPLATE_CONTENT: str | None = None
_USER_PROMPT_TEMPLATE: str | None = None

# Provider types
ProviderType = Literal["default", "gemini"]

# Dynamic placeholders replaced at runtime (not from YAML overrides)
DYNAMIC_PLACEHOLDERS = [
    "PERSONALITY_DESCRIPTION",
]

# User prompt template section marker
_USER_PROMPT_SECTION_MARKER = "## User Prompt Template"


def _get_template_path() -> Path:
    """Get the template file path."""
    from src.lib.constants import PROMPT_TEMPLATE_PATH

    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    return project_root / PROMPT_TEMPLATE_PATH


def _get_template_content() -> str:
    """Load template content once, cache for reuse.

    Returns:
        Raw template file content

    Raises:
        FileNotFoundError: If template file is missing
    """
    global _TEMPLATE_CONTENT
    if _TEMPLATE_CONTENT is None:
        template_path = _get_template_path()
        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")
        _TEMPLATE_CONTENT = template_path.read_text(encoding="utf-8")
        logger.debug(f"Loaded template content from {template_path}")
    return _TEMPLATE_CONTENT


def _get_user_prompt_template() -> str:
    """Extract and cache user prompt section from template.

    Returns:
        User prompt template section (after the marker, stripped)

    Raises:
        FileNotFoundError: If template file is missing
        ValueError: If user prompt section marker not found
    """
    global _USER_PROMPT_TEMPLATE
    if _USER_PROMPT_TEMPLATE is None:
        content = _get_template_content()

        if _USER_PROMPT_SECTION_MARKER not in content:
            raise ValueError(
                f"User prompt section not found in template: {_USER_PROMPT_SECTION_MARKER}"
            )

        # Get content after the marker (skip the heading line)
        user_prompt_start = content.index(_USER_PROMPT_SECTION_MARKER)
        user_prompt_section = content[user_prompt_start:]

        # Skip the heading line itself
        lines = user_prompt_section.split("\n")
        _USER_PROMPT_TEMPLATE = "\n".join(lines[1:]).strip()
        logger.debug("Extracted and cached user prompt template section")

    return _USER_PROMPT_TEMPLATE


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

        # Load template from cache
        template = _get_template_content()

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
        clear_cache()
        logger.debug("Prompt cache cleared via PromptBuilder")


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


def clear_cache() -> None:
    """Clear all cached prompts and templates (useful for testing).

    Clears:
    - Assembled system prompt cache
    - Raw template content cache
    - User prompt template cache
    """
    global _PROMPT_CACHE, _TEMPLATE_CONTENT, _USER_PROMPT_TEMPLATE
    _PROMPT_CACHE.clear()
    _TEMPLATE_CONTENT = None
    _USER_PROMPT_TEMPLATE = None
    logger.debug("All prompt caches cleared")


def build_user_prompt(
    user_query: str, context: list[str], chunk_ids: list[str] | None
) -> str:
    """Build user prompt with retrieved context using template.

    Uses cached user prompt template and replaces dynamic placeholders at runtime.

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

    # Get cached user prompt template
    user_prompt_template = _get_user_prompt_template()

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
