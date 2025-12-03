# Migration Plan: Native Structured JSON LLM Response

**Status**: Planning
**Created**: 2025-10-20
**Target Date**: TBD

## Overview

This document outlines the migration from unstructured markdown LLM responses to native structured JSON outputs using each provider's built-in capabilities (function calling, tool use, JSON mode).

## Current State

**Existing Implementation:**
- LLM returns unstructured markdown text following format defined in [prompts/rule-helper-prompt.md](../../../prompts/rule-helper-prompt.md)
- Response structure enforced via prompt instructions only
- Parsing is implicit (no extraction of sections)
- `BotResponse.answer_text` stores entire markdown response
- Discord formatter displays markdown as-is

**Problems:**
- No guaranteed structure compliance
- Difficult to parse specific sections (quotes, explanation, persona)
- Hard to track quote relevance in analytics
- Fragile markdown parsing for multi-hop reasoning
- Quality tests can't validate specific fields

## Target State

**New Implementation:**
- LLM returns validated JSON via native structured output
- Schema enforced at provider level (not prompt)
- Explicit field extraction and validation
- `BotResponse.structured_data` contains parsed JSON
- Discord formatter uses structured fields for better UX

**Benefits:**
- Zero parsing errors (provider guarantees schema compliance)
- Better Discord formatting (quotes as embed fields)
- Analytics can track quote relevance separately
- Multi-hop ready (structured quotes enable re-querying)
- Quality tests validate specific fields
- Easy A/B testing via feature flag

## JSON Schema Definition

```json
{
  "type": "object",
  "properties": {
    "short_answer": {
      "type": "string",
      "description": "Direct, short answer (e.g., 'Yes.')"
    },
    "persona_short_answer": {
      "type": "string",
      "description": "Short condescending phrase after the direct answer (e.g., 'The affirmative is undeniable.')"
    },
    "quotes": {
      "type": "array",
      "description": "Relevant rule quotations from Kill Team 3rd Edition rules",
      "items": {
        "type": "object",
        "properties": {
          "quote_title": {
            "type": "string",
            "description": "Rule name (e.g., 'Core Rules: Actions')"
          },
          "quote_text": {
            "type": "string",
            "description": "Relevant excerpt from the rule"
          }
        },
        "required": ["quote_title", "quote_text"]
      }
    },
    "explanation": {
      "type": "string",
      "description": "Brief rules-based explanation using official Kill Team terminology"
    },
    "persona_afterword": {
      "type": "string",
      "description": "Dismissive concluding sentence (e.g., 'The logic is unimpeachable.')"
    }
  },
  "required": ["short_answer", "persona_short_answer", "quotes", "explanation", "persona_afterword"]
}
```

**Example JSON Output:**
```json
{
  "short_answer": "No.",
  "persona_short_answer": "A trivial calculation.",
  "quotes": [
    {
      "quote_title": "Core Rules: Actions",
      "quote_text": "A model cannot perform the same action more than once in the same activation."
    }
  ],
  "explanation": "A model cannot perform two Shoot actions in one activation, per the Core Rules.",
  "persona_afterword": "The restriction is absolute."
}
```

## Provider-Specific Implementation

### OpenAI (ChatGPT, GPT-4, GPT-5, o-series)

**Capability**: Function calling with `strict: true`

**Implementation** ([src/services/llm/chatgpt.py](chatgpt.py)):
```python
async def generate(self, request: GenerationRequest) -> LLMResponse:
    if request.config.use_structured_output:
        # Use function calling with strict mode
        api_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.config.system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "format_kill_team_answer",
                    "description": "Format Kill Team rules answer with quotes and explanation",
                    "parameters": STRUCTURED_OUTPUT_SCHEMA,
                    "strict": True  # ← Enforces 100% schema compliance
                }
            }],
            "tool_choice": {
                "type": "function",
                "function": {"name": "format_kill_team_answer"}
            },
            "parallel_tool_calls": False  # Required for strict mode
        }

        response = await asyncio.wait_for(
            self.client.chat.completions.create(**api_params),
            timeout=request.config.timeout_seconds
        )

        # Extract JSON from tool call
        tool_call = response.choices[0].message.tool_calls[0]
        answer_text = tool_call.function.arguments  # This is JSON string

        return LLMResponse(
            response_id=uuid4(),
            answer_text=answer_text,  # JSON string
            ...
        )
```

**Notes:**
- `strict: true` guarantees 100% schema compliance
- All required fields must be listed in schema
- Not compatible with `parallel_tool_calls`
- Supported on GPT-4, GPT-5, o-series models

### Claude (Anthropic)

**Capability**: Tool use with `input_schema`

**Implementation** ([src/services/llm/claude.py](claude.py)):
```python
async def generate(self, request: GenerationRequest) -> LLMResponse:
    if request.config.use_structured_output:
        # Use tool use with forced tool calling
        response = await asyncio.wait_for(
            self.client.messages.create(
                model=self.model,
                max_tokens=request.config.max_tokens,
                temperature=request.config.temperature,
                system=request.config.system_prompt,
                messages=[{"role": "user", "content": full_prompt}],
                tools=[{
                    "name": "format_kill_team_answer",
                    "description": "Format Kill Team rules answer with quotes and explanation",
                    "input_schema": STRUCTURED_OUTPUT_SCHEMA
                }],
                tool_choice={
                    "type": "tool",
                    "name": "format_kill_team_answer"
                }
            ),
            timeout=request.config.timeout_seconds
        )

        # Extract JSON from tool use
        tool_use_block = response.content[0]  # Should be ToolUseBlock
        tool_input = tool_use_block.input  # Dict with structured data
        answer_text = json.dumps(tool_input)  # Convert to JSON string

        return LLMResponse(
            response_id=uuid4(),
            answer_text=answer_text,  # JSON string
            ...
        )
```

**Notes:**
- Tool use forces structured output without "strict" mode
- Claude returns dict, convert to JSON string for consistency
- Does NOT work with extended thinking mode (Claude 3.7 Sonnet)
- Supported on all Claude 3+ models

### Gemini (Google)

**Capability**: JSON mode with `response_schema`

**Implementation** ([src/services/llm/gemini.py](gemini.py)):
```python
async def generate(self, request: GenerationRequest) -> LLMResponse:
    if request.config.use_structured_output:
        # Use JSON mode with schema validation
        generation_config = {
            "max_output_tokens": request.config.max_tokens,
            "temperature": request.config.temperature,
            "response_mime_type": "application/json",
            "response_schema": STRUCTURED_OUTPUT_SCHEMA  # ← Gemini 2.5+ only
        }

        response = await asyncio.wait_for(
            asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=full_prompt,
                config=generation_config
            ),
            timeout=request.config.timeout_seconds
        )

        # Response.text is already JSON string
        answer_text = response.text

        # Validate it's valid JSON
        try:
            json.loads(answer_text)
        except json.JSONDecodeError as e:
            logger.error(f"Gemini returned invalid JSON: {e}")
            raise

        return LLMResponse(
            response_id=uuid4(),
            answer_text=answer_text,  # JSON string
            ...
        )
```

**Notes:**
- `response_schema` field available in Gemini 2.5+ only
- Returns JSON string directly in `response.text`
- May return invalid JSON on complex schemas (validate!)
- Supported on Gemini 2.5 Pro and Flash

### Grok (xAI)

**Capability**: Function calling (OpenAI-compatible)

**Implementation** ([src/services/llm/grok.py](grok.py)):
```python
# Same implementation as ChatGPT - uses OpenAI SDK with custom base_url
# Function calling with strict mode supported on grok-2-1212+, grok-3, grok-4
```

**Notes:**
- Uses OpenAI SDK with `base_url="https://api.x.ai/v1"`
- Supports `strict: true` mode
- Implementation identical to ChatGPT adapter

### DeepSeek

**Capability**: Function calling with strict mode (OpenAI-compatible)

**Implementation** ([src/services/llm/deepseek.py](deepseek.py)):
```python
# Already implemented - uses OpenAI SDK with custom base_url
# Function calling with strict mode supported on DeepSeek V3, DeepSeek R1
# Implementation identical to ChatGPT adapter
```

**Notes:**
- Uses OpenAI SDK with `base_url="https://api.deepseek.com"`
- Already supports function calling
- No changes needed if implemented like ChatGPT

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

**Files to Create:**
- `src/models/structured_response.py` - Data models for structured JSON

**Files to Modify:**
- `src/services/llm/base.py` - Add schema constant and config flag
- `src/services/llm/chatgpt.py` - Implement function calling
- `src/services/llm/claude.py` - Implement tool use
- `src/services/llm/gemini.py` - Implement JSON mode
- `src/services/llm/grok.py` - Implement function calling
- `src/services/llm/deepseek.py` - Verify function calling support
- `src/models/bot_response.py` - Add `structured_data` field

**Deliverables:**
1. StructuredLLMResponse model with JSON parsing
2. All 5 providers support structured output via feature flag
3. Unit tests for JSON parsing and schema validation

### Phase 2: Response Handling (Week 2)

**Files to Modify:**
- `src/services/discord/formatter.py` - Format structured JSON as Discord embeds
- `src/services/discord/bot.py` - Enable structured output in orchestrator
- `src/lib/constants.py` - Add feature flag
- `prompts/rule-helper-prompt.md` - Update with structured output note

**Deliverables:**
1. Discord formatter handles both markdown and JSON
2. Feature flag controls structured output (default: disabled)
3. Backward compatibility with existing markdown responses

### Phase 3: Database & Analytics (Week 2)

**Files to Modify:**
- `src/lib/database.py` - Add `response_format` column and `response_quotes` table
- `src/services/discord/bot.py` - Store structured data in analytics DB

**Deliverables:**
1. Database schema supports both formats
2. Quotes stored separately for analytics
3. Migration script for existing data

### Phase 4: Testing & Validation (Week 3)

**Files to Create:**
- `tests/unit/test_structured_response.py` - Unit tests for models
- `tests/contract/test_llm_structured_output.py` - Provider contract tests

**Files to Modify:**
- `tests/quality/evaluator.py` - Add structured field evaluators

**Deliverables:**
1. Unit tests cover all parsing edge cases
2. Contract tests verify all providers return valid JSON
3. Quality tests support structured field validation

### Phase 5: Rollout (Week 4)

**Strategy:**
1. Enable for 10% of queries (random sampling)
2. Monitor error rates, parsing success, user feedback
3. Compare metrics: quote accuracy, validation failures, latency
4. Gradual increase: 25% → 50% → 100%

**Rollback Plan:**
- Set `LLM_USE_STRUCTURED_OUTPUT=false` to revert to markdown
- Database supports both formats (no data loss)

## Detailed Implementation

### 1. Structured Response Models

**File**: `src/models/structured_response.py` (NEW)

```python
"""Structured LLM response models for native JSON output.

Defines data models for parsing structured JSON responses from LLM providers
using function calling, tool use, or JSON mode.
"""

import json
from dataclasses import dataclass
from typing import List


@dataclass
class StructuredQuote:
    """A single rule quotation."""

    quote_title: str  # "Core Rules: Actions"
    quote_text: str   # Relevant excerpt

    def to_markdown(self) -> str:
        """Convert to markdown blockquote format.

        Returns:
            Formatted blockquote with bold title
        """
        return f"> **{self.quote_title}**\n> {self.quote_text}"


@dataclass
class StructuredLLMResponse:
    """Structured LLM response with validated fields."""

    short_answer: str           # Direct answer (e.g., "Yes.")
    persona_short_answer: str   # Persona phrase
    quotes: List[StructuredQuote]  # Rule quotations
    explanation: str            # Rules-based explanation
    persona_afterword: str      # Concluding persona sentence

    def to_markdown(self) -> str:
        """Convert to markdown format for backwards compatibility.

        Returns:
            Markdown-formatted response matching existing format
        """
        # Short answer section
        markdown_parts = [
            f"**{self.short_answer}** {self.persona_short_answer}",
            ""  # Blank line
        ]

        # Quotes section
        for quote in self.quotes:
            markdown_parts.append(quote.to_markdown())
            markdown_parts.append("")  # Blank line between quotes

        # Explanation section
        markdown_parts.extend([
            "## Explanation",
            self.explanation,
            "",
            self.persona_afterword
        ])

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
            raise ValueError(f"Invalid JSON from LLM: {e}")

        # Validate required fields
        required_fields = [
            "short_answer",
            "persona_short_answer",
            "quotes",
            "explanation",
            "persona_afterword"
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
                    quote_text=quote_data["quote_text"]
                )
            )

        return cls(
            short_answer=data["short_answer"],
            persona_short_answer=data["persona_short_answer"],
            quotes=quotes,
            explanation=data["explanation"],
            persona_afterword=data["persona_afterword"]
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

        # Check at least one quote
        if not self.quotes:
            raise ValueError("quotes list cannot be empty")

        # Validate each quote
        for i, quote in enumerate(self.quotes):
            if not quote.quote_title.strip():
                raise ValueError(f"quote[{i}].quote_title cannot be empty")
            if not quote.quote_text.strip():
                raise ValueError(f"quote[{i}].quote_text cannot be empty")
```

### 2. Update LLM Base Class

**File**: `src/services/llm/base.py`

**Changes:**
```python
# Add at top of file after imports
from typing import Optional

# Add JSON schema constant
STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "short_answer": {
            "type": "string",
            "description": "Direct, short answer (e.g., 'Yes.')"
        },
        "persona_short_answer": {
            "type": "string",
            "description": "Short condescending phrase after the direct answer (e.g., 'The affirmative is undeniable.')"
        },
        "quotes": {
            "type": "array",
            "description": "Relevant rule quotations from Kill Team 3rd Edition rules",
            "items": {
                "type": "object",
                "properties": {
                    "quote_title": {
                        "type": "string",
                        "description": "Rule name (e.g., 'Core Rules: Actions')"
                    },
                    "quote_text": {
                        "type": "string",
                        "description": "Relevant excerpt from the rule"
                    }
                },
                "required": ["quote_title", "quote_text"]
            }
        },
        "explanation": {
            "type": "string",
            "description": "Brief rules-based explanation using official Kill Team terminology"
        },
        "persona_afterword": {
            "type": "string",
            "description": "Dismissive concluding sentence (e.g., 'The logic is unimpeachable.')"
        }
    },
    "required": [
        "short_answer",
        "persona_short_answer",
        "quotes",
        "explanation",
        "persona_afterword"
    ]
}

# Update GenerationConfig
@dataclass
class GenerationConfig:
    """Configuration for answer generation."""

    max_tokens: int = LLM_DEFAULT_MAX_TOKENS
    temperature: float = LLM_DEFAULT_TEMPERATURE
    system_prompt: str = field(default_factory=load_system_prompt)
    include_citations: bool = True
    timeout_seconds: int = LLM_GENERATION_TIMEOUT
    use_structured_output: bool = False  # ← NEW: Enable JSON structured output
```

### 3. Update BotResponse Model

**File**: `src/models/bot_response.py`

**Changes:**
```python
# Add import at top
from typing import Optional
from src.models.structured_response import StructuredLLMResponse

# Update BotResponse dataclass
@dataclass
class BotResponse:
    """An answer to a user query with rule citations."""

    response_id: UUID
    query_id: UUID
    answer_text: str  # JSON string if structured, markdown if not
    citations: List[Citation]
    confidence_score: float
    rag_score: float
    validation_passed: bool
    llm_model: LLMModel
    token_count: int
    latency_ms: int
    timestamp: datetime
    structured_data: Optional[StructuredLLMResponse] = None  # ← NEW

    # ... existing methods remain unchanged ...
```

### 4. Update Discord Formatter

**File**: `src/services/discord/formatter.py`

**Changes:**
```python
# Add import
from src.models.structured_response import StructuredLLMResponse
import json

def format_response(
    bot_response: BotResponse,
    validation_result: ValidationResult,
    smalltalk: bool = False,
) -> List[discord.Embed]:
    """Format bot response as Discord embeds with citations.

    Handles both markdown and structured JSON responses.

    Args:
        bot_response: LLM response (markdown or JSON)
        validation_result: Validation result for confidence display
        smalltalk: If True, use purple color and skip disclaimer

    Returns:
        List of Discord embeds (usually 1, split if >2000 chars)
    """
    # Check if structured data available
    if bot_response.structured_data:
        return _format_structured(bot_response, validation_result, smalltalk)
    else:
        return _format_markdown(bot_response, validation_result, smalltalk)


def _format_structured(
    bot_response: BotResponse,
    validation_result: ValidationResult,
    smalltalk: bool = False,
) -> List[discord.Embed]:
    """Format structured JSON response as Discord embeds.

    Args:
        bot_response: BotResponse with structured_data populated
        validation_result: Validation result
        smalltalk: If True, use purple color

    Returns:
        List of Discord embeds
    """
    data = bot_response.structured_data

    # Determine embed color based on confidence
    color = _get_embed_color(bot_response.confidence_score, smalltalk)

    # Main embed with short answer + persona
    description = f"**{data.short_answer}** {data.persona_short_answer}"

    embed = discord.Embed(
        title="Kill Team Rules Bot",
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # Add quotes as embed fields (max 25 fields per embed)
    for i, quote in enumerate(data.quotes[:25]):
        embed.add_field(
            name=f"**{quote.quote_title}**",
            value=f"> {quote.quote_text}",
            inline=False
        )

    # Add explanation field
    embed.add_field(
        name="Explanation",
        value=data.explanation,
        inline=False
    )

    # Add persona afterword
    embed.add_field(
        name="",
        value=f"*{data.persona_afterword}*",
        inline=False
    )

    # Add disclaimer if not smalltalk
    if not smalltalk:
        disclaimer_text = get_random_disclaimer()
        embed.add_field(
            name="Disclaimer",
            value=f"*{disclaimer_text}*",
            inline=True,
        )

    # Footer with metadata
    footer_content = (
        f"ID: {str(bot_response.response_id)[:8]} | "
        f"Model: {bot_response.llm_model} | "
        f"Latency: {bot_response.latency_ms}ms"
    )
    if not smalltalk:
        confidence_emoji = _get_confidence_emoji(bot_response.confidence_score)
        footer_content += f" | Confidence: {confidence_emoji} {bot_response.confidence_score:.0%}"

    embed.set_footer(text=footer_content)

    return [embed]


def _format_markdown(
    bot_response: BotResponse,
    validation_result: ValidationResult,
    smalltalk: bool = False,
) -> List[discord.Embed]:
    """Format markdown response as Discord embeds (existing implementation).

    This is the current implementation - kept for backwards compatibility.
    """
    # Existing format_response implementation goes here
    # (current code from line 27-64)
    color = _get_embed_color(bot_response.confidence_score, smalltalk)

    embed = discord.Embed(
        title="Kill Team Rules Bot",
        description=bot_response.answer_text[:2000],
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    if not smalltalk:
        disclaimer_text = get_random_disclaimer()
        embed.add_field(
            name="Disclaimer",
            value=f"*{disclaimer_text}*",
            inline=True,
        )

    footer_content = f"ID: {str(bot_response.response_id)[:8]} | Model: {bot_response.llm_model} | Latency: {bot_response.latency_ms}ms"
    if not smalltalk:
        confidence_emoji = _get_confidence_emoji(bot_response.confidence_score)
        footer_content += f" | Confidence: {confidence_emoji} {bot_response.confidence_score:.0%}"
    embed.set_footer(text=footer_content)

    return [embed]


def _get_embed_color(confidence_score: float, smalltalk: bool) -> discord.Color:
    """Get embed color based on confidence score.

    Args:
        confidence_score: LLM confidence (0-1)
        smalltalk: If True, return purple

    Returns:
        Discord color
    """
    if smalltalk:
        return discord.Color.purple()
    elif confidence_score >= 0.8:
        return discord.Color.green()
    elif confidence_score >= 0.6:
        return discord.Color.gold()
    else:
        return discord.Color.red()


def _get_confidence_emoji(confidence_score: float) -> str:
    """Get confidence emoji based on score.

    Args:
        confidence_score: LLM confidence (0-1)

    Returns:
        Emoji string
    """
    if confidence_score >= 0.8:
        return "🟢"
    elif confidence_score >= 0.6:
        return "🟡"
    else:
        return "🔴"
```

### 5. Update Orchestrator

**File**: `src/services/discord/bot.py`

**Changes:**
```python
# Add import at top
from src.models.structured_response import StructuredLLMResponse
from src.lib.constants import LLM_USE_STRUCTURED_OUTPUT
import json

# Update process_query method (around line 120)
# Step 4: LLM generation with structured output support
llm_response = await retry_on_content_filter(
    self.llm.generate,
    GenerationRequest(
        prompt=user_query.sanitized_text,
        context=[chunk.text for chunk in rag_context.document_chunks],
        config=GenerationConfig(
            timeout_seconds=LLM_GENERATION_TIMEOUT,
            use_structured_output=LLM_USE_STRUCTURED_OUTPUT  # ← Enable structured output
        ),
    ),
    timeout_seconds=LLM_GENERATION_TIMEOUT
)

# Parse structured data if JSON response
structured_data = None
if llm_response.answer_text.strip().startswith("{"):
    try:
        structured_data = StructuredLLMResponse.from_json(llm_response.answer_text)
        structured_data.validate()
        logger.debug(
            "Parsed structured LLM response",
            extra={
                "correlation_id": correlation_id,
                "quotes_count": len(structured_data.quotes),
            }
        )
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(
            f"Failed to parse structured response, using markdown fallback: {e}",
            extra={"correlation_id": correlation_id}
        )
        # Keep structured_data as None, will use markdown formatting

# ... (rest of existing code for validation, citation creation, etc.) ...

# Update BotResponse creation (around line 180)
bot_response = BotResponse.create(
    query_id=user_query.query_id,
    answer_text=llm_response.answer_text,
    citations=citations,
    confidence_score=llm_response.confidence_score,
    rag_score=rag_context.avg_relevance,
    llm_model=llm_response.model_version,
    token_count=llm_response.token_count,
    latency_ms=llm_response.latency_ms,
    structured_data=structured_data,  # ← NEW: Pass structured data
)
```

### 6. Database Schema Migration

**File**: `src/lib/database.py`

**Changes:**
```python
# Update SCHEMA_SQL constant
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS queries (
    query_id TEXT PRIMARY KEY,
    discord_server_id TEXT NOT NULL,
    discord_server_name TEXT,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    username TEXT NOT NULL,
    query_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    response_format TEXT DEFAULT 'markdown',  -- ← NEW: 'markdown' | 'json'
    llm_model TEXT NOT NULL,
    confidence_score REAL,
    rag_score REAL,
    validation_passed INTEGER,
    latency_ms INTEGER,
    timestamp TEXT NOT NULL,
    upvotes INTEGER DEFAULT 0,
    downvotes INTEGER DEFAULT 0,
    admin_status TEXT DEFAULT 'pending',
    admin_notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON queries(timestamp);
CREATE INDEX IF NOT EXISTS idx_admin_status ON queries(admin_status);
CREATE INDEX IF NOT EXISTS idx_llm_model ON queries(llm_model);
CREATE INDEX IF NOT EXISTS idx_channel_id ON queries(channel_id);
CREATE INDEX IF NOT EXISTS idx_response_format ON queries(response_format);  -- ← NEW

-- Optional: Store quotes separately for analytics
CREATE TABLE IF NOT EXISTS response_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id TEXT NOT NULL,
    quote_rank INTEGER NOT NULL,
    quote_title TEXT NOT NULL,
    quote_text TEXT NOT NULL,
    relevant INTEGER DEFAULT NULL,  -- Admin can mark relevant/irrelevant
    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_quote_query_id ON response_quotes(query_id);
CREATE INDEX IF NOT EXISTS idx_quote_relevant ON response_quotes(relevant);
"""

# Update insert_query method
def insert_query(self, query_data: Dict[str, Any]) -> None:
    """Insert query + response record.

    Args:
        query_data: Dictionary with query fields including:
            - response_format: 'markdown' or 'json' (optional, defaults to 'markdown')
    """
    if not self.enabled:
        return

    try:
        now = datetime.now(timezone.utc).isoformat()

        # Determine response format
        response_format = query_data.get("response_format", "markdown")

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO queries (
                    query_id, discord_server_id, discord_server_name,
                    channel_id, channel_name, username,
                    query_text, response_text, response_format, llm_model,
                    confidence_score, rag_score, validation_passed,
                    latency_ms, timestamp, upvotes, downvotes,
                    admin_status, admin_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                query_data["query_id"],
                query_data["discord_server_id"],
                query_data.get("discord_server_name", ""),
                query_data["channel_id"],
                query_data.get("channel_name", ""),
                query_data["username"],
                query_data["query_text"],
                query_data["response_text"],
                response_format,  # ← NEW
                query_data["llm_model"],
                query_data.get("confidence_score"),
                query_data.get("rag_score"),
                query_data.get("validation_passed", 0),
                query_data.get("latency_ms"),
                query_data["timestamp"],
                0,  # upvotes
                0,  # downvotes
                "pending",  # admin_status
                None,  # admin_notes
                now,
                now,
            ))
            conn.commit()

        logger.debug(f"Inserted query record: {query_data['query_id']}")

    except Exception as e:
        logger.error(f"Failed to insert query: {e}")

# Add new method for inserting quotes
def insert_response_quotes(
    self,
    query_id: str,
    quotes: List[Dict[str, str]]
) -> None:
    """Insert response quotes for a query.

    Args:
        query_id: Query ID
        quotes: List of dicts with 'quote_title' and 'quote_text'
    """
    if not self.enabled:
        return

    try:
        with self._get_connection() as conn:
            for rank, quote in enumerate(quotes):
                conn.execute("""
                    INSERT INTO response_quotes (
                        query_id, quote_rank, quote_title, quote_text
                    ) VALUES (?, ?, ?, ?)
                """, (
                    query_id,
                    rank,
                    quote["quote_title"],
                    quote["quote_text"]
                ))
            conn.commit()

        logger.debug(f"Inserted {len(quotes)} quotes for query {query_id}")

    except Exception as e:
        logger.error(f"Failed to insert quotes: {e}")
```

**Migration Script**: `scripts/migrate_database_for_structured_output.py` (NEW)

```python
"""Database migration script for structured output support.

Adds response_format column and response_quotes table.
Safe to run multiple times (idempotent).
"""

import sqlite3
from pathlib import Path


def migrate():
    """Run database migration."""
    db_path = Path("data/analytics.db")

    if not db_path.exists():
        print("No database found, skipping migration")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if response_format column exists
    cursor.execute("PRAGMA table_info(queries)")
    columns = [row[1] for row in cursor.fetchall()]

    if "response_format" not in columns:
        print("Adding response_format column...")
        cursor.execute("""
            ALTER TABLE queries
            ADD COLUMN response_format TEXT DEFAULT 'markdown'
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_response_format
            ON queries(response_format)
        """)
        conn.commit()
        print("✓ Added response_format column")
    else:
        print("✓ response_format column already exists")

    # Check if response_quotes table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='response_quotes'
    """)

    if not cursor.fetchone():
        print("Creating response_quotes table...")
        cursor.execute("""
            CREATE TABLE response_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id TEXT NOT NULL,
                quote_rank INTEGER NOT NULL,
                quote_title TEXT NOT NULL,
                quote_text TEXT NOT NULL,
                relevant INTEGER DEFAULT NULL,
                FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE INDEX idx_quote_query_id ON response_quotes(query_id)
        """)
        cursor.execute("""
            CREATE INDEX idx_quote_relevant ON response_quotes(relevant)
        """)
        conn.commit()
        print("✓ Created response_quotes table")
    else:
        print("✓ response_quotes table already exists")

    conn.close()
    print("\n✅ Migration complete!")


if __name__ == "__main__":
    migrate()
```

### 7. Update Constants

**File**: `src/lib/constants.py`

**Changes:**
```python
# Add feature flag for structured output
LLM_USE_STRUCTURED_OUTPUT = os.getenv(
    "LLM_USE_STRUCTURED_OUTPUT", "false"
).lower() == "true"
```

**File**: `config/.env.template`

**Changes:**
```bash
# LLM Structured Output (JSON mode)
# Set to "true" to enable native structured JSON responses from LLMs
# Default: "false" (uses markdown format)
LLM_USE_STRUCTURED_OUTPUT=false
```

### 8. Update System Prompt

**File**: `prompts/rule-helper-prompt.md`

**Changes:**
```markdown
## Output Structure

**Note**: When structured output is enabled, the response format is enforced via JSON schema. The structure below applies to markdown output mode only.

The output has 3 parts in this order:
1. Short answer
   - Open with a **direct, short answer** to the user's question in **bold**.
...
```

## Testing Strategy

### Unit Tests

**File**: `tests/unit/test_structured_response.py` (NEW)

```python
"""Unit tests for structured response models."""

import json
import pytest

from src.models.structured_response import StructuredQuote, StructuredLLMResponse


class TestStructuredQuote:
    """Tests for StructuredQuote model."""

    def test_to_markdown(self):
        """Test markdown conversion."""
        quote = StructuredQuote(
            quote_title="Core Rules: Actions",
            quote_text="A model cannot perform the same action twice."
        )

        markdown = quote.to_markdown()
        assert "**Core Rules: Actions**" in markdown
        assert "A model cannot perform the same action twice." in markdown
        assert markdown.startswith(">")


class TestStructuredLLMResponse:
    """Tests for StructuredLLMResponse model."""

    @pytest.fixture
    def valid_json(self):
        """Valid JSON response."""
        return json.dumps({
            "short_answer": "No.",
            "persona_short_answer": "A trivial calculation.",
            "quotes": [
                {
                    "quote_title": "Core Rules: Actions",
                    "quote_text": "A model cannot perform the same action twice."
                }
            ],
            "explanation": "The rule explicitly forbids it.",
            "persona_afterword": "The logic is absolute."
        })

    def test_from_json_valid(self, valid_json):
        """Test parsing valid JSON."""
        response = StructuredLLMResponse.from_json(valid_json)

        assert response.short_answer == "No."
        assert response.persona_short_answer == "A trivial calculation."
        assert len(response.quotes) == 1
        assert response.quotes[0].quote_title == "Core Rules: Actions"
        assert response.explanation == "The rule explicitly forbids it."
        assert response.persona_afterword == "The logic is absolute."

    def test_from_json_invalid_json(self):
        """Test parsing invalid JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            StructuredLLMResponse.from_json("{invalid json")

    def test_from_json_missing_fields(self):
        """Test parsing JSON with missing fields."""
        incomplete_json = json.dumps({
            "short_answer": "No.",
            "quotes": []
        })

        with pytest.raises(ValueError, match="Missing required fields"):
            StructuredLLMResponse.from_json(incomplete_json)

    def test_from_json_invalid_quote_structure(self):
        """Test parsing JSON with invalid quote structure."""
        invalid_quotes_json = json.dumps({
            "short_answer": "No.",
            "persona_short_answer": "Obvious.",
            "quotes": [{"title_only": "No text"}],
            "explanation": "Test",
            "persona_afterword": "Test"
        })

        with pytest.raises(ValueError, match="Invalid quote structure"):
            StructuredLLMResponse.from_json(invalid_quotes_json)

    def test_validate_empty_strings(self, valid_json):
        """Test validation catches empty strings."""
        response = StructuredLLMResponse.from_json(valid_json)
        response.short_answer = "   "  # Empty after strip

        with pytest.raises(ValueError, match="short_answer cannot be empty"):
            response.validate()

    def test_validate_empty_quotes(self, valid_json):
        """Test validation catches empty quotes list."""
        response = StructuredLLMResponse.from_json(valid_json)
        response.quotes = []

        with pytest.raises(ValueError, match="quotes list cannot be empty"):
            response.validate()

    def test_to_markdown(self, valid_json):
        """Test markdown conversion."""
        response = StructuredLLMResponse.from_json(valid_json)
        markdown = response.to_markdown()

        # Check all sections present
        assert "**No.**" in markdown
        assert "A trivial calculation." in markdown
        assert "**Core Rules: Actions**" in markdown
        assert "## Explanation" in markdown
        assert "The logic is absolute." in markdown
```

### Contract Tests

**File**: `tests/contract/test_llm_structured_output.py` (NEW)

```python
"""Contract tests for LLM structured output.

Verifies all providers return valid JSON conforming to schema.
Requires API keys - run with: pytest tests/contract/test_llm_structured_output.py
"""

import json
import pytest

from src.services.llm.factory import LLMProviderFactory
from src.services.llm.base import GenerationRequest, GenerationConfig, STRUCTURED_OUTPUT_SCHEMA
from src.models.structured_response import StructuredLLMResponse


PROVIDERS_TO_TEST = [
    "claude-sonnet",
    "gpt-4o",
    "gemini-2.5-flash",
    "grok-3",
    "deepseek-chat"
]

TEST_PROMPT = "Can a model perform two Shoot actions in the same activation?"
TEST_CONTEXT = [
    "Core Rules: Actions\nA model cannot perform the same action more than once in the same activation."
]


@pytest.mark.parametrize("provider", PROVIDERS_TO_TEST)
@pytest.mark.asyncio
async def test_provider_structured_output(provider):
    """Test provider returns valid structured JSON.

    This is a contract test - verifies the provider respects the schema.
    """
    # Create provider
    llm = LLMProviderFactory.create(provider)

    # Generate with structured output enabled
    request = GenerationRequest(
        prompt=TEST_PROMPT,
        context=TEST_CONTEXT,
        config=GenerationConfig(use_structured_output=True)
    )

    response = await llm.generate(request)

    # Verify response is valid JSON
    try:
        data = json.loads(response.answer_text)
    except json.JSONDecodeError:
        pytest.fail(f"{provider} returned invalid JSON: {response.answer_text}")

    # Verify all required fields present
    required_fields = STRUCTURED_OUTPUT_SCHEMA["required"]
    missing_fields = [f for f in required_fields if f not in data]
    assert not missing_fields, f"{provider} missing fields: {missing_fields}"

    # Verify quotes structure
    assert isinstance(data["quotes"], list), f"{provider} quotes must be array"
    assert len(data["quotes"]) > 0, f"{provider} must return at least one quote"

    for i, quote in enumerate(data["quotes"]):
        assert "quote_title" in quote, f"{provider} quote[{i}] missing quote_title"
        assert "quote_text" in quote, f"{provider} quote[{i}] missing quote_text"

    # Verify can parse into model
    try:
        structured_response = StructuredLLMResponse.from_json(response.answer_text)
        structured_response.validate()
    except Exception as e:
        pytest.fail(f"{provider} failed to parse: {e}")

    print(f"✓ {provider} returned valid structured output")
```

### Quality Test Updates

**File**: `tests/quality/evaluator.py`

**Changes:**
```python
import json

class RequirementEvaluator:
    """Evaluates test requirements against responses."""

    # ... existing code ...

    def _evaluate_contains(
        self, requirement: TestRequirement, response: str
    ) -> RequirementResult:
        """Evaluate a 'contains' requirement.

        Supports both markdown and structured JSON responses.

        Args:
            requirement: Requirement to evaluate
            response: Response text (markdown or JSON)

        Returns:
            RequirementResult
        """
        # Check if response is JSON
        if response.strip().startswith("{"):
            return self._evaluate_contains_structured(requirement, response)
        else:
            return self._evaluate_contains_markdown(requirement, response)

    def _evaluate_contains_structured(
        self, requirement: TestRequirement, response: str
    ) -> RequirementResult:
        """Evaluate 'contains' for structured JSON response.

        Supports field-specific checks like:
        - "short_answer contains 'Yes'"
        - "quote_title contains 'Overwatch'"
        - "explanation contains 'control range'"

        Args:
            requirement: Requirement with description like "field contains 'value'"
            response: JSON string

        Returns:
            RequirementResult
        """
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            return RequirementResult(
                requirement=requirement,
                passed=False,
                points_earned=0,
                details="Failed to parse JSON response"
            )

        # Parse requirement description
        # Format: "field contains 'expected_text'"
        if " contains " in requirement.description.lower():
            parts = requirement.description.split(" contains ", 1)
            field = parts[0].strip().lower()
            expected = parts[1].strip().strip("'\"")

            # Check field
            if field == "short_answer":
                actual = data.get("short_answer", "")
            elif field == "explanation":
                actual = data.get("explanation", "")
            elif field == "quote_title":
                # Check any quote title
                actual = " ".join([q.get("quote_title", "") for q in data.get("quotes", [])])
            elif field == "quote_text":
                # Check any quote text
                actual = " ".join([q.get("quote_text", "") for q in data.get("quotes", [])])
            else:
                actual = data.get(field, "")

            # Case-insensitive check
            passed = expected.lower() in actual.lower()

            return RequirementResult(
                requirement=requirement,
                passed=passed,
                points_earned=requirement.points if passed else 0,
                details=f"Field '{field}' {'contains' if passed else 'does not contain'} '{expected}'"
            )
        else:
            # Fall back to checking entire JSON string
            passed = requirement.description.lower() in response.lower()
            return RequirementResult(
                requirement=requirement,
                passed=passed,
                points_earned=requirement.points if passed else 0
            )

    def _evaluate_contains_markdown(
        self, requirement: TestRequirement, response: str
    ) -> RequirementResult:
        """Evaluate 'contains' for markdown response (existing implementation).

        Args:
            requirement: Requirement to evaluate
            response: Markdown response text

        Returns:
            RequirementResult
        """
        # Existing implementation (lines 86-113)
        clean_response = self._strip_markdown(response)
        clean_requirement = requirement.description.strip()

        # Case-insensitive check
        passed = clean_requirement.lower() in clean_response.lower()

        return RequirementResult(
            requirement=requirement,
            passed=passed,
            points_earned=requirement.points if passed else 0,
            details=f"Response {'contains' if passed else 'does not contain'} '{clean_requirement}'"
        )
```

## Rollout Plan

### Week 1: Implementation
- [ ] Create `src/models/structured_response.py`
- [ ] Update `src/services/llm/base.py` (schema + config)
- [ ] Implement structured output in all providers:
  - [ ] `src/services/llm/chatgpt.py` (function calling)
  - [ ] `src/services/llm/claude.py` (tool use)
  - [ ] `src/services/llm/gemini.py` (JSON mode)
  - [ ] `src/services/llm/grok.py` (function calling)
  - [ ] Verify `src/services/llm/deepseek.py` (function calling)
- [ ] Update `src/models/bot_response.py` (add structured_data field)
- [ ] Write unit tests (`tests/unit/test_structured_response.py`)

### Week 2: Integration
- [ ] Update `src/services/discord/formatter.py` (structured formatting)
- [ ] Update `src/services/discord/bot.py` (enable structured output)
- [ ] Add feature flag to `src/lib/constants.py`
- [ ] Update `prompts/rule-helper-prompt.md` (note about JSON mode)
- [ ] Database migration:
  - [ ] Update `src/lib/database.py` (schema changes)
  - [ ] Create migration script
  - [ ] Run migration on dev database

### Week 3: Testing
- [ ] Write contract tests (`tests/contract/test_llm_structured_output.py`)
- [ ] Update quality test evaluator (`tests/quality/evaluator.py`)
- [ ] Run contract tests with all providers (verify JSON output)
- [ ] Run quality tests with structured output enabled
- [ ] Compare metrics:
  - Parsing success rate (should be 100% with strict mode)
  - Quote accuracy (check if quotes are more relevant)
  - User feedback (if A/B testing enabled)

### Week 4: Rollout
- [ ] **Stage 1** (10% of queries):
  - Set `LLM_USE_STRUCTURED_OUTPUT=true` for 10% random sample
  - Monitor error rates, parsing failures
  - Collect user feedback
- [ ] **Stage 2** (50% of queries):
  - If Stage 1 successful, increase to 50%
  - Continue monitoring metrics
- [ ] **Stage 3** (100% rollout):
  - Enable for all queries
  - Update default in `.env.template` to `true`
  - Announce in release notes

### Rollback Plan
If issues arise:
1. Set `LLM_USE_STRUCTURED_OUTPUT=false` in `.env`
2. Restart bot (no code changes needed)
3. Database supports both formats (no data loss)
4. Investigate failures in logs
5. Fix issues and re-test before re-enabling

## Success Metrics

### Technical Metrics
- **Parsing Success Rate**: Should be 100% (strict mode guarantees schema)
- **Validation Failures**: Should drop to near 0
- **Response Latency**: Should remain within ±10% of baseline

### Quality Metrics
- **Quote Accuracy**: Measure if quotes are more relevant to question
- **Field Completeness**: All required fields populated
- **Schema Violations**: Should be 0 with strict mode

### User Experience Metrics
- **User Feedback**: Monitor upvotes/downvotes in Discord
- **Admin Review Time**: Structured quotes easier to review
- **Error Reports**: Track parsing/formatting errors

## Future Enhancements

### Multi-Hop Reasoning (Post-Migration)
Once structured output is stable:
1. Enable follow-up questions based on quotes
2. Extract specific quotes for clarification
3. Chain reasoning: quote → analyze → re-query

Example:
```
User: "Can I use Overwatch against a charge?"
Bot: **No.** [quotes Overwatch rule]
Bot: "Would you like me to explain the Charge action for context? [React: 👍]"
```

### Quote Relevance Tracking
Store quote relevance in `response_quotes` table:
- Admin marks quotes as relevant/irrelevant
- Train RAG retrieval based on marked quotes
- Improve chunk selection over time

### A/B Testing
Compare structured vs markdown:
- Random 50/50 split
- Track user feedback (upvotes)
- Measure response quality
- Choose winner based on data

## Open Questions

1. **Character Limits**: Discord embeds have field limits - what if LLM returns 30 quotes?
   - **Answer**: Limit to first 25 quotes (Discord embed field limit)

2. **Fallback Strategy**: What if JSON parsing fails despite strict mode?
   - **Answer**: Log error, use markdown fallback, increment failure counter

3. **Cost Impact**: Does structured output increase token usage?
   - **Answer**: ~50-100 extra tokens for function calling, offset by reduced parsing errors

4. **Extended Thinking**: Claude 3.7 Sonnet doesn't support tool calling with extended thinking - fallback?
   - **Answer**: Disable structured output for extended thinking mode, use markdown

## References

- OpenAI Function Calling: https://platform.openai.com/docs/guides/function-calling
- Claude Tool Use: https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview
- Gemini JSON Mode: https://ai.google.dev/gemini-api/docs/structured-output
- DeepSeek Function Calling: https://api-docs.deepseek.com/guides/function_calling
- Grok Structured Outputs: https://docs.x.ai/docs/guides/structured-outputs

---

**Last Updated**: 2025-10-20
**Next Review**: After Week 1 implementation complete
