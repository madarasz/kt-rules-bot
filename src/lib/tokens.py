"""Token counting utility for text chunking.

Uses tiktoken library for accurate token counting.
Based on specs/001-we-are-building/tasks.md T029
"""

import tiktoken

from src.lib.constants import EMBEDDING_MODEL

# Default encoding for OpenAI models
DEFAULT_ENCODING = "cl100k_base"


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
    """Estimate cost for LLM API call.

    Args:
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        model: Model name

    Returns:
        Estimated cost in USD
    """
    # Pricing per 1K tokens (as of 2025 October)
    pricing = {
        # https://platform.openai.com/docs/pricing
        "gpt-5.2": {"prompt": 0.00175, "completion": 0.014},
        "gpt-5.2-chat-latest": {"prompt": 0.00175, "completion": 0.014},
        "gpt-5.1": {"prompt": 0.00125, "completion": 0.01},
        "gpt-5.1-chat-latest": {"prompt": 0.00125, "completion": 0.01},
        "gpt-5": {"prompt": 0.00125, "completion": 0.01},
        "gpt-5-mini": {"prompt": 0.00025, "completion": 0.002},
        "gpt-5-nano": {"prompt": 0.00005, "completion": 0.0004},
        "gpt-4.1": {"prompt": 0.002, "completion": 0.008},
        "gpt-4.1-mini": {"prompt": 0.0004, "completion": 0.0016},
        "gpt-4.1-nano": {"prompt": 0.0001, "completion": 0.0004},
        "gpt-4o": {"prompt": 0.0025, "completion": 0.01},
        # https://www.claude.com/pricing#api
        # Actual model IDs (returned by API)
        "claude-sonnet-4-5-20250929": {"prompt": 0.003, "completion": 0.006},
        "claude-opus-4-6": {"prompt": 0.005, "completion": 0.025},
        "claude-opus-4-5-20251101": {"prompt": 0.005, "completion": 0.025},
        "claude-opus-4-1-20250805": {"prompt": 0.015, "completion": 0.075},
        "claude-haiku-4-5-20251001": {"prompt": 0.001, "completion": 0.005},
        # Friendly name aliases (used in constants/CLI)
        "claude-4.5-sonnet": {"prompt": 0.003, "completion": 0.006},
        "claude-4.6-opus": {"prompt": 0.005, "completion": 0.025},
        "claude-4.5-opus": {"prompt": 0.005, "completion": 0.025},
        "claude-4.1-opus": {"prompt": 0.015, "completion": 0.075},
        "claude-4.5-haiku": {"prompt": 0.001, "completion": 0.005},
        # https://ai.google.dev/gemini-api/docs/pricing
        "gemini-3-pro-preview": {"prompt": 0.002, "completion": 0.012},
        "gemini-2.5-pro": {"prompt": 0.00125, "completion": 0.01},
        "gemini-3-flash-preview": {"prompt": 0.0005, "completion": 0.003},
        "gemini-2.5-flash": {"prompt": 0.0003, "completion": 0.0025},
        # https://api-docs.deepseek.com/quick_start/pricing
        "deepseek-chat": {"prompt": 0.00028, "completion": 0.00042},
        "deepseek-reasoner": {"prompt": 0.00028, "completion": 0.00042},
        # https://platform.moonshot.ai/docs/pricing/chat
        "kimi-k2.5": {"prompt": 0.0001, "completion": 0.003},
        "kimi-k2-0905-preview": {"prompt": 0.00015, "completion": 0.0025},
        "kimi-k2-turbo-preview": {"prompt": 0.00015, "completion": 0.008},
        # https://docs.x.ai/docs/models
        "grok-4-1-fast-reasoning": {"prompt": 0.0002, "completion": 0.0005},
        "grok-4-1-fast-non-reasoning": {"prompt": 0.0002, "completion": 0.0005},
        # https://mistral.ai/pricing#api-pricing
        "mistral-large": {"prompt": 0.0005, "completion": 0.0015},
        "mistral-medium": {"prompt": 0.0004, "completion": 0.002},
        "mistral-small": {"prompt": 0.0001, "completion": 0.0003},
        "mistral-large-latest": {"prompt": 0.0005, "completion": 0.0015},
        "mistral-medium-2505": {"prompt": 0.0004, "completion": 0.002},
        "mistral-small-latest": {"prompt": 0.0001, "completion": 0.0003},
        "magistral-medium-latest": {"prompt": 0.002, "completion": 0.005},
    }

    # Default pricing if model not found
    if model not in pricing:
        pricing[model] = {"prompt": 0.002, "completion": 0.002}

    prompt_cost = (prompt_tokens / 1000) * pricing[model]["prompt"]
    completion_cost = (completion_tokens / 1000) * pricing[model]["completion"]

    return prompt_cost + completion_cost


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
    pricing = {
        "text-embedding-3-small": 0.020 / 1_000_000,  # $0.020 per 1M tokens
        "text-embedding-3-large": 0.130 / 1_000_000,  # $0.130 per 1M tokens
        "text-embedding-ada-002": 0.100 / 1_000_000,  # $0.100 per 1M tokens
    }

    # Count tokens
    tokens = count_tokens(text, model="gpt-3.5-turbo")  # Use default encoder

    # Get cost per token
    cost_per_token = pricing.get(model, pricing["text-embedding-3-small"])

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
