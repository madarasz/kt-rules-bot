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
LLM_GENERATION_TIMEOUT = 50  # Standard generation timeout
LLM_EXTRACTION_TIMEOUT = 120  # PDF extraction timeout (longer)
LLM_JUDGE_TIMEOUT = 30  # Quality test judge evaluation timeout

# Default LLM generation parameters
LLM_DEFAULT_MAX_TOKENS = 1024  # Maximum response length
LLM_DEFAULT_TEMPERATURE = 0.1  # Lower = more deterministic (0.0-1.0)

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

# Quality test concurrency and rate limit handling
QUALITY_TEST_MAX_CONCURRENT_LLM_REQUESTS = 2  # Max parallel LLM requests
QUALITY_TEST_MAX_RETRIES_ON_RATE_LIMIT = 2  # Retries when rate limited
QUALITY_TEST_RATE_LIMIT_INITIAL_DELAY = 10.0  # Initial retry delay in seconds (doubles each retry)

# ============================================================================
# RAG Retrieval Constants
# ============================================================================

# Default retrieval parameters (used everywhere including Discord bot)
RAG_MAX_CHUNKS = 8  # Maximum document chunks to retrieve
RAG_MIN_RELEVANCE = 0.45  # Minimum cosine similarity threshold

# Note: Increased from 5→15 chunks for better multi-hop queries
# Note: Lowered from 0.6→0.45 relevance for better recall
# See CHANGELOG-RETRIEVAL.md for tuning history

# Hybrid search parameters
RRF_K = 60  # RRF (Reciprocal Rank Fusion) constant for hybrid search
            # Lower k (e.g., 40): More weight to top-ranked results
            # Higher k (e.g., 80): More balanced fusion between vector and BM25

# BM25 keyword search parameters
BM25_K1 = 1.5  # Term frequency saturation parameter (typical range: 1.2-2.0)
               # Higher values give more weight to term frequency
BM25_B = 0.55  # Document length normalization parameter (typical range: 0.5-1.0)
               # 0 = no normalization, 1 = full normalization

# ============================================================================
# Embedding & Chunking Constants
# ============================================================================

# Default embedding model
EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI embedding model

# Note: Token limits and dimensions are now determined dynamically by the
# embedding model using get_embedding_token_limit() and get_embedding_dimensions()
# from src.lib.tokens

# ============================================================================
# LLM Prompt Constants
# ============================================================================

# System prompt file path for LLM providers (base template)
LLM_SYSTEM_PROMPT_FILE_PATH = "prompts/rule-helper-prompt.md"

# Note: Personality-specific files (acknowledgements, disclaimers) are now
# loaded via src.lib.personality based on PERSONALITY env variable

# ============================================================================
# RAG Keyword Normalization Constants
# ============================================================================

# Enable/disable automatic query keyword normalization (default: True)
# When enabled, queries are normalized to match game keywords (e.g., "accurate" → "Accurate")
# When disabled, queries are used as-is without capitalization changes
RAG_ENABLE_QUERY_NORMALIZATION = False

# Path to cached keyword library (auto-extracted from rules during ingestion)
RAG_KEYWORD_CACHE_PATH = "data/rag_keywords.json"

# ============================================================================
# Notes
# ============================================================================
# - LLM_GENERATION_TIMEOUT applies to total operation including retries
# - All timeouts are in seconds
# - Temperature: 0.0 = deterministic, 1.0 = creative
# - Constants are imported and used as defaults in dataclasses
