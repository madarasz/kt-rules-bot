"""Unit tests for StructuredLLMResponse model."""

import json

import pytest

from src.models.structured_response import StructuredLLMResponse, StructuredQuote


class TestStructuredQuote:
    """Test StructuredQuote model."""

    def test_to_markdown(self):
        """Test converting quote to markdown format."""
        quote = StructuredQuote(
            quote_title="Core Rules: Movement",
            quote_text="You can move up to your Movement characteristic.",
        )

        markdown = quote.to_markdown()

        assert markdown == "> **Core Rules: Movement**\n> You can move up to your Movement characteristic."

    def test_to_markdown_with_special_characters(self):
        """Test converting quote with special characters."""
        quote = StructuredQuote(
            quote_title="FAQ: Charge & Combat",
            quote_text="You must declare charge targets before rolling.",
        )

        markdown = quote.to_markdown()

        assert "**FAQ: Charge & Combat**" in markdown
        assert "You must declare charge targets before rolling." in markdown


class TestStructuredLLMResponse:
    """Test StructuredLLMResponse model."""

    def test_to_markdown(self):
        """Test converting structured response to markdown."""
        response = StructuredLLMResponse(
            smalltalk=False,
            short_answer="Yes.",
            persona_short_answer="That's correct!",
            quotes=[
                StructuredQuote(
                    quote_title="Core Rules: Overwatch",
                    quote_text="You can overwatch in the shooting phase.",
                )
            ],
            explanation="Overwatch is a special action that allows you to shoot during the opponent's charge phase.",
            persona_afterword="Hope that helps clarify the rules!",
        )

        markdown = response.to_markdown()

        assert "**Yes.** That's correct!" in markdown
        assert "> **Core Rules: Overwatch**" in markdown
        assert "> You can overwatch in the shooting phase." in markdown
        assert "## Explanation" in markdown
        assert "Overwatch is a special action" in markdown
        assert "Hope that helps clarify the rules!" in markdown

    def test_to_markdown_multiple_quotes(self):
        """Test converting response with multiple quotes."""
        response = StructuredLLMResponse(
            smalltalk=False,
            short_answer="No.",
            persona_short_answer="Unfortunately not.",
            quotes=[
                StructuredQuote(
                    quote_title="Core Rules: Movement",
                    quote_text="Movement rules here.",
                ),
                StructuredQuote(
                    quote_title="Core Rules: Charge",
                    quote_text="Charge rules here.",
                ),
            ],
            explanation="Detailed explanation.",
            persona_afterword="Let me know if you need more info!",
        )

        markdown = response.to_markdown()

        # Both quotes should be present
        assert "> **Core Rules: Movement**" in markdown
        assert "> **Core Rules: Charge**" in markdown

    def test_from_json_valid(self):
        """Test parsing valid JSON into structured response."""
        json_str = json.dumps({
            "smalltalk": False,
            "short_answer": "Yes.",
            "persona_short_answer": "Absolutely!",
            "quotes": [
                {
                    "quote_title": "Core Rules",
                    "quote_text": "Some rule text.",
                }
            ],
            "explanation": "This is because...",
            "persona_afterword": "Happy gaming!",
        })

        response = StructuredLLMResponse.from_json(json_str)

        assert response.smalltalk is False
        assert response.short_answer == "Yes."
        assert response.persona_short_answer == "Absolutely!"
        assert len(response.quotes) == 1
        assert response.quotes[0].quote_title == "Core Rules"
        assert response.quotes[0].quote_text == "Some rule text."
        assert response.explanation == "This is because..."
        assert response.persona_afterword == "Happy gaming!"

    def test_from_json_multiple_quotes(self):
        """Test parsing JSON with multiple quotes."""
        json_str = json.dumps({
            "smalltalk": False,
            "short_answer": "No.",
            "persona_short_answer": "Not quite.",
            "quotes": [
                {"quote_title": "Rule 1", "quote_text": "Text 1"},
                {"quote_title": "Rule 2", "quote_text": "Text 2"},
                {"quote_title": "Rule 3", "quote_text": "Text 3"},
            ],
            "explanation": "Explanation",
            "persona_afterword": "Afterword",
        })

        response = StructuredLLMResponse.from_json(json_str)

        assert len(response.quotes) == 3
        assert response.quotes[0].quote_title == "Rule 1"
        assert response.quotes[1].quote_title == "Rule 2"
        assert response.quotes[2].quote_title == "Rule 3"

    def test_from_json_smalltalk_true(self):
        """Test parsing JSON with smalltalk=true."""
        json_str = json.dumps({
            "smalltalk": True,
            "short_answer": "Hello!",
            "persona_short_answer": "How can I help?",
            "quotes": [],
            "explanation": "I'm here to answer your Kill Team questions.",
            "persona_afterword": "What would you like to know?",
        })

        response = StructuredLLMResponse.from_json(json_str)

        assert response.smalltalk is True
        assert response.quotes == []

    def test_validate_success(self):
        """Test successful validation."""
        response = StructuredLLMResponse(
            smalltalk=False,
            short_answer="Yes.",
            persona_short_answer="Correct!",
            quotes=[
                StructuredQuote("Core Rules", "Text here")
            ],
            explanation="Because of the rules...",
            persona_afterword="Hope that helps!",
        )
        # Should not raise
        response.validate()

    def test_validate_smalltalk_no_quotes_required(self):
        """Test validation allows empty quotes for smalltalk."""
        response = StructuredLLMResponse(
            smalltalk=True,
            short_answer="Hi!",
            persona_short_answer="Hello there!",
            quotes=[],  # Empty quotes OK for smalltalk
            explanation="I'm a bot.",
            persona_afterword="Ask me anything!",
        )
        # Should not raise
        response.validate()

    def test_markdown_format_structure(self):
        """Test that markdown format has correct structure."""
        response = StructuredLLMResponse(
            smalltalk=False,
            short_answer="Yes.",
            persona_short_answer="That's right!",
            quotes=[
                StructuredQuote("Rule 1", "Quote 1"),
                StructuredQuote("Rule 2", "Quote 2"),
            ],
            explanation="Explanation text here.",
            persona_afterword="Good luck!",
        )

        markdown = response.to_markdown()

        # Check structure order
        lines = markdown.split("\n")

        # First line should have short answer
        assert "**Yes.**" in lines[0]

        # Should have blank lines between sections
        assert "" in lines

        # Should have explanation header
        assert "## Explanation" in markdown

    def test_to_markdown_preserves_formatting(self):
        """Test that to_markdown preserves text formatting."""
        response = StructuredLLMResponse(
            smalltalk=False,
            short_answer="Yes.",
            persona_short_answer="Exactly!",
            quotes=[
                StructuredQuote(
                    "Core Rules",
                    "Line 1\nLine 2\nLine 3"
                )
            ],
            explanation="Multi-line\nexplanation\nhere.",
            persona_afterword="Enjoy!",
        )

        markdown = response.to_markdown()

        # Multiline text should be preserved
        assert "Line 1\nLine 2\nLine 3" in markdown
        assert "Multi-line\nexplanation\nhere." in markdown

    def test_from_json_to_markdown_roundtrip(self):
        """Test that from_json -> to_markdown produces expected output."""
        json_str = json.dumps({
            "smalltalk": False,
            "short_answer": "No.",
            "persona_short_answer": "Not allowed.",
            "quotes": [
                {
                    "quote_title": "Core Rules: Movement",
                    "quote_text": "Cannot move after shooting.",
                }
            ],
            "explanation": "The rules state you must complete movement before shooting.",
            "persona_afterword": "Let me know if you have more questions!",
        })

        response = StructuredLLMResponse.from_json(json_str)
        markdown = response.to_markdown()

        # Verify key elements are in markdown
        assert "**No.** Not allowed." in markdown
        assert "> **Core Rules: Movement**" in markdown
        assert "> Cannot move after shooting." in markdown
        assert "## Explanation" in markdown
        assert "The rules state you must complete movement before shooting." in markdown
        assert "Let me know if you have more questions!" in markdown
