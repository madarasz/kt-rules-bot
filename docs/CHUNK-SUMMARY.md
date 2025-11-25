# Chunk Summary Feature Implementation Plan

**Status**: ✅ IMPLEMENTED
**Date**: 2025-11-25 (Updated)
**Feature**: LLM-generated one-sentence summaries for RAG chunks and team structure
**Model**: OpenAI `gpt-4.1-mini` with Pydantic structured outputs

---

## Overview

This document describes the implementation of LLM-generated chunk summaries for the Kill Team Rules Bot. Summaries enhance both semantic (vector) and keyword (BM25) search by providing concise, content-focused descriptions of rule sections.

### Architecture Summary

**Summary Generation Pipeline**:
1. Document → Chunk → Generate Summaries (batch) → Embed (header + summary + text) → Store
2. Uses OpenAI `gpt-4.1-mini` with Pydantic structured outputs
3. One API call per markdown file (batch processing)
4. Summaries stored in ChromaDB metadata and included in embeddings

**Summary Usage**:
- **RAG Retrieval**: Summaries enhance both vector (semantic) and BM25 (keyword) search
- **Team Structure YAML**: Summaries replace children in teams-structure.yml for hop evaluation
- **Cost Tracking**: Actual token usage tracked and reported (~$0.02-0.03 per full ingestion)

### Key Benefits

1. **Improved Semantic Search**: Summaries included in vector embeddings provide better semantic matching
2. **Enhanced Keyword Search**: BM25 tokenization includes summary text for better keyword matching
3. **Team Structure Context**: Generated team-structure.yml includes summaries for better LLM hop evaluation
4. **Cost Tracking**: Ingestion tracks and reports summary generation costs

---

## Implementation Details

### Part 1: RAG Chunk Summaries

#### 1. Summary Prompt ([prompts/chunk-summary-prompt.md](../../prompts/chunk-summary-prompt.md))

**Purpose**: System prompt for LLM to generate one-sentence summaries

**Key Features**:
- Focus on content and effects, not meta-descriptions
- Omit filler phrases ("this section outlines", "this profile details")
- Special handling for operatives (focus on abilities, not stats)
- List of unimportant weapon rules to omit: Balanced, Lethal, Saturate, Range, Rending, Shock, Stun
- Batch format: accepts numbered chunks, returns Pydantic structured output

**Example Input/Output**:
```
Input:
Chunk 1:
Header: SPACE MARINE CAPTAIN - Heroic Leader
Text: Once per turning point, you can do one of the following: ...

Output (Pydantic ChunkSummaries model):
{
  "summaries": [
    {
      "chunk_number": 1,
      "summary": "Grants discounted firefight ploy usage and allows activating Combat Doctrine strategy ploy for free once per turning point when conditions are met"
    }
  ]
}
```

#### 2. ChunkSummarizer Service ([src/services/rag/summarizer.py](../../src/services/rag/summarizer.py))

**Purpose**: Generate summaries for batches of chunks using LLM

**Key Methods**:
- `async generate_summaries(chunks)` → Returns `(chunks, prompt_tokens, completion_tokens, model_name)`
- Batch processing: One LLM call per markdown file
- Error handling: Returns empty summaries if LLM fails
- Token counting: Returns actual prompt/completion tokens for cost tracking
- Uses OpenAI client with Pydantic structured output parsing

**Pydantic Models**:
```python
class ChunkSummary(BaseModel):
    chunk_number: int  # Chunk number (1-indexed)
    summary: str       # One-sentence summary

class ChunkSummaries(BaseModel):
    summaries: list[ChunkSummary]  # Batch response
```

**Configuration**:
- Model: `gpt-4.1-mini` (fast/cheap)
- Max tokens: `LLM_DEFAULT_MAX_TOKENS` (shared with other LLM operations)
- Temperature: 0.3 (consistent formatting)
- Response format: Pydantic structured output (`ChunkSummaries` model)

#### 3. Chunk Model Updates ([src/services/rag/chunker.py](../../src/services/rag/chunker.py))

**Changes**:
- Added `summary: str = ""` field to `MarkdownChunk` dataclass
- Summary populated during ingestion, after chunking

#### 4. Configuration Constants ([src/lib/constants.py](../../src/lib/constants.py))

**New Constants**:
```python
SUMMARY_ENABLED = True  # Enable/disable summary generation
SUMMARY_LLM_MODEL = "gpt-4.1-mini"  # Model for summaries
CHUNK_SUMMARY_PROMPT_PATH = "prompts/chunk-summary-prompt.md"
```

#### 5. Ingestor Integration ([src/services/rag/ingestor.py](../../src/services/rag/ingestor.py))

**Changes**:
1. **Initialization**: Create `ChunkSummarizer` if `SUMMARY_ENABLED`
2. **Summary Generation**: After chunking, call `asyncio.run(summarizer.generate_summaries(chunks))`
3. **Cost Tracking**: Track prompt/completion tokens, calculate cost with `estimate_cost()`
4. **Embedding Integration**: Include summary in embedding text: `f"{chunk.header}\n{chunk.summary}\n{chunk.text}"` if summary exists
5. **Metadata Storage**: Add `"summary": chunk.summary` to ChromaDB metadata
6. **Result Reporting**: Add `summary_cost_usd` to `IngestionResult`

**Flow**:
```python
# Ingestion flow with summary generation
for document in documents:
    chunks = chunker.chunk(document.content)  # Split into chunks
    chunks, tokens_in, tokens_out, model = await summarizer.generate_summaries(chunks)  # Batch LLM call
    cost = estimate_cost(tokens_in, tokens_out, model)  # Track cost

    # Embed with summary included
    chunk_texts = [f"{chunk.header}\n{chunk.summary}\n{chunk.text}" if chunk.summary else chunk.text
                   for chunk in chunks]
    embeddings = embedding_service.embed(chunk_texts)

    # Store with summary in metadata
    metadatas = [{"header": chunk.header, "summary": chunk.summary, ...} for chunk in chunks]
    vector_db.upsert_embeddings(ids, embeddings, chunk_texts, metadatas)
```

**Cost Tracking**:
- Uses actual `prompt_tokens` and `completion_tokens` from LLM response
- Calls `estimate_cost()` from `src/lib/tokens.py`
- Reports cost in logs and ingestion result

#### 6. BM25 Retriever Updates ([src/services/rag/bm25_retriever.py](../../src/services/rag/bm25_retriever.py))

**Changes**:
- Modified `index_chunks()` to include summary in tokenized corpus:
  ```python
  chunk.text + " " + chunk.header + (" " + chunk.metadata.get("summary", "") if chunk.metadata.get("summary") else "")
  ```
- Summary keywords now searchable via BM25

---

### Part 2: Team Structure YAML Enhancement

#### 7. Generate Rules Structure Script ([scripts/generate_rules_structure.py](../../scripts/generate_rules_structure.py))

**New Flag**: `--summary`

**Usage**:
```bash
python scripts/generate_rules_structure.py --summary
```

**Behavior**:
- Retrieves summaries from ChromaDB for **teams-structure.yml ONLY** (not rules-structure.yml)
- Retrieves summaries for header level 2 elements in team files
- **Requires ingestion to be run beforehand** (does NOT generate new summaries)
- Connects to ChromaDB via `VectorDBService` and queries by filename
- Prints connection status: `Connected to ChromaDB (X chunks)`
- Continues without summaries if ChromaDB connection fails

**YAML Output Format** (assumes `--header 2`):

For single-item categories (no children):
```yaml
Operative Selection: Defines team composition, leader selection, and limits on heavy or specialized operatives.
```

For multi-item categories:
```yaml
Faction Rules:
  - CHAPTER TACTICS: Selection of primary and secondary tactics that provide permanent passive buffs for the battle.
  - ASTARTES: Allows two Shoot or Fight actions per activation and enables counteracting regardless of current order.
```

**Summary Retrieval Logic** (`generate_category_summaries` function):
1. Query ChromaDB using `collection.get(where={"filename": filename})`
2. Extract metadata (header, summary, header_level) from results
3. Filter for header level 2 chunks only
4. Clean headers and remove team prefixes from operative names
5. Return dict mapping cleaned header titles to their summaries

**Integration in Structure Generation**:
- For single-node categories: `Category: summary` (scalar value)
- For multi-node categories: `- Title: summary` (list items)
- Summaries replace child nodes in the YAML output

**Structure Building**:
- **Single node, no children**: Use summary as scalar value (`Category: summary`)
- **Multiple nodes or nodes with children**: Use list format where each item is `{title: summary}` if summary exists
- **No summary available**: Fall back to original format with children

**Category Mapping**: Uses same keyword matching as `categorize_team()` function:
  - "OPERATIVE SELECTION" → "Operative Selection"
  - "FACTION RULE" / "ARCHETYPES" → "Faction Rules"
  - "STRATEGY PLOY" → "Strategy Ploys"
  - "FIREFIGHT PLOY" → "Firefight Ploys"
  - "FACTION EQUIPMENT" → "Faction Equipment"

---

## Files Created/Modified

### New Files
- `prompts/chunk-summary-prompt.md` - Summary generation prompt
- `src/services/rag/summarizer.py` - ChunkSummarizer service
- `docs/future-development/CHUNK-SUMMARY.md` - This document

### Modified Files
- `src/services/rag/chunker.py` - Added `summary` field to `MarkdownChunk`
- `src/services/rag/ingestor.py` - Summary generation and cost tracking
- `src/services/rag/bm25_retriever.py` - Include summary in tokenization
- `src/lib/constants.py` - Summary configuration constants
- `scripts/generate_rules_structure.py` - Added `--summary` argument

---

## Usage

### Re-ingest Rules with Summaries

```bash
# Ingest with summary generation (default: enabled)
python -m src.cli ingest extracted-rules/

# Cost will be reported in logs:
# ingestion_completed ... summary_cost_usd=$0.1234
```

### Generate Team Structure with Summaries

```bash
# Generate teams-structure.yml with summaries
python scripts/generate_rules_structure.py --summary

# Output: extracted-rules/teams-structure.yml with summary fields
```

### Disable Summary Generation

```python
# In config/.env or src/lib/constants.py
SUMMARY_ENABLED = False
```

---

## Design Decisions

### ✅ Summary as Metadata
- Stored as metadata field, not mixed with chunk text
- ChromaDB documents still contain original chunk text only
- Summaries accessible via metadata for display/debugging

### ✅ Batch Processing
- One LLM call per markdown file (not per chunk)
- Reduces API calls (~50x fewer calls)
- Lower cost and faster ingestion
- Structured output format ensures all summaries are parsed together

### ✅ Both Vector and BM25 Search
- Summary included in embedding text for semantic search
- Summary included in BM25 tokenization for keyword search
- Maximum search coverage

### ✅ Cost Tracking
- Uses actual prompt/completion tokens from API response (not estimated)
- Reports per-document costs in debug logs
- Reports total cost in ingestion result (`summary_cost_usd`)
- Helps monitor ingestion expenses
- Uses `estimate_cost()` from `src/lib/tokens.py` for cost calculation

### ✅ Teams-Structure Only
- Only team files get summaries in YAML output (not core rules)
- All chunks get summaries during ingestion (for RAG retrieval)
- Teams-structure.yml uses summaries to reduce token usage in multi-hop retrieval
- Focuses on most valuable use case for YAML (team filtering during hop evaluation)

---

## Example Output

### Ingestion Log
```
INFO: document_chunked document_id=abc123 chunk_count=15
INFO: summaries_generated document_id=abc123 chunk_count=15 cost_usd=$0.0005
INFO: document_ingested document_id=abc123 filename=angels_of_death.md embeddings=15
INFO: ingestion_completed job_id=xyz789 processed=48 failed=0 embeddings=720 duration=45.2 summary_cost_usd=$0.0235
```

**Note**: Costs are significantly lower with `gpt-4.1-mini` compared to the original estimates.

### Team Structure YAML
```yaml
Angels Of Death:
  Operative Selection: Defines team composition, leader selection, and limits on heavy or specialized operatives
  Faction Rules:
    - CHAPTER TACTICS: Selection of primary and secondary tactics that provide permanent passive buffs for the battle
    - ASTARTES: Allows two Shoot or Fight actions per activation and enables counteracting regardless of current order
  Operatives:
    - SPACE MARINE CAPTAIN:
      - Heroic Leader
      - Iron Halo
    - ASSAULT INTERCESSOR SERGEANT:
      - Doctrine Warfare
      - Chapter Veteran
    # ... more operatives
```

**Note**: Summaries replace children in the YAML output. When a header has a summary, its child elements are not displayed in the structure.

---

## Future Enhancements

### Potential Improvements
1. **Summary Refinement**: Tune prompt for better summaries based on user feedback
2. **Summary Caching**: Cache summaries to avoid regeneration on re-ingestion
3. **Multi-Language Summaries**: Generate summaries in multiple languages
4. **Summary Quality Metrics**: Track summary quality scores
5. **Admin Dashboard**: Display summaries in analytics dashboard for chunk review

### Not Implemented
- ❌ Summary quality evaluation (future work)
- ❌ Unit tests for summary generation (planned)
- ❌ Summary caching to avoid regeneration

### Implementation Notes
- Uses OpenAI API instead of Anthropic (gpt-4.1-mini vs claude-4.5-haiku)
- Significantly lower costs with gpt-4.1-mini (~$0.02-0.03 vs ~$0.10-0.20 for full ingestion)
- Pydantic structured outputs ensure consistent parsing
- Async/await pattern for summary generation
- Summary generation is optional and controlled by `SUMMARY_ENABLED` constant

---

## Testing

### Manual Testing Steps

1. **Test RAG Ingestion**:
   ```bash
   # Ingest one file
   python -m src.cli ingest extracted-rules/team/angels_of_death.md

   # Check logs for summary generation
   # Check cost reporting
   ```

2. **Test Search Integration**:
   ```bash
   # Query should use summaries in search
   python -m src.cli query "Can Space Marine Captain use ploys for free?"

   # Check retrieved chunks include summaries in metadata
   ```

3. **Test Team Structure Generation**:
   ```bash
   # Generate with summaries
   python scripts/generate_rules_structure.py --summary

   # Verify teams-structure.yml has summary fields
   # Verify rules-structure.yml has NO summaries
   ```

### Unit Test Coverage
- ⏳ `ChunkSummarizer.generate_summaries()` with mock LLM (planned)
- ⏳ Ingestor summary integration (planned)
- ⏳ BM25 summary tokenization (planned)
- ⏳ Vector embedding includes summary (planned)

---

## Cost Analysis

### Estimated Costs
- **Model**: gpt-4.1-mini
- **Pricing**: ~$0.15/1M prompt tokens, ~$0.60/1M completion tokens (OpenAI pricing)
- **Average**: ~5-10 chunks per team file, ~50 tokens per summary
- **Per Team**: ~$0.0005-0.001
- **Full Ingestion** (48 teams + core rules): ~$0.02-0.05

### Actual Costs (Example)
```
Angels of Death: 15 chunks, prompt: 2340 tokens, completion: 185 tokens = ~$0.0005
Full Ingestion: 48 files, 720 chunks, total cost: ~$0.02-0.03
```

---

## References

- [RAG Pipeline Contract](../../specs/001-we-are-building/contracts/rag-pipeline.md)
- [src/services/rag/CLAUDE.md](../../src/services/rag/CLAUDE.md)
- [src/lib/constants.py](../../src/lib/constants.py) - All configuration
- [prompts/chunk-summary-prompt.md](../../prompts/chunk-summary-prompt.md) - Prompt template
