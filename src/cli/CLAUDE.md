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
├── list_models.py          # Model/cost/reasoning-level listing
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
python -m src.cli query "Can I use overwatch against a charge?" --model claude-4.5-sonnet --max-chunks 10

# RAG-only mode (no LLM call)
python -m src.cli query "Can I shoot during conceal order?" --rag-only
```

**Options**:
- `--model`, `-m`: LLM model to use (default: from config)
- `--max-chunks`: Maximum RAG chunks to retrieve (default: 5)
- `--rag-only`: Stop after RAG retrieval, do not call LLM

### `list-models`
List LLM models per provider with input/output token costs (USD per million) and the
reasoning-effort levels each supports. No API calls, no cost.
```bash
python -m src.cli list-models --provider claude
```

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

**Batch API mode** (opt-in, ~50% cheaper via provider Batch APIs, ≤24h turnaround):
```bash
# Submit (returns batch IDs, runs non-batch models live, exits):
python -m src.cli quality-test --batch-submit --test <id> --model claude-4.6-sonnet
# Collect (single pass; re-run until "Phase: done"):
python -m src.cli quality-test --batch-collect tests/quality/results/<timestamp>
```
- `--batch-submit` / `--batch-collect <dir>` are mutually exclusive.
- Batchable: `claude-*`, `gpt-*`/`o3*`, `kimi-*`, `qwen*`, `mistral*`, `gemini-*`, `grok-*`. Only DeepSeek runs live at submit (no native batch API).
- The default `grok-4-1-fast-reasoning` judge is batchable, so a full run is typically two `--batch-collect` passes (gen batch, then judge batch).
- Kimi batch discount is estimated at 50% (unconfirmed reduced pricing) in `src/lib/pricing.py`; savings for it are approximate until confirmed. Grok is confirmed at 20%.
- State persists in `<dir>/batch_state.json` (resumable). See [tests/quality/CLAUDE.md](../../tests/quality/CLAUDE.md#batch-api-workflow-opt-in-50-cheaper).

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

`--model` / `--judge-model` accept any name in `ALL_LLM_PROVIDERS`
([src/lib/constants.py](../../src/lib/constants.py)). Run `python -m src.cli list-models`
for the current list with per-model costs and reasoning levels rather than relying on a
hand-maintained list here.

**Reasoning effort**: append `#level` to a model name (e.g. `--model grok-4.3#high`,
`--judge-model claude-4.8-opus#low`). The CLI validates the level against the model and
exits with an error if unsupported. See
[src/services/llm/CLAUDE.md](../services/llm/CLAUDE.md#reasoning-effort-model-name-postfix).

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
