# LLM Service

Multi-provider Large Language Model integration with unified interface.

## Purpose

Provides a provider-agnostic interface for LLM text generation and PDF extraction. Supports multiple LLM providers (Anthropic, OpenAI, Google, X) through a factory pattern with automatic retry, rate limiting, and error handling.

## Architecture

### Provider Pattern

All LLM providers implement the abstract base class [LLMProvider](base.py):

```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate response using LLM."""
        pass

    @abstractmethod
    async def extract_from_pdf(self, pdf_file: BinaryIO) -> str:
        """Extract markdown from PDF."""
        pass
```

This ensures:
- Provider independence (switch providers without code changes)
- Consistent error handling
- Unified configuration
- Easy testing with mocks

## Key Components

### Abstract Base Class ([base.py](base.py))
Defines the LLM provider interface:
- `GenerationRequest` / `LLMResponse` data models
- `GenerationConfig` for LLM parameters
- System prompt loading from `prompts/rule-helper-prompt.md`
- **Structured JSON output schema** for consistent response format
- Token counting and limits
- Abstract methods for `generate()` and `extract_pdf()`

**Contract**: Based on `specs/001-we-are-building/contracts/llm-adapter.md`

**Output Format**: All providers return **structured JSON** (not markdown) using:
- Claude: Tool use (`tool_choice`)
- ChatGPT/Grok: Function calling with strict mode
- Gemini: JSON mode (`response_mime_type: "application/json"`)
- DeepSeek: Function calling

This ensures consistent, parseable responses across all providers.

### LLM Factory ([factory.py](factory.py))
Creates LLM provider instances:
- Model registry mapping friendly names to actual model IDs
- Configuration-based provider selection
- API key management per provider
- Supports all providers and models in one place

**Supported Models**:
```python
# Anthropic
"claude-4.5-sonnet" → claude-sonnet-4-5-20250929
"claude-4.1-opus" → claude-opus-4-1-20250805
"claude-4.5-haiku" → claude-haiku-4-5-20251001

# Google
"gemini-2.5-pro" → gemini-2.5-pro
"gemini-2.5-flash" → gemini-2.5-flash

# OpenAI
"gpt-5" → gpt-5
"gpt-5-mini" → gpt-5-mini
"gpt-4.1" → gpt-4.1
"gpt-4.1-mini" → gpt-4.1-mini
"gpt-4o" → gpt-4o
"o3" → o3
"o3-mini" → o3-mini
"o4-mini" → o4-mini

# X/Grok
"grok-4-fast-reasoning" → grok-4-fast-reasoning
"grok-4-0709" → grok-4-0709
"grok-3" → grok-3
"grok-3-mini" → grok-3-mini

# DeepSeek
"deepseek-chat" → deepseek-chat
"deepseek-reasoner" → deepseek-reasoner
```

### Provider Implementations

#### Claude Adapter ([claude.py](claude.py))
Anthropic Claude integration:
- Uses `anthropic` Python SDK
- **Structured output**: Tool use with `format_kill_team_answer` tool
- Supports vision for PDF extraction
- Returns JSON via `tool_use_block.input` dict
- Default confidence: 0.8 (no logprobs available)

#### ChatGPT Adapter ([chatgpt.py](chatgpt.py))
OpenAI ChatGPT integration:
- Uses `openai` Python SDK
- **Structured output**: Function calling with `strict: true` mode
- Supports GPT-4, GPT-5, o-series models
- GPT-5/o-series: Uses `max_completion_tokens` (includes reasoning tokens)
- Returns JSON via `tool_calls[0].function.arguments`
- Default confidence: 0.8 (logprobs not available with function calling)
- PDF extraction via vision API (not yet implemented)

#### Gemini Adapter ([gemini.py](gemini.py))
Google Gemini integration:
- Uses `google-genai` SDK (new API)
- **Structured output**: JSON mode with `response_mime_type: "application/json"`
- Best for PDF extraction (native multimodal)
- Supports Gemini 2.5 Pro and Flash
- Returns JSON via `response.text`
- Confidence from safety ratings (0.5-0.9)
- Content filter detection via `finish_reason`

#### Grok Adapter ([grok.py](grok.py))
X/Grok integration:
- Uses `httpx` with OpenAI-compatible API
- **Structured output**: Function calling with tool choice
- Supports Grok 3 and Grok 4 models
- Fast reasoning capabilities
- Returns JSON via `tool_calls[0].function.arguments`
- Default confidence: 0.8
- PDF extraction not yet supported

#### DeepSeek Adapter ([deepseek.py](deepseek.py))
DeepSeek integration:
- Uses OpenAI SDK with custom base URL (`https://api.deepseek.com`)
- **Structured output**: Function calling (OpenAI-compatible)
- Supports deepseek-chat (standard) and deepseek-reasoner (with chain-of-thought)
- deepseek-reasoner uses Chain of Thought (CoT) reasoning before final answer
- Context window up to 128K tokens
- Default confidence: 0.8
- No PDF extraction support

### Supporting Services

#### Retry Logic ([retry.py](retry.py))
Automatic retry with exponential backoff:
- Handles transient errors (rate limits, timeouts)
- Handles content filter errors (rephrases prompt)
- Configurable max retries and backoff
- Preserves error context

#### Rate Limiter ([rate_limiter.py](rate_limiter.py))
Token-bucket rate limiting:
- Per-provider rate limits
- Prevents API quota exhaustion
- Configurable limits
- Thread-safe

#### Response Validator ([validator.py](validator.py))
Validates LLM responses:
- Checks for required fields
- Validates citation format
- Detects truncated responses
- Ensures response quality

## Request Flow

```
Application Code
    ↓
LLMProviderFactory.create("claude-4.5-sonnet")
    ↓
ClaudeAdapter instance
    ↓
generate(GenerationRequest)
    ↓
Rate limiter check
    ↓
Provider-specific API call (with retry)
    ↓
Response validation
    ↓
Return GenerationResponse
```

## Data Models

### GenerationRequest
```python
@dataclass
class GenerationRequest:
    prompt: str                    # User query
    context: List[str]             # RAG chunks
    config: GenerationConfig       # LLM parameters
```

### GenerationConfig
```python
@dataclass
class GenerationConfig:
    max_tokens: int = 2000
    temperature: float = 0.1
    system_prompt: str = load_system_prompt()
    include_citations: bool = True
    timeout_seconds: int = 30
```

### LLMResponse
```python
@dataclass
class LLMResponse:
    response_id: UUID
    answer_text: str               # Structured JSON string (not markdown!)
    confidence_score: float        # 0.0-1.0
    token_count: int               # Tokens used
    latency_ms: int                # Response time
    provider: str                  # "claude", "chatgpt", "gemini", etc.
    model_version: str             # Actual model ID
    citations_included: bool       # Whether citations are in response
```

### Structured JSON Output Schema
All LLM providers return JSON matching this schema:
```json
{
  "smalltalk": false,              // true if casual chat, false if rules question
  "short_answer": "Yes.",          // Direct answer
  "persona_short_answer": "Obviously.", // Condescending phrase
  "quotes": [                      // Rule quotations
    {
      "quote_title": "Core Rules: Actions",
      "quote_text": "Relevant excerpt from rules"
    }
  ],
  "explanation": "Detailed explanation...", // Rules-based explanation
  "persona_afterword": "Elementary."  // Concluding persona sentence
}
```

This JSON is parsed by [StructuredLLMResponse](../../../src/models/structured_response.py) and converted to Discord embeds.

## Configuration

From [src/lib/constants.py](../../lib/constants.py):
```python
# Default LLM
DEFAULT_LLM_PROVIDER = "claude-4.5-sonnet"

# Generation parameters
LLM_DEFAULT_MAX_TOKENS = 2000
LLM_DEFAULT_TEMPERATURE = 0.1
LLM_GENERATION_TIMEOUT = 30  # seconds

# PDF extraction parameters
LLM_EXTRACTION_MAX_TOKENS = 8000
LLM_EXTRACTION_TEMPERATURE = 0.0
LLM_EXTRACTION_TIMEOUT = 120  # seconds

# System prompt
LLM_SYSTEM_PROMPT_FILE_PATH = "prompts/rule-helper-prompt.md"

# Quality test judge
QUALITY_TEST_JUDGE_MODEL = "gpt-4o"
QUALITY_TEST_JUDGE_MAX_TOKENS = 200
QUALITY_TEST_JUDGE_TEMPERATURE = 0.0
```

From [src/lib/config.py](../../lib/config.py):
```python
# API keys (from environment)
ANTHROPIC_API_KEY
OPENAI_API_KEY
GOOGLE_API_KEY
X_API_KEY
DEEPSEEK_API_KEY
```

## Common Tasks

### Adding a New LLM Provider

1. **Create adapter file** (e.g., `cohere.py`):
```python
from src.services.llm.base import LLMProvider, GenerationRequest, GenerationResponse

class CohereAdapter(LLMProvider):
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.client = cohere.Client(api_key)

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        # Implement using Cohere SDK
        pass

    async def extract_from_pdf(self, pdf_file: BinaryIO) -> str:
        # Implement PDF extraction
        pass
```

2. **Register in factory** ([factory.py](factory.py)):
```python
from src.services.llm.cohere import CohereAdapter

_model_registry = {
    # ... existing models ...
    "cohere-command-r": (CohereAdapter, "command-r-plus", "cohere"),
}
```

3. **Add to type hints**:
```python
ProviderName = Literal[
    # ... existing ...
    "cohere-command-r",
]
```

4. **Update CLI choices** ([src/cli/__main__.py](../../cli/__main__.py)):
```python
choices=["claude-4.5-sonnet", ..., "cohere-command-r"]
```

5. **Add API key** to [src/lib/config.py](../../lib/config.py):
```python
COHERE_API_KEY: str = Field(..., description="Cohere API key")
```

### Handling Content Filter Errors

Content filters (e.g., Azure OpenAI) may block violent game content. Use retry logic:

```python
from src.services.llm.retry import retry_on_content_filter

response = await retry_on_content_filter(
    llm.generate,
    request,
    timeout_seconds=30
)
```

This automatically rephrases and retries on filter errors.

## PDF Extraction

Used for downloading team rule PDFs and converting to markdown.

### Usage
```bash
python -m src.cli download-team https://example.com/rules.pdf --model gemini-2.5-pro
```

### Extraction Flow
1. Download PDF from URL
2. Load PDF as binary
3. Call `extract_from_pdf(pdf_file)`
4. LLM reads PDF visually and extracts markdown
5. Save to `extracted-rules/`

## Error Handling

### Common Errors

**API Key Missing**:
```
KeyError: ANTHROPIC_API_KEY not found
```
→ Set environment variable or add to `.env`

**Rate Limit Exceeded**:
```
RateLimitError: Too many requests
```
→ Automatic retry with backoff (up to 3 attempts)

**Content Filter**:
```
ContentFilterError: Response blocked by content filter
```
→ Use `retry_on_content_filter()` to rephrase and retry

**Timeout**:
```
TimeoutError: LLM generation exceeded 30s
```
→ Increase `timeout_seconds` in GenerationConfig

**Invalid Model**:
```
ValueError: Unknown provider: invalid-model
```
→ Check model name against factory registry

### Error Logging

All errors logged with context:
```python
logger.error("llm_generation_failed", model=model, error=str(e))
```

## Performance & Cost

### Token Usage
- Tracked per request in `GenerationResponse.token_count`
- Estimated cost calculated in [src/lib/tokens.py](../../lib/tokens.py)
- Quality tests report total cost

### Optimization Tips
1. Cache responses (via RAG cache) - NOT YET IMPLEMENTED
2. Use mini/flash models for simple queries
3. Reduce `max_tokens` for concise answers
4. Batch PDF extractions to amortize latency

## Testing LLM Integration

### Unit Tests
Mock the LLM provider with structured JSON output:
```python
from unittest.mock import AsyncMock
import json

llm = AsyncMock(spec=LLMProvider)

# Mock structured JSON response
structured_json = json.dumps({
    "smalltalk": False,
    "short_answer": "Yes.",
    "persona_short_answer": "Obviously.",
    "quotes": [
        {
            "quote_title": "Core Rules: Movement",
            "quote_text": "Operatives can move 6 inches"
        }
    ],
    "explanation": "Movement is 6 inches per the core rules.",
    "persona_afterword": "Simple enough."
})

llm.generate.return_value = LLMResponse(
    response_id=uuid4(),
    answer_text=structured_json,  # JSON string, not markdown!
    confidence_score=0.88,
    token_count=125,
    latency_ms=1850,
    provider="claude",
    model_version="claude-3-sonnet",
    citations_included=True,
)
```

**Important**: All mocks must return JSON strings in `answer_text`, not markdown.

### Integration Tests
Test actual providers (requires API keys):
```bash
pytest tests/integration/test_llm_providers.py
```

### Quality Tests - costs money to run
End-to-end RAG + LLM quality:
```bash
python -m src.cli quality-test --test eliminator-concealed-counteract
```

## Dependencies

- `anthropic` - Anthropic Claude SDK
- `openai` - OpenAI GPT SDK (also used for Grok via custom base URL)
- `google-generativeai` - Google Gemini SDK
- `tiktoken` - Token counting for OpenAI models

## Related Documentation

- [src/services/CLAUDE.md](../CLAUDE.md) - Service architecture overview
- [src/services/rag/CLAUDE.md](../rag/CLAUDE.md) - RAG retrieval details
- [src/services/discord/CLAUDE.md](../discord/CLAUDE.md) - Discord bot integration
- [prompts/rule-helper-prompt.md](../../../prompts/rule-helper-prompt.md) - System prompt
- [tests/quality/CLAUDE.md](../../../tests/quality/CLAUDE.md) - Quality test documentation
