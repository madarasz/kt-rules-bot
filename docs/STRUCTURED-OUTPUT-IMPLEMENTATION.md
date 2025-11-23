# Structured JSON Output Implementation

**Status**: ✅ **COMPLETE** (as of 2025-11-23)
**Original Plan**: 2025-10-20
**Implementation Completed**: 2025-11-23

## Overview

The Kill Team Rules Bot now uses **native structured JSON outputs** from all LLM providers instead of unstructured markdown. This was accomplished using each provider's built-in capabilities: function calling (OpenAI/Grok/DeepSeek), tool use (Claude), and JSON mode with Pydantic schemas (Gemini).

## Implementation Summary

### ✅ What Was Implemented

All 5 LLM providers now return structured JSON responses with schema validation:

1. **ChatGPT** (OpenAI) - Function calling with `strict: true`
2. **Claude** (Anthropic) - Tool use with `input_schema`
3. **Gemini** (Google) - JSON mode with Pydantic models
4. **Grok** (xAI) - Function calling (OpenAI-compatible)
5. **DeepSeek** - Function calling (OpenAI-compatible)

### JSON Schema

All providers conform to this schema (with minor provider-specific variations):

```json
{
  "type": "object",
  "properties": {
    "smalltalk": {
      "type": "boolean",
      "description": "True if casual conversation, False if rules question"
    },
    "short_answer": {
      "type": "string",
      "description": "Direct, short answer (e.g., 'Yes.')"
    },
    "persona_short_answer": {
      "type": "string",
      "description": "Condescending phrase (e.g., 'The affirmative is undeniable.')"
    },
    "quotes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "quote_title": {
            "type": "string",
            "description": "Rule name (e.g., 'Core Rules: Actions')"
          },
          "quote_text": {
            "type": "string",
            "description": "Relevant rule excerpt"
          },
          "chunk_id": {
            "type": "string",
            "description": "RAG chunk identifier (last 8 chars of UUID)"
          }
        },
        "required": ["quote_title", "quote_text", "chunk_id"]
      }
    },
    "explanation": {
      "type": "string",
      "description": "Rules-based explanation using official terminology"
    },
    "persona_afterword": {
      "type": "string",
      "description": "Dismissive concluding sentence"
    }
  },
  "required": [
    "smalltalk",
    "short_answer",
    "persona_short_answer",
    "quotes",
    "explanation",
    "persona_afterword"
  ]
}
```

### Multi-Hop Evaluation Schema

For iterative RAG retrieval, a separate schema evaluates context sufficiency:

```json
{
  "type": "object",
  "properties": {
    "can_answer": {
      "type": "boolean",
      "description": "True if context sufficient, false otherwise"
    },
    "reasoning": {
      "type": "string",
      "description": "1-2 sentences explaining what's available or missing"
    },
    "missing_query": {
      "type": "string",
      "description": "Focused retrieval query for missing context (empty if can_answer=true)"
    }
  },
  "required": ["can_answer", "reasoning", "missing_query"]
}
```

## Provider-Specific Implementations

### OpenAI (ChatGPT, GPT-4, GPT-5, o-series)

**Location**: `src/services/llm/chatgpt.py`

**Approach**: Function calling with strict mode

```python
api_params["tools"] = [{
    "type": "function",
    "function": {
        "name": "format_kill_team_answer",
        "description": "Format Kill Team rules answer with quotes",
        "parameters": STRUCTURED_OUTPUT_SCHEMA,
        "strict": True  # ← Enforces 100% schema compliance
    }
}]
api_params["tool_choice"] = {
    "type": "function",
    "function": {"name": "format_kill_team_answer"}
}
```

**Reasoning Token Support**: GPT-5 and o-series models use `max_completion_tokens` (3x multiplier) to account for internal reasoning tokens.

### Anthropic (Claude)

**Location**: `src/services/llm/claude.py`

**Approach**: Tool use with forced tool calling

```python
tools=[{
    "name": "format_kill_team_answer",
    "description": "Format Kill Team rules answer",
    "input_schema": STRUCTURED_OUTPUT_SCHEMA
}],
tool_choice={
    "type": "tool",
    "name": "format_kill_team_answer"
}
```

**Note**: Does NOT work with extended thinking mode (Claude 3.7+ thinking).

### Google (Gemini)

**Location**: `src/services/llm/gemini.py`
**Schemas**: `src/services/llm/gemini_schemas.py`

**Approach**: JSON mode with Pydantic models (Google's November 2024 recommendation)

```python
# Pydantic models
class GeminiQuote(BaseModel):
    quote_title: str
    quote_text: str
    sentence_numbers: list[int]
    chunk_id: str

class GeminiAnswer(BaseModel):
    smalltalk: bool
    short_answer: str
    persona_short_answer: str
    quotes: list[GeminiQuote]
    explanation: str
    persona_afterword: str

# Generation config
generation_config = {
    "max_output_tokens": max_tokens,
    "temperature": request.config.temperature,
    "response_mime_type": "application/json",
    "response_schema": pydantic_model.model_json_schema(),
}

# Validation
pydantic_response = pydantic_model.model_validate_json(answer_text)
```

**Special Feature - Sentence Numbering**: To avoid RECITATION errors (Google safety filter blocking verbatim quotes), Gemini uses a two-phase approach:

1. **Pre-process**: Number all sentences in context chunks: `[S1] First sentence. [S2] Second sentence.`
2. **LLM returns**: Sentence numbers only in `sentence_numbers` field, `quote_text` is empty
3. **Post-process**: Extract verbatim quotes using sentence numbers

**Files**:
- `src/services/llm/gemini_quote_extractor.py` - Sentence numbering and extraction
- `prompts/rule-helper-prompt-gemini.md` - Gemini-specific system prompt

**Reasoning Token Support**: Gemini 2.5+ models use `max_output_tokens` (3x multiplier) for models with thinking capabilities.

### xAI (Grok)

**Location**: `src/services/llm/grok.py`

**Approach**: Function calling (OpenAI SDK with custom base_url)

Identical implementation to ChatGPT, using OpenAI SDK with `base_url="https://api.x.ai/v1"`.

### DeepSeek

**Location**: `src/services/llm/deepseek.py`

**Approach**: Function calling (OpenAI SDK with custom base_url)

Identical implementation to ChatGPT, using OpenAI SDK with `base_url="https://api.deepseek.com"`.

## Benefits Achieved

### Technical Benefits

✅ **Zero parsing errors** - Provider-level schema validation guarantees compliance
✅ **Type safety** - Pydantic models (Gemini) provide compile-time validation
✅ **Consistent structure** - All providers return identical JSON format
✅ **Multi-hop ready** - Structured quotes enable iterative context gathering

### Quality Benefits

✅ **Better quote extraction** - chunk_id enables precise citation tracking
✅ **Smalltalk detection** - Dedicated field separates casual chat from rules queries
✅ **Analytics-ready** - Quotes can be analyzed separately from explanations

### User Experience Benefits

✅ **Discord embed formatting** - (Not yet implemented, but structured data enables it)
✅ **Cleaner responses** - JSON structure enforced at provider level

## Configuration

**File**: `src/services/llm/base.py`

```python
@dataclass
class GenerationConfig:
    """Configuration for answer generation."""

    max_tokens: int = LLM_DEFAULT_MAX_TOKENS
    temperature: float = LLM_DEFAULT_TEMPERATURE
    system_prompt: str = field(default_factory=load_system_prompt)
    include_citations: bool = True
    timeout_seconds: int = LLM_GENERATION_TIMEOUT
    structured_output_schema: str = "default"  # "default" or "hop_evaluation"
```

**Schema Selection**:
- `"default"` → Uses `STRUCTURED_OUTPUT_SCHEMA` for normal queries
- `"hop_evaluation"` → Uses `HOP_EVALUATION_SCHEMA` for multi-hop retrieval evaluation

## Reasoning Token Support

Both **ChatGPT** and **Gemini** now support models with internal reasoning capabilities (GPT-5, o-series, Gemini 2.5+).

**Implementation**:
```python
# In __init__
reasoning_models = ["gpt-5", "o3", "o4-mini"]  # ChatGPT
reasoning_models = ["gemini-2.5-pro", "gemini-3-pro-preview"]  # Gemini
self.uses_completion_tokens = model in reasoning_models

# In generate()
if self.uses_completion_tokens:
    max_tokens = request.config.max_tokens * 3  # Account for reasoning tokens
    logger.info(f"Using max_tokens={max_tokens} (3x for reasoning)")
```

This multiplier gives models enough room for both:
- **Reasoning tokens** (internal thinking, not shown to user)
- **Completion tokens** (visible JSON output)

## Testing

### Contract Tests

**File**: `tests/contract/test_llm_adapters.py`

All providers have contract tests verifying:
- Valid JSON output
- Schema compliance (all required fields present)
- Quote structure (array with title/text/chunk_id)

Run with:
```bash
pytest tests/contract/test_llm_adapters.py -k structured
```

### Quality Tests

**File**: `tests/quality/`

Quality tests validate response quality using structured JSON fields. The evaluator supports both markdown (legacy) and JSON responses.

## Not Implemented (Future Work)

The following items from the original migration plan were NOT implemented:

### ❌ Discord Formatter Update
- **Status**: Not implemented
- **Location**: `src/services/discord/formatter.py`
- **Why**: Still uses markdown formatting, doesn't leverage structured JSON for embeds
- **Impact**: Users don't benefit from improved formatting

### ❌ Structured Response Models
- **Status**: Not created
- **Location**: `src/models/structured_response.py` (doesn't exist)
- **Why**: Parsing is handled directly in bot orchestrator
- **Impact**: No reusable data models for structured responses

### ❌ BotResponse.structured_data Field
- **Status**: Not added
- **Location**: `src/models/bot_response.py`
- **Why**: Responses stored as JSON strings only
- **Impact**: No type-safe access to response fields

### ❌ Database Schema Updates
- **Status**: Not implemented
- **Location**: `src/lib/database.py`
- **Why**: Analytics DB doesn't track response_format or store quotes separately
- **Impact**: Can't analyze quote relevance or compare JSON vs markdown

### ❌ Feature Flag
- **Status**: Always enabled
- **Location**: No flag exists
- **Why**: Structured output is the only mode, no toggle
- **Impact**: Can't A/B test or gradually roll out

## File Structure

```
src/services/llm/
├── base.py                      # STRUCTURED_OUTPUT_SCHEMA + HOP_EVALUATION_SCHEMA
├── chatgpt.py                   # ✅ Function calling (strict mode)
├── claude.py                    # ✅ Tool use
├── gemini.py                    # ✅ JSON mode with Pydantic
├── gemini_schemas.py            # Pydantic models (GeminiAnswer, HopEvaluation)
├── gemini_quote_extractor.py   # Sentence numbering for RECITATION avoidance
├── grok.py                      # ✅ Function calling (OpenAI-compatible)
└── deepseek.py                  # ✅ Function calling (OpenAI-compatible)

prompts/
├── rule-helper-prompt.md        # Standard system prompt (all providers except Gemini)
└── rule-helper-prompt-gemini.md # Gemini-specific prompt (sentence numbering)

tests/contract/
└── test_llm_adapters.py         # Schema compliance tests for all providers
```

## Migration Notes

### Original Plan vs Reality

**Planned** (2025-10-20):
- 4-week phased rollout with feature flag
- Gradual 10% → 50% → 100% rollout
- A/B testing markdown vs JSON
- Database migration with separate quotes table

**Reality** (2025-11-23):
- Structured output implemented as the only mode (no flag)
- All providers support structured JSON from day 1
- No A/B testing, markdown mode removed
- Database stores JSON strings only

### Why the Change?

1. **Simpler architecture** - One code path instead of two
2. **Provider guarantees** - Schema enforcement at provider level eliminates parsing errors
3. **No backward compatibility needed** - Bot was new, no legacy data

## Future Enhancements

### 1. Discord Embed Formatting

Update `src/services/discord/formatter.py` to use structured JSON fields:

```python
def format_structured(response: BotResponse) -> List[discord.Embed]:
    data = json.loads(response.answer_text)

    embed = discord.Embed(
        title="Kill Team Rules Bot",
        description=f"**{data['short_answer']}** {data['persona_short_answer']}",
        color=get_color(response.confidence_score)
    )

    # Add quotes as embed fields (max 25)
    for quote in data['quotes'][:25]:
        embed.add_field(
            name=f"**{quote['quote_title']}**",
            value=f"> {quote['quote_text']}",
            inline=False
        )

    return [embed]
```

### 2. Structured Response Models

Create `src/models/structured_response.py` with Pydantic models:

```python
from pydantic import BaseModel

class Quote(BaseModel):
    quote_title: str
    quote_text: str
    chunk_id: str

class StructuredAnswer(BaseModel):
    smalltalk: bool
    short_answer: str
    persona_short_answer: str
    quotes: list[Quote]
    explanation: str
    persona_afterword: str
```

### 3. Analytics Database

Add `response_format` column and `response_quotes` table:

```sql
ALTER TABLE queries ADD COLUMN response_format TEXT DEFAULT 'json';

CREATE TABLE response_quotes (
    id INTEGER PRIMARY KEY,
    query_id TEXT NOT NULL,
    quote_rank INTEGER NOT NULL,
    quote_title TEXT NOT NULL,
    quote_text TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    relevant INTEGER DEFAULT NULL,  -- Admin marks as relevant/irrelevant
    FOREIGN KEY (query_id) REFERENCES queries(query_id)
);
```

### 4. Quote Relevance Tracking

Allow admins to mark quotes as relevant/irrelevant in dashboard:
- Improves RAG chunk selection over time
- Identifies common retrieval mistakes
- Enables quote-level quality metrics

## Success Metrics

### Achieved

✅ **100% schema compliance** - All providers return valid JSON
✅ **Zero parsing errors** - Provider-level validation eliminates failures
✅ **Multi-hop ready** - `chunk_id` enables iterative retrieval
✅ **Reasoning token support** - GPT-5, o-series, Gemini 2.5+ supported

### Not Measured Yet

- Quote accuracy (no quote-level analytics)
- User feedback on JSON vs markdown (no A/B test)
- Admin review time improvement (no quote relevance tracking)

## References

### Provider Documentation

- **OpenAI Function Calling**: https://platform.openai.com/docs/guides/function-calling
- **Claude Tool Use**: https://docs.anthropic.com/claude/docs/tool-use
- **Gemini Structured Output**: https://ai.google.dev/gemini-api/docs/structured-output
- **Gemini Pydantic (Nov 2024)**: https://blog.google/technology/developers/gemini-api-structured-outputs/
- **Grok Structured Outputs**: https://docs.x.ai/docs/guides/structured-outputs
- **DeepSeek Function Calling**: https://api-docs.deepseek.com/guides/function_calling

### Related Files

- `src/services/CLAUDE.md` - Service architecture overview
- `src/services/llm/CLAUDE.md` - LLM provider integration guide
- `tests/quality/CLAUDE.md` - Quality testing framework

---

**Document Status**: Complete
**Last Updated**: 2025-11-23
**Original Migration Plan**: `src/services/llm/MIGRATE-TO-JSON-OUTPUT.md` (archived)
