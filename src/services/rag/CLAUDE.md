# RAG Service

Retrieval-Augmented Generation pipeline for finding relevant rule chunks.

## Purpose

Retrieves the most relevant Kill Team rule chunks for user queries using hybrid search (semantic vector similarity + keyword matching). Provides context to the LLM for accurate rule-based responses.

## Key Components

### RAG Retriever ([retriever.py](retriever.py))
Main retrieval interface implementing the RAG pipeline:
- Public API: `retrieve(RetrieveRequest) -> RAGContext`
- Orchestrates hybrid retrieval (vector + BM25)
- Applies relevance filtering
- Caches results for performance - NOT YET IMPLEMENTED
- Dependencies: EmbeddingService, VectorDBService, HybridRetriever

**Contract**: Based on `specs/001-we-are-building/contracts/rag-pipeline.md`

### Hybrid Retriever ([hybrid_retriever.py](hybrid_retriever.py))
Combines vector and keyword search using Reciprocal Rank Fusion (RRF):
- **Vector search**: Semantic similarity via embeddings
- **BM25 search**: Keyword/lexical matching
- **RRF fusion**: Merges results with formula `score(doc) = Σ (1 / (k + rank_i))`
- Configurable fusion weights
- Best of both worlds: catches semantic matches AND exact term matches

### Vector Database ([vector_db.py](vector_db.py))
ChromaDB wrapper for vector storage:
- Collection management
- Embedding storage and retrieval
- Cosine similarity search
- Metadata filtering
- Health checks

### Embeddings ([embeddings.py](embeddings.py))
OpenAI embedding generation:
- Model: `text-embedding-3-small` (1536 dimensions)
- Batch processing for efficiency
- Caching to reduce API calls
- Error handling and retries

### BM25 Retriever ([bm25_retriever.py](bm25_retriever.py))
Keyword-based lexical search:
- Classic BM25 algorithm
- Tokenization and preprocessing (case-insensitive)
- Fast in-memory search
- Complements vector search for exact matches

### Keyword Extractor ([keyword_extractor.py](keyword_extractor.py))
Automatic query normalization for case-insensitive retrieval:
- Extracts game-specific keywords from rule headers during ingestion
- Normalizes user queries by capitalizing known keywords (e.g., "accurate" → "Accurate")
- Enables case-insensitive queries: "accurate 1", "Accurate 1", "ACCURATE 1" all work
- Keyword library stored in `data/rag_keywords.json` (1300+ keywords)
- Minimum keyword length: 4 characters (filters out short words like "FLY", "APL")

### Query Expander ([query_expander.py](query_expander.py))
Synonym-based query expansion for better BM25 keyword matching:
- Maps user-friendly terms to official Kill Team terminology
- Expands queries by appending official terms (e.g., "heal" → "heal regain wounds")
- Improves BM25 recall for informal queries without affecting vector search
- Synonym dictionary stored in `data/rag_synonyms.json`
- Supports multi-word phrases and single-word synonyms
- Case-insensitive matching with word boundary detection

### Header Index ([header_index.py](header_index.py))
Fuzzy header lookup for multi-hop retrieval:
- In-memory index mapping chunk headers to chunks
- Fuzzy matching using rapidfuzz (configurable threshold, default 85%)
- Used when hop judge explicitly names rules to retrieve them directly
- Avoids semantic search dilution from compound `missing_query` strings
- Built automatically at startup from all indexed chunks

### Document Chunker ([chunker.py](chunker.py))
Semantic chunking strategy (configurable multi-level splitting):
- **Splits at multiple header levels** from ## up to configured maximum (e.g., ## and ### for level 3)
- Configurable via `MARKDOWN_CHUNK_HEADER_LEVEL` constant (2-4)
- Creates simple header names (e.g., "Subsection A1")
- Keeps whole document only if no headers at target levels
- **No overlap** between chunks (clean semantic boundaries)
- Metadata: header name, position, token count, actual header level (2-4)

### Ingestor ([ingestor.py](ingestor.py))
Ingestion pipeline for rule documents:
- Reads markdown files from `extracted-rules/`
- Chunks documents
- Extracts keywords from headers (for query normalization)
- Generates embeddings
- Stores in vector database
- Indexes for BM25 search
- Tracks document versions
- Updates keyword library automatically

### Cache ([cache.py](cache.py))
Query result caching:
- In-memory LRU cache
- TTL-based expiration
- Cache key: query hash + parameters
- Reduces latency and API costs

### Validator ([validator.py](validator.py))
Input validation for RAG requests:
- Query length limits
- Parameter range validation
- Sanitization checks

## Retrieval Flow

```
User Query
    ↓
retriever.retrieve(RetrieveRequest)
    ↓
Check cache → [Hit: return cached results]
    ↓ [Miss]
Normalize query (keyword_extractor.py)
    ↓ (e.g., "accurate 1" → "Accurate 1")
Expand query (query_expander.py)
    ↓ (e.g., "heal" → "heal regain wounds")
Generate query embedding (embeddings.py) ← uses NORMALIZED query
    ↓
Parallel retrieval:
    ├→ Vector search (vector_db.py) ← uses NORMALIZED query
    └→ BM25 search (bm25_retriever.py) ← uses EXPANDED query
    ↓
Hybrid fusion (hybrid_retriever.py)
    ↓
Relevance filtering (min_relevance threshold)
    ↓
Return top-k chunks
    ↓
Cache results → Return RAGContext
```

## Multi-Hop Retrieval

**Purpose**: Iteratively gather additional context when initial retrieval is insufficient.

### How It Works

Instead of a single retrieval, multi-hop performs multiple passes:

1. **Initial Retrieval**: Retrieve top-k chunks for user query
2. **Gap Analysis**: LLM evaluates if context is sufficient to answer the question
3. **Focused Retrieval** (if gaps found): Generate specific sub-query for missing information
   - **Header-based lookup**: First tries fuzzy header matching (85% threshold) for explicitly named rules
   - **Semantic fallback**: Unmatched titles go through standard hybrid search
4. **Repeat**: Continue until context is sufficient OR max hops reached
5. **Final Generation**: Pass all accumulated chunks to LLM for answer

### Header-Based Hop Retrieval

When the hop judge explicitly names rules (e.g., `"COUNTERACT, Movement: Minimum move stat"`), direct header matching outperforms semantic search because compound queries dilute relevance.

**Algorithm**:
1. Parse `missing_query` by comma (hyphens preserved as part of titles)
2. Remove apostrophes (judge sometimes wraps titles in quotes)
3. For each title, fuzzy match against chunk headers at 85% threshold
4. Score = fuzzy_match_percent - 0.01 (preserves match quality signal)
5. Unmatched titles fall back to semantic retrieval
6. Merge results: header matches first (higher precision), then semantic

**Example**:
```
missing_query: "'Movement: Minimum move stat', COUNTERACT, Cover rules"
                          │
              Parse → ["Movement: Minimum move stat", "COUNTERACT", "Cover rules"]
                          │
              Header fuzzy match (85%):
              ✅ "Movement: Minimum move stat" → 92% match → score=0.91
              ✅ "COUNTERACT" → 100% match → score=0.99
              ❌ "Cover rules" → no match at 85%
                          │
              Semantic fallback for "Cover rules"
                          │
              Final: [COUNTERACT(0.99), Movement(0.91), COVER(0.87), ...]
```

**Configuration**: `HEADER_FUZZY_THRESHOLD = 0.85` in [src/lib/constants.py](../../lib/constants.py)

### Configuration

From [src/lib/constants.py](../../lib/constants.py):
```python
# Set to 0 to disable, 1+ for number of additional retrieval iterations
RAG_MAX_HOPS = 0

# Chunks to retrieve per hop (smaller than RAG_MAX_CHUNKS for efficiency)
RAG_HOP_CHUNK_LIMIT = 5

# LLM model for gap analysis (fast model recommended)
RAG_HOP_EVALUATION_MODEL = "gpt-4.1-mini"

# Timeout for gap analysis LLM call
RAG_HOP_EVALUATION_TIMEOUT = 20

# Header fuzzy matching threshold for hop retrieval (0.0-1.0)
HEADER_FUZZY_THRESHOLD = 0.85
```

### Retrieval Flow (Multi-Hop Enabled)

```
User Query
    ↓
Multi-Hop Orchestrator (multi_hop_retriever.py)
    ↓
[Hop 0] Initial retrieval → 5 chunks
    ↓
Gap Analysis LLM: "Can I answer with these chunks?"
    ↓
    ├─ YES → Return all chunks
    └─ NO  → Generate focused sub-query (e.g., "COUNTERACT, Cover rules")
        ↓
[Hop 1] Header-based + Semantic retrieval:
    ├─ Parse titles by comma
    ├─ Fuzzy header match (85%) → direct chunk lookup
    └─ Unmatched → semantic fallback
    ↓ (deduplicate by chunk_id)
Add unique chunks to accumulated context
    ↓
Gap Analysis LLM: "Can I answer now?"
    ↓
    ├─ YES → Return all chunks (10 total)
    └─ NO  → Continue if hops < MAX_HOPS
        ↓
[MAX_HOPS reached] → Return accumulated chunks anyway
    ↓
LLM generates final answer with all context
```

### Example

**Query**: "Can nemesis claw operative use light barricade as cover?"

**Hop 0** (initial):
- Retrieved: Nemesis Claw faction rules, portable barricade rules
- Gap analysis: "Missing explicit cover rules - unclear how barricades provide cover"
- Missing query: "Rules on cover and whether barricades provide cover"

**Hop 1** (focused):
- Retrieved: Core Rules - COVER section, FAQ about cover mechanics
- Gap analysis: "Now I have cover rules AND barricade rules - can answer!"

**Result**: 6 total chunks (5 from hop 0 + 1 unique from hop 1)

### Testing Multi-Hop

```bash
# Enable multi-hop for single query
python -m src.cli query "your question" --max-hops 1

# Test with RAG-only mode to see hop details
python -m src.cli query "your question" --max-hops 1 --rag-only
```

Output shows:
- Number of hops performed
- Gap analysis reasoning for each hop
- Which chunks came from which hop (`[Hop 0]`, `[Hop 1]`, etc.)

### Team Filtering (Cost Optimization)

**Purpose**: Reduce hop evaluation prompt costs by filtering teams structure to only relevant teams.

Multi-hop evaluation prompts include the full teams structure (~48 teams, ~2000 tokens). Team filtering reduces this by detecting which teams are mentioned in the query and filtering out irrelevant ones.

**How it works** ([team_filter.py](team_filter.py)):
- Extracts team names from queries using 4 matching strategies:
  - Operative names (e.g., "Burna Boy" → Kommandos)
  - Abilities/ploys (e.g., "Ere We Go" → Kommandos)
  - Team aliases (e.g., "orks" → Kommandos, "tau" → Pathfinders)
  - Fuzzy team name matching (80% threshold)
- Filters teams structure to include only detected teams
- Falls back to full structure if no teams detected

**Impact**:
```
Query: "Can kommando use stikkbombs?"
Detected: ["Kommandos"] (1 of 48 teams)
Reduction: 95% fewer tokens in hop evaluation prompt
Savings: ~$0.0003 per hop evaluation
```

**Configuration**: Team aliases in `TEAM_ALIASES` constant ([team_filter.py](team_filter.py))

### Implementation Details

**Components**:
- [multi_hop_retriever.py](multi_hop_retriever.py): Orchestrates multi-hop process
- [header_index.py](header_index.py): Fuzzy header lookup for named rules
- [team_filter.py](team_filter.py): Filters teams structure for cost optimization
- Prompt: [prompts/hop-evaluation-prompt.md](../../../prompts/hop-evaluation-prompt.md)
- Schema: `HOP_EVALUATION_SCHEMA` in [src/services/llm/base.py](../llm/base.py)

**Database tracking**:
- `hop_evaluations` table: Stores gap analysis results (can_answer, reasoning, missing_query)
- `retrieved_chunks.hop_number`: Tracks which hop retrieved each chunk (0=initial, 1+=subsequent)
- `queries.hops_used`: Total hops performed for the query

**Admin Dashboard**:
- Query browser shows hop count column (🔄 icon)
- Query detail displays all hop evaluations with reasoning
- Chunks labeled with `[Hop N]` to show retrieval source

### When to Use

✅ **Enable multi-hop when**:
- Users ask complex questions requiring multiple rule sections
- Initial retrieval often misses important context
- Queries involve interactions between multiple game mechanics

❌ **Keep disabled (default) when**:
- Most queries are straightforward
- Performance/cost is critical (adds 1-2s per hop + LLM call)
- Users provide focused questions

### Performance Impact

- **Latency**: +1-2s per hop (retrieval + gap analysis LLM call)
- **Cost**: ~$0.0001 per gap analysis (gpt-4.1-mini)
- **Quality**: Improved answer completeness for complex queries
- **Deduplication**: Prevents redundant chunks across hops

## Key Data Models

From [src/models/rag_context.py](../../models/rag_context.py):
- **RAGContext**: Container for retrieved chunks
- **DocumentChunk**: Single chunk with text, metadata, score
- **RetrieveRequest**: Retrieval parameters

## Configuration

From [src/lib/constants.py](../../lib/constants.py):
- `RAG_MAX_CHUNKS`: Maximum chunks to retrieve (default: 8)
- `RAG_MIN_RELEVANCE`: Minimum cosine similarity (default: 0.45)
- `RAG_ENABLE_QUERY_NORMALIZATION`: Enable/disable query keyword normalization (default: True)
- `RAG_KEYWORD_CACHE_PATH`: Keyword library path (default: data/rag_keywords.json)
- `RAG_ENABLE_QUERY_EXPANSION`: Enable/disable synonym-based query expansion (default: True)
- `RAG_SYNONYM_DICT_PATH`: Synonym dictionary path (default: data/rag_synonyms.json)
- `EMBEDDING_MODEL`: OpenAI embedding model (text-embedding-3-small)

Note: Token limits and embedding dimensions are now determined dynamically based on `EMBEDDING_MODEL` using `get_embedding_token_limit()` and `get_embedding_dimensions()` from [src/lib/tokens.py](../../lib/tokens.py)

## Ingestion Pipeline

### Manual Ingestion
```bash
# Incremental (default): only changed files are re-summarized and re-embedded
python -m src.cli ingest extracted-rules/

# Same, but summarize via the provider Batch API (cheaper, waits for completion)
python -m src.cli ingest extracted-rules/ --batch

# Resume a --batch run that was interrupted while waiting
python -m src.cli ingest extracted-rules/ --batch-collect

# Full rebuild: reset the collection and re-ingest everything
python -m src.cli ingest extracted-rules/ --force
```

### Ingestion Process
1. Read markdown files from source directory
2. **Classify against `data/ingestion_state.json`** ([ingestion_state.py](ingestion_state.py)):
   new / changed / unchanged / removed, by SHA-256 of file content
3. Chunk documents ([chunker.py](chunker.py))
4. Summarize chunks — live ([summarizer.py](summarizer.py)) or batched
   ([summarizer_batch.py](summarizer_batch.py))
5. Extract keywords from headers ([keyword_extractor.py](keyword_extractor.py))
6. Generate embeddings ([embeddings.py](embeddings.py))
7. Delete the document's previous chunks, then upsert ([vector_db.py](vector_db.py))
8. Save keyword library to `data/rag_keywords.json`
9. Record the file's hash in the state file (after each file, so a crash resumes)

BM25 is indexed at query time from ChromaDB ([retriever.py](retriever.py)), not during
ingestion.

### Incremental Ingestion

**Identity is deterministic.** `document_id = uuid5(INGEST_ID_NAMESPACE, relative_path)`
([rule_document.py](../../models/rule_document.py)) and
`chunk_id = uuid5(document_id, "position:header")` (`RAGIngestor.assign_chunk_ids`).
This is what makes re-ingestion *replace* a file's chunks instead of appending a second
copy — with the previous random `uuid4()` ids, the delete-before-upsert in
[ingestor.py](ingestor.py) always matched zero rows.

> ⚠️ **Never change `INGEST_ID_NAMESPACE`** ([constants.py](../../lib/constants.py)).
> Every chunk already stored would be orphaned and a full rebuild forced.

**State file** (`data/ingestion_state.json`, gitignored):

```json
{
  "version": 1,
  "fingerprint": {"chunk_level": 2, "embedding_model": "...", "summary_model": "...",
                  "summary_prompt_sha256": "...", "summary_enabled": true},
  "files": {"team/kommandos.md": {"hash": "...", "document_id": "...", "chunks": 22,
                                  "ingested_at": "..."}},
  "batch": null
}
```

**Automatic full rebuild** happens when the fingerprint no longer matches — chunk level,
embedding model, summary model, or the summary prompt changed — because the stored hashes
then describe chunks these settings would no longer produce. Also on `--force`, or when
there is no state file at all. A rebuild resets the collection *and* clears the keyword
library (which is otherwise append-only, so edited/deleted headers would linger).

**Deleted files** are detected as state entries with no file on disk; their chunks are
removed from ChromaDB and the entry dropped.

### Batch Summarization

Summarization is the only LLM cost in ingestion and nothing downstream needs it until the
upsert (embeddings come from `chunk.text` alone), so it batches well.

- One batch request per markdown file, matching the live path's granularity.
- The prompt comes from `ChunkSummarizer.build_request`, shared with the live path, so
  batch and live summaries are interchangeable.
- Backend routing reuses `resolve_backend()` from
  [src/services/llm/batch/](../llm/batch/); a summary model with no batch backend
  silently falls back to live.
- Failures are classified by `classify_batch_error`: transient → re-requested in a fresh
  batch (bounded by `INGEST_MAX_BATCH_ITEM_RETRIES`), permanent → one live call for that
  file, and if that fails too, the file is ingested with empty summaries plus a warning.
- Discount is per-provider (`BATCH_DISCOUNT` in [pricing.py](../../lib/pricing.py)). The
  default `SUMMARY_LLM_MODEL = "grok-4.3"` gets xAI's **20%**, not the 50% most providers
  offer.
- Interrupting the wait is safe: the batch id is persisted before polling starts, so
  `--batch-collect` resumes instead of paying for a second submission.

## Common Tasks

### Tuning Retrieval Quality

**Adjust relevance threshold**:
Edit [src/lib/constants.py](../../lib/constants.py):
```python
RAG_MIN_RELEVANCE = 0.4  # Higher = stricter filtering
```

**Change chunk count**:
```python
RAG_MAX_CHUNKS = 10  # More chunks = more context (but slower)
```

**Modify RRF fusion** ([hybrid_retriever.py](hybrid_retriever.py)):
```python
# Adjust k constant (lower = more weight to top results)
HybridRetriever(k=40)  # Default is 60
```

**Test retrieval quality**:
```bash
# Run RAG tests to measure precision/recall
python -m src.cli rag-test -n 10
```

### Modifying Chunking Strategy

Current strategy: **Multi-level header splitting**
- Splits at all header levels from ## up to configured maximum
- Configured via `MARKDOWN_CHUNK_HEADER_LEVEL` in [src/lib/constants.py](../../lib/constants.py)
- Level 2: chunks at ## only
- Level 3: chunks at ## and ### 
- Level 4: chunks at ##, ###, and ####
- Creates simple header names (no hierarchical paths)
- Keeps whole document only if no headers at target levels
- No overlap (clean semantic boundaries)

**To adjust chunking behavior**:
- Change `MARKDOWN_CHUNK_HEADER_LEVEL` in [src/lib/constants.py](../../lib/constants.py)
- Valid values: 2, 3, or 4
- Higher values create smaller, more granular chunks
- Lower values create larger, more contextual chunks

**To change chunking logic**: Edit [chunker.py](chunker.py) `chunk()` method

**After changes**, re-ingest:
```bash
python -m src.cli ingest extracted-rules/ --force
```

### Adding New Embedding Provider

1. Create new embedding service class implementing the interface
2. Update [embeddings.py](embeddings.py) to use new provider
3. Update `EMBEDDING_MODEL` in constants
4. Re-ingest all documents

### Query Normalization

The system can automatically normalize queries to improve retrieval consistency:

**Enable/Disable**:
```python
# In src/lib/constants.py
RAG_ENABLE_QUERY_NORMALIZATION = True  # Enable (default)
RAG_ENABLE_QUERY_NORMALIZATION = False # Disable
```

**How it works** (when enabled):
- During ingestion, game-specific keywords are extracted from rule headers
- At query time, keywords are capitalized to match embeddings (e.g., "accurate" → "Accurate")
- This makes queries case-insensitive: all of these work identically:
  - `"accurate 1"` → normalized to `"Accurate 1"`
  - `"Accurate 1"` → already correct
  - `"ACCURATE 1"` → normalized to `"Accurate 1"`

**Keyword extraction rules**:
- Extracts from `## Header` patterns in markdown
- Minimum length: 4 characters (filters out "FLY", "APL", etc.)
- Patterns: "Accurate x", "Lethal 5+", "TEAM - ABILITY", etc.
- Keyword extraction always happens during ingestion (regardless of toggle)

**View keyword library**:
```bash
cat data/rag_keywords.json
```

**Rebuild keywords** (run after ingestion):
```bash
python -m src.cli ingest extracted-rules/
```

**Testing normalization impact**:
```bash
# Test with normalization enabled (default)
python -m src.cli query "accurate 1"

# Disable normalization in constants.py, then test
python -m src.cli query "accurate 1"  # Will use lowercase as-is
```

### Query Expansion with Synonyms

The system can expand user queries with official game terminology to improve BM25 keyword matching:

**Enable/Disable**:
```python
# In src/lib/constants.py
RAG_ENABLE_QUERY_EXPANSION = True  # Enable (default)
RAG_ENABLE_QUERY_EXPANSION = False # Disable
```

**How it works** (when enabled):
- Maps user-friendly terms to official Kill Team terminology
- Expands queries by appending official terms (preserves original query)
- Only affects BM25 keyword search (vector search handles synonyms semantically)
- Examples:
  - `"Can I heal my operative?"` → `"Can I heal my operative? regain wounds"`
  - `"Does the model die?"` → `"Does the model die? incapacitated"`
  - `"melee range"` → `"melee range control range"`

**Synonym dictionary format** (`data/rag_synonyms.json`):
```json
{
  "regain wounds": ["heal", "healing", "restore health", "recover hp"],
  "incapacitated": ["died", "killed", "destroyed", "eliminated"],
  "control range": ["melee range", "base contact", "engaged"]
}
```

**View synonym dictionary**:
```bash
cat data/rag_synonyms.json
```

**Add custom synonyms**:
Edit `data/rag_synonyms.json` and add your mappings. Format:
```json
{
  "official_term": ["user_synonym1", "user_synonym2", ...]
}
```

**Testing expansion impact**:
```bash
# Test with expansion enabled (default)
python -m src.cli query "Can I heal my operative?"

# Check logs for query_expanded event (enable DEBUG logging)
# Look for: query_expanded: original="...", expanded="...", added_terms=[...]
```

**When to use**:
- ✅ User queries with informal terminology (heal, kill, melee range)
- ✅ Multi-language communities using translated terms
- ✅ New players unfamiliar with official terminology
- ❌ Queries already using official terms (expansion has no effect)

**Performance**:
- No ingestion required (query-time expansion)
- Minimal latency impact (~1ms per query)
- Improves BM25 recall without affecting vector search quality

### Debugging Retrieval Issues

**Test specific query**:
```bash
python -m src.cli query "What happens when a banner carrier dies?" --max-chunks 10
```

**Check query normalization** (enable DEBUG logging):
```bash
# Look for "query_normalized" log entries
python -m src.cli query "accurate 1" 2>&1 | grep query_normalized
```

**Enable debug logging** in [src/lib/constants.py](../../lib/constants.py):
```python
LOG_LEVEL = "DEBUG"
```

**Check retrieved chunks**: Look for:
- Low similarity scores (< 0.3) indicate weak matches
- Wrong chunks suggest embedding quality issues
- Missing chunks indicate indexing problems

## Hybrid Retrieval Deep Dive

### Why Hybrid?

- **Vector search**: Catches semantic/conceptual matches (e.g., "operative dies" matches "incapacitated")
- **BM25 search**: Catches exact term matches (e.g., "Place Marker" rule)
- **Combined**: Best recall and precision

### RRF Fusion Formula

For each document:
```
RRF_score = Σ (1 / (k + rank_in_list_i))
```

Where:
- `k = 60` (constant from research)
- `rank_in_list_i` = position in vector or BM25 results (1-indexed)
- Sum over all lists containing the document

Documents appearing high in both lists get highest scores.

## Performance Optimization

### Caching Strategy
- Cache hit rate ~70% for common queries
- TTL: 1 hour (configurable in [cache.py](cache.py))
- Cache size: 1000 entries (LRU eviction)

### Embedding Optimization
- Batch embed during ingestion
- Cache query embeddings
- Use smaller model (text-embedding-3-small)

### Database Optimization
- ChromaDB runs in-memory for speed
- Periodic persistence to disk
- Index warming on startup

## Testing RAG Quality

### RAG Tests - NOT YET IMPLEMENTED
```bash
# Test retrieval quality with YAML test cases
python -m src.cli rag-test
python -m src.cli rag-test -t banner-carrier-placement -n 10
```

### Quality Tests
```bash
# End-to-end RAG + LLM quality
python -m src.cli quality-test --all-models
```

### Manual Testing
```bash
# Interactive query testing
python -m src.cli query "your test query here"
```

## Error Handling

- **Vector DB unavailable**: Fail fast with clear error
- **Embedding API failure**: Retry with exponential backoff
- **No relevant chunks found**: Return empty context (LLM handles gracefully)
- **Invalid query**: Validate and return user-friendly error

## Dependencies

- `chromadb` - Vector database
- `openai` - Embedding generation API
- `rank-bm25` - BM25 algorithm implementation
- `tiktoken` - Token counting for chunking

## Related Documentation

- [src/services/CLAUDE.md](../CLAUDE.md) - Service architecture overview
- [src/services/llm/CLAUDE.md](../llm/CLAUDE.md) - LLM integration details
- [src/services/discord/CLAUDE.md](../discord/CLAUDE.md) - Discord bot integration
- [tests/rag/CLAUDE.md](../../../tests/rag/CLAUDE.md) - RAG test documentation
