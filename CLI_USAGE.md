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
python -m src.cli query "<query_text>" [--provider MODEL] [--max-chunks N]
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
python -m src.cli query "What are ploys?" --provider claude-sonnet

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

### `download-team` - Download and Extract Team Rule PDF

Download a team rule PDF from a URL and extract it to markdown using LLM vision capabilities.

**Usage:**
```bash
python -m src.cli download-team <url> [--model {gemini-2.5-pro|gemini-2.5-flash}]
```

**Arguments:**
- `url` - PDF URL (must be HTTPS, required)

**Options:**
- `--model` - LLM model to use for extraction (default: gemini-2.5-pro)
  - `gemini-2.5-pro`: Higher quality, slower, more expensive
  - `gemini-2.5-flash`: Faster, cheaper, good quality

**Examples:**
```bash
# Download and extract team rules (default model)
python -m src.cli download-team https://assets.warhammer-community.com/eng_jul25_kt_teamrules_novitiates-qcjk0xtwmk-gakdgtyg7r.pdf

# Use faster model
python -m src.cli download-team https://example.com/team.pdf --model gemini-2.5-flash
```

**Process:**
1. Downloads PDF from URL
2. Extracts team rules using LLM vision (uses `prompts/team-extraction-prompt.md`)
3. Parses team name from extracted markdown
4. Adds YAML frontmatter with metadata:
   - `source`: "WC downloads"
   - `last_update_date`: Extracted from URL pattern or current date
   - `document_type`: "team-rules"
   - `section`: Team name (lowercase)
5. Saves to `extracted-rules/team/[team_name].md`

**Output:**
- Download progress (file size)
- Extraction status
- Validation warnings (if any)
- Team name detected
- Output file path
- Metrics:
  - Token count
  - Processing time
  - Estimated cost (USD)

**Requirements:**
- `GOOGLE_API_KEY` configured in environment
- HTTPS URL pointing to a PDF file

**Example Output:**
```
Downloading PDF from URL...
✓ Downloaded 2.3 MB

Extracting team rules using gemini-2.5-pro...
✓ Extraction complete

Team name: NOVITIATES
Saved to: extracted-rules/team/novitiates.md

Metrics:
  Tokens: 45,234
  Time: 12.4s
  Estimated cost: $0.34
```

**Date Extraction:**
The tool attempts to extract the last update date from URL patterns like:
- `eng_jul25_` → 2025-07-23 (last day of July 2025)
- `eng_jan24_` → 2024-01-31 (last day of January 2024)

If no date pattern is found, it uses the current date.

**Use Cases:**
- Extract new team rules from Warhammer Community PDFs
- Update existing team rules when new versions are released
- Bulk extraction of multiple team PDFs
- Automation via scripts (exit code 0 on success, 1 on failure)

---

### `download-all-teams` - Download All Team Rule PDFs

Automatically download and extract all team rule PDFs from Warhammer Community API.

**Usage:**
```bash
python -m src.cli download-all-teams [--dry-run] [--force]
```

**Options:**
- `--dry-run` - Check what needs updating without downloading
- `--force` - Re-download all teams regardless of date

**Examples:**
```bash
# Check what would be downloaded (dry-run)
python -m src.cli download-all-teams --dry-run

# Download all new/updated teams
python -m src.cli download-all-teams

# Force re-download all teams
python -m src.cli download-all-teams --force
```

**Process:**
1. Fetches team list from Warhammer Community API
2. Filters for team-rules downloads
3. For each team:
   - Checks if `extracted-rules/team/[team_name].md` exists
   - Compares API date with `last_update_date` from existing file
   - Skips if existing file is up-to-date (unless `--force`)
   - Downloads and extracts if new or updated
4. Outputs summary with metrics

**Skip Logic:**
- **New file**: Team doesn't exist locally → Download
- **Updated**: API date > existing file date → Download
- **Up-to-date**: API date ≤ existing file date → Skip
- **Force mode**: Always download, ignore dates

**Requirements:**
- `GOOGLE_API_KEY` configured in environment
- Network access to Warhammer Community API

**Example Output (Dry-run):**
```
python -m src.cli download-all-teams --dry-run
```
```
Fetching team list from Warhammer Community...
✓ Found 42 teams

Checking existing files...
  - 27 teams up-to-date (skipped)
  - 15 teams to download

============================================================
DRY RUN - No downloads will be performed
============================================================

Teams to download (15):
  ✓ NOVITIATES (new file)
  ✓ PATHFINDERS (updated: 2025-11-25 > 2025-07-23)
  ✓ ANGELS OF DEATH (updated: 2025-10-15 > 2025-06-10)
  ✓ VESPID STINGWINGS (new file)
  ...

Teams up-to-date (27):
  ⊘ WARPCOVEN (up-to-date: 2025-07-23)
  ⊘ DEATHWATCH (up-to-date: 2025-06-10)
  ...

============================================================
Summary (dry-run):
  Would download: 15 teams
  Already up-to-date: 27 teams
  Total teams: 42 teams
============================================================
```

**Example Output (Normal):**
```
python -m src.cli download-all-teams
```
```
Fetching team list from Warhammer Community...
✓ Found 42 teams

Checking existing files...
  - 27 teams up-to-date (skipped)
  - 15 teams to download

Downloading teams...
[1/15] NOVITIATES... ✓ (12.4s, $0.34)
[2/15] PATHFINDERS... ✓ (11.8s, $0.31)
[3/15] ANGELS OF DEATH... ✓ (13.2s, $0.36)
[4/15] VESPID STINGWINGS... ❌ HTTP 404
...

============================================================
Summary:
  Downloaded: 14 teams
  Skipped: 27 teams (up-to-date)
  Failed: 1 team
  Total time: 5m 32s
  Total cost: $8.16
  Total tokens: 234,567
============================================================

Failed teams:
  - VESPID STINGWINGS: HTTP 404
```

**Use Cases:**
- Bulk download all team rules for initial setup
- Update all team rules after Warhammer Community publishes updates
- Check which teams have new versions available (dry-run)
- Automated daily/weekly updates via cron jobs
- Re-extract all teams with improved extraction prompts (force mode)

**API Details:**
- **Endpoint**: `https://www.warhammer-community.com/api/search/downloads/`
- **Method**: POST
- **Payload**:
  ```json
  {
    "index": "downloads_v2",
    "searchTerm": "",
    "gameSystem": "kill-team",
    "language": "english"
  }
  ```
- **Filter**: Only downloads where `download_categories` contains `"team-rules"`

**Error Handling:**
- Continues processing remaining teams if one fails
- Reports all failures at end with error messages
- Exit code 1 if any downloads failed, 0 if all successful

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
python -m src.cli quality-test --help
python -m src.cli download-team --help
python -m src.cli download-all-teams --help
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
   python -m src.cli query "Test query" --provider claude-sonnet
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

## Utility Scripts

### `scripts/reset_rag_db.py` - Reset Vector Database

Delete all embeddings from the vector database. Useful after chunking improvements or when starting fresh.

**Usage:**
```bash
python3 scripts/reset_rag_db.py [--confirm]
```

**Options:**
- `--confirm` - Skip confirmation prompt (for automation)

**Examples:**
```bash
# Reset with confirmation prompt
python3 scripts/reset_rag_db.py

# Reset without confirmation
python3 scripts/reset_rag_db.py --confirm
```

**Output:**
- Current database stats (collection name, path, embedding count)
- Confirmation prompt (unless `--confirm`)
- Deletion summary

**Use Cases:**
- After improving chunking strategy (e.g., better ## header splitting)
- After changing embedding model
- When deduplication creates corrupt data
- Clean slate for re-ingestion

---

### `scripts/validate_documents.py` - Validate Rule Documents

Validate all markdown documents in `extracted-rules/` folder for correct structure and metadata.

**Usage:**
```bash
python3 scripts/validate_documents.py
```

**Validation Checks:**
- YAML frontmatter present
- Required metadata fields (`source`, `last_update_date`, `document_type`, `section`)
- Valid document type (core-rules, faq, team-rules, ops, killzone)
- Filename pattern (`[a-z0-9-]+\.md`)
- No executable code blocks

**Output:**
```
✅ rules-1-phases.md
✅ rules-2-actions.md
❌ invalid-doc.md
   - Missing YAML frontmatter
============================================================
Results: 16 valid, 1 invalid
============================================================
```

**Exit Codes:**
- `0` - All documents valid
- `1` - One or more validation errors

**Use Cases:**
- Before ingestion to catch malformed files
- After rule extraction from PDFs
- CI/CD validation gates
- Pre-commit hooks

---

## Support

For issues or questions:
- Check logs in `./logs/` directory
- Run health check: `python -m src.cli health -v`
- Validate documents: `python3 scripts/validate_documents.py`
- Review documentation in `/docs`
