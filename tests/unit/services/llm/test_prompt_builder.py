"""Unit tests for PromptBuilder class."""


import pytest

from src.services.llm.prompt_builder import (
    _PROMPT_CACHE,
    DYNAMIC_PLACEHOLDERS,
    PromptBuilder,
    build_system_prompt,
    build_user_prompt,
)


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
        prompt = build_system_prompt("default")

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

        # Verify no placeholders remain (except User Prompt Template section)
        # User Prompt Template has placeholders like {{CONTEXT_TEXT}} that are replaced at runtime
        prompt_without_user_template = prompt.split("## User Prompt Template")[0]
        assert "{{" not in prompt_without_user_template

    def test_build_gemini_prompt(self):
        """Test building Gemini provider prompt."""
        prompt = build_system_prompt("gemini")

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

        # Verify no placeholders remain (except User Prompt Template section)
        prompt_without_user_template = prompt.split("## User Prompt Template")[0]
        assert "{{" not in prompt_without_user_template

    def test_prompts_differ_in_expected_sections(self):
        """Test that default and Gemini prompts differ in expected sections."""
        default_prompt = build_system_prompt("default")
        gemini_prompt = build_system_prompt("gemini")

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
        prompt1 = build_system_prompt("default")

        # Second call should return cached version
        prompt2 = build_system_prompt("default")

        # Should be identical
        assert prompt1 == prompt2
        assert id(prompt1) == id(prompt2)  # Same object in memory

        # Cache should contain the prompt (cache key includes dynamic values)
        assert len(_PROMPT_CACHE) >= 1

    def test_clear_cache(self):
        """Test cache clearing."""
        from src.lib.constants import PROMPT_OVERRIDES_DIR, PROMPT_TEMPLATE_PATH

        builder = PromptBuilder(PROMPT_TEMPLATE_PATH, PROMPT_OVERRIDES_DIR)

        # Build and cache with dynamic values
        dynamic_values = {"PERSONALITY_DESCRIPTION": "Test personality"}
        prompt1 = builder.build_prompt("default", dynamic_values)
        assert len(_PROMPT_CACHE) >= 1

        # Clear cache
        builder.clear_cache()
        assert len(_PROMPT_CACHE) == 0

        # Build again (should reload)
        prompt2 = builder.build_prompt("default", dynamic_values)
        assert prompt1 == prompt2  # Content should be same
        assert len(_PROMPT_CACHE) >= 1

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

    def test_personality_placeholders_without_dynamic_values(self):
        """Test that personality placeholders remain when no dynamic_values provided."""
        # When no dynamic_values are provided, PERSONALITY_DESCRIPTION should remain
        # (this will raise an error in strict mode, but for backward compatibility test)
        from src.lib.constants import PROMPT_OVERRIDES_DIR, PROMPT_TEMPLATE_PATH

        builder = PromptBuilder(PROMPT_TEMPLATE_PATH, PROMPT_OVERRIDES_DIR)

        # Without dynamic_values, the placeholder should cause an error since it's required
        with pytest.raises(ValueError) as exc_info:
            builder.build_prompt("default")

        assert "PERSONALITY_DESCRIPTION" in str(exc_info.value)

    def test_all_placeholders_replaced(self):
        """Test that all template placeholders are replaced."""
        prompt = build_system_prompt("default")

        # No YAML placeholders should remain
        assert "{{QUOTE_EXTRACTION_PROTOCOL}}" not in prompt
        assert "{{QUOTES_FIELD_DEFINITION}}" not in prompt
        assert "{{QUOTE_CONSTRAINTS}}" not in prompt
        assert "{{QUOTES_PERSONALITY_APPLICATION}}" not in prompt
        assert "{{EXAMPLE_JSON}}" not in prompt
        # Personality placeholder should also be replaced
        assert "{{PERSONALITY_DESCRIPTION}}" not in prompt

    def test_gemini_prompt_has_sentence_numbers_example(self):
        """Test that Gemini prompt includes sentence_numbers in example JSON."""
        prompt = build_system_prompt("gemini")

        # Check for sentence_numbers in example
        assert '"sentence_numbers":' in prompt
        assert '"chunk_id":' in prompt
        assert '"quote_text": ""' in prompt or '"quote_text":""' in prompt

    def test_default_prompt_has_quote_text_example(self):
        """Test that default prompt includes quote_text in example JSON."""
        prompt = build_system_prompt("default")

        # Check for quote_text with actual content in example
        assert '"quote_text":' in prompt
        # Should have example quote text (not empty)
        assert '"quote_text": "During each friendly ANGEL OF DEATH' in prompt or \
               '"quote_text":"During each friendly ANGEL OF DEATH' in prompt

    def test_both_prompts_have_shared_structure(self):
        """Test that both prompts have the same overall structure."""
        default_prompt = build_system_prompt("default")
        gemini_prompt = build_system_prompt("gemini")

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

    def test_build_system_prompt_integration(self):
        """Test that build_system_prompt works with provider_type."""
        # Load using provider_type
        prompt = build_system_prompt("default")

        # Should have personality replaced
        assert "{{PERSONALITY_DESCRIPTION}}" not in prompt
        # Should have basic structure
        assert "## Instructions" in prompt
        assert "## Output Structure" in prompt

    def test_gemini_vs_default_quote_fields(self):
        """Test that quote field definitions differ between providers."""
        default_prompt = build_system_prompt("default")
        gemini_prompt = build_system_prompt("gemini")

        # Default should have standard quote_text field
        assert "**quote_text** (string): The relevant excerpt from the rule" in default_prompt

        # Gemini should have empty quote_text and additional fields
        assert "**quote_text** (string): **MUST BE EMPTY**" in gemini_prompt
        assert "**sentence_numbers** (array of integers)" in gemini_prompt
        assert "**chunk_id** (string)" in gemini_prompt


class TestDynamicPlaceholders:
    """Test dynamic placeholder replacement functionality."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear prompt cache before each test."""
        _PROMPT_CACHE.clear()
        yield
        _PROMPT_CACHE.clear()

    def test_dynamic_values_replace_placeholders(self):
        """Test that dynamic_values correctly replace placeholders."""
        from src.lib.constants import PROMPT_OVERRIDES_DIR, PROMPT_TEMPLATE_PATH

        builder = PromptBuilder(PROMPT_TEMPLATE_PATH, PROMPT_OVERRIDES_DIR)

        # Provide dynamic value
        dynamic_values = {"PERSONALITY_DESCRIPTION": "Test personality description"}
        prompt = builder.build_prompt("default", dynamic_values)

        # Placeholder should be replaced
        assert "{{PERSONALITY_DESCRIPTION}}" not in prompt
        assert "Test personality description" in prompt

    def test_cache_key_includes_dynamic_values(self):
        """Test that cache key differs based on dynamic values."""
        from src.lib.constants import PROMPT_OVERRIDES_DIR, PROMPT_TEMPLATE_PATH

        builder = PromptBuilder(PROMPT_TEMPLATE_PATH, PROMPT_OVERRIDES_DIR)

        # Build with first personality
        values1 = {"PERSONALITY_DESCRIPTION": "Personality A"}
        prompt1 = builder.build_prompt("default", values1)

        # Build with second personality
        values2 = {"PERSONALITY_DESCRIPTION": "Personality B"}
        prompt2 = builder.build_prompt("default", values2)

        # Prompts should be different
        assert prompt1 != prompt2
        assert "Personality A" in prompt1
        assert "Personality B" in prompt2

        # Both should be cached separately
        assert len(_PROMPT_CACHE) == 2

    def test_build_system_prompt_loads_personality(self):
        """Test build_system_prompt correctly loads personality values."""
        prompt = build_system_prompt("default")

        # Should have basic structure
        assert "## Instructions" in prompt
        assert "## Output Structure" in prompt

        # Should not have placeholder remaining
        assert "{{PERSONALITY_DESCRIPTION}}" not in prompt

        # Should have some personality content (varies by config)
        assert "## Persona description" in prompt

    def test_dynamic_placeholders_list_has_expected_values(self):
        """Test that DYNAMIC_PLACEHOLDERS contains expected placeholders."""
        assert "PERSONALITY_DESCRIPTION" in DYNAMIC_PLACEHOLDERS


class TestUserPromptBuilder:
    """Test user prompt building functionality."""

    def test_build_user_prompt_basic(self):
        """Test basic user prompt building."""
        user_query = "Can I shoot twice?"
        context = ["Rule 1: You cannot shoot twice in one activation."]
        chunk_ids = ["abc12345-6789-0123-4567-890abcdef123"]

        prompt = build_user_prompt(user_query, context, chunk_ids)

        # Should contain context with chunk ID (last 8 chars: "bcdef123")
        assert "[CHUNK_bcdef123]:" in prompt
        assert "Rule 1: You cannot shoot twice" in prompt

        # Should contain user query
        assert "Can I shoot twice?" in prompt

        # Should have answer prompt
        assert "Answer:" in prompt

    def test_build_user_prompt_multiple_chunks(self):
        """Test user prompt with multiple context chunks."""
        user_query = "What are the movement rules?"
        context = [
            "Chunk 1: Movement rules part 1.",
            "Chunk 2: Movement rules part 2.",
        ]
        chunk_ids = [
            "chunk-id-0000-0001",
            "chunk-id-0000-0002",
        ]

        prompt = build_user_prompt(user_query, context, chunk_ids)

        # Should contain both chunks
        assert "Chunk 1: Movement rules part 1" in prompt
        assert "Chunk 2: Movement rules part 2" in prompt

        # Should have chunk ID markers (last 8 chars: "000-0001", "000-0002")
        assert "[CHUNK_000-0001]:" in prompt
        assert "[CHUNK_000-0002]:" in prompt

    def test_build_user_prompt_example_chunk_id(self):
        """Test that example chunk ID is included in prompt."""
        user_query = "Test query"
        context = ["Test context"]
        chunk_ids = ["test1234-5678-90ab-cdef-1234567890ab"]

        prompt = build_user_prompt(user_query, context, chunk_ids)

        # Should mention the example chunk ID format
        assert "7890ab" in prompt  # Last 8 chars of first chunk ID

    def test_build_user_prompt_mismatched_lengths_raises(self):
        """Test that mismatched context and chunk_ids raises error."""
        user_query = "Test query"
        context = ["Chunk 1", "Chunk 2"]
        chunk_ids = ["only-one-id-here"]

        with pytest.raises(ValueError):
            build_user_prompt(user_query, context, chunk_ids)
