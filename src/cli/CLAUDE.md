# CLI Tools

Command-line interface for the Kill Team Rules Discord Bot. Provides utilities for bot management, testing, and data operations.

## Purpose

Unified CLI entry point that routes commands to appropriate handlers for:
- Running the Discord bot
- Ingesting rules into the vector database
- Testing RAG + LLM pipeline locally
- Health checks and monitoring
- GDPR compliance operations
- Quality testing
- Team rule PDF downloads

## Structure

```
src/cli/
├── __main__.py             # Main entry point with argparse routing
├── run_bot.py              # Discord bot launcher
├── ingest_rules.py         # Rules ingestion command
├── test_query.py           # Local query testing
├── health_check.py         # System health diagnostics
├── gdpr_delete.py          # User data deletion (GDPR)
├── quality_test.py         # Quality test runner
├── download_team.py        # Single team PDF download
└── download_all_teams.py   # Bulk team PDF downloads
```

## Available Commands

### `run`
Start the Discord bot in dev or production mode.
```bash
python -m src.cli run --mode production
```

### `ingest`
Ingest markdown rules from a directory into the vector database.
```bash
python -m src.cli ingest extracted-rules/ --force
```

### `query`
Test RAG + LLM pipeline locally without Discord.
```bash
# Full pipeline (RAG + LLM)
python -m src.cli query "Can I use overwatch against a charge?" --model claude-sonnet --max-chunks 10

# RAG-only mode (no LLM call)
python -m src.cli query "Can I shoot during conceal order?" --rag-only
```

**Options**:
- `--model`, `-m`: LLM model to use (default: from config)
- `--max-chunks`: Maximum RAG chunks to retrieve (default: 5)
- `--rag-only`: Stop after RAG retrieval, do not call LLM

### `health`
Check system health (Discord bot, vector DB, LLM providers).
```bash
python -m src.cli health --verbose
```

### `gdpr-delete`
Delete all user data for GDPR compliance.
```bash
python -m src.cli gdpr-delete <user_id> --confirm
```

### `quality-test`
Run quality tests for response evaluation.
```bash
python -m src.cli quality-test --all-models --runs 5
```

### `download-team`
Download and extract a single team rule PDF.
```bash
python -m src.cli download-team <pdf_url> --model gemini-2.5-pro
```

### `download-all-teams`
Download all team rules from Warhammer Community.
```bash
python -m src.cli download-all-teams --dry-run
```

## Main Entry Point

[__main__.py](../../src/cli/__main__.py) uses `argparse` to:
- Define all subcommands and their arguments
- Validate input parameters
- Route to appropriate handler functions
- Handle errors and keyboard interrupts gracefully

## Supported LLM Providers

Available across `query` and `quality-test` commands:
- `claude-sonnet`, `claude-opus`
- `gemini-2.5-pro`, `gemini-2.5-flash`
- `gpt-5`, `gpt-5-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`
- `o3`, `o3-mini`, `o4-mini`

Default provider is configured in [src/lib/constants.py](../../src/lib/constants.py).

## Development Guidelines

### Adding New Commands

1. Create a new handler file (e.g., `my_command.py`)
2. Define a main function that accepts parsed arguments
3. Add command definition in `__main__.py`:
   - Add to subparsers
   - Define arguments
   - Add routing in `main()`
4. Import handler at top of `__main__.py`

### Error Handling

All commands should:
- Use try/except blocks for graceful error handling
- Log errors using `src.lib.logging.get_logger()`
- Return appropriate exit codes (0 = success, 1 = error, 130 = interrupted)
- Print user-friendly error messages to stderr

### Best Practices

- Keep command handlers focused and single-purpose
- Use [src/lib/config.py](../../src/lib/config.py) for configuration
- Import constants from [src/lib/constants.py](../../src/lib/constants.py)
- Validate inputs before processing
- Provide helpful `--help` text for all commands
- Use `--verbose` flags for detailed output where appropriate
