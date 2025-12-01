# Kill Team Rules Bot

Discord bot answering Kill Team rules questions using RAG + LLM (ChromaDB + Claude/GPT/Gemini/Grok).

**Last updated:** 2025-10-13

## Quick Start for Agents

```bash
# Setup
pip install -r requirements.txt
cp config/.env.template config/.env  # Add your API keys

# Ingest rules
python -m src.cli ingest extracted-rules/

# Test locally (full pipeline)
python -m src.cli query "Can I use overwatch against a charge?"

# Test RAG only (no LLM call)
python -m src.cli query "Can I shoot during conceal order?" --rag-only

# Test with multi-hop retrieval (iterative context gathering)
python -m src.cli query "Can barricade provide cover?" --max-hops 1

# Run quality test
# Do not run all tests, all models, multiple runs by yourself. Running these tests costs money.
python -m src.cli quality-test --test eliminator-concealed-counteract

# Generate cached RAG context for quality tests (faster, cheaper, deterministic)
python3 -m src.cli query "Can the Eliminator shoot twice?" --rag-only --context-output tests/quality/context_cache/eliminator.json

# Start bot
python -m src.cli run --mode production

# Admin dashboard (optional, if analytics DB enabled)
streamlit run src/cli/admin_dashboard.py --server.port 8501

# Migrate database schema (if you get "no such column" errors)
python3 scripts/migrate_db.py
```

## Project Status

✅ **Production ready**: RAG pipeline, multi-LLM support, quality testing, PDF extraction
🏗️ **In progress**: Discord bot polish, RAG/prompt optimization, LLM model selection

## Architecture

**Tech Stack**: Python 3.11+, discord.py, ChromaDB, OpenAI, Anthropic, Google AI, X/Grok, DeepSeek

**RAG Pipeline**:
- Hybrid retrieval (vector + BM25) with RRF fusion
- Multi-hop retrieval for complex queries
- Query normalization for case-insensitive keyword matching
- ChromaDB + text-embedding-3-small
- 1300+ game-specific keywords auto-extracted from rules

**LLM Providers** (via factory pattern):
- Claude: `claude-4.5-sonnet`, `claude-4.1-opus`, `claude-4.5-haiku`
- Gemini: `gemini-2.5-pro`, `gemini-2.5-flash`
- GPT: `gpt-5`, `gpt-4.1`, `gpt-4o`, `o3`, `o4-mini` + variants
- Grok: `grok-4-fast-reasoning`, `grok-3` + variants
- DeepSeek: `deepseek-chat`, `deepseek-reasoner`

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
config/
  .env            → Global API keys (gitignored, see .env.template)
  servers.yaml    → Per-server API keys (optional, gitignored, see servers.yaml.template)
data/
  chroma_db/      → Vector database (ChromaDB)
  rag_keywords.json → Auto-extracted keyword library for query normalization
  analytics.db    → Optional analytics database (if enabled)
```

**Notes**:
- Markdown ingestion: `src/services/rag/ingestor.py` (part of RAG service)
- PDF extraction: `src/cli/download_team.py` and `download_all_teams.py` (CLI commands)
- Multi-server config: See [Multi-Server Deployment](#multi-server-deployment) below

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

**Hybrid Retrieval** (RAG): Query normalization → Vector (semantic) + BM25 (lexical) → RRF fusion → top-k chunks

**Case-Insensitive Queries**: Automatic keyword normalization (e.g., "accurate 1" → "Accurate 1") enables consistent retrieval regardless of capitalization

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

## Analytics Database (Optional)

The bot can optionally store queries, responses, feedback, and RAG chunks in SQLite for admin review and analytics.

**Enable**:
```bash
# In config/.env
ENABLE_ANALYTICS_DB=true
ADMIN_DASHBOARD_PASSWORD=your_secure_password
```

**What's stored** (30-day retention, auto-cleanup):
- Query text, response text, LLM model, scores, latency
- Upvote/downvote counts (from Discord reactions)
- Retrieved chunks with similarity scores
- Admin status (pending/approved/issues/flagged) and notes
- Chunk relevance flags (for RAG tuning)

**Admin Dashboard**:
```bash
streamlit run src/cli/admin_dashboard.py --server.port 8501
# Access: http://localhost:8501
```

**Features**:
- 📋 Query Browser: Filter/search queries, view feedback
- 🔍 Query Detail: Review full query/response, mark chunk relevance
- 📊 Analytics: Feedback trends, LLM model performance, top downvoted queries
- 🧪 RAG Tests: Generate RAG test cases from queries with relevant chunks (YAML export)
- ⚙️ Settings: Manual cleanup, export to CSV/JSON

**Privacy**:
- Username stored (not sensitive per Discord ToS)
- Query/response text stored (users notified in bot)
- 30-day auto-deletion (GDPR compliant)
- Password-protected dashboard

**See**: [src/lib/database.py](src/lib/database.py) for implementation

## Multi-Server Deployment

The bot uses **per-server API key configuration**, allowing multiple Discord servers to use their own LLM API keys and pay for their own usage.

### Setup

1. **Copy the template**:
   ```bash
   cp config/servers.yaml.template config/servers.yaml
   ```

2. **Get Discord Guild IDs**:
   - Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode)
   - Right-click on server icon → "Copy Server ID"

3. **Configure per-server settings** in `config/servers.yaml`:
   ```yaml
   servers:
     "123456789012345678":  # Discord guild ID
       name: "My Gaming Community"  # Optional, for documentation
       llm_provider: "claude-4.5-sonnet"  # REQUIRED
       anthropic_api_key: "sk-ant-..."  # REQUIRED for claude models

     "987654321098765432":
       name: "Tournament Server"
       llm_provider: "gpt-4.1"  # REQUIRED
       openai_api_key: "sk-..."  # REQUIRED for gpt models
       rag_hop_evaluation_model: "gpt-4.1-mini"  # Optional
   ```

### Per-Server Configurable Settings

- **LLM Provider** (REQUIRED): `llm_provider` - which model to use for queries
- **API Keys**: `anthropic_api_key`, `openai_api_key`, `google_api_key`, `x_api_key`, `deepseek_api_key`
  - The API key must match the `llm_provider` (e.g., claude models need `anthropic_api_key`)


## API Documentation

- Discord.py: https://discordpy.readthedocs.io/
- ChromaDB: https://docs.trychroma.com/
- OpenAI: https://platform.openai.com/docs
- Anthropic: https://docs.anthropic.com/
- Google AI: https://ai.google.dev/docs
- Streamlit: https://docs.streamlit.io/

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
