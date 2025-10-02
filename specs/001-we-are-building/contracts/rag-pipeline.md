# RAG Pipeline Contract

**Version**: 1.0.0
**Last Updated**: 2025-10-02

## Purpose

Defines the contract between RAG retrieval engine and its consumers (Discord bot, CLI tools). Ensures consistent behavior across LLM provider changes.

## Interface Definition

### `RAGPipeline.retrieve(query: str, context_key: str) -> RAGContext`

**Description**: Retrieves relevant rule documents for a user query

**Input**:
```python
@dataclass
class RetrieveRequest:
    query: str  # User question (sanitized)
    context_key: str  # "{channel_id}:{user_id}" for conversation tracking
    max_chunks: int = 5  # Maximum document chunks to retrieve
    min_relevance: float = 0.6  # Minimum cosine similarity threshold
```

**Output**:
```python
@dataclass
class RAGContext:
    context_id: UUID
    query_id: UUID
    document_chunks: List[DocumentChunk]  # Ordered by relevance DESC
    relevance_scores: List[float]  # Corresponding scores
    total_chunks: int
    avg_relevance: float
    meets_threshold: bool  # True if avg_relevance ≥ min_relevance

@dataclass
class DocumentChunk:
    chunk_id: UUID
    document_id: UUID
    text: str  # ~500 token segment
    metadata: Dict[str, Any]  # {source, doc_type, last_update_date, section}
    relevance_score: float  # 0-1
    position_in_doc: int  # For citation
```

**Contracts**:

1. **Relevance Ordering**:
   - `document_chunks` MUST be sorted by `relevance_score` in descending order
   - `relevance_scores` MUST match order of `document_chunks`

2. **Threshold Compliance**:
   - If `avg_relevance < min_relevance`, return empty `document_chunks`
   - Set `meets_threshold = False`

3. **Chunk Limits**:
   - Return at most `max_chunks` documents
   - If fewer than `max_chunks` meet threshold, return only those that qualify

4. **Metadata Completeness**:
   - Every `DocumentChunk.metadata` MUST include:
     - `source`: str (e.g., "Core Rules v3.1")
     - `doc_type`: enum ("core-rules" | "faq" | "team-rules" | "ops" | "killzone")
     - `last_update_date`: ISO date string
     - `section`: str (optional, for citation)

5. **Idempotency**:
   - Same `query` + `context_key` within 5 minutes SHOULD return cached result
   - Cache invalidated on document re-ingestion

6. **Performance**:
   - MUST complete within 5 seconds (p95)
   - Timeout after 10 seconds, return error

**Error Conditions**:

| Error Type | Condition | Response |
|------------|-----------|----------|
| `InvalidQueryError` | Empty query or >2000 chars | Raise exception |
| `VectorDBUnavailableError` | Chroma connection failed | Raise exception, log ERROR |
| `NoDocumentsFoundError` | No chunks meet threshold | Return RAGContext with empty chunks, meets_threshold=False |

---

### `RAGPipeline.ingest(documents: List[RuleDocument]) -> IngestionResult`

**Description**: Ingests new or updated rule documents into vector index

**Input**:
```python
@dataclass
class RuleDocument:
    document_id: UUID
    filename: str
    content: str  # Full markdown
    metadata: Dict[str, Any]
```

**Output**:
```python
@dataclass
class IngestionResult:
    job_id: UUID
    documents_processed: int
    documents_failed: int
    embedding_count: int  # Total embeddings created
    errors: List[str]  # Filenames that failed
    warnings: List[str]  # Non-fatal issues
    duration_seconds: float
```

**Contracts**:

1. **Chunking Strategy**:
   - **Only split when token limit reached**: Keep entire documents as single chunks when ≤8192 tokens
   - Embedding model limit: 8192 tokens (OpenAI text-embedding-3-small)
   - **If document exceeds 8192 tokens**: Split at `##` (H2) heading boundaries
   - No overlap between chunks (keeps information logically together)
   - Each chunk MUST include the section header for context
   - **If single `##` section exceeds 8192 tokens**: Split at `###` (H3) boundaries
   - Preserve complete paragraphs within chunks (no mid-sentence splits)
   - **Goal**: Maximize chunk size up to embedding limit for better context

2. **Embedding Generation**:
   - Use consistent embedding model (e.g., OpenAI text-embedding-3-small)
   - Store model version in metadata for reproducibility

3. **Versioning**:
   - If `document_id` already exists, update embeddings (upsert)
   - Track document hash to detect actual content changes

4. **Atomic Operations**:
   - All embeddings for a document MUST be written atomically
   - If partial failure, rollback entire document's embeddings

5. **Validation**:
   - Reject documents without required metadata (source, doc_type, last_update_date)
   - Log WARNING for ambiguous markdown structure

**Error Conditions**:

| Error Type | Condition | Response |
|------------|-----------|----------|
| `InvalidDocumentError` | Missing required metadata | Skip document, log to errors |
| `EmbeddingFailureError` | LLM embedding API failed | Retry 3x, then skip document |
| `VectorDBWriteError` | Chroma write failed | Raise exception, abort job |

---

## Test Cases

### Contract Test 1: Retrieve with High Relevance

**Given**: Vector DB contains "rules-1-phases.md" with "Movement Phase" section
**When**: `retrieve(query="What can I do during movement?", context_key="test:user1")`
**Then**:
- `avg_relevance ≥ 0.8`
- `meets_threshold = True`
- `document_chunks[0].metadata["section"] = "Movement Phase"`
- `len(document_chunks) ≥ 1`

### Contract Test 2: Retrieve with Low Relevance

**Given**: Vector DB contains only "weapon-rules.md"
**When**: `retrieve(query="How do I cook pasta?", context_key="test:user1")`
**Then**:
- `meets_threshold = False`
- `document_chunks = []`
- `avg_relevance < 0.6`

### Contract Test 3: Chunk Ordering

**Given**: Multiple relevant documents exist
**When**: `retrieve(query="Barricade rules", context_key="test:user1")`
**Then**:
- `document_chunks[0].relevance_score ≥ document_chunks[1].relevance_score`
- `relevance_scores` matches `document_chunks` order

### Contract Test 4: Metadata Completeness

**Given**: Document ingested with full metadata
**When**: Retrieve any query
**Then**:
- Every chunk has `metadata["source"]`
- Every chunk has `metadata["doc_type"]` in {"core-rules", "faq", "team-rules", "ops", "killzone"}
- Every chunk has `metadata["last_update_date"]` parseable as date

### Contract Test 5: Ingest Idempotency

**Given**: Document with `document_id=UUID1` ingested
**When**: Re-ingest same `document_id` with updated content
**Then**:
- Old embeddings removed
- New embeddings created
- `documents_processed = 1`
- `documents_failed = 0`

### Contract Test 6: Performance SLA

**Given**: Vector DB with 100 documents
**When**: `retrieve(query="test", context_key="test:user1")`
**Then**:
- Response time ≤ 5 seconds (p95)

---

## Implementation Notes

**Embedding Model**: OpenAI `text-embedding-3-small` (1536 dimensions)
**Chunking Library**: Custom markdown splitter (split at `##` headers)
**Vector DB**: Chroma with persistence to `data/chroma_db/`

**Configuration**:
```python
# config/rag.yaml
embedding:
  model: "text-embedding-3-small"
  dimensions: 1536
  max_tokens: 8192  # Model's token limit
chunking:
  split_only_when_needed: true  # Keep documents whole if ≤8192 tokens
  max_chunk_tokens: 8192  # Match embedding model limit
  header_level: 2  # Split at H2 (##) when limit exceeded
  fallback_header_level: 3  # Split at H3 (###) if single section >8192 tokens
  overlap_tokens: 0  # No overlap
retrieval:
  max_chunks: 5
  min_relevance: 0.6
  cache_ttl_seconds: 300
```
