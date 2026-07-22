"""LLM pricing and cost calculation.

Based on specs/001-we-are-building/tasks.md T029
"""

from dataclasses import dataclass

from src.lib.logging import get_logger
from src.lib.model_name import model_base_name

logger = get_logger(__name__)


@dataclass
class LLMCostBreakdown:
    """Cost breakdown for a single LLM call, including cache savings."""

    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    prompt_cost: float
    completion_cost: float
    cache_read_cost: float
    cache_creation_cost: float
    total_cost: float
    cache_savings: float
    batch_savings: float = 0.0

    @property
    def has_cache_activity(self) -> bool:
        return self.cache_read_tokens > 0 or self.cache_creation_tokens > 0


# Cached-read pricing is a fixed fraction of the base prompt rate, so it is
# stored once per provider family here instead of repeated on every model entry.
# Anthropic is the only provider that bills cache *writes*; everywhere else the
# write rate is zero and cache_creation_cost stays 0.
# Ratios verified against the pricing pages linked on each family below (July 2026).
ANTHROPIC_CACHE_READ_MULTIPLIER = 0.1
ANTHROPIC_CACHE_WRITE_MULTIPLIER = 1.25
OPENAI_CACHE_READ_MULTIPLIER = 0.5       # gpt-* and grok-* (both 50% cached discount)
GEMINI_CACHE_READ_MULTIPLIER = 0.1
MISTRAL_CACHE_READ_MULTIPLIER = 0.1
DEEPSEEK_CACHE_READ_MULTIPLIER = 0.02    # v4-flash $0.0028 hit vs $0.14 miss per 1M
MOONSHOT_CACHE_READ_MULTIPLIER = 0.2     # Kimi: k2.7-code $0.19 hit vs $0.95 miss per 1M
QWEN_CACHE_READ_MULTIPLIER = 0.2
NO_CACHE_DISCOUNT = 1.0                  # provider has no prompt caching

# Models whose published cached-read discount differs from their family's rate.
_CACHE_READ_RATIO_OVERRIDES = {
    "deepseek-v4-pro": 0.00833,  # $0.003625 hit vs $0.435 miss per 1M
}

# model name -> (prompt, completion) price per 1K tokens
_Rates = dict[str, tuple[float, float]]


def _family(cache_read_ratio: float, models: _Rates, cache_mode: str = "openai") -> dict[str, dict]:
    """Expand one provider family's rate table into full pricing entries."""
    return {
        name: {
            "prompt": prompt,
            "completion": completion,
            "cache_read_ratio": _CACHE_READ_RATIO_OVERRIDES.get(name, cache_read_ratio),
            "cache_mode": cache_mode,
        }
        for name, (prompt, completion) in models.items()
    }


# Pricing per 1K tokens (as of 2026 July)
# cache_mode: "openai" (default) = cached_tokens are a subset of prompt_tokens,
#                       billed at prompt * cache_read_ratio
#             "anthropic" = cache_read/write SEPARATE from prompt_tokens
pricing: dict[str, dict] = {
    # https://platform.openai.com/docs/pricing
    **_family(OPENAI_CACHE_READ_MULTIPLIER, {
        "gpt-5.6-luna":        (0.00100, 0.060),
        "gpt-5.5":             (0.00500, 0.030),
        "gpt-5.4":             (0.00250, 0.015),
        "gpt-5.4-mini":        (0.00075, 0.0045),
        "gpt-5.4-nano":        (0.00020, 0.00125),
        "gpt-5.3-chat-latest": (0.00175, 0.014),
        "gpt-5.2":             (0.00175, 0.014),
        "gpt-5.2-chat-latest": (0.00175, 0.014),
        "gpt-5.1":             (0.00125, 0.01),
        "gpt-5.1-chat-latest": (0.00125, 0.01),
        "gpt-5":               (0.00125, 0.01),
        "gpt-5-mini":          (0.00025, 0.002),
        "gpt-5-nano":          (0.00005, 0.0004),
        "gpt-4.1":             (0.002,   0.008),
        "gpt-4.1-mini":        (0.0004,  0.0016),
        "gpt-4.1-nano":        (0.0001,  0.0004),
        "gpt-4o":              (0.0025,  0.01),
    }),
    # https://www.claude.com/pricing#api
    # Keyed by the model IDs the API returns; friendly names are aliased below.
    **_family(ANTHROPIC_CACHE_READ_MULTIPLIER, {
        "claude-sonnet-4-6":          (0.003, 0.006),
        "claude-sonnet-4-5-20250929": (0.003, 0.006),
        "claude-opus-4-8":            (0.005, 0.025),
        "claude-opus-4-7":            (0.005, 0.025),
        "claude-opus-4-6":            (0.005, 0.025),
        "claude-opus-4-5-20251101":   (0.005, 0.025),
        "claude-opus-4-1-20250805":   (0.015, 0.075),
        "claude-haiku-4-5-20251001":  (0.001, 0.005),
    }, cache_mode="anthropic"),
    # https://docs.x.ai/docs/models - OpenAI-compatible cache format, 50% discount
    **_family(OPENAI_CACHE_READ_MULTIPLIER, {
        "grok-4.3":                     (0.00125, 0.00250),
        "grok-4.20-0309-reasoning":     (0.00125, 0.00250),
        "grok-4.20-0309-non-reasoning": (0.00125, 0.00250),
        "grok-build-0.1":               (0.00100, 0.00200),
    }),
    # https://ai.google.dev/gemini-api/docs/pricing
    # Implicit caching on by default for 2.5+ models (cached_content_token_count
    # is a subset of prompt_token_count)
    **_family(GEMINI_CACHE_READ_MULTIPLIER, {
        "gemini-3.1-pro-preview":  (0.002,   0.012),
        "gemini-3-pro-preview":    (0.002,   0.012),
        "gemini-2.5-pro":          (0.00125, 0.01),
        "gemini-3-flash-preview":  (0.0005,  0.003),
        "gemini-3.1-flash-lite":   (0.00025, 0.0015),
        "gemini-3.5-flash":        (0.0015,  0.009),
        "gemini-2.5-flash":        (0.0003,  0.0025),
    }),
    # https://api-docs.deepseek.com/quick_start/pricing
    **_family(DEEPSEEK_CACHE_READ_MULTIPLIER, {
        "deepseek-v4-flash": (0.00014,  0.00028),
        "deepseek-v4-pro":   (0.000435, 0.00087),
    }),
    # https://platform.kimi.ai/docs/pricing/chat
    # k2.5/k2.6 cache hits are ~17% of the miss rate, k2.7-code 20%; the family
    # rate rounds up to 20%, so cached reads are never under-billed.
    **_family(MOONSHOT_CACHE_READ_MULTIPLIER, {
        "kimi-k2.7-code": (0.00095, 0.004),
        "kimi-k2.6":      (0.00095, 0.004),
        "kimi-k2.5":      (0.0006,  0.003),
        "moonshot-v1-8k": (0.0002,  0.002),
    }),
    # https://mistral.ai/pricing#api-pricing
    # Opt-in caching via prompt_cache_key; cached reads billed at 10% of prompt rate
    **_family(MISTRAL_CACHE_READ_MULTIPLIER, {
        "mistral-medium-3-5": (0.0015,  0.0075),
        "mistral-small-2603": (0.00015, 0.0006),
        "mistral-large-2512": (0.0005,  0.0015),
        "ministral-14b-2512": (0.0002,  0.0002),
        "ministral-8b-2512":  (0.00015, 0.0015),
    }),
    # Qwen models (Alibaba Cloud) - https://help.aliyun.com/zh/model-studio/pricing
    **_family(QWEN_CACHE_READ_MULTIPLIER, {
        "qwen3.7-max-2026-05-20":       (0.0025,  0.0075),
        "qwen3.6-flash-2026-04-16":     (0.00025, 0.0015),
        "qwen3-turbo":                  (0.00005, 0.0002),   # non-thinking price
        "qwen3-coder-plus-2025-09-23":  (0.00100, 0.00500),
        "qwen3-coder-flash-2025-07-28": (0.00030, 0.00150),
    }),
    # GLM (Z.AI, https://platform.z.ai/pricing) and MiniMax
    # (https://platform.minimax.io/docs/pricing) - no prompt caching
    **_family(NO_CACHE_DISCOUNT, {
        "glm-5":        (0.00050, 0.00250),
        "glm-4.7":      (0.00050, 0.00250),
        "MiniMax-M2.5": (0.00020, 0.00080),
    }),
}

# Friendly name (CLI / constants / servers.yaml) -> model ID the API reports.
# Both spellings reach cost calculation — model_version for served responses,
# the friendly name when no response is available — so both must price alike.
# Mirrors LLMProviderFactory._model_registry, which cannot be imported here
# (src/lib must not depend on src/services); tests/unit/test_pricing_aliases.py
# fails if the two drift apart.
_PRICING_ALIASES = {
    "claude-4.6-sonnet":  "claude-sonnet-4-6",
    "claude-4.5-sonnet":  "claude-sonnet-4-5-20250929",
    "claude-4.8-opus":    "claude-opus-4-8",
    "claude-4.7-opus":    "claude-opus-4-7",
    "claude-4.6-opus":    "claude-opus-4-6",
    "claude-4.5-opus":    "claude-opus-4-5-20251101",
    "claude-4.1-opus":    "claude-opus-4-1-20250805",
    "claude-4.5-haiku":   "claude-haiku-4-5-20251001",
    "gpt-5.4-mini-2026-03-17": "gpt-5.4-mini",
    "mistral-small-4":    "mistral-small-2603",
    "mistral-large-3":    "mistral-large-2512",
    "ministral-3-14-b":   "ministral-14b-2512",
    "ministral-3-8-b":    "ministral-8b-2512",
    "qwen3.7-max":        "qwen3.7-max-2026-05-20",
    "qwen3.6-flash":      "qwen3.6-flash-2026-04-16",
    "qwen3-coder-plus":   "qwen3-coder-plus-2025-09-23",
    "qwen3-coder-flash":  "qwen3-coder-flash-2025-07-28",
}
pricing.update({alias: pricing[target] for alias, target in _PRICING_ALIASES.items()})

# Rate used when a model has no pricing entry at all.
_FALLBACK_PRICING = {"prompt": 0.002, "completion": 0.002, "cache_read_ratio": NO_CACHE_DISCOUNT}


# Batch API discount per backend (fraction off the live, post-cache cost).
# Anthropic, OpenAI, Mistral, Qwen/DashScope, Gemini confirmed 50%. Grok (x)
# confirmed 20%. Moonshot (Kimi) publishes "reduced pricing" without a
# confirmed %, defaulted to 0.5 — confirm against their pricing page and correct
# here if different; batch_savings_usd for it is an estimate until then.
DEFAULT_BATCH_DISCOUNT = 0.5
BATCH_DISCOUNT: dict[str, float] = {
    "anthropic": 0.5,
    "openai": 0.5,
    "mistral": 0.5,
    "alibaba": 0.5,   # Qwen / DashScope
    "google": 0.5,    # Gemini
    "moonshot": 0.5,  # Kimi — estimate, confirm
    "x": 0.2,         # Grok — confirmed
}


def batch_discount_for(backend: str | None) -> float:
    """Return the batch discount fraction for a backend name (default 0.5).

    OpenAI-compatible callers pass a compound `"backend::model"` group key
    (see `tests/quality/batch/backends.py::batch_group_key`) since those
    providers batch one model per submission; strip the model suffix so the
    lookup still hits BATCH_DISCOUNT's bare backend names instead of silently
    falling through to the default.
    """
    name = (backend or "").split("::", 1)[0]
    return BATCH_DISCOUNT.get(name, DEFAULT_BATCH_DISCOUNT)


def calculate_llm_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    batch: bool = False,
    batch_backend: str | None = None,
) -> LLMCostBreakdown:
    """Calculate detailed cost breakdown for an LLM call, including cache savings.

    Args:
        prompt_tokens: Number of prompt tokens (non-cached, or total for anthropic)
        completion_tokens: Number of completion tokens
        model: Model name
        cache_read_tokens: Tokens served from cache (default: 0)
        cache_creation_tokens: Tokens written to cache (default: 0, anthropic only)
        batch: If True, apply the Batch-API discount on top of cache accounting
               and report the delta as batch_savings.
        batch_backend: Backend name selecting the discount rate (see BATCH_DISCOUNT);
               None falls back to DEFAULT_BATCH_DISCOUNT (0.5).

    Returns:
        LLMCostBreakdown with full cost and savings breakdown
    """
    # Model names may carry a "#effort" postfix; pricing is keyed by the base
    # name. Strip here rather than at each call site so no caller can leak the
    # postfix into the lookup and silently get the placeholder rate.
    model = model_base_name(model)
    if model not in pricing:
        logger.warning(f"No pricing entry for model '{model}'; using placeholder rate")
        p = _FALLBACK_PRICING
    else:
        p = pricing[model]
    cache_mode = p.get("cache_mode", "openai")

    completion_cost = (completion_tokens / 1000) * p["completion"]

    if cache_mode == "anthropic":
        # Anthropic: cache_read and cache_creation tokens are SEPARATE from prompt_tokens.
        # Cache rates are fixed multipliers of the base prompt rate (see constants above).
        cache_read_rate = p["prompt"] * ANTHROPIC_CACHE_READ_MULTIPLIER
        cache_write_rate = p["prompt"] * ANTHROPIC_CACHE_WRITE_MULTIPLIER
        prompt_cost = (prompt_tokens / 1000) * p["prompt"]
        cache_read_cost = (cache_read_tokens / 1000) * cache_read_rate
        cache_creation_cost = (cache_creation_tokens / 1000) * cache_write_rate
        total_cost = prompt_cost + cache_read_cost + cache_creation_cost + completion_cost
        # Savings = what we would have paid at full prompt rate minus what we actually paid for cache
        read_savings = (cache_read_tokens / 1000) * (p["prompt"] - cache_read_rate)
        write_extra = (cache_creation_tokens / 1000) * (cache_write_rate - p["prompt"])
        cache_savings = read_savings - write_extra

    else:
        # OpenAI-style: cached_tokens are a subset of prompt_tokens, billed at the
        # family's fixed fraction of the prompt rate. Providers without caching use
        # ratio 1.0 (NO_CACHE_DISCOUNT), which prices cached tokens at the full
        # prompt rate and yields zero savings — same total as no caching at all.
        cache_read_rate = p["prompt"] * p["cache_read_ratio"]
        cache_read_tokens = min(cache_read_tokens, prompt_tokens)
        non_cached = prompt_tokens - cache_read_tokens
        prompt_cost = (non_cached / 1000) * p["prompt"]
        cache_read_cost = (cache_read_tokens / 1000) * cache_read_rate
        cache_creation_cost = 0.0
        total_cost = prompt_cost + cache_read_cost + completion_cost
        cache_savings = (cache_read_tokens / 1000) * (p["prompt"] - cache_read_rate)

    # Batch discount stacks on top of cache accounting. cache_savings stays computed
    # on the live (pre-discount) numbers above so the two savings never double-count.
    if batch:
        discount = batch_discount_for(batch_backend)
        factor = 1.0 - discount
        batch_savings = total_cost * discount
        prompt_cost *= factor
        completion_cost *= factor
        cache_read_cost *= factor
        cache_creation_cost *= factor
        total_cost *= factor
    else:
        batch_savings = 0.0

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
        batch_savings=batch_savings,
    )


def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Estimate cost for LLM API call. Returns total USD."""
    return calculate_llm_cost(prompt_tokens, completion_tokens, model).total_cost
