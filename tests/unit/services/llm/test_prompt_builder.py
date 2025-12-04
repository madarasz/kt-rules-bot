"""Unit tests for PromptBuilder class."""


import pytest

from src.services.llm.prompt_builder import _PROMPT_CACHE, PromptBuilder, build_prompt_for_provider


class TestPromptBuilder:
    """Test PromptBuilder class."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear prompt cache before each test."""
        _PROMPT_CACHE.clear()
        yield
        _PROMPT_CACHE.clear()

    def test_build_default_prompt(self):
        """Test building default provider prompt."""
        prompt = build_prompt_for_provider("default")

        # Check basic structure
        assert "## Instructions" in prompt
        assert "## Output Structure" in prompt
        assert "## Constraints" in prompt
        assert "## Personality Application" in prompt
        assert "## Examples" in prompt

        # Check that default content is used
        assert "## Quote Extraction Protocol" in prompt
        assert "Copy relevant chunk text verbatim" in prompt
        assert "quote_text" in prompt
        assert "**quote_text** (string): The relevant excerpt from the rule" in prompt

        # Verify no placeholders remain
        assert "{{" not in prompt
        assert "}}" not in prompt

    def test_build_gemini_prompt(self):
        """Test building Gemini provider prompt."""
        prompt = build_prompt_for_provider("gemini")

        # Check basic structure (same as default)
        assert "## Instructions" in prompt
        assert "## Output Structure" in prompt
        assert "## Constraints" in prompt

        # Check that Gemini-specific content is used
        assert "## Quote Extraction Protocol (Gemini-specific)" in prompt
        assert "NOT include verbatim text" in prompt
        assert "sentence_numbers" in prompt
        assert "**MUST BE EMPTY**" in prompt
        assert "RECITATION" in prompt

        # Verify no placeholders remain
        assert "{{" not in prompt
        assert "}}" not in prompt

    def test_prompts_differ_in_expected_sections(self):
        """Test that default and Gemini prompts differ in expected sections."""
        default_prompt = build_prompt_for_provider("default")
        gemini_prompt = build_prompt_for_provider("gemini")

        # They should not be identical
        assert default_prompt != gemini_prompt

        # Default should have verbatim quote instructions
        assert "Copy relevant chunk text verbatim" in default_prompt
        assert "Copy relevant chunk text verbatim" not in gemini_prompt

        # Gemini should have sentence number instructions
        assert "sentence_numbers" in gemini_prompt
        assert "sentence_numbers" not in default_prompt

        # Both should have shared sections
        assert "## Instructions" in default_prompt
        assert "## Instructions" in gemini_prompt

    def test_caching_works(self):
        """Test that prompts are cached correctly."""
        # First call should load and cache
        prompt1 = build_prompt_for_provider("default")

        # Second call should return cached version
        prompt2 = build_prompt_for_provider("default")

        # Should be identical
        assert prompt1 == prompt2
        assert id(prompt1) == id(prompt2)  # Same object in memory

        # Cache should contain the prompt
        assert "default" in _PROMPT_CACHE

    def test_clear_cache(self):
        """Test cache clearing."""
        from src.lib.constants import PROMPT_OVERRIDES_DIR, PROMPT_TEMPLATE_PATH

        builder = PromptBuilder(PROMPT_TEMPLATE_PATH, PROMPT_OVERRIDES_DIR)

        # Build and cache
        prompt1 = builder.build_prompt("default")
        assert "default" in _PROMPT_CACHE

        # Clear cache
        builder.clear_cache()
        assert len(_PROMPT_CACHE) == 0

        # Build again (should reload)
        prompt2 = builder.build_prompt("default")
        assert prompt1 == prompt2  # Content should be same
        assert "default" in _PROMPT_CACHE

    def test_invalid_provider_type(self):
        """Test error handling for invalid provider type."""
        from src.lib.constants import PROMPT_OVERRIDES_DIR, PROMPT_TEMPLATE_PATH

        builder = PromptBuilder(PROMPT_TEMPLATE_PATH, PROMPT_OVERRIDES_DIR)

        with pytest.raises(FileNotFoundError) as exc_info:
            builder.build_prompt("nonexistent")

        assert "Overrides file not found" in str(exc_info.value)
        assert "nonexistent-overrides.yaml" in str(exc_info.value)

    def test_missing_template_file(self):
        """Test error handling for missing template file."""
        with pytest.raises(FileNotFoundError) as exc_info:
            PromptBuilder("nonexistent/template.md", "prompts/overrides")

        assert "Prompt template not found" in str(exc_info.value)

    def test_missing_overrides_dir(self):
        """Test error handling for missing overrides directory."""
        with pytest.raises(FileNotFoundError) as exc_info:
            PromptBuilder("prompts/base-prompt-template.md", "nonexistent/overrides")

        assert "Overrides directory not found" in str(exc_info.value)

    def test_personality_placeholders_not_in_template(self):
        """Test that personality placeholders are handled by load_system_prompt, not PromptBuilder."""
        prompt = build_prompt_for_provider("default")

        # Personality placeholders should still be present (not replaced by PromptBuilder)
        assert "[PERSONALITY DESCRIPTION]" in prompt
        # Note: These are replaced by load_system_prompt in base.py, not by PromptBuilder

    def test_all_placeholders_replaced(self):
        """Test that all template placeholders are replaced."""
        prompt = build_prompt_for_provider("default")

        # No double-brace placeholders should remain
        assert "{{QUOTE_EXTRACTION_PROTOCOL}}" not in prompt
        assert "{{QUOTES_FIELD_DEFINITION}}" not in prompt
        assert "{{QUOTE_CONSTRAINTS}}" not in prompt
        assert "{{QUOTES_PERSONALITY_APPLICATION}}" not in prompt
        assert "{{EXAMPLE_JSON}}" not in prompt

    def test_gemini_prompt_has_sentence_numbers_example(self):
        """Test that Gemini prompt includes sentence_numbers in example JSON."""
        prompt = build_prompt_for_provider("gemini")

        # Check for sentence_numbers in example
        assert '"sentence_numbers":' in prompt
        assert '"chunk_id":' in prompt
        assert '"quote_text": ""' in prompt or '"quote_text":""' in prompt

    def test_default_prompt_has_quote_text_example(self):
        """Test that default prompt includes quote_text in example JSON."""
        prompt = build_prompt_for_provider("default")

        # Check for quote_text with actual content in example
        assert '"quote_text":' in prompt
        # Should have example quote text (not empty)
        assert '"quote_text": "During each friendly ANGEL OF DEATH' in prompt or \
               '"quote_text":"During each friendly ANGEL OF DEATH' in prompt

    def test_both_prompts_have_shared_structure(self):
        """Test that both prompts have the same overall structure."""
        default_prompt = build_prompt_for_provider("default")
        gemini_prompt = build_prompt_for_provider("gemini")

        # Both should have these major sections
        shared_sections = [
            "## Instructions",
            "## Output Structure",
            "## Output rules, formatting",
            "## Personality Application",
            "## Persona description",
            "## Examples",
        ]

        for section in shared_sections:
            assert section in default_prompt, f"Default prompt missing: {section}"
            assert section in gemini_prompt, f"Gemini prompt missing: {section}"

    def test_load_system_prompt_integration(self):
        """Test that load_system_prompt works with provider_type."""
        from src.services.llm.base import load_system_prompt

        # Load using provider_type
        prompt = load_system_prompt("default")

        # Should have personality replaced
        assert "[PERSONALITY DESCRIPTION]" not in prompt
        # Should have basic structure
        assert "## Instructions" in prompt
        assert "## Output Structure" in prompt

    def test_gemini_vs_default_quote_fields(self):
        """Test that quote field definitions differ between providers."""
        default_prompt = build_prompt_for_provider("default")
        gemini_prompt = build_prompt_for_provider("gemini")

        # Default should have standard quote_text field
        assert "**quote_text** (string): The relevant excerpt from the rule" in default_prompt

        # Gemini should have empty quote_text and additional fields
        assert "**quote_text** (string): **MUST BE EMPTY**" in gemini_prompt
        assert "**sentence_numbers** (array of integers)" in gemini_prompt
        assert "**chunk_id** (string)" in gemini_prompt
