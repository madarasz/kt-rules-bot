"""Token counting utility for text chunking.

Uses tiktoken library for accurate token counting.
Based on specs/001-we-are-building/tasks.md T029
"""

from dataclasses import dataclass

import tiktoken

from src.lib.constants import EMBEDDING_MODEL

# Default encoding for OpenAI models
DEFAULT_ENCODING = "cl100k_base"


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

    @property
    def has_cache_activity(self) -> bool:
        return self.cache_read_tokens > 0 or self.cache_creation_tokens > 0


# Pricing per 1K tokens (as of 2025 October)
# cache_mode: "openai" = cached_tokens subset of prompt_tokens (50% discount)
#             "anthropic" = cache_read/write SEPARATE from prompt_tokens
#             "none" = no caching support
pricing: dict[str, dict] = {
    # https://platform.openai.com/docs/pricing
    "gpt-5.5":             {"prompt": 0.00500, "completion": 0.030,  "cache_read": 0.00250,  "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.4":             {"prompt": 0.00250, "completion": 0.015,  "cache_read": 0.00125,  "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.4-mini":        {"prompt": 0.00075, "completion": 0.0045, "cache_read": 0.000375, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.4-nano":        {"prompt": 0.00020, "completion": 0.00125,"cache_read": 0.00010,  "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.3-chat-latest": {"prompt": 0.00175, "completion": 0.014,  "cache_read": 0.000875, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.2":             {"prompt": 0.00175, "completion": 0.014,  "cache_read": 0.000875, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.2-chat-latest": {"prompt": 0.00175, "completion": 0.014,  "cache_read": 0.000875, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.1":             {"prompt": 0.00125, "completion": 0.01,   "cache_read": 0.000625, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5.1-chat-latest": {"prompt": 0.00125, "completion": 0.01,   "cache_read": 0.000625, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5":               {"prompt": 0.00125, "completion": 0.01,   "cache_read": 0.000625, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5-mini":          {"prompt": 0.00025, "completion": 0.002,  "cache_read": 0.000125, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-5-nano":          {"prompt": 0.00005, "completion": 0.0004, "cache_read": 0.000025, "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-4.1":             {"prompt": 0.002,   "completion": 0.008,  "cache_read": 0.001,    "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-4.1-mini":        {"prompt": 0.0004,  "completion": 0.0016, "cache_read": 0.0002,   "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-4.1-nano":        {"prompt": 0.0001,  "completion": 0.0004, "cache_read": 0.00005,  "cache_write": 0.0, "cache_mode": "openai"},
    "gpt-4o":              {"prompt": 0.0025,  "completion": 0.01,   "cache_read": 0.00125,  "cache_write": 0.0, "cache_mode": "openai"},
    # https://www.claude.com/pricing#api
    # Actual model IDs (returned by API) - cache_read/write SEPARATE from prompt_tokens
    "claude-sonnet-4-6":         {"prompt": 0.003,  "completion": 0.006,  "cache_read": 0.0003,   "cache_write": 0.00375, "cache_mode": "anthropic"},
    "claude-sonnet-4-5-20250929":{"prompt": 0.003,  "completion": 0.006,  "cache_read": 0.0003,   "cache_write": 0.00375, "cache_mode": "anthropic"},
    "claude-opus-4-6":           {"prompt": 0.005,  "completion": 0.025,  "cache_read": 0.0005,   "cache_write": 0.00625, "cache_mode": "anthropic"},
    "claude-opus-4-5-20251101":  {"prompt": 0.005,  "completion": 0.025,  "cache_read": 0.0005,   "cache_write": 0.00625, "cache_mode": "anthropic"},
    "claude-opus-4-1-20250805":  {"prompt": 0.015,  "completion": 0.075,  "cache_read": 0.0015,   "cache_write": 0.01875, "cache_mode": "anthropic"},
    "claude-haiku-4-5-20251001": {"prompt": 0.001,  "completion": 0.005,  "cache_read": 0.0001,   "cache_write": 0.00125, "cache_mode": "anthropic"},
    # Friendly name aliases (used in constants/CLI)
    "claude-4.6-sonnet":         {"prompt": 0.003,  "completion": 0.006,  "cache_read": 0.0003,   "cache_write": 0.00375, "cache_mode": "anthropic"},
    "claude-4.5-sonnet":         {"prompt": 0.003,  "completion": 0.006,  "cache_read": 0.0003,   "cache_write": 0.00375, "cache_mode": "anthropic"},
    "claude-4.6-opus":           {"prompt": 0.005,  "completion": 0.025,  "cache_read": 0.0005,   "cache_write": 0.00625, "cache_mode": "anthropic"},
    "claude-4.5-opus":           {"prompt": 0.005,  "completion": 0.025,  "cache_read": 0.0005,   "cache_write": 0.00625, "cache_mode": "anthropic"},
    "claude-4.1-opus":           {"prompt": 0.015,  "completion": 0.075,  "cache_read": 0.0015,   "cache_write": 0.01875, "cache_mode": "anthropic"},
    "claude-4.5-haiku":          {"prompt": 0.001,  "completion": 0.005,  "cache_read": 0.0001,   "cache_write": 0.00125, "cache_mode": "anthropic"},
    # https://docs.x.ai/docs/models
    # Grok - OpenAI-compatible cache format, 50% discount
    "grok-4-1-fast-reasoning":    {"prompt": 0.0002,  "completion": 0.0005,  "cache_read": 0.00005,  "cache_write": 0.0, "cache_mode": "openai"},
    "grok-4-1-fast-non-reasoning":{"prompt": 0.0002,  "completion": 0.0005,  "cache_read": 0.00005,  "cache_write": 0.0, "cache_mode": "openai"},
    "grok-4.3":                   {"prompt": 0.00125, "completion": 0.00250, "cache_read": 0.000625, "cache_write": 0.0, "cache_mode": "openai"},
    "grok-4.20-0309-reasoning":   {"prompt": 0.00125, "completion": 0.00250, "cache_read": 0.000625, "cache_write": 0.0, "cache_mode": "openai"},
    "grok-build-0.1":             {"prompt": 0.00100, "completion": 0.00200, "cache_read": 0.0005,   "cache_write": 0.0, "cache_mode": "openai"},
    # https://ai.google.dev/gemini-api/docs/pricing
    # Gemini - no explicit caching support in current integration
    "gemini-3.1-pro-preview":  {"prompt": 0.002,   "completion": 0.012,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "gemini-3-pro-preview":    {"prompt": 0.002,   "completion": 0.012,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "gemini-2.5-pro":          {"prompt": 0.00125, "completion": 0.01,   "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "gemini-3-flash-preview":  {"prompt": 0.0005,  "completion": 0.003,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "gemini-3.5-flash":        {"prompt": 0.0015,  "completion": 0.009,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "gemini-2.5-flash":        {"prompt": 0.0003,  "completion": 0.0025, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    # https://api-docs.deepseek.com/quick_start/pricing
    "deepseek-chat":    {"prompt": 0.00028, "completion": 0.00042, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "deepseek-reasoner":{"prompt": 0.00028, "completion": 0.00042, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    # https://platform.moonshot.ai/docs/pricing/chat
    "kimi-k2.5":             {"prompt": 0.0001,  "completion": 0.003,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "kimi-k2-0905-preview":  {"prompt": 0.00015, "completion": 0.0025, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "kimi-k2-turbo-preview": {"prompt": 0.00015, "completion": 0.008,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    # https://mistral.ai/pricing#api-pricing
    "mistral-large":          {"prompt": 0.0005, "completion": 0.0015, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-medium":         {"prompt": 0.0004, "completion": 0.002,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-small":          {"prompt": 0.0001, "completion": 0.0003, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-large-latest":   {"prompt": 0.0005, "completion": 0.0015, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-medium-2505":    {"prompt": 0.0004, "completion": 0.002,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "mistral-small-latest":   {"prompt": 0.0001, "completion": 0.0003, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    "magistral-medium-latest":{"prompt": 0.002,  "completion": 0.005,  "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},
    # Qwen models (Alibaba Cloud) - https://help.aliyun.com/zh/model-studio/pricing
    "qwen3.5-plus":         {"prompt": 0.00040, "completion": 0.00240, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},  # $0.40/$2.40 per 1M tokens
    "qwen3-max-2026-01-23": {"prompt": 0.00120, "completion": 0.00600, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},  # $1.20/$6.00 per 1M tokens
    "qwen3-coder-plus":     {"prompt": 0.00100, "completion": 0.00500, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},  # $1.00/$5.00 per 1M tokens
    "qwen3-coder-next":     {"prompt": 0.00030, "completion": 0.00150, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},  # $0.30/$1.50 per 1M tokens
    # GLM models (Z.AI) - https://platform.z.ai/pricing
    "glm-5":   {"prompt": 0.00050, "completion": 0.00250, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},  # $0.50/$2.50 per 1M tokens
    "glm-4.7": {"prompt": 0.00050, "completion": 0.00250, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},  # $0.50/$2.50 per 1M tokens
    # MiniMax models - https://platform.minimax.io/docs/pricing
    "MiniMax-M2.5": {"prompt": 0.00020, "completion": 0.00080, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"},  # $0.20/$0.80 per 1M tokens
}


def calculate_llm_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> LLMCostBreakdown:
    """Calculate detailed cost breakdown for an LLM call, including cache savings.

    Args:
        prompt_tokens: Number of prompt tokens (non-cached, or total for anthropic)
        completion_tokens: Number of completion tokens
        model: Model name
        cache_read_tokens: Tokens served from cache (default: 0)
        cache_creation_tokens: Tokens written to cache (default: 0, anthropic only)

    Returns:
        LLMCostBreakdown with full cost and savings breakdown
    """
    if model not in pricing:
        p = {"prompt": 0.002, "completion": 0.002, "cache_read": 0.0, "cache_write": 0.0, "cache_mode": "none"}
    else:
        p = pricing[model]
    cache_mode = p.get("cache_mode", "none")

    completion_cost = (completion_tokens / 1000) * p["completion"]

    if cache_mode == "anthropic":
        # Anthropic: cache_read and cache_creation tokens are SEPARATE from prompt_tokens
        prompt_cost = (prompt_tokens / 1000) * p["prompt"]
        cache_read_cost = (cache_read_tokens / 1000) * p["cache_read"]
        cache_creation_cost = (cache_creation_tokens / 1000) * p["cache_write"]
        total_cost = prompt_cost + cache_read_cost + cache_creation_cost + completion_cost
        # Savings = what we would have paid at full prompt rate minus what we actually paid for cache
        read_savings = (cache_read_tokens / 1000) * p["prompt"] * 0.9
        write_extra = (cache_creation_tokens / 1000) * p["prompt"] * 0.25
        cache_savings = read_savings - write_extra

    elif cache_mode == "openai":
        # OpenAI: cached_tokens are a subset of prompt_tokens, billed at 50% discount
        non_cached = max(0, prompt_tokens - cache_read_tokens)
        prompt_cost = (non_cached / 1000) * p["prompt"]
        cache_read_cost = (cache_read_tokens / 1000) * p["cache_read"]
        cache_creation_cost = 0.0
        total_cost = prompt_cost + cache_read_cost + completion_cost
        cache_savings = (cache_read_tokens / 1000) * p["prompt"] * 0.5

    else:
        # No caching support
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


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """Count tokens in text using tiktoken.

    Args:
        text: Text to count tokens for
        model: Model name (default: gpt-3.5-turbo)

    Returns:
        Number of tokens
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to default encoding if model not found
        encoding = tiktoken.get_encoding(DEFAULT_ENCODING)

    return len(encoding.encode(text))


def count_tokens_with_encoding(text: str, encoding_name: str = DEFAULT_ENCODING) -> int:
    """Count tokens using specific encoding.

    Args:
        text: Text to count tokens for
        encoding_name: Encoding name (default: cl100k_base)

    Returns:
        Number of tokens
    """
    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(text))


def truncate_to_token_limit(text: str, max_tokens: int, model: str = "gpt-3.5-turbo") -> str:
    """Truncate text to fit within token limit.

    Args:
        text: Text to truncate
        max_tokens: Maximum number of tokens
        model: Model name

    Returns:
        Truncated text
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding(DEFAULT_ENCODING)

    tokens = encoding.encode(text)

    if len(tokens) <= max_tokens:
        return text

    # Truncate tokens and decode back to text
    truncated_tokens = tokens[:max_tokens]
    decoded: str = encoding.decode(truncated_tokens)
    return decoded


def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Estimate cost for LLM API call. Returns total USD."""
    return calculate_llm_cost(prompt_tokens, completion_tokens, model).total_cost


def get_embedding_token_limit(model: str = EMBEDDING_MODEL) -> int:
    """Get token limit for embedding model.

    Args:
        model: Embedding model name

    Returns:
        Maximum token limit
    """
    limits = {
        "text-embedding-3-small": 8191,
        "text-embedding-3-large": 8191,
        "text-embedding-ada-002": 8191,  # Different model with different limit
    }

    return limits.get(model, 8191)


def get_embedding_dimensions(model: str = EMBEDDING_MODEL) -> int:
    """Get embedding dimensions for embedding model.

    Args:
        model: Embedding model name

    Returns:
        Embedding vector dimensions
    """
    dimensions = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    return dimensions.get(model, 1536)


def estimate_embedding_cost(text: str, model: str = EMBEDDING_MODEL) -> float:
    """Estimate cost for embedding generation.

    Args:
        text: Text to generate embedding for
        model: Embedding model name (default: from constants)

    Returns:
        Estimated cost in USD
    """
    # Pricing per 1M tokens (as of 2025 October)
    embedding_pricing = {
        "text-embedding-3-small": 0.020 / 1_000_000,  # $0.020 per 1M tokens
        "text-embedding-3-large": 0.130 / 1_000_000,  # $0.130 per 1M tokens
        "text-embedding-ada-002": 0.100 / 1_000_000,  # $0.100 per 1M tokens
    }

    # Count tokens
    tokens = count_tokens(text, model="gpt-3.5-turbo")  # Use default encoder

    # Get cost per token
    cost_per_token = embedding_pricing.get(model, embedding_pricing["text-embedding-3-small"])

    return tokens * cost_per_token


def split_text_by_tokens(
    text: str, max_tokens: int, model: str = "gpt-3.5-turbo", overlap: int = 0
) -> list[str]:
    """Split text into chunks by token count.

    Args:
        text: Text to split
        max_tokens: Maximum tokens per chunk
        model: Model name for token counting
        overlap: Number of overlapping tokens between chunks

    Returns:
        List of text chunks
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding(DEFAULT_ENCODING)

    tokens = encoding.encode(text)
    chunks = []

    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        chunks.append(encoding.decode(chunk_tokens))

        # Move start forward by (max_tokens - overlap)
        start = end - overlap if overlap > 0 else end

    return chunks
