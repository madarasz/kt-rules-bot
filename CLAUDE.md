# Kill Team Rules Bot

Discord bot answering Kill Team rules questions using RAG + LLM (ChromaDB + Claude/GPT/Gemini/Grok).

**Last updated:** 2025-10-10

## Quick Start for Agents

```bash
# Setup
pip install -r requirements.txt
cp config/.env.template config/.env  # Add your API keys

# Ingest rules
python -m src.cli ingest extracted-rules/

# Test locally
python -m src.cli query "Can I use overwatch against a charge?"

# Run quality test
# Do not run all tests, all models, multiple runs by yourself. Running these tests costs money.
python -m src.cli quality-test --test eliminator-concealed-counteract

# Start bot
python -m src.cli run --mode production
```

## Project Status

✅ **Production ready**: RAG pipeline, multi-LLM support, quality testing, PDF extraction
🏗️ **In progress**: Discord bot polish, RAG/prompt optimization, LLM model selection

## Architecture

**Tech Stack**: Python 3.11+, discord.py, ChromaDB, OpenAI, Anthropic, Google AI, X/Grok

**RAG Pipeline**: Hybrid retrieval (vector + BM25) → ChromaDB + text-embedding-3-small

**LLM Providers** (via factory pattern):
- Claude: `claude-sonnet` (default), `claude-opus`
- Gemini: `gemini-2.5-pro`, `gemini-2.5-flash`
- GPT: `gpt-5`, `gpt-4.1`, `gpt-4o`, `o3`, `o4-mini` + variants
- Grok: `grok-4-fast-reasoning`, `grok-3` + variants

**See**: [src/services/CLAUDE.md](src/services/CLAUDE.md) for detailed architecture

## Directory Structure

```
src/
  cli/          → Commands (run, ingest, query, health, quality-test, download-team)
  lib/          → Utilities (constants.py ⭐, config.py, logging, validation, gdpr)
  models/       → Data structures (UserQuery, RAGContext, BotResponse, etc.)
  services/     → Core business logic
    discord/    → Bot orchestration, handlers, context management
    rag/        → Hybrid retrieval (vector + BM25), embeddings, chunking, ingestion
    llm/        → Multi-provider LLM integration (Claude, GPT, Gemini, Grok)

tests/
  unit/         → Module/function tests
  integration/  → End-to-end pipeline tests
  contract/     → Interface compliance tests
  quality/      → RAG+LLM quality evaluation framework
  rag/          → RAG chunk retrieval tests (planned)

extracted-rules/  → Markdown source documents
prompts/          → LLM system prompts
config/.env       → API keys (gitignored, see .env.template)
```

**Notes**:
- Markdown ingestion: `src/services/rag/ingestor.py` (part of RAG service)
- PDF extraction: `src/cli/download_team.py` and `download_all_teams.py` (CLI commands)

## Documentation Map

**Start here** (agents): [src/lib/constants.py](src/lib/constants.py) ⭐ - All tunable parameters

**Domain guides**:
- [src/cli/CLAUDE.md](src/cli/CLAUDE.md) - CLI commands
- [src/services/CLAUDE.md](src/services/CLAUDE.md) - Services
- [src/services/discord/CLAUDE.md](src/services/discord/CLAUDE.md) - Discord bot layer
- [src/services/rag/CLAUDE.md](src/services/rag/CLAUDE.md) - RAG retrieval pipeline
- [src/services/llm/CLAUDE.md](src/services/llm/CLAUDE.md) - LLM provider integration
- [tests/quality/CLAUDE.md](tests/quality/CLAUDE.md) - Quality testing framework

**Overviews**: [src/CLAUDE.md](src/CLAUDE.md), [tests/CLAUDE.md](tests/CLAUDE.md)

## Common Agent Tasks

### Adding New LLM Provider
1. Create `src/services/llm/my_provider.py` inheriting from `LLMProvider`
2. Add to `LLMProviderFactory._model_registry` in [factory.py](src/services/llm/factory.py)
3. Update type in [src/lib/config.py](src/lib/config.py)
4. Test: `python -m src.cli quality-test --model my-provider`

See [src/services/llm/CLAUDE.md](src/services/llm/CLAUDE.md) for details.

## Code Conventions

✅ **Do**:
- Import constants from [src/lib/constants.py](src/lib/constants.py)
- Use type hints and dataclasses
- Hash user IDs with SHA-256 (GDPR)
- Use async/await for I/O
- Test with `pytest` before committing

❌ **Don't**:
- Hardcode config values
- Store raw Discord user IDs
- Add provider-specific code outside `src/services/llm/`

**Linting**: `ruff check .`

## Architecture Patterns

**Provider Pattern** (LLM): All providers implement `LLMProvider` base class → factory creates instances → swappable via config

**Hybrid Retrieval** (RAG): Vector (semantic) + BM25 (lexical) → RRF fusion → top-k chunks

**GDPR**: Hash all user IDs, 7-day retention, support deletion via `gdpr-delete` command

## Testing

```bash
pytest tests/unit/                      # Unit tests
pytest tests/contract/                  # Interface compliance
python -m src.cli quality-test          # RAG+LLM quality
```

**Before committing**:
1. `pytest`
2. `ruff check .`
3. `python -m src.cli quality-test` (if changed RAG/LLM)

## API Documentation

- Discord.py: https://discordpy.readthedocs.io/
- ChromaDB: https://docs.trychroma.com/
- OpenAI: https://platform.openai.com/docs
- Anthropic: https://docs.anthropic.com/
- Google AI: https://ai.google.dev/docs

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
