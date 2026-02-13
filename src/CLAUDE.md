# Source Code (src/)

Main application source code for the Kill Team Rules Discord Bot. Organized into four major subsystems for clarity and maintainability.

## Purpose

Contains all production code for:
- Discord bot interaction and message handling
- RAG (Retrieval-Augmented Generation) pipeline
- Multi-provider LLM integration
- CLI tools for bot management and testing
- Shared utilities and configuration
- Domain models and data structures

## Directory Structure

```
src/
├── admin_dashboard/  # Streamlit admin web interface
├── cli/              # Command-line interface tools
├── lib/              # Shared utilities and configuration
├── models/           # Domain models and data structures
└── services/         # Core business logic and external integrations
    ├── discord/      # Discord bot and message handling
    ├── rag/          # RAG retrieval pipeline (includes ingestor.py)
    └── llm/          # LLM provider integrations
```

## Subsystem Overview

### [admin_dashboard/](admin_dashboard/CLAUDE.md) - Admin Web Interface

### [cli/](cli/CLAUDE.md) - Command-Line Interface
Entry points for all operations:
- `run` - Start Discord bot
- `ingest` - Load rules into vector database
- `query` - Test RAG + LLM pipeline locally
- `health` - System health checks
- `quality-test` - Run quality evaluation tests
- `download-team` - Download and extract team rules
- `download-all-teams` - Downloads list of all teams, downloads the ones with updated rules

See [cli/CLAUDE.md](cli/CLAUDE.md) for detailed CLI documentation.

### [lib/](lib/CLAUDE.md) - Shared Utilities
Application-wide utilities and configuration:
- **[constants.py](lib/constants.py)** - SINGLE SOURCE OF TRUTH for all tunable parameters
- **[config.py](lib/config.py)** - Environment-based configuration (.env loading)
- **[logging.py](lib/logging.py)** - Structured logging infrastructure
- **[validation.py](lib/validation.py)** - Input sanitization
- **[gdpr.py](lib/gdpr.py)** - GDPR compliance utilities
- **[tokens.py](lib/tokens.py)** - Token counting
- **[metrics.py](lib/metrics.py)** - Usage metrics
- **[discord_utils.py](lib/discord_utils.py)** - Discord helpers

See [lib/CLAUDE.md](lib/CLAUDE.md) for utilities documentation.

### [models/](models/CLAUDE.md) - Domain Models
Data structures using Python dataclasses:
- `UserQuery` - Discord user questions (GDPR-compliant)
- `ConversationContext` - Multi-turn conversation state
- `RAGContext` - RAG retrieval results
- `BotResponse` - Formatted bot responses
- `RuleDocument` - Rule document metadata
- `IngestionJob` - Ingestion task tracking
- `PDFUpdate` - PDF download metadata

See [models/CLAUDE.md](models/CLAUDE.md) for data model documentation.

### [services/](services/CLAUDE.md) - Core Services
Business logic and external integrations:

**Discord Service** - Bot client and message handling
- Message event processing
- Conversation context management
- Error handling and logging
- Response formatting

**RAG Service** - Retrieval pipeline
- ChromaDB vector database
- Hybrid retrieval (vector + BM25)
- Document embeddings (OpenAI)
- Document chunking and ingestion ([ingestor.py](services/rag/ingestor.py))

**LLM Service** - Multi-provider integration
- Abstract base class for provider independence
- Anthropic Claude (Sonnet, Opus)
- OpenAI ChatGPT (GPT-4.1, GPT-5, o3, etc.)
- Google Gemini (2.5 Pro, Flash)
- X/Grok (Grok 3, Grok 4)
- Retry logic and rate limiting

See [services/CLAUDE.md](services/CLAUDE.md) for detailed service documentation.

## Architecture Patterns

### Configuration Hierarchy
1. **Constants** ([lib/constants.py](lib/constants.py)) - Default values, limits, tunable parameters
2. **Environment** ([lib/config.py](lib/config.py)) - API keys, secrets from `.env`
3. **Runtime** (CLI args) - Command-line overrides

### Dependency Flow
```
CLI → Services → Models ← Lib
      ↓
  External APIs
  (Discord, LLMs, Vector DB)
```

### GDPR Compliance
All user data handling follows GDPR principles:
- User IDs hashed with SHA-256 (never store raw Discord IDs)
- 7-day retention policy
- Data deletion support via `gdpr-delete` command
- Audit logging for compliance

## Key Technologies

- **Python 3.11+** - Modern Python with type hints
- **discord.py** - Discord API client
- **ChromaDB** - Vector database for embeddings
- **OpenAI** - Embeddings (text-embedding-3-small)
- **Anthropic** - Claude models
- **Google AI** - Gemini models
- **asyncio** - Asynchronous I/O

## Development Guidelines

### Code Organization
- Keep services focused on single responsibilities
- Use dataclasses for data models
- Import constants from [lib/constants.py](lib/constants.py)
- Use type hints throughout
- Follow Python 3.11+ conventions

### Adding New Features
1. Create models in [models/](models/)
2. Implement business logic in [services/](services/)
3. Add CLI command in [cli/](cli/)
4. Update constants in [lib/constants.py](lib/constants.py)
5. Write tests in [../tests/](../tests/)

### Configuration Changes
- Modify [lib/constants.py](lib/constants.py) for tunable parameters
- Update [lib/config.py](lib/config.py) for environment variables
- Document changes in code comments
- Test with quality tests before committing

### LLM Provider Integration
See [services/llm/](services/llm/) for adding new LLM providers:
1. Inherit from `LLMProvider` base class
2. Implement `generate()` and `extract_from_pdf()` methods
3. Add to `LLMProviderFactory`
4. Update type definitions in [lib/config.py](lib/config.py)

## Testing
Run tests from project root:
```bash
pytest tests/unit/        # Unit tests
pytest tests/integration/ # Integration tests
pytest tests/contract/    # Contract tests
python -m src.cli quality-test  # Quality tests
```

## Documentation
Each subdirectory has its own CLAUDE.md:
- [admin_dashboard/CLAUDE.md](admin_dashboard/CLAUDE.md) - Admin dashboard
- [cli/CLAUDE.md](cli/CLAUDE.md) - CLI documentation
- [lib/CLAUDE.md](lib/CLAUDE.md) - Utilities documentation
- [models/CLAUDE.md](models/CLAUDE.md) - Data models
- [services/CLAUDE.md](services/CLAUDE.md) - Services architecture
