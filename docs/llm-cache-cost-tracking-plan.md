# LLM Cache Cost Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add prompt-caching token tracking to LLM cost calculations and surface cache savings everywhere costs are displayed.

**Architecture:** Extend `LLMResponse` with cache token fields; add `LLMCostBreakdown` dataclass to `tokens.py` and a new `calculate_llm_cost()` that handles provider-specific cache accounting (Anthropic: cache_read + cache_write are separate from prompt_tokens; OpenAI/Grok: cached_tokens are a subset of prompt_tokens). Update Claude, ChatGPT, and Grok providers to extract cache fields from API responses. Propagate breakdown through query_cost_calculator → CLI display → quality tests.

**Tech Stack:** Python 3.11+, `anthropic` SDK, `openai` SDK, `httpx` (Grok), `dataclasses`, `pytest`

---

## File Map

| File | Change |
|------|--------|
| `src/lib/tokens.py` | Add `LLMCostBreakdown` dataclass; add `calculate_llm_cost()`; extend pricing table with cache rates and `cache_mode`; keep `estimate_cost()` as thin wrapper |
| `src/services/llm/base.py` | Add `cache_read_tokens: int = 0` and `cache_creation_tokens: int = 0` to `LLMResponse` |
| `src/services/llm/claude.py` | Extract `cache_read_input_tokens`, `cache_creation_input_tokens` from `response.usage` |
| `src/services/llm/chatgpt.py` | Extract `prompt_tokens_details.cached_tokens` from `response.usage` |
| `src/services/llm/grok.py` | Extract `usage["prompt_tokens_details"]["cached_tokens"]` from raw dict |
| `src/services/discord/query_cost_calculator.py` | Use `calculate_llm_cost()`, add `cache_savings` to returned dict |
| `src/lib/statistics.py` | Add cache savings line to cost formatter |
| `src/cli/test_query.py` | Pass `cache_savings` through to formatter |
| `tests/quality/reporting/report_models.py` | Add `cache_savings_usd: float = 0.0` to `IndividualTestResult` |
| `tests/quality/test_runner.py` | Capture `cache_savings` from `LLMCostBreakdown`, store in result |
| `tests/quality/reporting/report_generator.py` | Display cache savings in report |
| `tests/unit/test_tokens.py` | New tests for `LLMCostBreakdown` and `calculate_llm_cost()` |
| `tests/unit/test_llm_providers.py` (or new) | Tests for cache token extraction per provider |

---

## Cache Accounting by Provider

### Anthropic (Claude)
- `response.usage.input_tokens` = regular (uncached) prompt tokens — **does NOT include cache tokens**
- `response.usage.cache_read_input_tokens` = tokens served from cache (10% of prompt price)
- `response.usage.cache_creation_input_tokens` = tokens written to cache (125% of prompt price)
- `cache_mode = "anthropic"` in pricing table
- Net savings = `(cache_read_tokens × prompt_price × 0.9) - (cache_creation_tokens × prompt_price × 0.25)` (per 1K)

### OpenAI (ChatGPT)
- `response.usage.prompt_tokens` = total prompt tokens **including** cached
- `response.usage.prompt_tokens_details.cached_tokens` = how many were cached (50% price)
- `cache_mode = "openai"` in pricing table
- Net savings = `cached_tokens × prompt_price × 0.5` (per 1K)

### Grok (X.AI)
- Same OpenAI-compatible format via raw dict: `usage["prompt_tokens_details"]["cached_tokens"]`
- `cache_mode = "openai"` in pricing table (50% cache discount)
- Note: not all Grok models support caching — `cached_tokens` will be 0 when not applicable

---

## Task 1: `LLMCostBreakdown` + `calculate_llm_cost()` in `tokens.py`

**Files:**
- Modify: `src/lib/tokens.py`
- Test: `tests/unit/test_tokens.py`

- [ ] **Step 1.1: Add `LLMCostBreakdown` dataclass**

In `src/lib/tokens.py`, after the imports, add:

```python
from dataclasses import dataclass

@dataclass
class LLMCostBreakdown:
    """Cost breakdown for a single LLM call, including cache savings."""
    # Token counts
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    # Cost components (USD)
    prompt_cost: float         # Non-cached prompt tokens
    completion_cost: float
    cache_read_cost: float
    cache_creation_cost: float
    total_cost: float          # Actual USD paid
    cache_savings: float       # USD saved vs. no caching (can be negative if cache write > read)

    @property
    def has_cache_activity(self) -> bool:
        return self.cache_read_tokens > 0 or self.cache_creation_tokens > 0
```

- [ ] **Step 1.2: Extend pricing table with cache fields**

In `estimate_cost()` (line 75), replace the `pricing` dict entries for Claude, OpenAI, and Grok models to add `cache_read`, `cache_write`, and `cache_mode`. Keep all other models unchanged (they get `cache_mode: "none"` implicitly).

Replace the pricing dict definition with one that includes these three extra keys for affected models:

```python
# Pricing per 1K tokens (as of 2025 October)
# cache_mode: "anthropic" = separate cache_read/write tokens; "openai" = cached subset of prompt; "none" = no caching
pricing: dict[str, dict] = {
    # OpenAI - cached_tokens = subset of prompt_tokens, 50% discount
    "gpt-5.5":            {"prompt": 0.00500, "completion": 0.030,  "cache_read": 0.00250, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.4":            {"prompt": 0.00250, "completion": 0.015,  "cache_read": 0.00125, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.4-mini":       {"prompt": 0.00075, "completion": 0.0045, "cache_read": 0.000375,"cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.4-nano":       {"prompt": 0.00020, "completion": 0.00125,"cache_read": 0.00010, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.3-chat-latest":{"prompt": 0.00175, "completion": 0.014,  "cache_read": 0.000875,"cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.2":            {"prompt": 0.00175, "completion": 0.014,  "cache_read": 0.000875,"cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.2-chat-latest":{"prompt": 0.00175, "completion": 0.014,  "cache_read": 0.000875,"cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.1":            {"prompt": 0.00125, "completion": 0.01,   "cache_read": 0.000625,"cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.1-chat-latest":{"prompt": 0.00125, "completion": 0.01,   "cache_read": 0.000625,"cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5":              {"prompt": 0.00125, "completion": 0.01,   "cache_read": 0.000625,"cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5-mini":         {"prompt": 0.00025, "completion": 0.002,  "cache_read": 0.000125,"cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5-nano":         {"prompt": 0.00005, "completion": 0.0004, "cache_read": 0.000025,"cache_write": 0.0, "cache_mode": "openai"},
    "gpt-4.1":            {"prompt": 0.002,   "completion": 0.008,  "cache_read": 0.001,   "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-4.1-mini":       {"prompt": 0.0004,  "completion": 0.0016, "cache_read": 0.0002,  "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-4.1-nano":       {"prompt": 0.0001,  "completion": 0.0004, "cache_read": 0.00005, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-4o":             {"prompt": 0.0025,  "completion": 0.01,   "cache_read": 0.00125, "cache_write": 0.0, "cache_mode": "openai"},
    # Claude - cache_read/write are SEPARATE from prompt_tokens
    "claude-sonnet-4-6":        {"prompt": 0.003,  "completion": 0.006,  "cache_read": 0.0003,   "cache_write": 0.00375, "cache_mode": "anthropic"},
    "claude-sonnet-4-5-20250929":{"prompt": 0.003, "completion": 0.006,  "cache_read": 0.0003,   "cache_write": 0.00375, "cache_mode": "anthropic"},
    "claude-opus-4-6":          {"prompt": 0.005,  "completion": 0.025,  "cache_read": 0.0005,   "cache_write": 0.00625, "cache_mode": "anthropic"},
    "claude-opus-4-5-20251101": {"prompt": 0.005,  "completion": 0.025,  "cache_read": 0.0005,   "cache_write": 0.00625, "cache_mode": "anthropic"},
    "claude-opus-4-1-20250805": {"prompt": 0.015,  "completion": 0.075,  "cache_read": 0.0015,   "cache_write": 0.01875, "cache_mode": "anthropic"},
    "claude-haiku-4-5-20251001":{"prompt": 0.001,  "completion": 0.005,  "cache_read": 0.0001,   "cache_write": 0.00125, "cache_mode": "anthropic"},
    "claude-4.6-sonnet":        {"prompt": 0.003,  "completion": 0.006,  "cache_read": 0.0003,   "cache_write": 0.00375, "cache_mode": "anthropic"},
    "claude-4.5-sonnet":        {"prompt": 0.003,  "completion": 0.006,  "cache_read": 0.0003,   "cache_write": 0.00375, "cache_mode": "anthropic"},
    "claude-4.6-opus":          {"prompt": 0.005,  "completion": 0.025,  "cache_read": 0.0005,   "cache_write": 0.00625, "cache_mode": "anthropic"},
    "claude-4.5-opus":          {"prompt": 0.005,  "completion": 0.025,  "cache_read": 0.0005,   "cache_write": 0.00625, "cache_mode": "anthropic"},
    "claude-4.1-opus":          {"prompt": 0.015,  "completion": 0.075,  "cache_read": 0.0015,   "cache_write": 0.01875, "cache_mode": "anthropic"},
    "claude-4.5-haiku":         {"prompt": 0.001,  "completion": 0.005,  "cache_read": 0.0001,   "cache_write": 0.00125, "cache_mode": "anthropic"},
    # Grok - OpenAI-compatible cache format, 50% discount
    "grok-4-1-fast-reasoning":    {"prompt": 0.0002,  "completion": 0.0005,  "cache_read": 0.0001,   "cache_write": 0.0, "cache_mode": "openai"},
    "grok-4-1-fast-non-reasoning":{"prompt": 0.0002,  "completion": 0.0005,  "cache_read": 0.0001,   "cache_write": 0.0, "cache_mode": "openai"},
    "grok-4.3":                   {"prompt": 0.00125, "completion": 0.00250, "cache_read": 0.000625, "cache_write": 0.0, "cache_mode": "openai"},
    "grok-4.20-0309-reasoning":   {"prompt": 0.00125, "completion": 0.00250, "cache_read": 0.000625, "cache_write": 0.0, "cache_mode": "openai"},
    "grok-build-0.1":             {"prompt": 0.00100, "completion": 0.00200, "cache_read": 0.0005,   "cache_write": 0.0, "cache_mode": "openai"},
    # Gemini - no explicit caching support in current integration
    "gemini-3.1-pro-preview":  {"prompt": 0.002,   "completion": 0.012,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "gemini-3-pro-preview":    {"prompt": 0.002,   "completion": 0.012,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "gemini-2.5-pro":          {"prompt": 0.00125, "completion": 0.01,   "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "gemini-3-flash-preview":  {"prompt": 0.0005,  "completion": 0.003,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "gemini-3.5-flash":        {"prompt": 0.0015,  "completion": 0.009,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "gemini-2.5-flash":        {"prompt": 0.0003,  "completion": 0.0025, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    # Remaining providers - no caching
    "deepseek-chat":    {"prompt": 0.00028, "completion": 0.00042, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "deepseek-reasoner":{"prompt": 0.00028, "completion": 0.00042, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "kimi-k2.5":                {"prompt": 0.0001,  "completion": 0.003,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "kimi-k2-0905-preview":     {"prompt": 0.00015, "completion": 0.0025, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "kimi-k2-turbo-preview":    {"prompt": 0.00015, "completion": 0.008,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-large":        {"prompt": 0.0005, "completion": 0.0015, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-medium":       {"prompt": 0.0004, "completion": 0.002,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-small":        {"prompt": 0.0001, "completion": 0.0003, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-large-latest": {"prompt": 0.0005, "completion": 0.0015, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-medium-2505":  {"prompt": 0.0004, "completion": 0.002,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-small-latest": {"prompt": 0.0001, "completion": 0.0003, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "magistral-medium-latest":{"prompt": 0.002,"completion": 0.005,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "qwen3.5-plus":             {"prompt": 0.00040, "completion": 0.00240, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "qwen3-max-2026-01-23":     {"prompt": 0.00120, "completion": 0.00600, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "qwen3-coder-plus":         {"prompt": 0.00100, "completion": 0.00500, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "qwen3-coder-next":         {"prompt": 0.00030, "completion": 0.00150, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "glm-5":                    {"prompt": 0.00050, "completion": 0.00250, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "glm-4.7":                  {"prompt": 0.00050, "completion": 0.00250, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "MiniMax-M2.5":             {"prompt": 0.00020, "completion": 0.00080, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
}
```

- [ ] **Step 1.3: Add `calculate_llm_cost()` function**

Add after the pricing dict (below `estimate_cost`):

```python
def calculate_llm_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> LLMCostBreakdown:
    """Calculate LLM cost with cache savings breakdown.

    For Anthropic models:
        prompt_tokens = regular (uncached) tokens only.
        cache_read_tokens and cache_creation_tokens are separate.

    For OpenAI/Grok models:
        prompt_tokens = total (includes cached_tokens).
        cache_read_tokens = subset of prompt_tokens that were cached.
    """
    if model not in pricing:
        pricing[model] = {"prompt": 0.002, "completion": 0.002, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"}

    p = pricing[model]
    cache_mode = p.get("cache_mode", "none")

    completion_cost = (completion_tokens / 1000) * p["completion"]

    if cache_mode == "anthropic":
        # prompt_tokens does NOT include cache tokens
        prompt_cost = (prompt_tokens / 1000) * p["prompt"]
        cache_read_cost = (cache_read_tokens / 1000) * p["cache_read"]
        cache_creation_cost = (cache_creation_tokens / 1000) * p["cache_write"]
        total_cost = prompt_cost + cache_read_cost + cache_creation_cost + completion_cost
        # Savings: reads cost 10% vs 100%; writes cost 125% vs 100%
        read_savings = (cache_read_tokens / 1000) * p["prompt"] * 0.9
        write_extra = (cache_creation_tokens / 1000) * p["prompt"] * 0.25
        cache_savings = read_savings - write_extra

    elif cache_mode == "openai":
        # prompt_tokens includes cached; non-cached portion costs full price
        non_cached = prompt_tokens - cache_read_tokens
        prompt_cost = (non_cached / 1000) * p["prompt"]
        cache_read_cost = (cache_read_tokens / 1000) * p["cache_read"]
        cache_creation_cost = 0.0
        total_cost = prompt_cost + cache_read_cost + completion_cost
        cache_savings = (cache_read_tokens / 1000) * p["prompt"] * 0.5

    else:  # "none"
        prompt_cost = (prompt_tokens / 1000) * p["prompt"]
        cache_read_cost = 0.0
        cache_creation_cost = 0.0
        total_cost = prompt_cost + completion_cost
        cache_savings = 0.0

    return LLMCostBreakdown(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        prompt_cost=prompt_cost,
        completion_cost=completion_cost,
        cache_read_cost=cache_read_cost,
        cache_creation_cost=cache_creation_cost,
        total_cost=total_cost,
        cache_savings=cache_savings,
    )
```

- [ ] **Step 1.4: Update `estimate_cost()` to use `calculate_llm_cost()`**

Replace the body of `estimate_cost()` (keep the signature for backward compat):

```python
def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Estimate cost for LLM API call. Returns total USD."""
    return calculate_llm_cost(prompt_tokens, completion_tokens, model).total_cost
```

- [ ] **Step 1.5: Write tests for `calculate_llm_cost()`**

In `tests/unit/test_tokens.py` (create if missing, append if exists):

```python
from src.lib.tokens import calculate_llm_cost, LLMCostBreakdown, estimate_cost


class TestCalculateLlmCost:
    def test_no_caching_returns_simple_cost(self):
        result = calculate_llm_cost(1000, 200, "gpt-4.1")
        assert isinstance(result, LLMCostBreakdown)
        assert result.cache_savings == 0.0
        assert result.cache_read_tokens == 0
        assert result.total_cost == pytest.approx(
            (1000 / 1000) * 0.002 + (200 / 1000) * 0.008
        )

    def test_openai_cache_savings(self):
        # 1000 prompt tokens total, 500 were cached
        result = calculate_llm_cost(
            prompt_tokens=1000,
            completion_tokens=200,
            model="gpt-4.1",
            cache_read_tokens=500,
        )
        # non-cached: 500 @ $0.002/1K = $0.001
        # cached: 500 @ $0.001/1K = $0.0005
        # completion: 200 @ $0.008/1K = $0.0016
        assert result.prompt_cost == pytest.approx(0.001)
        assert result.cache_read_cost == pytest.approx(0.0005)
        assert result.total_cost == pytest.approx(0.001 + 0.0005 + 0.0016)
        assert result.cache_savings == pytest.approx(0.0005)  # saved 50% on 500 cached

    def test_anthropic_cache_savings_reads(self):
        # Claude: prompt_tokens=500 regular, cache_read=400, cache_creation=0
        result = calculate_llm_cost(
            prompt_tokens=500,
            completion_tokens=100,
            model="claude-4.5-sonnet",
            cache_read_tokens=400,
        )
        # prompt: 500 @ $0.003/1K = $0.0015
        # cache_read: 400 @ $0.0003/1K = $0.00012
        # completion: 100 @ $0.006/1K = $0.0006
        assert result.prompt_cost == pytest.approx(0.0015)
        assert result.cache_read_cost == pytest.approx(0.00012)
        assert result.cache_creation_cost == 0.0
        assert result.total_cost == pytest.approx(0.0015 + 0.00012 + 0.0006)
        # savings: 400 tokens * $0.003/1K * 0.9 = $0.00108
        assert result.cache_savings == pytest.approx(0.00108)

    def test_anthropic_cache_creation_reduces_savings(self):
        result = calculate_llm_cost(
            prompt_tokens=500,
            completion_tokens=100,
            model="claude-4.5-sonnet",
            cache_read_tokens=0,
            cache_creation_tokens=400,
        )
        # cache_creation: 400 @ $0.00375/1K = $0.0015
        # savings should be negative: paid 25% extra
        assert result.cache_creation_cost == pytest.approx(0.0015)
        assert result.cache_savings == pytest.approx(-0.0003)  # -400/1K * 0.003 * 0.25

    def test_unknown_model_uses_fallback(self):
        result = calculate_llm_cost(1000, 200, "new-unknown-model")
        assert result.total_cost > 0
        assert result.cache_savings == 0.0

    def test_estimate_cost_backward_compat(self):
        # estimate_cost must still return a float
        result = estimate_cost(1000, 200, "gpt-4.1")
        assert isinstance(result, float)
        assert result == pytest.approx(calculate_llm_cost(1000, 200, "gpt-4.1").total_cost)

    def test_has_cache_activity_flag(self):
        no_cache = calculate_llm_cost(1000, 200, "gpt-4.1")
        with_cache = calculate_llm_cost(1000, 200, "gpt-4.1", cache_read_tokens=300)
        assert not no_cache.has_cache_activity
        assert with_cache.has_cache_activity
```

- [ ] **Step 1.6: Run tests**

```bash
source venv/bin/activate && pytest tests/unit/test_tokens.py -v
```

Expected: all new tests pass.

- [ ] **Step 1.7: Commit**

```bash
git add src/lib/tokens.py tests/unit/test_tokens.py
git commit -m "feat: add LLMCostBreakdown and calculate_llm_cost() with cache savings"
```

---

## Task 2: Add Cache Fields to `LLMResponse` + Update Providers

**Files:**
- Modify: `src/services/llm/base.py` (LLMResponse)
- Modify: `src/services/llm/claude.py`
- Modify: `src/services/llm/chatgpt.py`
- Modify: `src/services/llm/grok.py`

- [ ] **Step 2.1: Add fields to `LLMResponse`**

In `src/services/llm/base.py`, in the `LLMResponse` dataclass (currently ends at line ~360), add two new optional fields after `completion_tokens`:

```python
@dataclass
class LLMResponse:
    response_id: UUID
    answer_text: str
    confidence_score: float
    token_count: int
    latency_ms: int
    provider: str
    model_version: str
    citations_included: bool
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0       # Tokens served from cache
    cache_creation_tokens: int = 0   # Tokens written to cache (Anthropic only)
    structured_output: dict | None = None
```

- [ ] **Step 2.2: Update Claude provider**

In `src/services/llm/claude.py`, around lines 178-181 where token count is extracted, extend to:

```python
# Token count
prompt_tokens = response.usage.input_tokens
completion_tokens = response.usage.output_tokens
token_count = prompt_tokens + completion_tokens
cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0
cache_creation_tokens = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
```

Then in the `LLMResponse(...)` constructor call (a few lines below), add the two new fields:
```python
cache_read_tokens=cache_read_tokens,
cache_creation_tokens=cache_creation_tokens,
```

There is a second token extraction block around lines 316-318 (extract_from_pdf path) — apply the same change there too. The `ExtractionResponse` model does NOT get these fields (out of scope).

- [ ] **Step 2.3: Update ChatGPT provider**

In `src/services/llm/chatgpt.py`, around lines 158-161:

```python
# Token count
prompt_tokens = response.usage.prompt_tokens
completion_tokens = response.usage.completion_tokens
token_count = response.usage.total_tokens
prompt_details = getattr(response.usage, "prompt_tokens_details", None)
cache_read_tokens = 0
if prompt_details is not None:
    cache_read_tokens = getattr(prompt_details, "cached_tokens", 0) or 0
```

Add `cache_read_tokens=cache_read_tokens, cache_creation_tokens=0,` to the `LLMResponse(...)` constructor.

- [ ] **Step 2.4: Update Grok provider**

In `src/services/llm/grok.py`, around lines 174-178:

```python
# Token count
usage = response_data.get("usage", {})
prompt_tokens = usage.get("prompt_tokens", 0)
completion_tokens = usage.get("completion_tokens", 0)
token_count = usage.get("total_tokens", 0)
prompt_details = usage.get("prompt_tokens_details", {})
cache_read_tokens = prompt_details.get("cached_tokens", 0) if prompt_details else 0
```

Add `cache_read_tokens=cache_read_tokens, cache_creation_tokens=0,` to the `LLMResponse(...)` constructor.

There is also a second token block in Grok's extract_from_pdf path (around line 331) — apply the same treatment.

- [ ] **Step 2.5: Write provider cache field tests**

In `tests/unit/test_llm_providers.py` (create or append):

```python
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
import pytest


class TestClaudeCacheTokenExtraction:
    @pytest.mark.asyncio
    async def test_extracts_cache_read_tokens(self):
        """Cache read tokens from Anthropic response are captured in LLMResponse."""
        from src.services.llm.claude import ClaudeAdapter

        mock_usage = MagicMock()
        mock_usage.input_tokens = 500
        mock_usage.output_tokens = 100
        mock_usage.cache_read_input_tokens = 300
        mock_usage.cache_creation_input_tokens = 0

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.parsed_output = MagicMock()
        mock_response.parsed_output.model_dump_json.return_value = '{"smalltalk": false, "short_answer": "Yes."}'
        mock_response.parsed_output.model_dump.return_value = {"smalltalk": False, "short_answer": "Yes."}

        with patch("src.services.llm.claude.anthropic.AsyncAnthropic"):
            adapter = ClaudeAdapter.__new__(ClaudeAdapter)
            # Verify the extraction logic directly
            cache_read = getattr(mock_usage, "cache_read_input_tokens", 0) or 0
            cache_creation = getattr(mock_usage, "cache_creation_input_tokens", 0) or 0
            assert cache_read == 300
            assert cache_creation == 0

    @pytest.mark.asyncio
    async def test_extracts_cache_creation_tokens(self):
        mock_usage = MagicMock()
        mock_usage.input_tokens = 500
        mock_usage.output_tokens = 100
        mock_usage.cache_read_input_tokens = 0
        mock_usage.cache_creation_input_tokens = 400

        cache_read = getattr(mock_usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(mock_usage, "cache_creation_input_tokens", 0) or 0
        assert cache_read == 0
        assert cache_creation == 400

    def test_missing_cache_fields_default_to_zero(self):
        mock_usage = MagicMock(spec=["input_tokens", "output_tokens"])
        mock_usage.input_tokens = 500
        mock_usage.output_tokens = 100

        cache_read = getattr(mock_usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(mock_usage, "cache_creation_input_tokens", 0) or 0
        assert cache_read == 0
        assert cache_creation == 0


class TestOpenAICacheTokenExtraction:
    def test_extracts_cached_tokens_from_prompt_details(self):
        mock_details = MagicMock()
        mock_details.cached_tokens = 400

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 1000
        mock_usage.completion_tokens = 200
        mock_usage.prompt_tokens_details = mock_details

        prompt_details = getattr(mock_usage, "prompt_tokens_details", None)
        cache_read = getattr(prompt_details, "cached_tokens", 0) or 0
        assert cache_read == 400

    def test_no_cache_details_defaults_to_zero(self):
        mock_usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "total_tokens"])
        mock_usage.prompt_tokens = 1000
        mock_usage.completion_tokens = 200

        prompt_details = getattr(mock_usage, "prompt_tokens_details", None)
        cache_read = 0
        if prompt_details is not None:
            cache_read = getattr(prompt_details, "cached_tokens", 0) or 0
        assert cache_read == 0


class TestGrokCacheTokenExtraction:
    def test_extracts_cached_tokens_from_usage_dict(self):
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "total_tokens": 1200,
            "prompt_tokens_details": {"cached_tokens": 500, "text_tokens": 500},
        }
        prompt_details = usage.get("prompt_tokens_details", {})
        cache_read = prompt_details.get("cached_tokens", 0) if prompt_details else 0
        assert cache_read == 500

    def test_missing_prompt_details_defaults_to_zero(self):
        usage = {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200}
        prompt_details = usage.get("prompt_tokens_details", {})
        cache_read = prompt_details.get("cached_tokens", 0) if prompt_details else 0
        assert cache_read == 0
```

- [ ] **Step 2.6: Run tests**

```bash
source venv/bin/activate && pytest tests/unit/test_llm_providers.py -v
```

Expected: all pass.

- [ ] **Step 2.7: Commit**

```bash
git add src/services/llm/base.py src/services/llm/claude.py src/services/llm/chatgpt.py src/services/llm/grok.py tests/unit/test_llm_providers.py
git commit -m "feat: extract cache tokens from Claude, ChatGPT, Grok API responses"
```

---

## Task 3: Update `query_cost_calculator.py` to Return Cache Savings

**Files:**
- Modify: `src/services/discord/query_cost_calculator.py`

- [ ] **Step 3.1: Read current file**

Read `src/services/discord/query_cost_calculator.py` fully before editing.

- [ ] **Step 3.2: Replace `estimate_cost` call with `calculate_llm_cost`**

Change the import and the main LLM cost calculation:

```python
# Change import from:
from src.lib.tokens import estimate_cost, estimate_embedding_cost
# To:
from src.lib.tokens import calculate_llm_cost, estimate_embedding_cost
```

Find the `main_llm_cost = estimate_cost(...)` call and replace with:

```python
llm_breakdown = calculate_llm_cost(
    prompt_tokens=llm_response.prompt_tokens,
    completion_tokens=llm_response.completion_tokens,
    model=llm_response.model_version,
    cache_read_tokens=llm_response.cache_read_tokens,
    cache_creation_tokens=llm_response.cache_creation_tokens,
)
main_llm_cost = llm_breakdown.total_cost
cache_savings = llm_breakdown.cache_savings
```

In the returned cost dict, add `cache_savings`:

```python
return {
    "initial_embedding_cost": initial_embedding_cost,
    "hop_embedding_cost": hop_embedding_cost,
    "hop_evaluation_cost": hop_evaluation_cost,
    "main_llm_cost": main_llm_cost,
    "cache_savings": cache_savings,
    "total_cost": total_cost,
}
```

- [ ] **Step 3.3: Commit**

```bash
git add src/services/discord/query_cost_calculator.py
git commit -m "feat: include cache savings in query cost breakdown"
```

---

## Task 4: Update CLI Display to Show Cache Savings

**Files:**
- Modify: `src/lib/statistics.py`
- Modify: `src/cli/test_query.py`

- [ ] **Step 4.1: Read both files fully**

Read `src/lib/statistics.py` and `src/cli/test_query.py` before editing.

- [ ] **Step 4.2: Add `cache_savings` to `CostBreakdown` in `test_query.py`**

Find the `CostBreakdown` dataclass (around lines 57-83). Add:

```python
cache_savings: float = 0.0
cache_read_tokens: int = 0
cache_creation_tokens: int = 0
```

In `_perform_llm_generation()` (around line 251), replace `estimate_cost` with `calculate_llm_cost`:

```python
from src.lib.tokens import calculate_llm_cost
# ...
breakdown = calculate_llm_cost(
    prompt_tokens=llm_response.prompt_tokens,
    completion_tokens=llm_response.completion_tokens,
    model=llm_response.model_version,
    cache_read_tokens=llm_response.cache_read_tokens,
    cache_creation_tokens=llm_response.cache_creation_tokens,
)
llm_cost = breakdown.total_cost
cache_savings = breakdown.cache_savings
```

Pass `cache_savings`, `cache_read_tokens`, `cache_creation_tokens` through to the `CostBreakdown` being returned.

- [ ] **Step 4.3: Add cache savings display to `statistics.py`**

Read `CostFormatter.format()` and `format_statistics_summary()`. After the existing LLM cost line (which shows prompt/completion tokens), add a conditional cache savings line.

In `CostFormatter.format()`, after the LLM generation cost line, add:

```python
if cache_savings and cache_savings != 0.0:
    savings_sign = "+" if cache_savings > 0 else ""
    lines.append(
        f"    Cache savings:     ${cache_savings:.6f}  "
        f"({savings_sign}{cache_savings:.6f} vs. no caching)"
    )
```

In `format_statistics_summary()`, accept `cache_savings: float = 0.0` as a keyword arg and pass it through to the formatter.

- [ ] **Step 4.4: Run manually to verify display**

```bash
source venv/bin/activate && python -m src.cli query "Can I use overwatch against a charge?" --rag-only
```

Expected: cost breakdown appears with cache savings line (will show $0.000000 for RAG-only, normal for LLM queries).

- [ ] **Step 4.5: Commit**

```bash
git add src/lib/statistics.py src/cli/test_query.py
git commit -m "feat: display cache savings in CLI cost breakdown"
```

---

## Task 5: Update Quality Test Tracking

**Files:**
- Modify: `tests/quality/reporting/report_models.py`
- Modify: `tests/quality/test_runner.py`
- Modify: `tests/quality/reporting/report_generator.py`

- [ ] **Step 5.1: Read all three files**

Read `tests/quality/reporting/report_models.py`, `tests/quality/test_runner.py`, and `tests/quality/reporting/report_generator.py` fully before editing.

- [ ] **Step 5.2: Add `cache_savings_usd` to `IndividualTestResult`**

In `report_models.py`, in the `IndividualTestResult` dataclass, add:

```python
cache_savings_usd: float = 0.0
```

Update the `total_cost_usd` property if it does not already exclude savings (savings reduce cost, the field is additive to reporting only — don't subtract from total_cost, which already reflects actual paid amount).

In the aggregate stats class (if present), add `avg_cache_savings` computed similarly to `avg_cost`.

- [ ] **Step 5.3: Capture cache savings in `test_runner.py`**

Find the `estimate_cost()` call around lines 387-404. Replace with:

```python
from src.lib.tokens import calculate_llm_cost
# ...
llm_cost_breakdown = calculate_llm_cost(
    prompt_tokens=actual_prompt_tokens,
    completion_tokens=actual_completion_tokens,
    model=actual_model_id,
    cache_read_tokens=getattr(llm_response, "cache_read_tokens", 0),
    cache_creation_tokens=getattr(llm_response, "cache_creation_tokens", 0),
)
cost = llm_cost_breakdown.total_cost
cache_savings = llm_cost_breakdown.cache_savings
```

When building `IndividualTestResult`, pass `cache_savings_usd=cache_savings`.

- [ ] **Step 5.4: Add cache savings to report output**

In `report_generator.py`, in the per-test or aggregate cost section, add a line like:

```python
if total_cache_savings > 0:
    lines.append(f"  Cache Savings:       ${total_cache_savings:.4f} ({pct_savings:.1f}% of gross)")
```

Compute `total_cache_savings = sum(r.cache_savings_usd for r in results)`.
Compute `pct_savings = total_cache_savings / gross_cost * 100` where `gross_cost = total_cost + total_cache_savings`.

- [ ] **Step 5.5: Run a quality test to verify**

```bash
source venv/bin/activate && python -m src.cli quality-test --test eliminator-concealed-counteract
```

Expected: cost breakdown in report shows cache savings (may be $0 if model doesn't use caching for this call).

- [ ] **Step 5.6: Commit**

```bash
git add tests/quality/reporting/report_models.py tests/quality/test_runner.py tests/quality/reporting/report_generator.py
git commit -m "feat: track and report cache savings in quality test results"
```

---

## Task 6: Update Admin Dashboard (LLM Re-run)

**Files:**
- Modify: `src/admin_dashboard/services/llm_rerun.py`

- [ ] **Step 6.1: Read file**

Read `src/admin_dashboard/services/llm_rerun.py` fully.

- [ ] **Step 6.2: Replace `estimate_cost` with `calculate_llm_cost`**

Find the `result.cost_usd = estimate_cost(...)` call (around line 197). Replace:

```python
from src.lib.tokens import calculate_llm_cost
# ...
breakdown = calculate_llm_cost(
    prompt_tokens=llm_response.prompt_tokens,
    completion_tokens=llm_response.completion_tokens,
    model=model_name,
    cache_read_tokens=getattr(llm_response, "cache_read_tokens", 0),
    cache_creation_tokens=getattr(llm_response, "cache_creation_tokens", 0),
)
result.cost_usd = breakdown.total_cost
result.cache_savings_usd = breakdown.cache_savings
```

If `result` is a dataclass/dict, add `cache_savings_usd` to it. If it's a dict, just add the key.

- [ ] **Step 6.3: Commit**

```bash
git add src/admin_dashboard/services/llm_rerun.py
git commit -m "feat: include cache savings in admin dashboard re-run cost"
```

---

## Verification

### Unit tests

```bash
source venv/bin/activate && pytest tests/unit/test_tokens.py tests/unit/test_llm_providers.py -v
```

Expected: all pass.

### Full test suite

```bash
source venv/bin/activate && pytest tests/unit/ tests/contract/ -v
```

Expected: no regressions.

### End-to-end CLI

```bash
source venv/bin/activate && python -m src.cli query "Can I use overwatch against a charge?"
```

Expected: cost summary shows a `Cache savings:` line. If the provider (Claude/GPT/Grok) returns cache tokens, the savings will be non-zero.

### Quality test

```bash
source venv/bin/activate && python -m src.cli quality-test --test eliminator-concealed-counteract
```

Expected: report includes cache savings line in cost breakdown.

### Lint

```bash
source venv/bin/activate && ruff check src/ tests/
```

Expected: no errors.
