"""Application-wide constants for LLM, RAG, and quality testing.

This is the single source of truth for all tunable parameters.
Modify values here to change behavior across the entire application.
"""

from typing import Literal, get_args
from uuid import UUID

# ============================================================================
# LLM Generation Constants
# ============================================================================

# All available LLM providers (complete list)
LLM_PROVIDERS_LITERAL = Literal[
    "claude-4.8-opus",
    "claude-4.7-opus",
    "claude-4.6-opus",
    "claude-4.6-sonnet",
    "claude-4.5-sonnet",
    "claude-4.5-opus",
    "claude-4.1-opus",
    "claude-4.5-haiku",
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gpt-5.6-luna",
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.3-chat-latest",
    "gpt-5.2",
    "gpt-5.2-chat-latest",
    "gpt-5.1",
    "gpt-5.1-chat-latest",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    # "o3", --- does not support JSON output
    "o3-mini",
    "o4-mini",
    "grok-4.3",
    "grok-4.20-0309-reasoning",
    "grok-4.20-0309-non-reasoning",
    "grok-build-0.1",
    "grok-3",
    "grok-3-mini",
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "kimi-k2.7-code",
    "kimi-k2.6",
    "kimi-k2.5",
    "moonshot-v1-8k",
    "mistral-medium-3-5",
    "mistral-small-4",
    "mistral-large-3",
    "ministral-3-14-b",
    "ministral-3-8-b",
    # Qwen models (Alibaba Cloud)
    "qwen3.7-max",
    "qwen3.7-plus",
    "qwen3.6-flash",
    "qwen-turbo",
    "qwen3-coder-flash",
    "qwen3-coder-plus",
    # GLM models (Z.AI)
    "glm-5",
    "glm-4.7",
    # MiniMax models
    "MiniMax-M2.5",
]

ALL_LLM_PROVIDERS = list(get_args(LLM_PROVIDERS_LITERAL))

PDF_EXTRACTION_PROVIDERS = [
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-2.5-pro",  # Recommended: Most reliable
    "gemini-3.5-flash",
    "gemini-2.5-flash",  # Recommended: Fast and reliable
    "claude-4.5-sonnet",
    "claude-4.1-opus",
    "grok-4.3"
]

# Quality test providers (curated list for --all-models testing)
QUALITY_TEST_PROVIDERS = [
    #"gpt-5.6-luna",
    #"gpt-5.4",
    #"gpt-5.4-mini",
    #"gpt-5.4-nano",
    "gpt-5.3-chat-latest",
    #"gpt-5.2",
    "gpt-5.2-chat-latest",
    #"gpt-5.1-chat-latest",
    #"gpt-4.1",
    #"gpt-4o",
    # "gpt-4.1-mini",
    #"claude-4.6-sonnet",
    #"claude-4.5-sonnet",
    #"claude-4.6-opus",
    #"claude-4.5-opus",
    #"gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    #"gemini-3.1-pro-preview",
    #"gemini-3-flash-preview",
    #"gemini-2.5-flash",
    #"kimi-k2.6",
    #"kimi-k2.5",
    #"kimi-k2-0905-preview",
    #"kimi-k2-turbo-preview",
    #"gemini-2.5-pro",
    #"deepseek-chat",
    "grok-4.3",
    "grok-4.20-0309-reasoning",
    #"grok-build-0.1",
    #"mistral-large",
    "mistral-medium-3-5",
    # "grok-3",
    # "grok-3-mini",
    "deepseek-v4-flash",
    "qwen3.6-flash"
]

# Default LLM provider for generation
DEFAULT_LLM_PROVIDER = "grok-4.3"  # Default model for Discord bot and CLI

# LLM retry configuration
LLM_MAX_RETRIES = 2  # Number of retry attempts on ContentFilterError

# Default LLM timeouts (in seconds)
LLM_GENERATION_TIMEOUT = 120  # Standard generation timeout
LLM_EXTRACTION_TIMEOUT = 300  # PDF extraction timeout (5 minutes for large PDFs)

# Default LLM generation parameters
LLM_DEFAULT_MAX_TOKENS = 2048  # Maximum response length
LLM_DEFAULT_TEMPERATURE = 0.1  # Lower = more deterministic (0.0-1.0)

# Reasoning/thinking tokens are billed against the output budget, so reasoning
# models need a larger max_tokens or the answer is truncated. Matches the
# multiplier already applied in the ChatGPT and Gemini adapters.
LLM_REASONING_TOKEN_MULTIPLIER = 3


# PDF extraction parameters
LLM_EXTRACTION_MAX_TOKENS = 16000  # Large output for full rulebook sections
LLM_EXTRACTION_TEMPERATURE = 0  # Low temperature for consistent structure

# ============================================================================
# Quality Test Constants
# ============================================================================

# Default judge model for quality tests (custom unified LLM judge)
QUALITY_TEST_JUDGE_MODEL = "grok-4.3"

# Quality Testing - Metric Weights (Phase 1.1)
# These weights are used to calculate the aggregate score from individual metrics
# Higher weight = more important for overall score
QUALITY_METRIC_WEIGHTS = {
    "answer_correctness": 0.50,       # Must get answer right (50%)
    "quote_recall": 0.20,             # Must cite all key rules (20%)
    "explanation_faithfulness": 0.15, # Explanation must be grounded (15%)
    "quote_faithfulness": 0.10,       # No hallucinated citations (10%)
    "quote_precision": 0.05,          # Nice to have - prefer concise (5%)
}

# Quality Testing - Ground Truth Priority Weights (Phase 1.2)
# These weights are used to prioritize critical rules over supporting context
# in quote recall calculations
GROUND_TRUTH_PRIORITY_WEIGHTS = {
    "critical": 10,    # Critical rules (exceptions, core mechanics)
    "important": 5,    # Important details
    "supporting": 3,   # Supporting context (baseline rules, general info)
}
DEFAULT_GROUND_TRUTH_PRIORITY = "critical"

# Custom Judge Configuration (Phase 1.3)
# Unified LLM judge for quality testing (single call: explanation faithfulness,
# answer correctness, and feedback)
CUSTOM_JUDGE_PROMPT_PATH = "prompts/quality-test-custom-judge.md"  # Prompt template path

# Quote Validation Configuration
# Uses fuzzy string matching (rapidfuzz) to detect quote inaccuracies
QUOTE_SIMILARITY_THRESHOLD = 0.98
QUOTE_MERGE_SEPARATOR = "[...]"  # Separator for merged quotes from the same chunk

# Quality test concurrency and rate limit handling
QUALITY_TEST_MAX_CONCURRENT_LLM_REQUESTS = 2  # Max parallel LLM requests
QUALITY_TEST_MAX_RETRIES_ON_RATE_LIMIT = 2  # Retries when rate limited
QUALITY_TEST_RATE_LIMIT_INITIAL_DELAY = 10.0  # Initial retry delay in seconds (doubles each retry)

# Batch-API error tolerance: how many times a single failed batch item (generation
# or judge) may be re-requested before it is treated as a permanent failure. Each
# re-request is a fresh small batch picked up on the next `batch-collect` pass, so
# the effective backoff is the (hours-long) gap between manual collects.
QUALITY_TEST_MAX_BATCH_ITEM_RETRIES = 2

# ============================================================================
# RAG Retrieval Constants
# ============================================================================

# Default retrieval parameters (used everywhere including Discord bot)
RAG_MAX_CHUNKS = 15  # Maximum document chunks to retrieve
RAG_MIN_RELEVANCE = 0.45  # Minimum cosine similarity threshold

# Maximum chunks in final context after reranking (especially for multi-hop)
# This limits the total number of chunks sent to the LLM after all hops are complete
# Default: 20 chunks (tune based on max_ground_truth_rank from RAG tests)
MAXIMUM_FINAL_CHUNK_COUNT = 20

# Note: Increased from 5→15 chunks for better multi-hop queries
# Note: Lowered from 0.6→0.45 relevance for better recall
# See CHANGELOG-RETRIEVAL.md for tuning history

# Hybrid search parameters
# Weight for BM25 keyword search in hybrid fusion (0.0-1.0)
# Higher values (e.g., 0.7): Prefer exact keyword matching
# Lower values (e.g., 0.3): Prefer semantic similarity
# Vector weight is automatically 1.0 - BM25_WEIGHT
BM25_WEIGHT = 0.5

# BM25 keyword search parameters
# Term frequency saturation parameter (typical range: 1.2-2.0)
# Higher values give more weight to term frequency
BM25_K1 = 1.6

# Document length normalization parameter (typical range: 0.5-1.0)
# 0 = no normalization, 1 = full normalization
BM25_B = 0.8

# RRF (Reciprocal Rank Fusion) constant for hybrid search
# Lower k (e.g., 40): More weight to top-ranked results
# Higher k (e.g., 80): More balanced fusion between vector and BM25
# DOES NOT AFFECT ANYTHING because we RRK scores are normalized
RRF_K = 60

# ============================================================================
# Embedding & Chunking Constants
# ============================================================================

# Default embedding model
# Options: text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
EMBEDDING_MODEL = "text-embedding-ada-002"

# Markdown chunking configuration
MARKDOWN_CHUNK_HEADER_LEVEL = 2  # Max header level to chunk at: chunks at ## up to this level

# Note: Token limits and dimensions are now determined dynamically by the
# embedding model using get_embedding_token_limit() and get_embedding_dimensions()
# from src.lib.tokens

# ============================================================================
# LLM Prompt Constants
# ============================================================================

# Prompt template system (modular approach with provider-specific overrides)
PROMPT_TEMPLATE_PATH = "prompts/base-prompt-template.md"
PROMPT_OVERRIDES_DIR = "prompts/overrides"

# Note: Personality-specific files (acknowledgements, disclaimers) are now
# loaded via src.lib.personality based on PERSONALITY env variable

# ============================================================================
# Chunk Summary Generation Constants
# ============================================================================

# Enable/disable LLM-generated chunk summaries during ingestion (default: True)
SUMMARY_ENABLED = True

# LLM model to use for summary generation (use cheap/fast model)
SUMMARY_LLM_MODEL = "grok-4.3"

# Path to summary generation prompt template
CHUNK_SUMMARY_PROMPT_PATH = "prompts/chunk-summary-prompt.md"

# ============================================================================
# Ingestion Constants
# ============================================================================

# Namespace for deterministic (uuid5) document and chunk ids. Ingesting the same
# file twice must produce the same ids, otherwise re-ingestion appends duplicate
# chunks instead of replacing them. NEVER change this value: doing so orphans
# every chunk already in the vector store and forces a full rebuild.
INGEST_ID_NAMESPACE = UUID("6f0d4a1e-6c3b-5f7a-9c2d-1b8e4a7f0c93")

# Per-file hashes + config fingerprint, so a re-run only processes changed files
INGEST_STATE_PATH = "data/ingestion_state.json"

# Batch summarization: how often to check a submitted batch, and how long to wait
# before giving up. Providers promise <=24h turnaround; in practice ingestion
# batches complete in minutes.
INGEST_BATCH_POLL_INTERVAL = 30  # seconds between poll() calls
INGEST_BATCH_MAX_WAIT = 24 * 60 * 60  # seconds before the poll loop aborts

# How many times a single transiently-failed batch item is re-requested before
# falling back to a live summarization call for that file.
INGEST_MAX_BATCH_ITEM_RETRIES = 2

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

# Header fuzzy matching threshold for hop retrieval (0.0-1.0)
# When hop judge names specific rules, we first try direct header matching
# at this threshold before falling back to semantic search
HEADER_FUZZY_THRESHOLD = 0.85

# Maximum number of retrieval iterations after initial query (default: 0 = disabled)
# 0 = single-hop only (multi-hop disabled)
# 1 = initial + 1 hop, 2 = initial + 2 hops, etc.
RAG_MAX_HOPS = 1

# Maximum chunks to retrieve per hop
# Total chunks accumulated = (MAX_HOPS + 1) × HOP_CHUNK_LIMIT
RAG_HOP_CHUNK_LIMIT = 5

# LLM model for hop context evaluation
RAG_HOP_EVALUATION_MODEL = "ministral-3-14-b"

# Hop evaluation timeout in seconds
RAG_HOP_EVALUATION_TIMEOUT = 30

# Hop evaluation retry delay on rate limit (seconds)
RAG_HOP_RATE_LIMIT_DELAY = 5.0

# Hop evaluation prompt file path
#RAG_HOP_EVALUATION_PROMPT_PATH = "prompts/hop-evaluation-prompt.md"
RAG_HOP_EVALUATION_PROMPT_PATH = "prompts/hop-evaluation-prompt-with-rule-reference.md"

# Rules structure file paths (for hop evaluation context)
RULES_STRUCTURE_PATH = "extracted-rules/rules-structure.yml"
TEAMS_STRUCTURE_PATH = "extracted-rules/teams-structure.yml"

# Max length of chunk text for hop evaluation formatting
MAX_CHUNK_LENGTH_FOR_EVALUATION = 500

# Max tokens for hop evaluation LLM response
RAG_HOP_EVALUATION_MAX_TOKENS = 300

# ============================================================================
# Maintenance Mode Constants
# ============================================================================

# Path to maintenance mode flag file
# Create this file to enable maintenance mode: touch data/maintenance.flag
# Delete this file to disable maintenance mode: rm data/maintenance.flag
MAINTENANCE_FLAG_PATH = "data/maintenance.flag"

# Message shown to users during maintenance
MAINTENANCE_MESSAGE = "🚧 The Oracle enters a mandatory recalibration cycle. Your primitive queries must wait while systems older than your species realign. Return when the stars permit. 🚧"

# ============================================================================
# Notes
# ============================================================================
# - LLM_GENERATION_TIMEOUT applies to total operation including retries
# - All timeouts are in seconds
# - Temperature: 0.0 = deterministic, 1.0 = creative
# - Constants are imported and used as defaults in dataclasses
