# Kill Team Rules Bot

A Discord bot that answers questions about Warhammer 40,000 Kill Team rules using AI and retrieval-augmented generation (RAG).

## Purpose

Helps Kill Team players quickly find accurate rule information by asking questions in Discord. The bot searches through official rule documents and provides AI-generated answers with citations and confidence scores.

## Roadmap
- ✅ Kill Team rules extracted
- ✅ LLM models integrated
- ✅ RAG system operational
- ✅ Rules query available via CLI
- 🏗️ Assessing LLM models, optimizing prompts
- ❌ Discord integration

## Technology, Architecture

- **Python 3.12** with discord.py for Discord integration
- **RAG Pipeline**: ChromaDB vector database + LLM
- **Orchestrator Pattern**: Centralized coordination of Discord, RAG, and LLM services
- **GDPR-compliant**: SHA-256 user ID hashing, 7-day retention, audit logging

**Supported LLM models:**
- **Claude**: `claude-sonnet` (Sonnet 4.5), `claude-opus` (Opus 4.1)
- **Gemini**: `gemini-2.5-pro`, `gemini-2.5-flash`
- **OpenAI**: `gpt-5`, `gpt-5-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `o3`, `o3-mini`, `o4-mini`

## Installation, Requirements

```bash
# Install dependencies
pip install -r requirements.txt

# make a copy of .env.template
cp config/.env.template config/.env
```

Set `DEFAULT_LLM_PROVIDER` (e.g., `claude-sonnet`, `gemini-2.5-pro`, `gpt-4o`, `o3`) and related `*_API_KEY` values in the `config/.env` file you just created.

```bash
# Ingest rules into vector database
python -m src.cli ingest ./extracted-rules
```

## Running

### In development
```bash
python -m src.cli run --mode dev
```

### In production
```bash
python -m src.cli run --mode production
```

## Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html
```

**Current status**: 87 tests passing (unit, integration, contract)

## Project structure

```
├── src/
│   ├── cli/              # CLI commands (run, ingest, query, health, gdpr-delete)
│   ├── services/
│   │   ├── discord/      # Discord bot (orchestrator pattern)
│   │   ├── llm/          # LLM providers (Claude, ChatGPT, Gemini)
│   │   └── rag/          # Vector DB and retrieval
│   ├── models/           # Data models
│   └── lib/              # Utilities (logging, config)
├── tests/
│   ├── unit/             # Unit tests
│   └── integration/      # Integration tests
├── extracted-rules/      # Markdown rule files
├── specs/                # Specification documents
└── docs/                 # Documentation
```

## CLI commands

Detailed document about [CLI usage](CLI_USAGE.md)

**Quick reference**:
- `python -m src.cli run` - Start Discord bot
- `python -m src.cli ingest <dir>` - Ingest rules
- `python -m src.cli query "question"` - Test locally
- `python -m src.cli health` - Check system health
- `python -m src.cli gdpr-delete <user_id>` - Delete user data

## Spec Kit

This project uses the [Spec Kit](https://github.com/github/spec-kit) workflow for systematic development. See [specs/001-we-are-building/](specs/001-we-are-building/) for detailed specifications, plans, and tasks.

## Licence

MIT License
