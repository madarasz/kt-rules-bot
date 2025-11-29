"""Pydantic models for LLM structured output schemas.

Uses Pydantic BaseModel for type-safe schema definitions, compatible with:
- Anthropic Claude Structured Outputs (Nov 2025)
- OpenAI Structured Outputs (2024)
- Google Gemini JSON mode (Nov 2024)
- X/Grok Structured Outputs (2024)
"""

from pydantic import BaseModel, Field


# Standard models (Claude, OpenAI, Grok)
class Quote(BaseModel):
    """Quote from Kill Team rules with verbatim text."""

    quote_title: str = Field(description="Rule name (e.g., 'Core Rules: Actions', 'Silent')")
    quote_text: str = Field(
        description="Relevant excerpt from the rule (must be verbatim from context)"
    )
    chunk_id: str = Field(
        description="Chunk ID from context (last 8 chars of UUID, e.g., 'a1b2c3d4')"
    )


class Answer(BaseModel):
    """Structured answer for Kill Team rules queries."""

    smalltalk: bool = Field(
        description="True if casual conversation (not rules-related), False if answering a rules question"
    )
    short_answer: str = Field(description="Direct, short answer (e.g., 'Yes.', 'No.')")
    persona_short_answer: str = Field(
        description="Short condescending phrase after the direct answer (e.g., 'The affirmative is undeniable.')"
    )
    quotes: list[Quote] = Field(
        description="Relevant rule quotations from Kill Team 3rd Edition rules"
    )
    explanation: str = Field(
        description="Brief rules-based explanation using official Kill Team terminology"
    )
    persona_afterword: str = Field(
        description="Dismissive concluding sentence (e.g., 'The logic is unimpeachable.')"
    )


# Gemini-specific models (uses sentence numbers to avoid RECITATION errors)
class GeminiQuote(BaseModel):
    """Quote from Kill Team rules with sentence numbers for extraction (Gemini-specific)."""

    quote_title: str = Field(description="Rule name (e.g., 'Core Rules: Actions', 'Silent')")
    quote_text: str = Field(
        description="MUST BE EMPTY to avoid RECITATION errors. Use sentence_numbers instead.",
        default="",
    )
    sentence_numbers: list[int] = Field(
        description="1-indexed sentence numbers containing relevant rule text (e.g., [2] or [2, 3])"
    )
    chunk_id: str = Field(
        description="Chunk ID from context (last 8 chars of UUID, e.g., 'a1b2c3d4')"
    )


class GeminiAnswer(BaseModel):
    """Structured answer for Kill Team rules queries (Gemini-specific with sentence numbers)."""

    smalltalk: bool = Field(
        description="True if casual conversation (not rules-related), False if answering a rules question"
    )
    short_answer: str = Field(description="Direct, short answer (e.g., 'Yes.', 'No.')")
    persona_short_answer: str = Field(
        description="Short condescending phrase after the direct answer (e.g., 'The affirmative is undeniable.')"
    )
    quotes: list[GeminiQuote] = Field(
        description="Relevant rule quotations from Kill Team 3rd Edition rules"
    )
    explanation: str = Field(
        description="Brief rules-based explanation using official Kill Team terminology"
    )
    persona_afterword: str = Field(
        description="Dismissive concluding sentence (e.g., 'The logic is unimpeachable.')"
    )


class HopEvaluation(BaseModel):
    """Evaluation of whether retrieved context is sufficient for answering a query.

    Used in multi-hop retrieval to determine if additional context is needed.
    """

    can_answer: bool = Field(
        description="True if the retrieved context is sufficient to answer the question, false otherwise"
    )
    reasoning: str = Field(
        description="Brief explanation (1-2 sentences) of what context you have or what's missing"
    )
    missing_query: str | None = Field(
        default=None,
        description="If can_answer=false, a focused retrieval query for missing rules. If can_answer=true, null or empty string",
    )


class CustomJudgeResponse(BaseModel):
    """Structured response from custom LLM judge for quality testing.

    Used to evaluate Kill Team rules bot responses on three dimensions:
    - Quote faithfulness (are quotes verbatim?)
    - Explanation faithfulness (is reasoning grounded in quotes?)
    - Answer correctness (does conclusion match ground truth?)
    """

    quote_faithfulness: float = Field(
        ge=0.0, le=1.0, description="Score 0.0-1.0: Are quotes verbatim from RAG contexts?"
    )
    explanation_faithfulness: float = Field(
        ge=0.0,
        le=1.0,
        description="Score 0.0-1.0: Is explanation grounded only in cited quotes?",
    )
    answer_correctness: float = Field(
        ge=0.0, le=1.0, description="Score 0.0-1.0: Does answer match ground truth semantically?"
    )
    feedback: str = Field(
        description="3-5 sentences covering strengths, problems, and suggestions for improvement"
    )
