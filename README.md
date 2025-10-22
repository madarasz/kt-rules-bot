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
- 🏗️ Discord integration

## Technology, Architecture

- **Python 3.12** with discord.py for Discord integration
- **RAG Pipeline**: ChromaDB vector database + LLM
- **Orchestrator Pattern**: Centralized coordination of Discord, RAG, and LLM services
- **GDPR-compliant**: SHA-256 user ID hashing, 7-day retention, audit logging

**Supported LLM models:**
- **Claude**: `claude-4.5-sonnet`, `claude-4.1-opus`, `claude-4.5-haiku`
- **Gemini**: `gemini-2.5-pro`, `gemini-2.5-flash`
- **OpenAI**: `gpt-5`, `gpt-5-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `o3`, `o3-mini`, `o4-mini`

## Installation, Requirements

```bash
# Install dependencies
pip install -r requirements.txt

# make a copy of .env.template
cp config/.env.template config/.env
```

Set `DEFAULT_LLM_PROVIDER` (e.g., `claude-4.5-sonnet`, `gemini-2.5-pro`, `gpt-4o`, `o3`) and related `*_API_KEY` values in the `config/.env` file you just created.

```bash
# Get the rules descriptions from submodule. Reach out to me for access. 
# Alternatively you can download team rules only via CLI script
git submodule update --init --recursive
```

```bash
# Ingest rules into vector database
python -m src.cli ingest ./extracted-rules
```

## Running the bot
```bash
python -m src.cli run
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

[Apache 2.0 Licence](LICENSE)

**DISCLAIMER: This is an unofficial fan-made project and is in no way affiliated with, endorsed, or sponsored by Games Workshop Limited. It is a non-commercial project for personal use only.**

Kill Team, Warhammer 40,000, Games Workshop and all associated logos, illustrations, images, names, creatures, races, vehicles, locations, weapons, characters, and the distinctive likeness thereof, are either ® or ™, and/or © Games Workshop Limited, variably registered around the world, and used without permission. All rights reserved to their respective owners.

This tool is not intended to be a substitute for purchasing the official rulebooks. It is strongly recommended that you purchase the official Kill Team rules from Games Workshop to support their work.
