# Kill Team Rules Bot - CLI Usage Guide

This guide covers all CLI commands for the Kill Team Rules Discord Bot.

## Installation

Ensure you have installed the bot and its dependencies:

```bash
pip install -r requirements.txt
```

## Running Commands

All commands can be run using Python's module syntax:

```bash
python -m src.cli <command> [options]
```

Or if you've set up an alias:

```bash
kill-team-bot <command> [options]
```

---

## Commands

### `run` - Start Discord Bot

Start the Discord bot in development or production mode.

**Usage:**
```bash
python -m src.cli run [--mode {dev|production}]
```

**Options:**
- `--mode` - Runtime mode (default: production)
  - `dev`: Development mode with verbose logging
  - `production`: Production mode with standard logging

**Examples:**
```bash
# Start in production mode
python -m src.cli run

# Start in development mode
python -m src.cli run --mode dev
```

**Requirements:**
- Discord bot token configured in environment/config
- Vector database initialized with rules
- LLM provider credentials configured

**Graceful Shutdown:**
- Press `Ctrl+C` or send `SIGTERM` for graceful shutdown
- Bot will close Discord connection and cleanup resources

---

### `ingest` - Ingest Rules into Vector Database

Ingest markdown rule files into the vector database for RAG retrieval.

**Usage:**
```bash
python -m src.cli ingest <source_dir> [--force]
```

**Arguments:**
- `source_dir` - Directory containing markdown rule files (required)

**Options:**
- `--force` - Force re-ingestion of all documents (skips duplicate check)

**Examples:**
```bash
# Ingest rules from extracted-rules directory
python -m src.cli ingest ./extracted-rules

# Force re-ingestion (overwrites existing)
python -m src.cli ingest ./extracted-rules --force
```

**Output:**
- Documents processed count
- Documents skipped count
- Validation errors (if any)
- Total chunks created

**File Requirements:**
- Markdown files (`.md`)
- Valid frontmatter with required fields:
  - `title`
  - `category` (killteam, operation, or team)
  - `source`
  - `last_update_date`

---

### `query` - Test RAG + LLM Pipeline Locally

Test query processing locally without Discord. Useful for debugging and testing.

**Usage:**
```bash
python -m src.cli query "<query_text>" [--provider {claude|chatgpt|gemini}] [--max-chunks N]
```

**Arguments:**
- `query` - Query text to test (required, use quotes)

**Options:**
- `--provider` - LLM provider to use (default: from config)
  - `claude` - Anthropic Claude
  - `chatgpt` - OpenAI ChatGPT
  - `gemini` - Google Gemini
- `--max-chunks` - Maximum RAG chunks to retrieve (default: 5)

**Examples:**
```bash
# Test query with default provider
python -m src.cli query "Can I shoot through barricades?"

# Test with specific provider
python -m src.cli query "What are ploys?" --provider claude

# Test with more chunks
python -m src.cli query "How does overwatch work?" --max-chunks 10
```

**Output:**
- **Step 1: RAG Retrieval**
  - Chunks retrieved
  - Average relevance score
  - Latency
- **Step 2: LLM Generation**
  - Answer text
  - Confidence score
  - Token count
  - Latency
- **Step 3: Validation**
  - Validation result (PASS/FAIL)
  - Reason (if failed)
- **Summary**
  - Total time breakdown

---

### `health` - Check System Health

Check health status of Discord bot, vector database, and LLM provider.

**Usage:**
```bash
python -m src.cli health [-v] [--wait-for-discord]
```

**Options:**
- `-v, --verbose` - Show detailed health information (error rates, latency)
- `--wait-for-discord` - Wait for Discord connection (use when checking running bot)

**Examples:**
```bash
# Basic health check
python -m src.cli health

# Detailed health check
python -m src.cli health -v

# Check running bot (waits for Discord)
python -m src.cli health --wait-for-discord
```

**Output:**
- Overall health status (✅ HEALTHY or ❌ UNHEALTHY)
- Component status:
  - Discord connection
  - Vector database availability
  - LLM provider availability
- Metrics (with `--verbose`):
  - Error rate
  - Average latency
  - Check timestamp

**Exit Codes:**
- `0` - System is healthy
- `1` - System is unhealthy or error occurred

**Note:** Discord connection will show as disconnected unless bot is running. Use `--wait-for-discord` to check a running bot instance.

---

### `gdpr-delete` - Delete User Data (GDPR Compliance)

Delete all data for a user to comply with GDPR right to erasure.

**Usage:**
```bash
python -m src.cli gdpr-delete <user_id> [--confirm]
```

**Arguments:**
- `user_id` - Discord user ID or hashed user ID (required)

**Options:**
- `--confirm` - Skip confirmation prompt (for automated scripts)

**Examples:**
```bash
# Delete user data (with confirmation)
python -m src.cli gdpr-delete 123456789012345678

# Delete without confirmation prompt
python -m src.cli gdpr-delete 123456789012345678 --confirm

# Delete using hashed ID
python -m src.cli gdpr-delete abc123def456...
```

**What Gets Deleted:**
1. Structured logs (user queries, feedback)
2. Vector database conversation context
3. In-memory conversation history (if bot is running)

**Safety:**
- Confirmation prompt (unless `--confirm` used)
- Audit trail logged for compliance
- User ID hashing (SHA-256) for privacy

**Audit Log:**
- Deletion event logged with:
  - Timestamp
  - User ID (hashed)
  - Data categories deleted
  - Initiator (system admin)

---

## Global Options

### Version

Display bot version:
```bash
python -m src.cli --version
```

### Help

Show help for any command:
```bash
# General help
python -m src.cli --help

# Command-specific help
python -m src.cli run --help
python -m src.cli ingest --help
python -m src.cli query --help
python -m src.cli health --help
python -m src.cli gdpr-delete --help
```

---

## Configuration

All commands use configuration from:
1. Environment variables
2. Configuration file (if implemented)
3. Default values

**Required Configuration:**
- `DISCORD_TOKEN` - Discord bot token (for `run` command)
- `LLM_PROVIDER` - LLM provider (claude/chatgpt/gemini)
- `LLM_API_KEY` - API key for LLM provider
- `VECTORDB_PERSIST_DIRECTORY` - Vector database storage path

**Optional Configuration:**
- `VECTORDB_COLLECTION_NAME` - Collection name (default: kill_team_rules)
- `RATE_LIMIT_REQUESTS` - Requests per minute (default: 10)
- `CONTEXT_TTL_SECONDS` - Context TTL (default: 1800)

---

## Common Workflows

### Initial Setup

1. Ingest rules into vector database:
   ```bash
   python -m src.cli ingest ./extracted-rules
   ```

2. Test queries locally:
   ```bash
   python -m src.cli query "How do overwatch tokens work?"
   ```

3. Check system health:
   ```bash
   python -m src.cli health -v
   ```

4. Start bot:
   ```bash
   python -m src.cli run
   ```

### Development Workflow

1. Start in dev mode:
   ```bash
   python -m src.cli run --mode dev
   ```

2. Test changes locally:
   ```bash
   python -m src.cli query "Test query" --provider claude
   ```

3. Monitor health:
   ```bash
   python -m src.cli health -v
   ```

### GDPR Compliance Workflow

1. Receive deletion request from user
2. Verify user identity
3. Delete user data:
   ```bash
   python -m src.cli gdpr-delete <user_id> --confirm
   ```
4. Archive audit logs for compliance records

---

## Troubleshooting

### "Discord token not found"
- Ensure `DISCORD_TOKEN` environment variable is set
- Check configuration file if using config-based setup

### "Vector database not found"
- Run `ingest` command to populate database
- Check `VECTORDB_PERSIST_DIRECTORY` path exists

### "LLM provider unavailable"
- Verify API key is configured correctly
- Check network connectivity to LLM provider
- Verify API quota/limits

### Health check fails
- Run `health -v` for detailed diagnostics
- Check logs for specific error messages
- Verify all dependencies are installed

---

## Exit Codes

All commands use standard exit codes:
- `0` - Success
- `1` - Error or failure
- `130` - Interrupted by user (Ctrl+C)

Use exit codes in scripts:
```bash
python -m src.cli health
if [ $? -eq 0 ]; then
    echo "System healthy"
    python -m src.cli run
fi
```

---

## Support

For issues or questions:
- Check logs in `./logs/` directory
- Run health check: `python -m src.cli health -v`
- Review documentation in `/docs`
