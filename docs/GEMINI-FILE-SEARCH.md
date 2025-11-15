# Gemini File Search Integration

**Status**: ✅ Implemented
**Last Updated**: 2025-01-14

## Overview

Gemini File Search provides an alternative to the traditional RAG (Retrieval-Augmented Generation) pipeline by using Gemini's built-in semantic search capabilities. Instead of maintaining a local ChromaDB vector store and performing hybrid BM25+vector retrieval, file-search models upload documents directly to Google's infrastructure and leverage Gemini's native file search tool during generation.

**Requirements:**
- `google-genai>=1.50.1` (File Search support added in v1.49.0)
- `GOOGLE_API_KEY` configured in `config/.env`

**Known Limitations:**
- File search tools conflict with `response_schema` in the Gemini API (causes schema echoing bug)
- JSON structure is enforced via prompt instructions instead of schema validation
- Gemini may occasionally wrap JSON in markdown code blocks (automatically stripped by our implementation)

## Architecture

### Traditional RAG Flow
```
User Query → RAG Retrieval (ChromaDB + BM25) → Context Chunks → LLM → Response
```

### File Search Flow
```
User Query → LLM with File Search Tool → Gemini searches uploaded documents → Response
```

### Key Differences

| Aspect | Traditional RAG | File Search |
|--------|----------------|-------------|
| **Document Storage** | Local ChromaDB | Google Cloud (file search store) |
| **Retrieval** | Hybrid BM25 + Vector | Gemini's semantic search |
| **Context Passing** | Chunks in prompt | Tool call to file search API |
| **Embeddings** | OpenAI text-embedding-3-small | Gemini embeddings (automatic) |
| **Cost** | Free (local compute) | $0.15 per 1M tokens at upload time |
| **Multi-hop** | Supported | Not applicable |
| **Setup** | One-time ingestion | One-time upload + store creation |

## Model Names

Two new model variants are available:
- `gemini-2.5-pro-file-search` - High-quality reasoning with file search
- `gemini-2.5-flash-file-search` - Fast responses with file search

## Setup Guide

### 1. Create File Search Store

```bash
python -m src.cli.gemini_store create
```

This creates a persistent Gemini file search store and saves the store ID to `data/gemini_file_search_store_id.txt`.

**Output Example:**
```
🔍 Creating Gemini File Search store...
✅ Store created successfully!
   Store ID: file-search-stores/abc123xyz
   Saved to: data/gemini_file_search_store_id.txt

Next step: Upload documents with:
  python -m src.cli.gemini_store upload
```

### 2. Upload Documents

```bash
python -m src.cli.gemini_store upload
```

This uploads all markdown files from `extracted-rules/` directory to the file search store. Only changed files are uploaded on subsequent runs (based on content hash).

**Output Example:**
```
📤 Uploading documents from extracted-rules...
Uploading: core-rules/movement.md
Uploading: core-rules/shooting.md
...

📊 Upload Statistics:
   Files uploaded: 45
   Files skipped:  0 (unchanged)
   Files failed:   0

💰 Cost Estimation:
   Estimated tokens: 234,567
   Estimated cost:   $0.0352 USD
   (Embeddings: $0.15 per 1M tokens)

✅ Upload complete!
   You can now use file-search models:
   - gemini-2.5-pro-file-search
   - gemini-2.5-flash-file-search
```

### 3. Use File Search Models

#### CLI Query
```bash
python -m src.cli query "Can I overwatch during conceal?" --model gemini-2.5-pro-file-search
```

#### Discord Bot
Set in `config/.env`:
```env
DEFAULT_LLM_PROVIDER=gemini-2.5-pro-file-search
```

Or per-server in `config/servers.yaml`:
```yaml
servers:
  "123456789012345678":
    name: "My Server"
    llm_provider: "gemini-2.5-flash-file-search"
    google_api_key: "AIza..."
```

#### Quality Tests
```bash
python -m src.cli quality-test --model gemini-2.5-pro-file-search
```

## CLI Commands

### `create` - Create New Store
```bash
python -m src.cli.gemini_store create
```

Creates a new file search store and saves ID to `data/gemini_file_search_store_id.txt`.

**When to use:**
- First-time setup
- After deleting an old store

### `upload [dir]` - Upload Documents
```bash
python -m src.cli.gemini_store upload                # Default: extracted-rules/
python -m src.cli.gemini_store upload custom-rules/  # Custom directory
```

Uploads markdown documents to the file search store. Only uploads files that have changed since last upload (based on SHA-256 hash tracking in `data/gemini_file_search_hashes.json`).

**When to use:**
- After creating a new store
- After updating rule documents
- When adding new documents

### `refresh [dir]` - Re-upload Changed Documents
```bash
python -m src.cli.gemini_store refresh
```

Alias for `upload` - re-uploads only changed files.

**When to use:**
- After editing rule documents
- After pulling new rules from source

### `info` - Display Store Details
```bash
python -m src.cli.gemini_store info
```

Displays file search store metadata:
- Store ID
- Display name
- Creation time
- Last update time

### `delete` - Delete Store
```bash
python -m src.cli.gemini_store delete
```

**⚠️ Warning**: Permanently deletes the file search store. Requires confirmation.

**When to use:**
- Cleaning up old/test stores
- Starting fresh with new document structure

## Cost Management

### Embedding Costs
- **Rate**: $0.15 per 1 million tokens
- **Charged**: One-time at document upload
- **Estimation**: ~4 characters per token (rough estimate)

### Example Costs
- Small rulebook (50KB): ~$0.002
- Medium rulebook (500KB): ~$0.019
- Large rulebook (2MB): ~$0.075
- Full game rules (10MB): ~$0.375

### Cost Tracking
The CLI displays estimated cost after each upload:
```
💰 Cost Estimation:
   Estimated tokens: 234,567
   Estimated cost:   $0.0352 USD
```

**Note**: Hash-based tracking ensures you only pay for changed files, not full re-uploads.

## File Management

### Store ID Persistence
- **Location**: `data/gemini_file_search_store_id.txt`
- **Format**: Plain text, single line
- **Gitignored**: Yes (local configuration)

### Document Hashes
- **Location**: `data/gemini_file_search_hashes.json`
- **Format**: JSON mapping `{relative_path: sha256_hash}`
- **Purpose**: Skip unchanged files during upload
- **Gitignored**: Yes (local state)

### Example Hash File
```json
{
  "core-rules/movement.md": "a1b2c3d4...",
  "core-rules/shooting.md": "e5f6g7h8...",
  "teams/space-marines.md": "i9j0k1l2..."
}
```

## Technical Implementation

### Code Architecture

**New Files:**
- `src/services/llm/gemini_file_search.py` - File search store management service
- `src/cli/gemini_store.py` - CLI commands
- `data/gemini_file_search_store_id.txt` - Store ID persistence (gitignored)
- `data/gemini_file_search_hashes.json` - Document hash tracking (gitignored)

**Modified Files:**
- `src/lib/constants.py` - Added file-search model names and store paths
- `src/lib/config.py` - Added provider-to-key mapping
- `src/services/llm/gemini.py` - Added file search mode detection and tool integration
- `src/services/llm/factory.py` - Registered file-search models
- `src/services/discord/bot.py` - Skip RAG for file-search models
- `config/.env.template` - Added model documentation

### Gemini Adapter Flow

```python
# In GeminiAdapter.__init__()
self.use_file_search = "-file-search" in model
self.base_model = model.replace("-file-search", "")

# In GeminiAdapter.generate()
if self.use_file_search:
    # Load store ID
    store_id = self._load_file_search_store_id()

    # Configure file search tool
    config = genai_types.GenerateContentConfig(
        tools=[
            genai_types.Tool(
                file_search=genai_types.FileSearch(
                    file_search_store_names=[store_id]
                )
            )
        ]
    )

    # Call Gemini with base model name (e.g., "gemini-2.5-pro")
    response = client.models.generate_content(
        model=self.base_model,
        contents=prompt,
        config=config
    )
```

### Bot Orchestrator Flow

```python
# In KillTeamBotOrchestrator.process_query()
use_file_search = "-file-search" in llm.model

if use_file_search:
    # Skip RAG, create empty context
    rag_context = RAGContext(document_chunks=[], avg_relevance=1.0)
else:
    # Traditional RAG retrieval
    rag_context = self.rag.retrieve(query)

# LLM generation (same for both modes)
llm_response = await llm.generate(
    prompt=query,
    context=rag_context.document_chunks  # Empty for file-search
)
```

## Error Handling

### Missing Store ID
If file search store ID is not found:
```
❌ Error: Store ID not found. Create a store first with:
   python -m src.cli.gemini_store create
```

### Missing API Key
If `GOOGLE_API_KEY` not configured:
```
❌ Error: GOOGLE_API_KEY not found in config/.env
   Add your Google API key to config/.env:
   GOOGLE_API_KEY=AIza...
```

### Upload Failures
Individual file upload failures are logged but don't abort the entire upload:
```
⚠️  Errors:
   - invalid-file.md: Unsupported file format
   - corrupted.md: File read error
```

### File Search Failures
If file search fails during generation, the error is raised (no fallback to RAG):
```python
# In gemini.py
if self.use_file_search:
    try:
        store_id = self._load_file_search_store_id()
    except FileNotFoundError as e:
        raise FileSearchStoreError(str(e))
```

## Quality Testing

File-search models are fully supported in the quality test framework:

```bash
# Single test
python -m src.cli quality-test --test eliminator-concealed-counteract --model gemini-2.5-pro-file-search

# All tests
python -m src.cli quality-test --model gemini-2.5-pro-file-search

# A/B comparison
python -m src.cli quality-test --model gemini-2.5-pro
python -m src.cli quality-test --model gemini-2.5-pro-file-search
# Compare results in tests/quality/findings/findings.md
```

**Evaluation Metrics:**
- Quote Precision
- Quote Recall
- Quote Faithfulness
- Explanation Faithfulness
- Answer Correctness

**Note**: File-search models are evaluated the same way as traditional RAG models. The quality framework evaluates the LLM response structure, not the retrieval mechanism.

## Troubleshooting

### "Store ID not found" Error
**Problem**: File search store ID missing from `data/gemini_file_search_store_id.txt`

**Solution**:
```bash
python -m src.cli.gemini_store create
python -m src.cli.gemini_store upload
```

### "Invalid API key" Error
**Problem**: `GOOGLE_API_KEY` not set or invalid

**Solution**:
1. Get API key from https://aistudio.google.com/apikey
2. Add to `config/.env`:
   ```env
   GOOGLE_API_KEY=AIza...
   ```

### "No documents found" / Low Quality Responses
**Problem**: Documents not uploaded or store empty

**Solution**:
```bash
# Check store info
python -m src.cli.gemini_store info

# Re-upload documents
python -m src.cli.gemini_store upload
```

### Files Not Being Re-uploaded
**Problem**: Hash tracking preventing re-upload of edited files

**Solution**:
```bash
# Delete hash file to force full re-upload
rm data/gemini_file_search_hashes.json
python -m src.cli.gemini_store upload
```

### Cost Concerns
**Problem**: Concerned about upload costs

**Solution**:
1. Check cost estimation before proceeding:
   ```bash
   python -m src.cli.gemini_store upload
   # Review cost estimate, Ctrl+C to cancel
   ```
2. Hash tracking ensures only changed files are uploaded
3. Typical full rulebook upload: $0.05-0.50 USD

## Comparison: File Search vs Traditional RAG

### When to Use File Search
✅ **Advantages:**
- No local vector DB maintenance
- Automatic embeddings and indexing
- Native integration with Gemini
- Simpler architecture (no BM25, no fusion)
- May provide better semantic search (proprietary Gemini algorithm)

✅ **Best For:**
- Production deployments relying on Gemini models
- Teams wanting to minimize local infrastructure
- A/B testing against traditional RAG

### When to Use Traditional RAG
✅ **Advantages:**
- Zero ongoing costs (local compute)
- Full control over retrieval (BM25 weight, RRF, multi-hop)
- LLM-agnostic (works with Claude, GPT, Grok, etc.)
- Hybrid search tuning (keyword + semantic)
- Query expansion and normalization

✅ **Best For:**
- Multi-LLM deployments
- Development/testing environments
- Cost-sensitive scenarios
- Custom retrieval requirements

### Performance Considerations

| Metric | Traditional RAG | File Search |
|--------|----------------|-------------|
| **Initial Setup** | Ingest to ChromaDB | Upload to Gemini store |
| **Query Latency** | ~200-500ms (retrieval) | ~0ms (built-in) |
| **LLM Latency** | Same | Same |
| **Total Latency** | Slightly slower | Slightly faster |
| **Scalability** | Local disk limits | Google infrastructure |
| **Retrieval Quality** | Tunable | Fixed (Gemini algorithm) |

**Note**: Both approaches should provide similar overall response times since LLM generation dominates latency (1-5 seconds).

## Future Enhancements

### Phase 2 (Not Yet Implemented)
- [ ] Custom chunking configuration (currently uses Gemini defaults)
- [ ] Document metadata filtering
- [ ] Citation extraction from `grounding_metadata`
- [ ] Automatic store refresh on document changes
- [ ] Multi-store support (per-server stores)
- [ ] Store analytics (document count, index size)

### Phase 3 (Potential)
- [ ] Hybrid mode: Combine traditional RAG + file search
- [ ] File search for non-Gemini models (via API translation)
- [ ] Incremental updates (delta uploads)
- [ ] Store versioning and rollback

## References

- **Gemini File Search Docs**: https://ai.google.dev/gemini-api/docs/file-search
- **Gemini API Reference**: https://ai.google.dev/api/files
- **google-genai SDK**: https://github.com/googleapis/python-genai
- **Pricing**: https://ai.google.dev/pricing (Embeddings: $0.15/1M tokens)

## Related Files

- [src/services/llm/CLAUDE.md](../src/services/llm/CLAUDE.md) - LLM provider architecture
- [src/services/rag/CLAUDE.md](../src/services/rag/CLAUDE.md) - Traditional RAG pipeline
- [CLAUDE.md](../CLAUDE.md) - Project overview
