"""LLM Provider base interface.

Abstract base class for LLM integrations ensuring provider independence.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, BinaryIO
from uuid import UUID

if TYPE_CHECKING:
    from pydantic import BaseModel

from src.lib.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
    LLM_EXTRACTION_MAX_TOKENS,
    LLM_EXTRACTION_TEMPERATURE,
    LLM_EXTRACTION_TIMEOUT,
    LLM_GENERATION_TIMEOUT,
)


def _default_system_prompt() -> str:
    """Load default system prompt for GenerationConfig.

    Deferred import to avoid circular dependencies.
    """
    from src.services.llm.prompt_builder import build_system_prompt

    return build_system_prompt("default")


# Exception classes
class LLMError(Exception):
    """Base exception for LLM errors."""

    pass


class RateLimitError(LLMError):
    """Provider rate limit exceeded."""

    pass


class AuthenticationError(LLMError):
    """Invalid API key or authentication failed."""

    pass


class TimeoutError(LLMError):
    """Request exceeded timeout limit."""

    pass


class ContentFilterError(LLMError):
    """Provider blocked content due to safety filters."""

    pass


class PDFParseError(LLMError):
    """PDF corrupted or unreadable."""

    pass


class TokenLimitError(LLMError):
    """Token limit exceeded (e.g., PDF too large)."""

    pass


# Structured output schema for JSON responses (OpenAI/Claude/Grok/DeepSeek)
STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "smalltalk": {
            "type": "boolean",
            "description": "True if this is casual conversation (not rules-related), False if answering a rules question",
        },
        "short_answer": {"type": "string", "description": "Direct, short answer (e.g., 'Yes.')"},
        "persona_short_answer": {
            "type": "string",
            "description": "Short condescending phrase after the direct answer (e.g., 'The affirmative is undeniable.')",
        },
        "quotes": {
            "type": "array",
            "description": "Relevant rule quotations from Kill Team 3rd Edition rules",
            "items": {
                "type": "object",
                "properties": {
                    "quote_title": {
                        "type": "string",
                        "description": "Rule name (e.g., 'Core Rules: Actions')",
                    },
                    "quote_text": {
                        "type": "string",
                        "description": "Relevant excerpt from the rule (must be verbatim from context)",
                    },
                    "chunk_id": {
                        "type": "string",
                        "description": "Chunk ID from context (last 8 chars of UUID, e.g., 'a1b2c3d4'). Optional for backward compatibility.",
                    },
                },
                "required": ["quote_title", "quote_text", "chunk_id"],
                "additionalProperties": False,
            },
        },
        "explanation": {
            "type": "string",
            "description": "Brief rules-based explanation using official Kill Team terminology",
        },
        "persona_afterword": {
            "type": "string",
            "description": "Dismissive concluding sentence (e.g., 'The logic is unimpeachable.')",
        },
    },
    "required": [
        "smalltalk",
        "short_answer",
        "persona_short_answer",
        "quotes",
        "explanation",
        "persona_afterword",
    ],
    "additionalProperties": False,
}

# Schema for multi-hop retrieval context evaluation
HOP_EVALUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "can_answer": {
            "type": "boolean",
            "description": "True if the retrieved context is sufficient to answer the question, false otherwise",
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation (1-2 sentences) of what context you have or what's missing",
        },
        "missing_query": {
            "type": ["string", "null"],
            "description": "If can_answer=false, a focused retrieval query for missing rules. If can_answer=true, null",
        },
    },
    "required": ["can_answer", "reasoning", "missing_query"],
    "additionalProperties": False,
}

# Schema for chunk summaries (used during ingestion)
CHUNK_SUMMARIES_SCHEMA = {
    "type": "object",
    "properties": {
        "summaries": {
            "type": "array",
            "description": "List of chunk summaries",
            "items": {
                "type": "object",
                "properties": {
                    "chunk_number": {
                        "type": "integer",
                        "description": "Chunk number (1-indexed)",
                    },
                    "summary": {
                        "type": "string",
                        "description": "One-sentence summary of the chunk",
                    },
                },
                "required": ["chunk_number", "summary"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summaries"],
    "additionalProperties": False,
}

# Schema for custom LLM judge in quality testing
CUSTOM_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "explanation_faithfulness": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Score 0.0-1.0: Is explanation grounded only in cited quotes?",
        },
        "feedback": {
            "type": "string",
            "description": "3-8 sentences in 3 sections: Problems, Style, Suggestions",
        },
        "answer_correctness_details": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "answer_key": {
                        "type": "string",
                        "description": "Ground truth answer key (e.g., 'Final Answer', 'Weapon')",
                    },
                    "score": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Correctness score 0.0-1.0",
                    },
                },
                "required": ["answer_key", "score"],
                "additionalProperties": False,
            },
            "description": "Per-answer correctness scores as array of {answer_key, score} objects",
        },
    },
    "required": ["explanation_faithfulness", "feedback", "answer_correctness_details"],
    "additionalProperties": False,
}


# Schema selection helpers to reduce code duplication across LLM adapters
@dataclass
class SchemaInfo:
    """Full schema information for structured output configuration.

    Used by adapters that need more than just the Pydantic model (e.g., Claude, DeepSeek).
    """

    pydantic_model: type["BaseModel"]
    json_schema: dict
    tool_name: str
    tool_description: str


def _get_schema_registry() -> dict[str, SchemaInfo]:
    """Lazily build schema registry to avoid circular imports.

    Returns:
        Dictionary mapping schema type names to SchemaInfo objects.
    """
    from src.services.llm.schemas import Answer, ChunkSummaries, CustomJudgeResponse, HopEvaluation

    return {
        "hop_evaluation": SchemaInfo(
            pydantic_model=HopEvaluation,
            json_schema=HOP_EVALUATION_SCHEMA,
            tool_name="evaluate_context_sufficiency",
            tool_description="Evaluate if retrieved context is sufficient to answer the question",
        ),
        "custom_judge": SchemaInfo(
            pydantic_model=CustomJudgeResponse,
            json_schema=CUSTOM_JUDGE_SCHEMA,
            tool_name="evaluate_answer_quality",
            tool_description="Evaluate Kill Team rules answer quality and correctness",
        ),
        "chunk_summaries": SchemaInfo(
            pydantic_model=ChunkSummaries,
            json_schema=CHUNK_SUMMARIES_SCHEMA,
            tool_name="generate_chunk_summaries",
            tool_description="Generate one-sentence summaries for rule chunks",
        ),
        "default": SchemaInfo(
            pydantic_model=Answer,
            json_schema=STRUCTURED_OUTPUT_SCHEMA,
            tool_name="format_kill_team_answer",
            tool_description="Format Kill Team rules answer with quotes and explanation",
        ),
    }


def get_pydantic_model(schema_type: str, use_gemini_answer: bool = False) -> type["BaseModel"]:
    """Get Pydantic model for structured output schema type.

    This is the simpler helper for adapters that only need the Pydantic model
    (ChatGPT, Grok, Gemini, Kimi, Mistral).

    Args:
        schema_type: One of "default", "hop_evaluation", "custom_judge", "chunk_summaries"
        use_gemini_answer: If True and schema_type is "default", returns GeminiAnswer
                          instead of Answer (for Gemini's sentence-number quote extraction)

    Returns:
        Pydantic model class for the specified schema type
    """
    # Handle Gemini's special case for default schema
    if use_gemini_answer and schema_type == "default":
        from src.services.llm.schemas import GeminiAnswer

        return GeminiAnswer

    registry = _get_schema_registry()
    schema_info = registry.get(schema_type, registry["default"])
    return schema_info.pydantic_model


def get_schema_info(schema_type: str) -> SchemaInfo:
    """Get full schema info including JSON schema and tool metadata.

    This is the comprehensive helper for adapters that need more than just the
    Pydantic model (Claude, DeepSeek).

    Args:
        schema_type: One of "default", "hop_evaluation", "custom_judge", "chunk_summaries"

    Returns:
        SchemaInfo with pydantic_model, json_schema, tool_name, and tool_description
    """
    registry = _get_schema_registry()
    return registry.get(schema_type, registry["default"])


# Data classes for generation
@dataclass
class GenerationConfig:
    """Configuration for answer generation.

    By default, LLM providers return structured JSON responses conforming to
    STRUCTURED_OUTPUT_SCHEMA. Available schema types:
    - "default": Standard Kill Team rules answer (Answer model)
    - "hop_evaluation": Multi-hop retrieval context evaluation (HopEvaluation model)
    - "custom_judge": Quality test evaluation (CustomJudgeResponse model)
    - "chunk_summaries": Chunk summary generation during ingestion (ChunkSummaries model)
    """

    max_tokens: int = LLM_DEFAULT_MAX_TOKENS  # Maximum response length
    temperature: float = LLM_DEFAULT_TEMPERATURE  # Lower = more deterministic
    system_prompt: str = field(default_factory=_default_system_prompt)
    include_citations: bool = True
    timeout_seconds: int = LLM_GENERATION_TIMEOUT  # Must respond within timeout
    structured_output_schema: str = "default"  # "default", "hop_evaluation", or "custom_judge"


@dataclass
class GenerationRequest:
    """Request for answer generation."""

    prompt: str  # User query (sanitized)
    context: list[str]  # Retrieved document chunks (up to 5)
    config: GenerationConfig
    chunk_ids: list[str] | None = None  # Optional chunk IDs for attribution (UUIDs)


@dataclass
class LLMResponse:
    """Response from LLM generation."""

    response_id: UUID
    answer_text: str  # Generated answer (JSON string)
    confidence_score: float  # 0-1, provider-specific confidence metric
    token_count: int  # Total tokens (prompt + completion)
    latency_ms: int  # Generation time in milliseconds
    provider: str  # "claude", "gemini", "chatgpt"
    model_version: str  # e.g., "claude-3-sonnet-20240229"
    citations_included: bool  # True if answer references context chunks
    prompt_tokens: int = 0  # Input/prompt tokens
    completion_tokens: int = 0  # Output/completion tokens
    structured_output: dict | None = None  # Parsed Pydantic model as dict (for structured schemas)


# Data classes for extraction
@dataclass
class ExtractionConfig:
    """Configuration for PDF extraction."""

    max_tokens: int = LLM_EXTRACTION_MAX_TOKENS  # Large output for full rulebook sections
    temperature: float = LLM_EXTRACTION_TEMPERATURE  # Low temperature for consistent structure
    timeout_seconds: int = LLM_EXTRACTION_TIMEOUT  # PDF extraction takes longer


@dataclass
class ExtractionRequest:
    """Request for PDF extraction."""

    pdf_file: BinaryIO  # PDF file handle
    extraction_prompt: str  # Structured extraction instructions
    config: ExtractionConfig


@dataclass
class ExtractionResponse:
    """Response from PDF extraction."""

    extraction_id: UUID
    markdown_content: str  # Extracted markdown with YAML frontmatter
    token_count: int  # Total tokens used (for backward compatibility)
    latency_ms: int  # Extraction time
    provider: str  # "claude", "gemini", "chatgpt"
    model_version: str
    validation_warnings: list[str]  # E.g., "Missing YAML frontmatter"
    prompt_tokens: int = 0  # Input tokens (PDF + prompt)
    completion_tokens: int = 0  # Output tokens (markdown)


# Abstract base class
class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Ensures provider independence (Constitution Principle II).
    All LLM adapters must implement this interface.
    """

    def __init__(self, api_key: str, model: str):
        """Initialize LLM provider.

        Args:
            api_key: API key for provider
            model: Model identifier (e.g., "claude-3-sonnet-20240229")
        """
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> LLMResponse:
        """Generate answer to user query using RAG context.

        Args:
            request: Generation request with prompt, context, config

        Returns:
            LLMResponse with answer, confidence, token count

        Raises:
            RateLimitError: Provider rate limit exceeded
            AuthenticationError: Invalid API key
            TimeoutError: Response time exceeded timeout_seconds
            ContentFilterError: Provider blocked content
        """
        pass

    @abstractmethod
    async def extract_pdf(self, request: ExtractionRequest) -> ExtractionResponse:
        """Extract structured markdown from PDF rulebook.

        Args:
            request: Extraction request with PDF file, prompt, config

        Returns:
            ExtractionResponse with markdown content, validation warnings

        Raises:
            PDFParseError: PDF corrupted or unreadable
            TimeoutError: Extraction exceeded timeout
            TokenLimitError: PDF too large (>100 pages)
            RateLimitError: Provider rate limit exceeded
        """
        pass

    def _build_prompt(
        self, user_query: str, context: list[str], chunk_ids: list[str] | None = None
    ) -> str:
        """Build user prompt with retrieved context using template.

        Note: System prompt is configured separately in GenerationConfig.

        Args:
            user_query: Sanitized user question
            context: Retrieved document chunks
            chunk_ids: List of chunk IDs (UUIDs) for attribution (None or empty for no context)

        Returns:
            Formatted user prompt with context
        """
        from src.services.llm.prompt_builder import build_user_prompt

        return build_user_prompt(user_query, context, chunk_ids)

    @staticmethod
    def _create_extraction_prompt() -> str:
        """Create standard extraction prompt for PDF processing.

        Returns:
            Extraction prompt template
        """
        return """Extract this Kill Team rulebook PDF to markdown format.

Requirements:
1. Preserve all headings, lists, and section structure
2. Include YAML frontmatter with:
   - source: (e.g., "Core Rules v3.1")
   - last_update_date: (YYYY-MM-DD format)
   - document_type: ("core-rules" or "faq" or "team-rules" or "ops" or "killzone")
   - section: (thematic grouping, e.g., "Movement Phase")
3. Use proper markdown syntax (##, ###, -, *, etc.)
4. Preserve rule citations and cross-references
5. Extract tables as markdown tables

Document type selection guide:
- core-rules: Base game mechanics (phases, actions, terrain)
- faq: Official FAQs and clarifications
- team-rules: Faction-specific rules (e.g., Space Marines)
- ops: Tactical operations and mission rules"""
