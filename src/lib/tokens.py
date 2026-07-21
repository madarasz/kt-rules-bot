"""Token counting utility for text chunking.

Uses tiktoken library for accurate token counting.
Based on specs/001-we-are-building/tasks.md T029
"""

import tiktoken

from src.lib.constants import EMBEDDING_MODEL
from src.lib.logging import get_logger

logger = get_logger(__name__)

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
