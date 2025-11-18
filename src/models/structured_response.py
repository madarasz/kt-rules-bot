"""Structured LLM response models for native JSON output.

Defines data models for parsing structured JSON responses from LLM providers
using function calling, tool use, or JSON mode.
"""

import json
from dataclasses import dataclass


@dataclass
class StructuredQuote:
    """A single rule quotation."""

    quote_title: str  # "Core Rules: Actions"
    quote_text: str  # Relevant excerpt
    chunk_id: str = ""  # Optional chunk ID for attribution (last 8 chars of UUID)

    def to_markdown(self) -> str:
        """Convert to markdown blockquote format.

        Returns:
            Formatted blockquote with bold title
        """
        return f"> **{self.quote_title}**\n> {self.quote_text}"


@dataclass
class StructuredLLMResponse:
    """Structured LLM response with validated fields."""

    smalltalk: bool  # True if casual conversation, False if rules question
    short_answer: str  # Direct answer (e.g., "Yes.")
    persona_short_answer: str  # Persona phrase
    quotes: list[StructuredQuote]  # Rule quotations
    explanation: str  # Rules-based explanation
    persona_afterword: str  # Concluding persona sentence

    def to_markdown(self) -> str:
        """Convert to markdown format for backwards compatibility.

        Returns:
            Markdown-formatted response matching existing format
        """
        # Short answer section
        markdown_parts = [
            f"**{self.short_answer}** {self.persona_short_answer}",
            "",  # Blank line
        ]

        # Quotes section
        for quote in self.quotes:
            markdown_parts.append(quote.to_markdown())
            markdown_parts.append("")  # Blank line between quotes

        # Explanation section
        markdown_parts.extend(["## Explanation", self.explanation, "", self.persona_afterword])

        return "\n".join(markdown_parts)

    @classmethod
    def from_json(cls, json_str: str) -> "StructuredLLMResponse":
        """Parse JSON string from LLM into structured response.

        Args:
            json_str: JSON string from LLM provider

        Returns:
            StructuredLLMResponse instance

        Raises:
            ValueError: If JSON is invalid or missing required fields
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from LLM: {e}") from e

        # Validate required fields
        required_fields = [
            "smalltalk",
            "short_answer",
            "persona_short_answer",
            "quotes",
            "explanation",
            "persona_afterword",
        ]
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

        # Parse quotes
        quotes = []
        for quote_data in data["quotes"]:
            if "quote_title" not in quote_data or "quote_text" not in quote_data:
                raise ValueError(f"Invalid quote structure: {quote_data}")
            quotes.append(
                StructuredQuote(
                    quote_title=quote_data["quote_title"],
                    quote_text=quote_data["quote_text"],
                    chunk_id=quote_data.get("chunk_id", ""),  # Optional field
                )
            )

        return cls(
            smalltalk=data["smalltalk"],
            short_answer=data["short_answer"],
            persona_short_answer=data["persona_short_answer"],
            quotes=quotes,
            explanation=data["explanation"],
            persona_afterword=data["persona_afterword"],
        )

    def validate(self) -> None:
        """Validate response structure and content.

        Raises:
            ValueError: If validation fails
        """
        # Check non-empty strings
        if not self.short_answer.strip():
            raise ValueError("short_answer cannot be empty")
        if not self.persona_short_answer.strip():
            raise ValueError("persona_short_answer cannot be empty")
        if not self.explanation.strip():
            raise ValueError("explanation cannot be empty")
        if not self.persona_afterword.strip():
            raise ValueError("persona_afterword cannot be empty")

        # For rules questions (not smalltalk), check at least one quote
        if not self.smalltalk and not self.quotes:
            raise ValueError("quotes list cannot be empty for rules questions")

        # Validate each quote
        for i, quote in enumerate(self.quotes):
            if not quote.quote_title.strip():
                raise ValueError(f"quote[{i}].quote_title cannot be empty")
            if not quote.quote_text.strip():
                raise ValueError(f"quote[{i}].quote_text cannot be empty")
