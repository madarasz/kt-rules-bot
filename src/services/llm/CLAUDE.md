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

## Provider Output Differences

All LLM providers return structured JSON conforming to the same schema, but they differ in **how** they generate and return that JSON.

### Structured Output Generation Methods

| Provider | API Method | Pydantic Usage | `structured_output` Field |
|----------|-----------|----------------|--------------------------|
| **Claude** | `beta.messages.parse()` | Native parse (Pydantic instance returned) | ✅ Populated |
| **ChatGPT** | `beta.chat.completions.parse()` | Native parse (Pydantic instance returned) | ✅ Populated |
| **Gemini** | JSON mode with schema | Post-response validation | ✅ Populated |
| **Grok** | OpenAI-style JSON schema | Post-response validation | ❌ Not populated |
| **DeepSeek** | Function calling | Post-response validation | ❌ Not populated |

### Native Parse Methods

**Claude and ChatGPT** use their providers' native Pydantic structured output methods:
- Pass Pydantic model directly to API via `output_format` or `response_format` parameter
- API returns fully validated Pydantic model instance
- No manual validation needed
- Both populate `structured_output` field with `parsed_output.model_dump()`

**Implementation:**
```python
# Claude: beta.messages.parse()
response = await client.beta.messages.parse(
    output_format=pydantic_model,  # Pydantic model class
    ...
)
parsed_output = response.parsed_output  # Pydantic instance

# ChatGPT: beta.chat.completions.parse()
response = await client.beta.chat.completions.parse(
    response_format=pydantic_model,  # Pydantic model class
    ...
)
parsed_output = choice.message.parsed  # Pydantic instance
```

### Post-Response Validation

**Gemini, Grok, and DeepSeek** receive raw JSON strings and validate them manually:
- Configure API to return JSON using schema, but receive raw string
- Manually call `pydantic_model.model_validate_json(json_string)`
- More flexible but requires explicit validation step

**Implementation:**
```python
# Gemini: JSON mode
response = await client.models.generate_content(
    response_mime_type="application/json",
    response_schema=pydantic_model,  # Schema configuration
    ...
)
answer_text = response.text  # Raw JSON string
pydantic_response = pydantic_model.model_validate_json(answer_text)

# Grok: OpenAI-compatible JSON schema
response = await client.post(
    response_format={
        "type": "json_schema",
        "json_schema": pydantic_model.model_json_schema()
    },
    ...
)
content = response["choices"][0]["message"]["content"]  # Raw JSON
parsed_output = pydantic_model.model_validate_json(content)

# DeepSeek: Function calling
response = await client.chat.completions.create(
    tools=[{
        "function": {
            "parameters": pydantic_model.model_json_schema()
        }
    }],
    ...
)
function_args = response.choices[0].message.tool_calls[0].function.arguments
parsed_output = pydantic_model.model_validate_json(function_args)
```

### structured_output Field Population

The `LLMResponse.structured_output` field is **optional** and only populated by some providers:

**✅ Populated (Claude, ChatGPT, Gemini):**
- Contains the parsed Pydantic model as a dictionary
- Allows consumers to access structured data without re-parsing JSON
- Source: `parsed_output.model_dump()` or post-processed dict

**❌ Not Populated (Grok, DeepSeek):**
- Field remains `None`
- Consumers must parse `answer_text` JSON string themselves
- Keeps response minimal

**Usage Example:**
```python
response = await llm.generate(request)

# Option 1: Use structured_output if available
if response.structured_output:
    short_answer = response.structured_output["short_answer"]
    quotes = response.structured_output["quotes"]

# Option 2: Always parse answer_text JSON
import json
parsed = json.loads(response.answer_text)
short_answer = parsed["short_answer"]
```

### Confidence Score Calculation

| Provider | Method | Value Range |
|----------|--------|-------------|
| **Claude** | Hardcoded | 0.8 (no logprobs with structured outputs) |
| **ChatGPT** | Hardcoded | 0.8 (no logprobs with structured outputs) |
| **Gemini** | Safety ratings | 0.5-0.9 (NEGLIGIBLE→0.9, LOW→0.8, MEDIUM→0.7, HIGH→0.5) |
| **Grok** | Hardcoded | 0.8 (no logprobs support yet) |
| **DeepSeek** | Hardcoded | 0.8 (0.85 for deepseek-reasoner) |

**Gemini is unique**: Derives confidence from content safety ratings rather than using a static value.

### Token Limits for Reasoning Models

Some models use internal reasoning tokens that don't appear in the final output. These providers multiply `max_tokens` by 3:

- **ChatGPT**: GPT-5, o-series (o3, o4-mini, etc.) - use `max_completion_tokens` instead of `max_tokens`
- **Gemini**: Gemini 2.5 Pro, Gemini 2.5 Flash (2.5+)
- **DeepSeek**: deepseek-reasoner

Standard models use `max_tokens` directly without multiplication.

### Provider Implementations

#### Claude Adapter ([claude.py](claude.py))
Anthropic Claude integration:
- Uses `anthropic` Python SDK
- **Structured output**: `beta.messages.parse()` with Pydantic (Structured Outputs beta API)
- **Pydantic usage**: Native parse - API returns Pydantic instance directly via `response.parsed_output`
- **Output fields**: Populates both `answer_text` (JSON string) and `structured_output` (dict) in LLMResponse
- Supports vision for PDF extraction
- Default confidence: 0.8 (no logprobs available with structured outputs)

#### ChatGPT Adapter ([chatgpt.py](chatgpt.py))
OpenAI ChatGPT integration:
- Uses `openai` Python SDK
- **Structured output**: `beta.chat.completions.parse()` with Pydantic
- **Pydantic usage**: Native parse - API returns Pydantic instance directly via `choice.message.parsed`
- **Output fields**: Populates both `answer_text` (JSON string) and `structured_output` (dict) in LLMResponse
- Supports GPT-4, GPT-5, o-series models
- GPT-5/o-series: Uses `max_completion_tokens` instead of `max_tokens` (includes reasoning tokens)
- Default confidence: 0.8 (logprobs not available with structured outputs)
- PDF extraction via vision API (not yet implemented)

#### Gemini Adapter ([gemini.py](gemini.py))
Google Gemini integration:
- Uses `google-genai` SDK (new API)
- **Structured output**: JSON mode with `response_mime_type: "application/json"` and `response_schema`
- **Pydantic usage**: Post-response validation - manually validates JSON string with `model_validate_json()`
- **Output fields**: Populates both `answer_text` (JSON string) and `structured_output` (dict) in LLMResponse
- **Special feature**: Sentence numbering for quote extraction (see Gemini Quote Extraction below)
- Uses different Pydantic schema (`GeminiAnswer` with sentence numbers) to avoid RECITATION errors
- Best for PDF extraction (native multimodal)
- Supports Gemini 2.5 Pro and Flash
- Gemini 2.5+ models: Multiply max_tokens by 3 (internal reasoning tokens)
- Confidence from safety ratings (0.5-0.9): NEGLIGIBLE→0.9, LOW→0.8, MEDIUM→0.7, HIGH→0.5
- Content filter detection via `finish_reason`

#### Grok Adapter ([grok.py](grok.py))
X/Grok integration:
- Uses `httpx` with OpenAI-compatible API
- **Structured output**: OpenAI-style JSON schema via `response_format`
- **Pydantic usage**: Post-response validation - manually validates JSON string with `model_validate_json()`
- **Output fields**: Only populates `answer_text` (JSON string), `structured_output` field is **NOT populated**
- Converts Pydantic model to JSON schema via `model_json_schema()`
- Supports Grok 3 and Grok 4 models
- Fast reasoning capabilities
- Default confidence: 0.8
- PDF extraction not yet supported

#### DeepSeek Adapter ([deepseek.py](deepseek.py))
DeepSeek integration:
- Uses OpenAI SDK with custom base URL (`https://api.deepseek.com`)
- **Structured output**: Function calling with `tools` parameter (OpenAI-compatible)
- **Pydantic usage**: Post-response validation - manually validates JSON string with `model_validate_json()`
- **Output fields**: Only populates `answer_text` (JSON string), `structured_output` field is **NOT populated**
- Converts Pydantic model to JSON schema for function parameters
- Supports deepseek-chat (standard) and deepseek-reasoner (with chain-of-thought)
- deepseek-reasoner: Uses Chain of Thought (CoT) reasoning before final answer, exposes `reasoning_content` field (logged but not returned)
- deepseek-reasoner: Multiplies max_tokens by 3 (internal reasoning tokens), uses confidence 0.85
- Context window up to 128K tokens
- Default confidence: 0.8 (0.85 for reasoner)
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
    structured_output: Optional[Dict[str, Any]]  # Parsed Pydantic model as dict (optional)
```

**Note on `structured_output` field:**
- **Populated by**: Claude, ChatGPT, Gemini - contains parsed Pydantic model as dictionary
- **Not populated by**: Grok, DeepSeek - field is `None`
- **Usage**: Allows consumers to access structured data without re-parsing `answer_text` JSON
- **Format**: Dictionary matching the Pydantic schema (Answer, GeminiAnswer, HopEvaluation, or CustomJudgeResponse)

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

**Provider-Specific Schema Notes:**

- **Standard providers (Claude, ChatGPT, Grok, DeepSeek)**: Use `Answer` model with `Quote(quote_title, quote_text)`
- **Gemini**: Uses `GeminiAnswer` model with `GeminiQuote(quote_title, sentence_numbers, quote_text="")` - see [Gemini Quote Extraction](#gemini-quote-extraction) for details

**Output Field Population:**

All providers return this JSON in the `LLMResponse.answer_text` field as a JSON string. Additionally:

- **Claude, ChatGPT, Gemini**: Also populate `LLMResponse.structured_output` with the parsed dict
- **Grok, DeepSeek**: Leave `structured_output` as `None`

This JSON is parsed by [StructuredLLMResponse](../../../src/models/structured_response.py) and converted to Discord embeds.

## Gemini Quote Extraction

Gemini has a unique approach to quote extraction due to its **RECITATION filter**, which blocks verbatim text from the training data.

### The Problem

When asked to return exact quotes from rules, Gemini's content filter may block the response as "RECITATION" (verbatim reproduction of source material). This prevents normal quote extraction.

### The Solution: Sentence Numbering

Instead of asking Gemini to return quote text directly, we:

1. **Pre-process RAG chunks**: Number each sentence in the context
   ```
   Original: "The operative can move. It can also shoot."
   Numbered: "[S1] The operative can move. [S2] It can also shoot."
   ```

2. **LLM returns sentence numbers**: Gemini responds with which sentences to quote, not the text itself
   ```json
   {
     "quotes": [
       {
         "quote_title": "Movement Rules",
         "sentence_numbers": [1, 2],
         "quote_text": ""  // Empty - filled by post-processor
       }
     ]
   }
   ```

3. **Post-process response**: Extract actual quote text using sentence numbers
   ```python
   # Map sentence numbers back to actual text
   sentence_1 = "The operative can move."
   sentence_2 = "It can also shoot."
   quote_text = "The operative can move. It can also shoot."
   ```

### Implementation Details

**Pydantic Schema Difference:**
- **Standard providers**: Use `Answer` model with `Quote(quote_title, quote_text)`
- **Gemini**: Uses `GeminiAnswer` model with `GeminiQuote(quote_title, sentence_numbers, quote_text="")`

**Pre-processing** (`number_sentences_in_chunk()`):
- Splits chunk text into sentences
- Adds `[S1]`, `[S2]`, etc. markers
- Stores mapping: `chunk_id → list of original sentences`

**Post-processing** (`post_process_gemini_response()`):
- Receives response with sentence numbers
- Looks up original sentences using stored mapping
- Reconstructs verbatim quotes
- Updates `quote_text` field in response dict

**Why this works:**
- Gemini doesn't see itself as "reciting" - just returning numbers
- We reconstruct exact quotes on our side
- No content filter triggered

**Trade-offs:**
- More complex implementation
- Requires sentence parsing/numbering
- Extra pre/post-processing overhead
- Only needed for Gemini

### Code References

- Pre-processing: `src/services/llm/gemini.py:84-112` (`number_sentences_in_chunk()`)
- Post-processing: `src/services/llm/gemini.py:244-266` (`post_process_gemini_response()`)
- Pydantic schemas: `src/models/structured_response.py` (GeminiAnswer, GeminiQuote)

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
PROMPT_TEMPLATE_PATH = "prompts/base-prompt-template.md"

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
