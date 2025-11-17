"""LLM Provider base interface.

Abstract base class for LLM integrations ensuring provider independence.
Based on specs/001-we-are-building/contracts/llm-adapter.md
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from src.lib.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
    LLM_EXTRACTION_MAX_TOKENS,
    LLM_EXTRACTION_TEMPERATURE,
    LLM_EXTRACTION_TIMEOUT,
    LLM_GENERATION_TIMEOUT,
    LLM_SYSTEM_PROMPT_FILE_PATH,
)
from src.lib.personality import (
    get_afterword_example,
    get_personality_description,
    get_short_answer_example,
)

# Cached system prompt (loaded once from file)
_SYSTEM_PROMPT_CACHE: str | None = None


def load_system_prompt() -> str:
    """Load system prompt from prompts/rule-helper-prompt.md.

    Loads the prompt file once, replaces personality placeholders, and caches it.

    Returns:
        System prompt text with personality injected

    Raises:
        FileNotFoundError: If prompts/rule-helper-prompt.md does not exist
    """
    global _SYSTEM_PROMPT_CACHE

    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE

    # Locate prompt file relative to project root
    # Assuming this file is at src/services/llm/base.py
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    prompt_file = project_root / LLM_SYSTEM_PROMPT_FILE_PATH

    if not prompt_file.exists():
        raise FileNotFoundError(
            f"System prompt file not found: {prompt_file}\n"
            f"Expected location: {LLM_SYSTEM_PROMPT_FILE_PATH}"
        )

    # Read the base template
    template = prompt_file.read_text(encoding="utf-8")

    # Replace personality placeholders
    template = template.replace("[PERSONALITY DESCRIPTION]", get_personality_description())
    template = template.replace("[PERSONALITY SHORT ANSWER]", get_short_answer_example())
    template = template.replace("[PERSONALITY AFTERWORD]", get_afterword_example())

    # Cache and return
    _SYSTEM_PROMPT_CACHE = template
    return _SYSTEM_PROMPT_CACHE


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
                        "description": "Relevant excerpt from the rule",
                    },
                },
                "required": ["quote_title", "quote_text"],
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


# Data classes for generation
@dataclass
class GenerationConfig:
    """Configuration for answer generation.

    By default, LLM providers return structured JSON responses conforming to
    STRUCTURED_OUTPUT_SCHEMA. For multi-hop retrieval evaluation, use
    structured_output_schema='hop_evaluation'.
    """

    max_tokens: int = LLM_DEFAULT_MAX_TOKENS  # Maximum response length
    temperature: float = LLM_DEFAULT_TEMPERATURE  # Lower = more deterministic
    system_prompt: str = field(default_factory=load_system_prompt)
    include_citations: bool = True
    timeout_seconds: int = LLM_GENERATION_TIMEOUT  # Must respond within timeout
    structured_output_schema: str = "default"  # "default" or "hop_evaluation"


@dataclass
class GenerationRequest:
    """Request for answer generation."""

    prompt: str  # User query (sanitized)
    context: list[str]  # Retrieved document chunks (up to 5)
    config: GenerationConfig


@dataclass
class LLMResponse:
    """Response from LLM generation."""

    response_id: UUID
    answer_text: str  # Generated answer
    confidence_score: float  # 0-1, provider-specific confidence metric
    token_count: int  # Total tokens (prompt + completion)
    latency_ms: int  # Generation time in milliseconds
    provider: str  # "claude", "gemini", "chatgpt"
    model_version: str  # e.g., "claude-3-sonnet-20240229"
    citations_included: bool  # True if answer references context chunks
    prompt_tokens: int = 0  # Input/prompt tokens
    completion_tokens: int = 0  # Output/completion tokens


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

    def _build_prompt(self, user_query: str, context: list[str]) -> str:
        """Build user prompt with retrieved context.

        Note: System prompt is configured separately in GenerationConfig.

        Args:
            user_query: Sanitized user question
            context: Retrieved document chunks

        Returns:
            Formatted user prompt with context
        """
        context_text = "\n\n".join(
            [f"[Context {i + 1}]:\n{chunk}" for i, chunk in enumerate(context)]
        )

        return f"""Context from Kill Team 3rd Edition rules:
{context_text}

User Question: {user_query}

Answer:"""

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
