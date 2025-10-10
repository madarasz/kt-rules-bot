# Services

Core business logic and external integrations organized by domain. Each service handles a specific aspect of the bot's functionality.

## Service Domains

### [Discord Service](discord/CLAUDE.md)
Bot interaction layer handling Discord message processing, conversation context, security, and response formatting. Orchestrates RAG and LLM services to process user queries.

**Quick summary**: User messages → validation → RAG retrieval → LLM generation → formatted response

### [RAG Service](rag/CLAUDE.md)
Retrieval-Augmented Generation pipeline using hybrid search (vector embeddings + BM25 keyword matching). Finds the most relevant Kill Team rule chunks to provide context for LLM responses. Also handles markdown ingestion ([ingestor.py](rag/ingestor.py)).

**Quick summary**: Query → embed → hybrid retrieval (vector + BM25) → top-k chunks

**Ingestion**: Markdown files → chunk → embed → store in ChromaDB

### [LLM Service](llm/CLAUDE.md)
Multi-provider LLM integration with unified interface. Supports Claude, ChatGPT, Gemini, and Grok through a factory pattern with automatic retry and rate limiting. Includes PDF extraction capabilities for downloading team rules.

**Quick summary**: Provider-agnostic interface → factory creates adapter → generate response

**PDF Extraction**: Available via CLI ([download_team.py](../cli/download_team.py), [download_all_teams.py](../cli/download_all_teams.py))

## Request Flow

End-to-end user query processing:

```
User Message (Discord)
    ↓
Discord Service
    ├→ Validate & sanitize input
    ├→ Check rate limits
    └→ Extract conversation context
    ↓
RAG Service
    ├→ Embed query
    ├→ Hybrid retrieval (vector + BM25)
    └→ Return top-k relevant chunks
    ↓
LLM Service
    ├→ Build prompt with context
    ├→ Generate response (selected provider)
    └→ Return formatted answer + citations
    ↓
Discord Service
    ├→ Format response for Discord
    ├→ Add citations
    └→ Send to user
```

## Testing

**Quick commands**:
```bash
# Health check all services
python -m src.cli health

# Test query end-to-end
python -m src.cli query "your test query"

# Quality tests (RAG + LLM) - costs real money
python -m src.cli quality-test --test eliminator-concealed-counteract

# RAG retrieval tests - NOT YET IMPLEMENTED
python -m src.cli rag-test

# Unit tests
pytest tests/
```

See individual service CLAUDE.md files for service-specific testing details.

## Dependencies

**By service**:
- **Discord**: `discord.py`
- **RAG**: `chromadb`, `openai`, `rank-bm25`
- **LLM**: `anthropic`, `openai`, `google-generativeai`
- **Common**: `asyncio`, `aiohttp`, `pydantic`

## Quick Links

- [Discord Service Details](discord/CLAUDE.md)
- [RAG Service Details](rag/CLAUDE.md)
- [LLM Service Details](llm/CLAUDE.md)
- [Project Root CLAUDE.md](../CLAUDE.md)
