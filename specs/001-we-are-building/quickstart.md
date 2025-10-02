# Kill Team Bot - Developer Quickstart

**Last Updated**: 2025-10-02

## Prerequisites

- Python 3.11+ installed
- Discord Developer account (for bot token)
- LLM API key (Anthropic/OpenAI/Google - at least one)
- Git

## Initial Setup

### 1. Clone and Install Dependencies

```bash
# Clone repository
git clone <repo-url>
cd kill-team-rules-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip3 install -r requirements.txt
```

**Expected `requirements.txt`**:
```
discord.py==2.3.2
langchain==0.1.0
llama-index==0.9.0
chromadb==0.4.0
anthropic==0.8.0
openai==1.6.0
google-generativeai==0.3.0
pytest==7.4.0
pytest-asyncio==0.21.0
structlog==23.2.0
pydantic==2.5.0
python-dotenv==1.0.0
# Note: No PDF parsing libraries needed - using LLM-based extraction
```

### 2. Configure Environment Variables

```bash
# Copy template
cp config/.env.template .env

# Edit .env with your API keys
```

**`.env` file structure**:
```bash
# Discord
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# LLM Providers (configure at least one)
ANTHROPIC_API_KEY=sk-ant-...  # For Claude
OPENAI_API_KEY=sk-...          # For ChatGPT
GOOGLE_API_KEY=AIza...         # For Gemini

# LLM Selection
DEFAULT_LLM_PROVIDER=claude  # or "chatgpt", "gemini"

# RAG Configuration
VECTOR_DB_PATH=./data/chroma_db
EMBEDDING_MODEL=text-embedding-3-small

# Logging
LOG_LEVEL=INFO  # DEBUG for development, INFO for production
```

### 3. Initialize Vector Database

```bash
# Ingest existing markdown rules
python -m src.cli.ingest_rules --source extracted-rules/

# Expected output:
# ✓ Ingested 12 documents
# ✓ Created 247 embeddings
# ✓ Duration: 23.4s
```

### 4. Verify Installation

```bash
# Run tests
pytest tests/

# Expected: All tests pass (or skip integration tests if no API keys)
```

---

## Running the Bot

### Development Mode

```bash
# Start bot with auto-reload
python -m src.cli.run_bot --dev

# Expected output:
# [INFO] Discord bot starting...
# [INFO] Connected as KillTeamBot#1234
# [INFO] LLM provider: claude (claude-3-sonnet-20240229)
# [INFO] Vector DB: 247 embeddings loaded
# [INFO] Ready to answer questions!
```

### Production Mode

```bash
# Run as background service
nohup python -m src.cli.run_bot > logs/bot.log 2>&1 &

# Or use Docker
docker-compose up -d
```

---

## Manual Testing Scenarios

### Test 1: Basic Query

**Discord**: `@KillTeamBot What actions can I take during the movement phase?`

**Expected Response**:
```
According to rules-1-phases.md (Movement Phase):

During the Movement Phase, operatives can perform the following actions:
- **Move**: Traverse terrain up to their Movement characteristic
- **Dash**: Move an additional distance equal to Movement ÷ 2
- **Climb/Jump**: Scale vertical terrain or leap gaps

Source: Core Rules v3.1, Section 2.3
Confidence: 92%
```

**Validation**:
- Response received within 30 seconds ✓
- Citations included ✓
- Confidence score displayed ✓

### Test 2: Ambiguous Query

**Discord**: `@KillTeamBot What about barricades?`

**Expected Response**:
```
I found multiple rules about barricades. Which aspect are you asking about?

1. **Cover Rules**: How barricades provide cover (killzone-gallowdark.md)
2. **Traversing Terrain**: Moving through barricades (rules-4-killzones.md)
3. **Line of Sight**: Shooting through barricades (weapon-rules.md)

Please clarify your question!
```

**Validation**:
- Bot asks for clarification ✓
- Multiple options presented ✓

### Test 3: Out-of-Scope Query

**Discord**: `@KillTeamBot How do I paint my miniatures?`

**Expected Response**:
```
I couldn't find relevant Kill Team 3rd Edition rules for your question. I specialize in game rules, not hobby or painting advice.

Try rephrasing if you have a rules question, or check out Warhammer's painting guides!
```

**Validation**:
- Bot recognizes out-of-scope ✓
- Helpful suggestion provided ✓

### Test 4: Concurrent Users

**Setup**: Two users in different channels ask simultaneously

**User 1 (channel #general)**: `@KillTeamBot Explain the shooting phase`
**User 2 (channel #rules-help)**: `@KillTeamBot What is overwatch?`

**Expected**:
- Both users receive correct, contextual responses ✓
- No cross-talk between conversations ✓
- Both responses < 30 seconds ✓

**Validation**:
```python
# Check logs for conversation isolation
# User 1 context_key: "general:user1_id"
# User 2 context_key: "rules-help:user2_id"
```

### Test 5: Low Confidence Response

**Discord**: `@KillTeamBot vague incomprehensible question xyz`

**Expected Response**:
```
I'm not confident I understand your question. Could you rephrase or provide more details?

My confidence in answering was below the threshold (score: 0.42).
```

**Validation**:
- Bot declines to answer ✓
- Confidence score logged (DEBUG level) ✓

---

## CLI Tools

### Ingest New Rules

```bash
# Download latest PDF from Warhammer Community
python -m src.cli.download_pdf --url https://warhammer.com/rules/killteam-faq-2024.pdf

# Expected:
# ✓ Downloaded killteam-faq-2024.pdf (2.3 MB)
# ✓ Extracting with LLM (Claude)...
# ✓ Extraction complete: 12,458 tokens used ($0.15 estimated cost)
# ✓ Created faq-core-rules-2024.md
# ✓ Validated YAML frontmatter: OK
# ✓ Re-ingested into vector DB (15 new embeddings)
# ✓ Total latency: 45.2s
```

### Test Query (Without Discord)

```bash
# Test RAG retrieval locally
python -m src.cli.test_query "What is the movement phase?"

# Expected output:
# Query: "What is the movement phase?"
#
# Retrieved Chunks (3):
# 1. [rules-1-phases.md] Relevance: 0.94
#    "The Movement Phase is the first phase..."
#
# 2. [game-sequence.md] Relevance: 0.87
#    "Each turning point begins with Movement..."
#
# Generated Answer:
# "According to rules-1-phases.md: The Movement Phase is when..."
#
# Confidence: 0.89
# Latency: 4.2s
# Tokens: 1247
```

### Manual Data Cleanup (GDPR)

```bash
# Delete user's conversation data
python -m src.cli.gdpr_delete --user-id <discord_user_id>

# Expected:
# ✓ Deleted 14 query logs for user <hash>
# ✓ Deleted 14 response logs
# ✓ Audit trail logged
```

---

## Troubleshooting

### Bot Not Responding

**Check**:
1. Bot has "Read Messages" and "Send Messages" permissions in channel
2. Bot is online (check Discord server member list)
3. @ mention is correct (not just typing bot name)

**Logs**:
```bash
tail -f logs/bot.log | grep ERROR
```

### Low RAG Precision

**Symptom**: Bot gives irrelevant answers

**Check**:
```bash
# Re-run ingestion with validation
python -m src.cli.ingest_rules --source extracted-rules/ --validate

# Look for warnings about malformed markdown
```

**Fix**:
- Ensure markdown files have YAML frontmatter
- Check for broken headers or formatting

### LLM API Errors

**Symptom**: `AuthenticationError` or `RateLimitError`

**Check**:
```bash
# Verify API key
python -m src.cli.test_llm --provider claude

# Expected: "✓ Claude API authenticated successfully"
```

**Fix**:
- Verify `.env` file has correct API key
- Check rate limits on provider dashboard

### High Latency (>30s)

**Symptom**: Responses timeout

**Check**:
```bash
# Profile slow queries
python -m src.cli.test_query "test" --profile

# Expected output shows bottleneck:
# - RAG retrieval: 0.8s
# - LLM generation: 23.1s <-- Slow!
```

**Fix**:
- Reduce `max_tokens` in config (default 1000 → 500)
- Switch to faster LLM model (GPT-4-turbo → GPT-3.5-turbo)

---

## Next Steps

1. **Run Contract Tests**: `pytest tests/contract/`
2. **Deploy to Server**: See `docs/deployment.md` (future)
3. **Configure CI/CD**: See `.github/workflows/` (future)
4. **Monitor Metrics**: Set up Prometheus + Grafana (future)

---

## Support

- **Bugs**: Open GitHub issue
- **Questions**: Check `docs/faq.md`
- **Constitution**: See `.specify/memory/constitution.md` for development principles
