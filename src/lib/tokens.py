"""Token counting utility for text chunking.

Uses tiktoken library for accurate token counting.
Based on specs/001-we-are-building/tasks.md T029
"""

import tiktoken
from typing import Optional


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


def truncate_to_token_limit(
    text: str, max_tokens: int, model: str = "gpt-3.5-turbo"
) -> str:
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
    return encoding.decode(truncated_tokens)


def estimate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "gpt-3.5-turbo",
) -> float:
    """Estimate cost for LLM API call.

    Args:
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        model: Model name

    Returns:
        Estimated cost in USD
    """
    # Pricing per 1K tokens (as of 2024)
    pricing = {
        "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002},
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
        "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
        "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
        "gemini-pro": {"prompt": 0.00025, "completion": 0.0005},
    }

    # Default pricing if model not found
    if model not in pricing:
        pricing[model] = {"prompt": 0.002, "completion": 0.002}

    prompt_cost = (prompt_tokens / 1000) * pricing[model]["prompt"]
    completion_cost = (completion_tokens / 1000) * pricing[model]["completion"]

    return prompt_cost + completion_cost


def get_embedding_token_limit(model: str = "text-embedding-3-small") -> int:
    """Get token limit for embedding model.

    Args:
        model: Embedding model name

    Returns:
        Maximum token limit
    """
    limits = {
        "text-embedding-3-small": 8192,
        "text-embedding-3-large": 8192,
        "text-embedding-ada-002": 8191,
    }

    return limits.get(model, 8192)


def split_text_by_tokens(
    text: str,
    max_tokens: int,
    model: str = "gpt-3.5-turbo",
    overlap: int = 0,
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
