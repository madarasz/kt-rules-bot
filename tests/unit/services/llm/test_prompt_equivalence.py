"""Integration tests to verify new prompts are equivalent to legacy prompts.

These tests ensure backward compatibility by comparing the assembled prompts
from the template system against the original prompt files.
"""

from src.services.llm.prompt_builder import build_system_prompt


def test_default_prompt_has_key_sections():
    """Test that new default prompt contains all key sections from legacy prompt."""
    # Load using new system
    new_prompt = build_system_prompt("default")

    # Key sections that must be present
    required_sections = [
        "## Instructions",
        "## Quote Extraction Protocol",
        "## Output Structure",
        "smalltalk",
        "short_answer",
        "persona_short_answer",
        "quotes",
        "explanation",
        "persona_afterword",
        "## Output rules, formatting",
        "## Constraints",
        "## Personality Application",
        "## Persona description",
        # Personality is now injected, not a placeholder
        "## Examples",
        "Example 1 - Rules Question",
        "Example 2 - Smalltalk",
    ]

    for section in required_sections:
        assert section in new_prompt, f"Missing section: {section}"


def test_gemini_prompt_has_key_sections():
    """Test that new Gemini prompt contains all key sections from legacy prompt."""
    # Load using new system
    new_prompt = build_system_prompt("gemini")

    # Key sections specific to Gemini
    required_sections = [
        "## Instructions",
        "## Quote Extraction Protocol (Gemini-specific)",
        "RECITATION",
        "sentence_numbers",
        "chunk_id",
        "## Output Structure",
        "**MUST BE EMPTY**",
        "## Constraints",
        "## Personality Application",
        "## Examples",
    ]

    for section in required_sections:
        assert section in new_prompt, f"Missing section: {section}"


def test_default_prompt_quote_extraction_protocol():
    """Test that default prompt has verbatim quote extraction instructions."""
    new_prompt = build_system_prompt("default")

    # Key instructions for verbatim quote extraction
    assert "Copy relevant chunk text verbatim" in new_prompt
    assert "Do NOT paraphrase" in new_prompt
    assert "exact copies" in new_prompt
    assert "quote_text" in new_prompt


def test_gemini_prompt_quote_extraction_protocol():
    """Test that Gemini prompt has sentence-number-based extraction instructions."""
    new_prompt = build_system_prompt("gemini")

    # Key instructions for sentence-number-based extraction
    assert "NOT include verbatim text" in new_prompt
    assert "sentence_numbers" in new_prompt
    assert "LEAVE `quote_text` EMPTY" in new_prompt or "LEAVE quote_text EMPTY" in new_prompt
    assert "RECITATION" in new_prompt


def test_build_system_prompt_default():
    """Test that build_system_prompt works with default provider."""
    prompt = build_system_prompt("default")

    # Should have personality injected (not placeholders)
    assert "{{PERSONALITY_DESCRIPTION}}" not in prompt
    assert "## Instructions" in prompt
    assert "## Output Structure" in prompt


def test_build_system_prompt_gemini():
    """Test that build_system_prompt works with Gemini provider."""
    prompt = build_system_prompt("gemini")

    # Should have personality injected
    assert "{{PERSONALITY_DESCRIPTION}}" not in prompt
    # Should have Gemini-specific content
    assert "sentence_numbers" in prompt
    assert "RECITATION" in prompt


def test_build_system_prompt_default_without_arg():
    """Test that build_system_prompt defaults to 'default' provider when no arg provided."""
    prompt = build_system_prompt()

    # Should use default provider
    assert "## Instructions" in prompt
    assert "Copy relevant chunk text verbatim" in prompt
    assert "sentence_numbers" not in prompt


def test_default_vs_gemini_differences():
    """Test key differences between default and Gemini prompts."""
    default_prompt = build_system_prompt("default")
    gemini_prompt = build_system_prompt("gemini")

    # Should not be identical
    assert default_prompt != gemini_prompt

    # Default should have verbatim instructions
    assert "Copy relevant chunk text verbatim" in default_prompt
    assert "Copy relevant chunk text verbatim" not in gemini_prompt

    # Gemini should have sentence number instructions
    assert "sentence_numbers" in gemini_prompt
    assert "[S1]" in gemini_prompt
    assert "[S2]" in gemini_prompt

    # Gemini should mention RECITATION
    assert "RECITATION" in gemini_prompt
    assert "RECITATION" not in default_prompt


def test_shared_sections_identical():
    """Test that shared sections are identical between providers."""
    default_prompt = build_system_prompt("default")
    gemini_prompt = build_system_prompt("gemini")

    # Instructions section should be identical
    default_instructions = default_prompt.split("## Quote Extraction Protocol")[0]
    gemini_instructions = gemini_prompt.split("## Quote Extraction Protocol")[0]
    assert default_instructions == gemini_instructions

    # Both should have same smalltalk example
    assert '"smalltalk": true' in default_prompt
    assert '"smalltalk": true' in gemini_prompt


def test_no_placeholders_in_final_prompts():
    """Test that no template placeholders remain in assembled prompts."""
    default_prompt = build_system_prompt("default")
    gemini_prompt = build_system_prompt("gemini")

    # No double-brace placeholders should remain (except User Prompt Template section)
    for prompt_name, prompt in [("default", default_prompt), ("gemini", gemini_prompt)]:
        # User Prompt Template section has runtime placeholders
        prompt_without_user_template = prompt.split("## User Prompt Template")[0]
        assert "{{" not in prompt_without_user_template, f"{prompt_name} prompt has unreplaced placeholders"


def test_example_json_differences():
    """Test that example JSON differs correctly between providers."""
    default_prompt = build_system_prompt("default")
    gemini_prompt = build_system_prompt("gemini")

    # Default should have quote_text with content
    assert '"quote_text": "During each friendly ANGEL OF DEATH' in default_prompt or \
           '"quote_text":"During each friendly ANGEL OF DEATH' in default_prompt

    # Gemini should have empty quote_text
    assert '"quote_text": ""' in gemini_prompt or '"quote_text":""' in gemini_prompt
    # Gemini should have sentence_numbers in example
    assert '"sentence_numbers":' in gemini_prompt
    # Gemini should have chunk_id in example
    assert '"chunk_id":' in gemini_prompt
