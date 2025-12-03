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


class QuoteFaithfulnessScore(BaseModel):
    """Individual quote faithfulness score."""

    chunk_id: str = Field(description="Chunk ID (last 8 chars of UUID, e.g., 'a1b2c3d4')")
    score: float = Field(ge=0.0, le=1.0, description="Faithfulness score 0.0-1.0")


class AnswerCorrectnessScore(BaseModel):
    """Individual answer correctness score."""

    answer_key: str = Field(
        description="Ground truth answer key (e.g., 'Final Answer', 'Weapon')"
    )
    score: float = Field(ge=0.0, le=1.0, description="Correctness score 0.0-1.0")


class CustomJudgeResponse(BaseModel):
    """Structured response from custom LLM judge for quality testing.

    Used to evaluate Kill Team rules bot responses on two dimensions:
    - Explanation faithfulness (is reasoning grounded in quotes?) - single score
    - Answer correctness (does conclusion match ground truth?) - provided as per-answer details, backend calculates aggregate

    Note: Quote faithfulness is evaluated separately using fuzzy string matching (not LLM-based).
    Note: answer_correctness aggregate is calculated by the backend from answer_correctness_details array.
    """

    explanation_faithfulness: float = Field(
        ge=0.0,
        le=1.0,
        description="Score 0.0-1.0: Is explanation grounded only in cited quotes?",
    )
    feedback: str = Field(
        description="3-8 sentences in 3 sections: Problems, Style, Suggestions"
    )

    # Detailed per-item breakdowns (backend calculates aggregates from these)
    # Note: Using arrays instead of dicts for OpenAI structured output compatibility
    answer_correctness_details: list[AnswerCorrectnessScore] = Field(
        default_factory=list,
        description="Per-answer correctness scores as array of {answer_key, score} objects",
    )
