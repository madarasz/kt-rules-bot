"""Application-wide constants for LLM, RAG, and quality testing.

This is the single source of truth for all tunable parameters.
Modify values here to change behavior across the entire application.
"""
from typing import Literal, get_args

# ============================================================================
# LLM Generation Constants
# ============================================================================

# All available LLM providers (complete list)
LLM_PROVIDERS_LITERAL = Literal[
    "claude-4.5-sonnet",
    "claude-4.1-opus",
    "claude-4.5-haiku",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gpt-5",
    "gpt-5-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    # "o3", --- does not support JSON output
    "o3-mini",
    "o4-mini",
    "grok-4-fast-reasoning",
    "grok-4-0709",
    "grok-3",
    "grok-3-mini",
    "deepseek-chat",
    "deepseek-reasoner",
    "dial-gpt-4o",
    "dial-gpt-4.1",
    "dial-gpt-5",
    "dial-gpt-5-chat",
    "dial-gpt-5-mini",
    "dial-gpt-o3",
    "dial-sonet-4.5",
    "dial-sonet-4.5-thinking",
    "dial-opus-4.1",
    "dial-opus-4.1-thinking",
    "dial-amazon-nova-pro",
    "dial-amazon-titan",
    "dial-gemini-2.5-pro",
    "dial-gemini-2.5-flash",
]

ALL_LLM_PROVIDERS = list(get_args(LLM_PROVIDERS_LITERAL))

# PDF extraction providers (models that support PDF processing)
PDF_EXTRACTION_PROVIDERS = [
    "gemini-2.5-pro", 
    "gemini-2.5-flash",
]

# Quality test providers (curated list for --all-models testing)
QUALITY_TEST_PROVIDERS = [
    "gpt-4.1",
    "gpt-4o",
    "gpt-4.1-mini",
    "claude-4.5-sonnet",
    "claude-4.5-haiku",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "deepseek-chat",
    "grok-4-fast-reasoning",
    "grok-3",
    "grok-3-mini",
    # "deepseek-reasoner"
    # "dial-gpt-4.1",  # denied WHY??
    # "dial-gpt-5",    # denied
    # "dial-gpt-5-chat",  # denied
    # "dial-gpt-5-mini",
    # "dial-gpt-o3",   # denied
    # "dial-sonet-4.5",  # denied
    # "dial-sonet-4.5-thinking",  # denied
    # "dial-opus-4.1",  # denied
    # "dial-opus-4.1-thinking",  # denied
    # "dial-amazon-nova-pro",  # denied
    # "dial-amazon-titan",  # denied
    # "dial-gemini-2.5-pro",
    # "dial-gemini-2.5-flash"
]

# Default LLM provider for generation
DEFAULT_LLM_PROVIDER = "claude-4.5-sonnet"  # Default model for Discord bot and CLI

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
QUALITY_TEST_JUDGE_MODEL = "gpt-4o"  # Ragas judge model for generation tests

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
RAG_MAX_CHUNKS = 7  # Maximum document chunks to retrieve
RAG_MIN_RELEVANCE = 0.45  # Minimum cosine similarity threshold

# Note: Increased from 5→15 chunks for better multi-hop queries
# Note: Lowered from 0.6→0.45 relevance for better recall
# See CHANGELOG-RETRIEVAL.md for tuning history

# Hybrid search parameters
BM25_WEIGHT = 0.5  # Weight for BM25 keyword search in hybrid fusion (0.0-1.0)
                   # Higher values (e.g., 0.7): Prefer exact keyword matching
                   # Lower values (e.g., 0.3): Prefer semantic similarity
                   # Vector weight is automatically 1.0 - BM25_WEIGHT

# BM25 keyword search parameters
BM25_K1 = 1.6  # Term frequency saturation parameter (typical range: 1.2-2.0)
               # Higher values give more weight to term frequency
BM25_B = 0.8  # Document length normalization parameter (typical range: 0.5-1.0)
               # 0 = no normalization, 1 = full normalization

RRF_K = 60  # RRF (Reciprocal Rank Fusion) constant for hybrid search
            # Lower k (e.g., 40): More weight to top-ranked results
            # Higher k (e.g., 80): More balanced fusion between vector and BM25
            # DOES NOT AFFECT ANYTHING because we  RRK scores are normalized

# ============================================================================
# Embedding & Chunking Constants
# ============================================================================

# Default embedding model
EMBEDDING_MODEL = "text-embedding-ada-002"  # OpenAI embedding model
                                            # text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002

# Markdown chunking configuration
MARKDOWN_CHUNK_HEADER_LEVEL = 2  # Max header level to chunk at: chunks at ## up to this level

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
RAG_ENABLE_QUERY_NORMALIZATION = True

# Path to cached keyword library (auto-extracted from rules during ingestion)
RAG_KEYWORD_CACHE_PATH = "data/rag_keywords.json"

# ============================================================================
# RAG Query Expansion Constants
# ============================================================================

# Enable/disable query expansion with synonym dictionary (default: True)
# When enabled, user-friendly terms are expanded with official game terminology
# Example: "heal" → "heal regain wounds" (improves BM25 keyword matching)
RAG_ENABLE_QUERY_EXPANSION = True

# Path to synonym dictionary mapping user terms to official terminology
RAG_SYNONYM_DICT_PATH = "data/rag_synonyms.json"

# ============================================================================
# Multi-Hop RAG Constants
# ============================================================================

# Maximum number of retrieval iterations after initial query (default: 0 = disabled)
# 0 = single-hop only (multi-hop disabled)
# 1 = initial + 1 hop, 2 = initial + 2 hops, etc.
RAG_MAX_HOPS = 1

# Maximum chunks to retrieve per hop
# Total chunks accumulated = (MAX_HOPS + 1) × HOP_CHUNK_LIMIT
RAG_HOP_CHUNK_LIMIT = 5

# LLM model for hop context evaluation (default: gpt-4.1-mini for speed)
RAG_HOP_EVALUATION_MODEL = "gpt-4.1-mini"

# Hop evaluation timeout in seconds
RAG_HOP_EVALUATION_TIMEOUT = 20

# Hop evaluation prompt file path
RAG_HOP_EVALUATION_PROMPT_PATH = "prompts/hop-evaluation-prompt.md"

# Max length of chunk text for hop evaluation formatting
MAX_CHUNK_LENGTH_FOR_EVALUATION = 300

# ============================================================================
# Notes
# ============================================================================
# - LLM_GENERATION_TIMEOUT applies to total operation including retries
# - All timeouts are in seconds
# - Temperature: 0.0 = deterministic, 1.0 = creative
# - Constants are imported and used as defaults in dataclasses
