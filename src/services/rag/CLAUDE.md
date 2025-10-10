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
- Tokenization and preprocessing
- Fast in-memory search
- Complements vector search for exact matches

### Document Chunker ([chunker.py](chunker.py))
Semantic chunking strategy (lazy splitting):
- **ALWAYS splits at ## headers** if document has structured sections (better semantic granularity)
- Keeps whole document only if no ## headers AND ≤ 8192 tokens
- Falls back to ### headers if single section exceeds limit
- **No overlap** between chunks (clean semantic boundaries)
- Metadata: header, position, token count

### Ingestor ([ingestor.py](ingestor.py))
Ingestion pipeline for rule documents:
- Reads markdown files from `extracted-rules/`
- Chunks documents
- Generates embeddings
- Stores in vector database
- Indexes for BM25 search
- Tracks document versions

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
Generate query embedding (embeddings.py)
    ↓
Parallel retrieval:
    ├→ Vector search (vector_db.py)
    └→ BM25 search (bm25_retriever.py)
    ↓
Hybrid fusion (hybrid_retriever.py)
    ↓
Relevance filtering (min_relevance threshold)
    ↓
Return top-k chunks
    ↓
Cache results → Return RAGContext
```

## Key Data Models

From [src/models/rag_context.py](../../models/rag_context.py):
- **RAGContext**: Container for retrieved chunks
- **DocumentChunk**: Single chunk with text, metadata, score
- **RetrieveRequest**: Retrieval parameters

## Configuration

From [src/lib/constants.py](../../lib/constants.py):
- `RAG_MAX_CHUNKS`: Maximum chunks to retrieve (default: 15)
- `RAG_MIN_RELEVANCE`: Minimum cosine similarity (default: 0.45)
- `EMBEDDING_MODEL`: OpenAI embedding model (text-embedding-3-small)
- `CHUNKING_MAX_TOKENS`: Maximum tokens per chunk (8192, matches embedding limit)

## Ingestion Pipeline

### Manual Ingestion
```bash
# Ingest all markdown files from directory
python -m src.cli ingest extracted-rules/

# Force re-ingestion
python -m src.cli ingest extracted-rules/ --force
```

### Ingestion Process
1. Read markdown files from source directory
2. Chunk documents ([chunker.py](chunker.py))
3. Generate embeddings ([embeddings.py](embeddings.py))
4. Store in ChromaDB ([vector_db.py](vector_db.py))
5. Index for BM25 ([bm25_retriever.py](bm25_retriever.py))
6. Update metadata store

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

Current strategy: **Semantic splitting at ## headers** (lazy splitting)
- Splits at ## headers if document has structure
- Keeps whole document only if no headers AND ≤ 8192 tokens
- No overlap (clean semantic boundaries)

**To adjust max tokens** in [src/lib/constants.py](../../lib/constants.py):
```python
CHUNKING_MAX_TOKENS = 8192  # Match embedding model limit
```

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

### Debugging Retrieval Issues

**Test specific query**:
```bash
python -m src.cli query "What happens when a banner carrier dies?" --max-chunks 10
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
