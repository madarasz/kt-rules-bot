# LLM Adapter Contract

**Version**: 1.0.0
**Last Updated**: 2025-10-02

## Purpose

Defines the provider-agnostic interface for LLM interactions. Ensures business logic remains independent of specific LLM providers (Constitution Principle II).

## Interface Definition

### `LLMProvider.generate(prompt: str, context: List[str], config: GenerationConfig) -> LLMResponse`

**Description**: Generates an answer to a user query using retrieved context

**Input**:
```python
@dataclass
class GenerationRequest:
    prompt: str  # User query (sanitized)
    context: List[str]  # Retrieved document chunks (up to 5)
    config: GenerationConfig

@dataclass
class GenerationConfig:
    max_tokens: int = 2048  # Maximum response length
    temperature: float = 0.1  # Lower = more deterministic
    system_prompt: str = "You are a Kill Team rules assistant..."
    include_citations: bool = True
    timeout_seconds: int = 25  # Must respond within 25s for <30s total latency
```

**Output**:
```python
@dataclass
class LLMResponse:
    response_id: UUID
    answer_text: str  # Generated answer
    confidence_score: float  # 0-1, provider-specific confidence metric
    token_count: int  # Total tokens (prompt + completion)
    latency_ms: int  # Generation time in milliseconds
    provider: str  # "claude", "gemini", "chatgpt"
    model_version: str  # e.g., "claude-3-sonnet-20240229"
    citations_included: bool  # True if answer references context chunks
```

**Contracts**:

1. **Provider Independence**:
   - Same `prompt` + `context` MUST produce semantically equivalent answers across providers
   - Differences in phrasing acceptable, but factual accuracy MUST be consistent

2. **Confidence Scoring**:
   - `confidence_score` MUST be normalized to 0-1 range
   - Implementation:
     - **Claude**: Use logprobs or "confidence" field if available, else default 0.8
     - **ChatGPT**: Use logprobs from API, average top token probabilities
     - **Gemini**: Use safety ratings as proxy, map to 0-1

3. **Citation Requirement**:
   - If `include_citations = True`, answer MUST reference specific context chunks
   - Citation format: `"According to [source]: [quote]"`
   - Set `citations_included = True` only if answer contains citations

4. **Timeout Enforcement**:
   - MUST return response or raise exception within `timeout_seconds`
   - Partial responses allowed if timeout approaching (with lower confidence)

5. **Token Tracking**:
   - `token_count` MUST include both prompt tokens and completion tokens
   - Used for cost monitoring (NFR budget enforcement)

6. **Error Handling**:
   - Network failures → Retry 2x with exponential backoff
   - Rate limit errors → Raise `RateLimitError`, allow caller to handle
   - Invalid API key → Raise `AuthenticationError`

**Error Conditions**:

| Error Type | Condition | Response |
|------------|-----------|----------|
| `RateLimitError` | Provider rate limit exceeded | Raise exception, log WARNING |
| `AuthenticationError` | Invalid API key | Raise exception, log ERROR |
| `TimeoutError` | Response time > timeout_seconds | Raise exception, log WARNING |
| `ContentFilterError` | Provider blocked content | Return empty response, confidence=0 |

---

## Provider Implementations

### Claude Adapter

**API**: Anthropic Claude API (claude-3-sonnet-20240229)
**Endpoint**: `https://api.anthropic.com/v1/messages`

**Implementation**:
```python
class ClaudeAdapter(LLMProvider):
    async def generate(self, request: GenerationRequest) -> LLMResponse:
        # Construct prompt with context
        full_prompt = self._build_prompt(request.prompt, request.context)

        # Call Anthropic API
        response = await anthropic.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=request.config.max_tokens,
            temperature=request.config.temperature,
            messages=[{"role": "user", "content": full_prompt}]
        )

        # Extract confidence (use default 0.8 if not available)
        confidence = 0.8  # Anthropic doesn't provide logprobs yet

        return LLMResponse(
            answer_text=response.content[0].text,
            confidence_score=confidence,
            token_count=response.usage.input_tokens + response.usage.output_tokens,
            provider="claude",
            model_version="claude-3-sonnet-20240229"
        )
```

**Confidence Mapping**: Default 0.8 (Anthropic doesn't expose logprobs)

---

### ChatGPT Adapter

**API**: OpenAI Chat Completions API (gpt-4-turbo)
**Endpoint**: `https://api.openai.com/v1/chat/completions`

**Implementation**:
```python
class ChatGPTAdapter(LLMProvider):
    async def generate(self, request: GenerationRequest) -> LLMResponse:
        full_prompt = self._build_prompt(request.prompt, request.context)

        response = await openai.chat.completions.create(
            model="gpt-4-turbo",
            max_tokens=request.config.max_tokens,
            temperature=request.config.temperature,
            messages=[{"role": "user", "content": full_prompt}],
            logprobs=True,  # Request logprobs for confidence
            top_logprobs=5
        )

        # Calculate confidence from logprobs
        confidence = self._calculate_confidence(response.choices[0].logprobs)

        return LLMResponse(
            answer_text=response.choices[0].message.content,
            confidence_score=confidence,
            token_count=response.usage.total_tokens,
            provider="chatgpt",
            model_version="gpt-4-turbo"
        )

    def _calculate_confidence(self, logprobs) -> float:
        # Average top token probabilities across response
        if not logprobs or not logprobs.content:
            return 0.7  # Default if logprobs unavailable
        probs = [exp(lp.logprob) for lp in logprobs.content]
        return sum(probs) / len(probs)
```

**Confidence Mapping**: Average of token-level logprobs (0-1)

---

### Gemini Adapter

**API**: Google Gemini API (gemini-1.5-pro)
**Endpoint**: `https://generativelanguage.googleapis.com/v1/models/gemini-1.5-pro:generateContent`

**Implementation**:
```python
class GeminiAdapter(LLMProvider):
    async def generate(self, request: GenerationRequest) -> LLMResponse:
        full_prompt = self._build_prompt(request.prompt, request.context)

        response = await genai.generate_content(
            model="gemini-1.5-pro",
            prompt=full_prompt,
            generation_config={
                "max_output_tokens": request.config.max_tokens,
                "temperature": request.config.temperature
            }
        )

        # Map safety ratings to confidence (higher safety = higher confidence)
        confidence = self._safety_to_confidence(response.safety_ratings)

        return LLMResponse(
            answer_text=response.text,
            confidence_score=confidence,
            token_count=response.usage_metadata.total_token_count,
            provider="gemini",
            model_version="gemini-1.5-pro"
        )

    def _safety_to_confidence(self, safety_ratings) -> float:
        # Map safety ratings to 0-1 confidence
        # HIGH_SAFE → 0.9, MEDIUM → 0.7, LOW → 0.5
        pass
```

**Confidence Mapping**: Safety ratings proxy (0.5-0.9 range)

---

## Test Cases

### Contract Test 1: Provider Consistency

**Given**: Same prompt + context across all providers
**When**: Generate responses from Claude, ChatGPT, Gemini
**Then**:
- All answers mention "Movement Phase" (factual consistency)
- All confidence scores ≥ 0.6
- Token counts within 20% of each other

### Contract Test 2: Confidence Thresholds

**Given**: High-quality context (relevance > 0.9)
**When**: Generate response
**Then**:
- `confidence_score ≥ 0.7` for all providers

**Given**: Low-quality context (relevance < 0.5)
**When**: Generate response
**Then**:
- `confidence_score ≤ 0.6` for all providers

### Contract Test 3: Citation Inclusion

**Given**: `include_citations = True`
**When**: Generate response
**Then**:
- `answer_text` contains at least one citation formatted as `"According to [source]..."`
- `citations_included = True`

### Contract Test 4: Timeout Enforcement

**Given**: Slow LLM API (simulated)
**When**: `generate()` with `timeout_seconds = 5`
**Then**:
- Raises `TimeoutError` within 5 seconds
- No partial response returned

### Contract Test 5: Token Tracking

**Given**: Any valid request
**When**: Generate response
**Then**:
- `token_count > 0`
- `token_count = prompt_tokens + completion_tokens`

### Contract Test 6: Rate Limit Handling

**Given**: Provider rate limit exceeded (simulated)
**When**: `generate()`
**Then**:
- Raises `RateLimitError`
- Error logged with provider and timestamp

---

## Configuration

**Provider Selection**:
```python
# config/llm.yaml
default_provider: "claude"  # or "chatgpt", "gemini"

providers:
  claude:
    api_key_env: "ANTHROPIC_API_KEY"
    model: "claude-3-sonnet-20240229"
    rate_limit: 50  # requests per minute

  chatgpt:
    api_key_env: "OPENAI_API_KEY"
    model: "gpt-4-turbo"
    rate_limit: 100

  gemini:
    api_key_env: "GOOGLE_API_KEY"
    model: "gemini-1.5-pro"
    rate_limit: 60
```

**System Prompt** (shared across providers):
```
You are a Kill Team 3rd Edition rules assistant. Answer user questions accurately using ONLY the provided context from official rulebooks. Always cite your sources. If the context doesn't contain relevant information, say so clearly.
```

---

## Observability

**Metrics to Track**:
- `llm_response_latency_ms` (histogram, labeled by provider)
- `llm_token_count` (counter, labeled by provider)
- `llm_confidence_score` (histogram, labeled by provider)
- `llm_errors_total` (counter, labeled by provider + error_type)

**Logs**:
- DEBUG: Full prompt and response (PII redacted)
- INFO: Token count, latency, confidence
- WARNING: Timeouts, rate limits
- ERROR: Authentication failures, API errors
