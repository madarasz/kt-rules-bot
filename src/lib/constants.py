"""Application-wide constants for LLM, RAG, and quality testing.

This is the single source of truth for all tunable parameters.
Modify values here to change behavior across the entire application.
"""

# ============================================================================
# LLM Generation Constants
# ============================================================================

# Default LLM provider for generation
DEFAULT_LLM_PROVIDER = "gpt-4.1"  # Default model for Discord bot and CLI

# LLM retry configuration
LLM_MAX_RETRIES = 2  # Number of retry attempts on ContentFilterError

# Default LLM timeouts (in seconds)
LLM_GENERATION_TIMEOUT = 60  # Standard generation timeout
LLM_EXTRACTION_TIMEOUT = 120  # PDF extraction timeout (longer)
LLM_JUDGE_TIMEOUT = 30  # Quality test judge evaluation timeout

# Default LLM generation parameters
LLM_DEFAULT_MAX_TOKENS = 2048  # Maximum response length
LLM_DEFAULT_TEMPERATURE = 0  # Lower = more deterministic (0.0-1.0)

# PDF extraction parameters
LLM_EXTRACTION_MAX_TOKENS = 16000  # Large output for full rulebook sections
LLM_EXTRACTION_TEMPERATURE = 0  # Low temperature for consistent structure

# ============================================================================
# Quality Test Constants
# ============================================================================

# Default judge model for quality tests
QUALITY_TEST_JUDGE_MODEL = "gpt-4.1-mini"

# Judge evaluation parameters
QUALITY_TEST_JUDGE_MAX_TOKENS = 150  # Short evaluation responses
QUALITY_TEST_JUDGE_TEMPERATURE = 0.0  # Deterministic for consistency

# ============================================================================
# RAG Retrieval Constants
# ============================================================================

# Default retrieval parameters (used everywhere including Discord bot)
RAG_MAX_CHUNKS = 15  # Maximum document chunks to retrieve
RAG_MIN_RELEVANCE = 0.45  # Minimum cosine similarity threshold

# Note: Increased from 5→15 chunks for better multi-hop queries
# Note: Lowered from 0.6→0.45 relevance for better recall
# See CHANGELOG-RETRIEVAL.md for tuning history

# ============================================================================
# Embedding & Chunking Constants
# ============================================================================

# Default embedding model
EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI embedding model

# Token limits for embeddings and chunking
EMBEDDING_MAX_TOKENS = 8192  # text-embedding-3-small token limit
CHUNKING_MAX_TOKENS = 8192  # Match embedding model limit

# ============================================================================
# Notes
# ============================================================================
# - LLM_GENERATION_TIMEOUT applies to total operation including retries
# - All timeouts are in seconds
# - Temperature: 0.0 = deterministic, 1.0 = creative
# - Constants are imported and used as defaults in dataclasses
