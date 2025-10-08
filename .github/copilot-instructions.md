# Kill Team Rules Bot - AI Agent Instructions

## Architecture Overview

This is a **Discord bot for Warhammer 40K Kill Team rules queries** using RAG (Retrieval-Augmented Generation) with multiple LLM providers. The system follows an **Orchestrator Pattern** where `KillTeamBotOrchestrator` coordinates all services.

### Core Components
- **Discord Client** (`src/services/discord/client.py`) - Raw event handlers, not command-based
- **Orchestrator** (`src/services/discord/bot.py`) - Coordinates RAG → LLM → Discord flow
- **RAG System** (`src/services/rag/`) - ChromaDB vector store + BM25 hybrid retrieval
- **LLM Providers** (`src/services/llm/`) - Claude, Gemini, GPT, OpenAI O-Series with factory pattern
- **CLI Interface** (`src/cli/`) - Complete toolset for development and operations

## Development Workflows

### Essential Commands
```bash
# Setup (one-time)
pip install -r requirements.txt
cp config/.env.template config/.env  # Configure API keys
python -m src.cli ingest ./extracted-rules

# Development cycle
python -m src.cli query "your test question"  # Test RAG+LLM locally
python -m src.cli run --mode dev              # Start Discord bot
python -m src.cli health -v                   # Check all services

# Quality assurance
python -m src.cli quality-test --all-models --runs 3  # Comprehensive testing
pytest --cov=src --cov-report=html                    # Unit/integration tests
```

### Testing Strategy
- **Unit/Integration** (`pytest`) - Standard testing for services
- **Quality Tests** (`src/cli/quality_test.py`) - RAG+LLM response validation using YAML test cases
- **Contract Tests** - API interface validation
- Use `--all-models --runs N` for statistical quality assessment

## Project-Specific Patterns

### Orchestrator Pattern Implementation
The bot **does not use discord.py commands**. Instead:
- Raw event handlers in `client.py` delegate to `handlers.py`
- `KillTeamBotOrchestrator.process_query()` manages the entire flow
- All services are dependency-injected into the orchestrator

### LLM Provider Architecture
- **Factory Pattern**: `LLMProviderFactory` creates providers from config
- **Unified Interface**: All providers implement `BaseLLMProvider`
- **Provider Switching**: Change `DEFAULT_LLM_PROVIDER` in config, no code changes
- **Rate Limiting**: Built-in per-provider rate limiting with `RateLimiter`

### Configuration Management
- **Environment-driven**: All config via `config/.env` (copy from `.env.template`)
- **Typed Config**: `src/lib/config.py` uses dataclasses for validation
- **Multi-LLM Support**: Configure multiple API keys, switch via `DEFAULT_LLM_PROVIDER`

### RAG Pipeline Specifics
- **Hybrid Retrieval**: Combines vector similarity + BM25 keyword matching
- **Document Structure**: Markdown files in `extracted-rules/` (teams, rules, killzones)
- **Chunking Strategy**: Custom chunker preserves rule context boundaries
- **Ingestion**: `python -m src.cli ingest <dir>` processes markdown → ChromaDB

## Integration Points

### Data Flow
1. Discord message → `client.py` → `handlers.py` → `orchestrator.process_query()`
2. RAG retrieval → LLM generation → response validation → Discord formatting
3. Feedback buttons → reaction handlers → `FeedbackLogger`

### External Dependencies
- **ChromaDB**: Vector database at `./data/chroma_db` (configurable via `VECTOR_DB_PATH`)
- **LLM APIs**: Anthropic, OpenAI, Google (configure keys in `.env`)
- **Discord API**: Requires `DISCORD_BOT_TOKEN` and message content intents

### Cross-Component Communication
- **Models** (`src/models/`) define data contracts between services
- **UserQuery** → **RAGContext** → **BotResponse** flow
- **GDPR Compliance**: SHA-256 user hashing, 7-day retention, audit logging

## Key File Locations

### Essential Implementation Files
- `src/services/discord/bot.py` - Core orchestrator logic
- `src/services/rag/retriever.py` - Hybrid RAG implementation  
- `src/services/llm/factory.py` - Multi-provider LLM factory
- `src/cli/__main__.py` - Complete CLI interface
- `src/lib/config.py` - Environment configuration management

### Quality Assurance
- `tests/quality/` - RAG+LLM response quality framework
- `tests/quality/test_cases/` - YAML test definitions
- `src/cli/quality_test.py` - Quality test runner with multi-model support

### Rule Content
- `extracted-rules/team/` - Kill Team faction rules (markdown)
- `extracted-rules/rules-*.md` - Core game rules
- `extracted-rules/killzone/` - Map-specific rules
- `prompts/` - LLM system prompts for different use cases

## Development Notes

- **Python 3.11+** required, use `ruff` for linting, `mypy` for type checking
- **Async patterns**: Discord handlers are async, LLM calls support async
- **Error handling**: Comprehensive validation, rate limiting, content filter retry
- **Logging**: Structured logging via `src/lib/logging.py`, configurable levels
- **Spec-driven**: Follow GitHub Spec Kit methodology (see `specs/001-we-are-building/`)

## Common Pitfalls

- Don't use discord.py command decorators - this uses raw event handlers
- Always test LLM changes with `quality-test --all-models` before deployment
- RAG changes need `ingest --force` to rebuild vector database
- Config changes require bot restart; test locally with `query` command first