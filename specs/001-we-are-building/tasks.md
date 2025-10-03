# Implementation Tasks: Kill Team Rules Discord Bot

**Feature Branch**: `001-we-are-building`
**Generated**: 2025-10-02
**Total Tasks**: 97

## Task Execution Guide

**Parallel Execution**: Tasks marked with `[P]` can be executed in parallel with other `[P]` tasks in the same phase.

**Dependencies**: Each task lists prerequisites. Do not start a task until its dependencies are complete.

**File Paths**: All file paths are relative to repository root.

---

## Phase 1: Project Setup (T001-T006) ✅

### [X] T001: Initialize Python project structure
**File**: Project root
**Dependencies**: None
**Description**: Create directory structure for Python project
```
src/
├── models/
├── services/
│   ├── rag/
│   ├── discord/
│   ├── llm/
│   └── ingestion/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

config/
data/
logs/
```

---

### [X] T002: Create requirements.txt [P]
**File**: `requirements.txt`
**Dependencies**: T001
**Description**: Define all Python dependencies
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
pytest-mock==3.12.0
freezegun==1.4.0
hypothesis==6.92.0
structlog==23.2.0
pydantic==2.5.0
python-dotenv==1.0.0
ruff==0.1.0
mypy==1.7.0
bandit==1.7.5
safety==2.3.5
radon==6.0.1
pytest-cov==4.1.0
```

---

### [X] T003: Create .env template [P]
**File**: `config/.env.template`
**Dependencies**: T001
**Description**: Create environment variable template
```bash
# Discord
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# LLM Providers (configure at least one)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...

# LLM Selection
DEFAULT_LLM_PROVIDER=claude

# RAG Configuration
VECTOR_DB_PATH=./data/chroma_db
EMBEDDING_MODEL=text-embedding-3-small

# Logging
LOG_LEVEL=INFO
```

---

### [X] T004: Setup linting and type checking config [P]
**File**: `pyproject.toml`
**Dependencies**: T001
**Description**: Configure ruff, mypy, pytest
```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
```

---

### [X] T005: Create .gitignore [P]
**File**: `.gitignore`
**Dependencies**: None
**Description**: Ignore venv, .env, data/, __pycache__, etc.

---

### [X] T006: Setup pre-commit hooks [P]
**File**: `.pre-commit-config.yaml`
**Dependencies**: T002, T004
**Description**: Configure ruff, mypy, bandit for pre-commit

---

## Phase 2: Contract Tests (T007-T018) - TDD Phase ✅

### [X] T007: RAG pipeline contract test - Retrieve with high relevance [P]
**File**: `tests/contract/test_rag_pipeline.py`
**Dependencies**: T006
**Description**: Implement contract test from `contracts/rag-pipeline.md` - Contract Test 1
- Mock vector DB with "rules-1-phases.md" containing "Movement Phase"
- Query: "What can I do during movement?"
- Assert: avg_relevance ≥ 0.8, meets_threshold = True, chunk metadata contains "Movement Phase"

---

### [X] T008: RAG pipeline contract test - Retrieve with low relevance [P]
**File**: `tests/contract/test_rag_pipeline.py`
**Dependencies**: T006
**Description**: Implement Contract Test 2
- Mock vector DB with only "weapon-rules.md"
- Query: "How do I cook pasta?"
- Assert: meets_threshold = False, document_chunks = [], avg_relevance < 0.6

---

### [X] T009: RAG pipeline contract test - Chunk ordering [P]
**File**: `tests/contract/test_rag_pipeline.py`
**Dependencies**: T006
**Description**: Implement Contract Test 3
- Assert: document_chunks[0].relevance_score ≥ document_chunks[1].relevance_score
- Assert: relevance_scores matches document_chunks order

---

### [X] T010: RAG pipeline contract test - Metadata completeness [P]
**File**: `tests/contract/test_rag_pipeline.py`
**Dependencies**: T006
**Description**: Implement Contract Test 4
- Assert: Every chunk has metadata["source"], metadata["doc_type"] in {"core-rules", "faq", "team-rules", "ops", "killzone"}, parseable last_update_date

---

### [X] T011: RAG pipeline contract test - Ingest idempotency [P]
**File**: `tests/contract/test_rag_pipeline.py`
**Dependencies**: T006
**Description**: Implement Contract Test 5
- Ingest document with UUID1
- Re-ingest same UUID1 with updated content
- Assert: Old embeddings removed, new embeddings created, documents_processed = 1

---

### [X] T012: RAG pipeline contract test - Performance SLA [P]
**File**: `tests/contract/test_rag_pipeline.py`
**Dependencies**: T006
**Description**: Implement Contract Test 6
- Mock vector DB with 100 documents
- Assert: Response time ≤ 5 seconds (p95)

---

### [X] T013: LLM adapter contract test - Provider consistency [P]
**File**: `tests/contract/test_llm_adapter.py`
**Dependencies**: T006
**Description**: Implement Contract Test 1 from `contracts/llm-adapter.md`
- Same prompt + context across all mock providers
- Assert: All answers mention factual information, confidence ≥ 0.6, token counts within 20%

---

### [X] T014: LLM adapter contract test - Confidence thresholds [P]
**File**: `tests/contract/test_llm_adapter.py`
**Dependencies**: T006
**Description**: Implement Contract Test 2
- High-quality context (relevance > 0.9) → confidence ≥ 0.7
- Low-quality context (relevance < 0.5) → confidence ≤ 0.6

---

### [X] T015: LLM adapter contract test - Citation inclusion [P]
**File**: `tests/contract/test_llm_adapter.py`
**Dependencies**: T006
**Description**: Implement Contract Test 3
- include_citations = True
- Assert: answer_text contains citation format, citations_included = True

---

### [X] T016: LLM adapter contract test - Timeout enforcement [P]
**File**: `tests/contract/test_llm_adapter.py`
**Dependencies**: T006
**Description**: Implement Contract Test 4
- Mock slow LLM API
- Assert: Raises TimeoutError within timeout_seconds

---

### [X] T017: LLM adapter contract test - Token tracking [P]
**File**: `tests/contract/test_llm_adapter.py`
**Dependencies**: T006
**Description**: Implement Contract Test 5
- Assert: token_count > 0, token_count = prompt_tokens + completion_tokens

---

### [X] T018: LLM adapter contract test - Rate limit handling [P]
**File**: `tests/contract/test_llm_adapter.py`
**Dependencies**: T006
**Description**: Implement Contract Test 6
- Mock rate limit error
- Assert: Raises RateLimitError, error logged

---

## Phase 3: Data Models (T019-T025) ✅

### [X] T019: Implement UserQuery model [P]
**File**: `src/models/user_query.py`
**Dependencies**: T018
**Description**: Create UserQuery dataclass from `data-model.md`
- All fields: query_id, user_id (hashed), channel_id, message_text, sanitized_text, timestamp, conversation_context_id, pii_redacted
- Validation: message_text max 2000 chars, user_id SHA-256 hashed, timestamp within 7 days

---

### [X] T020: Implement RuleDocument model [P]
**File**: `src/models/rule_document.py`
**Dependencies**: T018
**Description**: Create RuleDocument dataclass
- All fields including metadata dict with YAML frontmatter
- Validation: filename pattern, document_type enum, last_update_date parsing
- Hash computation (SHA-256)

---

### [X] T021: Implement RAGContext model [P]
**File**: `src/models/rag_context.py`
**Dependencies**: T018
**Description**: Create RAGContext and DocumentChunk dataclasses
- DocumentChunk: chunk_id, document_id, text, header, header_level, metadata, relevance_score, position_in_doc
- RAGContext: context_id, query_id, document_chunks list, relevance_scores, total_chunks, avg_relevance, meets_threshold

---

### [X] T022: Implement BotResponse model [P]
**File**: `src/models/bot_response.py`
**Dependencies**: T018
**Description**: Create BotResponse and Citation dataclasses
- Citation: document_name, section, quote, document_type, last_update_date
- BotResponse: response_id, query_id, answer_text, citations, confidence_score, rag_score, validation_passed, llm_provider, token_count, latency_ms, timestamp

---

### [X] T023: Implement PDFUpdate model [P]
**File**: `src/models/pdf_update.py`
**Dependencies**: T018
**Description**: Create PDFUpdate dataclass
- Fields: update_id, pdf_filename, pdf_url, download_date, last_update_date, version, file_size_bytes, file_hash, extraction_status, error_message

---

### [X] T024: Implement IngestionJob model [P]
**File**: `src/models/ingestion_job.py`
**Dependencies**: T018
**Description**: Create IngestionJob dataclass
- Fields including extraction_token_count, extraction_cost_usd, extraction_latency_ms for LLM-based PDF processing

---

### [X] T025: Implement ConversationContext model [P]
**File**: `src/models/conversation_context.py`
**Dependencies**: T018
**Description**: Create ConversationContext and Message dataclasses
- In-memory only (not persisted)
- TTL-based expiration logic (30 minutes)

---

## Phase 4: Shared Utilities (T026-T031) ✅

### [X] T026: Implement configuration management [P]
**File**: `src/lib/config.py`
**Dependencies**: T025
**Description**: Load .env variables, provide Config dataclass with validation

---

### [X] T027: Implement structured logging [P]
**File**: `src/lib/logging.py`
**Dependencies**: T025
**Description**: Setup structlog with correlation IDs, PII redaction middleware

---

### [X] T028: Implement input validation and sanitization [P]
**File**: `src/lib/validation.py`
**Dependencies**: T025
**Description**: Discord message sanitization, prompt injection detection, markdown validation

---

### [X] T029: Implement token counter utility [P]
**File**: `src/lib/tokens.py`
**Dependencies**: T025
**Description**: Token counting function for chunking (tiktoken library)

---

### [X] T030: Implement GDPR data cleanup scheduler [P]
**File**: `src/lib/gdpr.py`
**Dependencies**: T025
**Description**: 7-day retention enforcement, deletion audit logging

---

### [X] T031: Implement metrics and observability [P]
**File**: `src/lib/metrics.py`
**Dependencies**: T025
**Description**: Performance metrics tracking (latency, token usage, confidence scores)

---

## Phase 5: RAG Pipeline Implementation (T032-T039) ✅

### [X] T032: Implement markdown chunking service
**File**: `src/services/rag/chunker.py`
**Dependencies**: T029
**Description**: Lazy chunking at ## headers when >8192 tokens
- Check token count first, keep whole document if ≤8192
- Split at ## boundaries if needed, fallback to ### if section >8192
- No overlap between chunks

---

### [X] T033: Implement embedding service
**File**: `src/services/rag/embeddings.py`
**Dependencies**: T026
**Description**: OpenAI text-embedding-3-small integration
- Generate embeddings for document chunks
- Track model version in metadata

---

### [X] T034: Implement vector database service
**File**: `src/services/rag/vector_db.py`
**Dependencies**: T033
**Description**: Chroma integration with persistence
- Store/retrieve embeddings
- Metadata filtering support

---

### [X] T035: Implement RAG retrieval service
**File**: `src/services/rag/retriever.py`
**Dependencies**: T021, T034
**Description**: Implement retrieve() method from RAG contract
- Query vector DB
- Return RAGContext with sorted chunks by relevance
- Apply threshold filtering

---

### [X] T036: Implement RAG ingestion service
**File**: `src/services/rag/ingestor.py`
**Dependencies**: T020, T032, T033, T034
**Description**: Implement ingest() method from RAG contract
- Chunk markdown documents
- Generate embeddings
- Store in vector DB with metadata

---

### [X] T037: Implement document validation service [P]
**File**: `src/services/rag/validator.py`
**Dependencies**: T020
**Description**: Validate markdown files have YAML frontmatter, correct document_type enum

---

### [X] T038: Implement caching layer for RAG queries [P]
**File**: `src/services/rag/cache.py`
**Dependencies**: T035
**Description**: 5-minute TTL cache for same query + context_key

---

### [X] T039: Unit tests for RAG services [P]
**File**: `tests/unit/test_rag_services.py`
**Dependencies**: T032-T038
**Description**: 80%+ coverage for chunker, embeddings, retriever, ingestor

---

## Phase 6: LLM Provider Adapters (T040-T047) ✅

### [X] T040: Implement LLM base interface
**File**: `src/services/llm/base.py`
**Dependencies**: T022
**Description**: Abstract base class for LLMProvider with generate() and extract_pdf() methods

---

### [X] T041: Implement Claude adapter [P]
**File**: `src/services/llm/claude.py`
**Dependencies**: T040
**Description**: Anthropic Claude API integration
- generate() for answering queries
- extract_pdf() for PDF to markdown extraction
- Confidence scoring (default 0.8)
- Token usage tracking

---

### [X] T042: Implement ChatGPT adapter [P]
**File**: `src/services/llm/chatgpt.py`
**Dependencies**: T040
**Description**: OpenAI ChatGPT API integration
- Same methods as Claude adapter
- Logprobs-based confidence scoring
- Token usage tracking

---

### [X] T043: Implement Gemini adapter [P]
**File**: `src/services/llm/gemini.py`
**Dependencies**: T040
**Description**: Google Gemini API integration
- Same methods as Claude adapter
- Safety ratings → confidence mapping
- Token usage tracking

---

### [X] T044: Implement LLM provider factory
**File**: `src/services/llm/factory.py`
**Dependencies**: T041, T042, T043
**Description**: Get provider by config (claude/chatgpt/gemini)

---

### [X] T045: Implement response validation service
**File**: `src/services/llm/validator.py`
**Dependencies**: T022
**Description**: Combined LLM confidence + RAG retrieval score validation (FR-013)

---

### [X] T046: Implement rate limiting for LLM calls [P]
**File**: `src/services/llm/rate_limiter.py`
**Dependencies**: T040
**Description**: Token bucket per-provider, per-user throttling (10 queries/minute)

---

### [X] T047: Unit tests for LLM adapters [P]
**File**: `tests/unit/test_llm_adapters.py`
**Dependencies**: T041-T046
**Description**: Mock API calls, test token tracking, confidence scoring, error handling

---

## Phase 7: Discord Bot Integration - Orchestrator Pattern (T048-T056)

**Architecture Note**: Phase 7 uses the **Orchestrator Pattern** where a single orchestrator class coordinates all services (RAG, LLM, validation, rate limiting) without complex layering.

### T048: Implement Discord client setup
**File**: `src/services/discord/client.py`
**Dependencies**: T026
**Description**: discord.py client initialization using raw event handlers (on_message, on_ready)
- Use discord.Intents with message_content and guild_messages
- No commands extension, only raw events

---

### T049: Implement message handler for @ mentions
**File**: `src/services/discord/handlers.py`
**Dependencies**: T019, T048
**Description**: Raw on_message event handler - parse @ mentions, extract query text, create UserQuery
- **Non-question mentions** (e.g., "@bot hello"): Handled by AI agent prompt with friendly acknowledgment guidelines
- Use raw discord.py events (not commands framework)

---

### T050: Implement conversation context manager
**File**: `src/services/discord/context_manager.py`
**Dependencies**: T025
**Description**: Track message history only (NOT RAG chunks) by channel_id:user_id, TTL-based cleanup
- Store last 10 messages (user + bot turns)
- No RAG context in conversation state

---

### T051: Implement response formatter with feedback buttons
**File**: `src/services/discord/formatter.py`
**Dependencies**: T022
**Description**: Format BotResponse with citations, split long messages, create embeds
- **Add reaction buttons**: 👍 (helpful) and 👎 (not helpful) to each response
- Buttons for feedback tracking (logged for analytics)

---

### T052: Implement main bot orchestrator
**File**: `src/services/discord/bot.py`
**Dependencies**: T035, T044, T045, T049, T050, T051
**Description**: **Orchestrator Pattern** - single class coordinates full flow: receive query → RAG retrieval → LLM generation → validation → send response
- Simple linear flow, no complex layering
- Orchestrates all Phase 5 + Phase 6 services

---

### T053: Implement error handling and retry logic
**File**: `src/services/discord/error_handler.py`
**Dependencies**: T052
**Description**: Handle Discord API errors, LLM timeouts, rate limits with user-friendly messages

---

### T054: Implement health check endpoint [P]
**File**: `src/services/discord/health.py`
**Dependencies**: T034, T048
**Description**: Check Discord connection, vector DB status, LLM provider availability

---

### T055: Implement security logging for Discord events [P]
**File**: `src/services/discord/security.py`
**Dependencies**: T027
**Description**: Log security-sensitive events (malformed messages, rate limit hits, prompt injection attempts)

---

### T056: Unit tests for Discord services [P]
**File**: `tests/unit/test_discord_services.py`
**Dependencies**: T048-T055
**Description**: Mock Discord events, test message parsing, context tracking, response formatting, reaction button handling

---

### T056.1: Implement feedback logging service [P]
**File**: `src/services/discord/feedback_logger.py`
**Dependencies**: T027
**Description**: Log user feedback from helpful/not helpful reaction buttons
- Handle on_reaction_add event for 👍👎 reactions
- Log UserFeedback entity to structured logs (or optional DB)
- Track response_id, query_id, user_id (hashed), feedback_type, timestamp
- Support analytics queries (response quality, problematic queries, LLM provider performance)

---

## Phase 8: Integration Tests (T057-T062)

### T057: Integration test - Basic query flow [P]
**File**: `tests/integration/test_basic_query.py`
**Dependencies**: T056
**Description**: Test scenario from `quickstart.md` Test 1
- Mock Discord @ mention with "What actions can I take during the movement phase?"
- Assert: Response within 30s, citations included, confidence displayed

---

### T058: Integration test - Ambiguous query [P]
**File**: `tests/integration/test_ambiguous_query.py`
**Dependencies**: T056
**Description**: Test scenario from quickstart Test 2
- Query: "What about barricades?"
- Assert: Bot asks clarifying questions or provides multiple options

---

### T059: Integration test - Out-of-scope query [P]
**File**: `tests/integration/test_out_of_scope.py`
**Dependencies**: T056
**Description**: Test scenario from quickstart Test 3
- Query: "How do I paint my miniatures?"
- Assert: Bot recognizes out-of-scope, helpful suggestion

---

### T060: Integration test - Concurrent users [P]
**File**: `tests/integration/test_concurrent_users.py`
**Dependencies**: T056
**Description**: Test scenario from quickstart Test 4
- Two users in different channels ask simultaneously
- Assert: No cross-talk, both receive correct contextual responses

---

### T061: Integration test - Low confidence response [P]
**File**: `tests/integration/test_low_confidence.py`
**Dependencies**: T056
**Description**: Test scenario from quickstart Test 5
- Vague query
- Assert: Bot declines to answer, confidence logged

---

## Phase 9: CLI Tools (T063-T070)

### T063: Implement CLI - ingest_rules command [P]
**File**: `src/cli/ingest_rules.py`
**Dependencies**: T036
**Description**: Load markdown files from extracted-rules/, ingest into vector DB
- Progress output, validation errors, embedding count

---

### T064: Implement CLI - test_query command [P]
**File**: `src/cli/test_query.py`
**Dependencies**: T052
**Description**: Test RAG + LLM locally without Discord
- Show retrieved chunks, confidence, latency, token count

---

### T065: Implement CLI - gdpr_delete command [P]
**File**: `src/cli/gdpr_delete.py`
**Dependencies**: T030
**Description**: Delete user's conversation data by user_id
- Audit trail logging

---

### T066: Implement CLI - run_bot command [P]
**File**: `src/cli/run_bot.py`
**Dependencies**: T052
**Description**: Start Discord bot in dev or production mode

---

### T067: Implement CLI - health_check command [P]
**File**: `src/cli/health_check.py`
**Dependencies**: T054
**Description**: Run health checks, output system status

---

### T068: Implement CLI main entry point
**File**: `src/cli/__main__.py`
**Dependencies**: T063-T067
**Description**: Argument parsing, route to correct CLI command

---

### T069: Add CLI help documentation [P]
**File**: `src/cli/help.py`
**Dependencies**: T068
**Description**: Generate help text for all CLI commands

---

### T070: Unit tests for CLI commands [P]
**File**: `tests/unit/test_cli.py`
**Dependencies**: T063-T069
**Description**: Test argument parsing, command execution, output formatting

---

## Phase 10: Quality & Polish (T071-T085)

### T071: Setup CI/CD pipeline [P]
**File**: `.github/workflows/ci.yml`
**Dependencies**: T070
**Description**: GitHub Actions workflow
- Run ruff, mypy, bandit
- Run pytest with coverage
- Fail if coverage <80%, security issues found

---

### T072: Add code complexity checks [P]
**File**: `.github/workflows/quality.yml`
**Dependencies**: T070
**Description**: Radon complexity checks (max cyclomatic complexity 10)

---

### T073: Performance benchmark tests [P]
**File**: `tests/performance/test_latency.py`
**Dependencies**: T062
**Description**: Measure p50, p95, p99 latency for full query flow
- Assert: p95 < 30 seconds

---

### T074: Token usage monitoring tests [P]
**File**: `tests/performance/test_token_usage.py`
**Dependencies**: T062
**Description**: Track token counts per query, assert within budget

---

### T075: Add missing unit tests for coverage gaps [P]
**File**: `tests/unit/test_coverage_gaps.py`
**Dependencies**: T070
**Description**: Identify and test uncovered code paths to reach 80%+

---

### T076: Create Docker configuration [P]
**File**: `Dockerfile`, `docker-compose.yml`
**Dependencies**: T002
**Description**: Containerize bot for production deployment

---

### T077: Create deployment documentation [P]
**File**: `docs/deployment.md`
**Dependencies**: T076
**Description**: Production deployment guide (Docker, environment variables, secrets)

---

### T078: Create architecture documentation [P]
**File**: `docs/architecture.md`
**Dependencies**: T062
**Description**: System architecture diagram, component interactions

---

### T079: Create API documentation [P]
**File**: `docs/api.md`
**Dependencies**: T062
**Description**: Document internal APIs (RAG pipeline, LLM adapters)

---

### T080: Add logging best practices enforcement [P]
**File**: `docs/logging-guide.md`
**Dependencies**: T027
**Description**: Guide for structured logging, PII redaction, correlation IDs

---

### T081: Security audit [P]
**File**: `docs/security-audit.md`
**Dependencies**: T070
**Description**: Review input validation, secrets management, rate limiting, GDPR compliance

---

### T082: Add observability dashboards [P]
**File**: `docs/observability.md`
**Dependencies**: T031
**Description**: Prometheus + Grafana dashboard configurations

---

### T083: Load testing [P]
**File**: `tests/load/test_concurrent_load.py`
**Dependencies**: T062
**Description**: Simulate 5 concurrent users, verify no degradation

---

### T084: Create runbook for common issues [P]
**File**: `docs/runbook.md`
**Dependencies**: T070
**Description**: Troubleshooting guide (low RAG precision, high latency, LLM API errors)

---

### T085: Implement NFR-002 validation [P]
**File**: `tests/quality/test_rag_precision_recall.py`
**Dependencies**: T062
**Description**: Validate RAG retrieval meets NFR-002 thresholds
- Measure precision ≥90% using labeled test dataset
- Measure recall ≥70% using labeled test dataset
- Create test dataset with 50+ queries and known correct rule citations
- Assert thresholds met in CI/CD pipeline
- Document precision/recall measurement methodology

---

### T086: Final integration smoke test
**File**: `tests/integration/test_smoke.py`
**Dependencies**: T083
**Description**: End-to-end test with real Discord mock, vector DB, all components

---

## Phase 11: PDF Extraction & Rule Updates (T087-T096)

**Note**: These tasks are for the rule update pipeline - placed at end of queue per user request.

### T087: Implement PDF download service
**File**: `src/services/ingestion/downloader.py`
**Dependencies**: T023
**Description**: Download PDFs from Warhammer Community API
- Compute PDF hash (SHA-256)
- Check for duplicates before download
- **Error handling**: Network errors (retry with exponential backoff), 404s (log and skip), timeouts (configurable timeout with fallback)

---

### T088: Implement LLM-based PDF extraction service
**File**: `src/services/ingestion/pdf_extractor.py`
**Dependencies**: T044
**Description**: Use LLM API to extract PDF → markdown
- Structured extraction prompt with YAML frontmatter requirements
- Token usage tracking
- Validation warnings for missing metadata

---

### T089: Implement markdown post-processor
**File**: `src/services/ingestion/markdown_processor.py`
**Dependencies**: T088
**Description**: Validate extracted markdown
- Check YAML frontmatter completeness
- Validate document_type enum
- Fix common formatting issues

---

### T090: Implement extraction cache
**File**: `src/services/ingestion/cache.py`
**Dependencies**: T088
**Description**: Cache PDF hash → markdown mapping
- Avoid re-extracting same PDF
- Budget monitoring

---

### T091: Implement ingestion job orchestrator
**File**: `src/services/ingestion/job_runner.py`
**Dependencies**: T024, T087, T088, T089, T036
**Description**: Orchestrate full ingestion flow
- Download PDF → Extract → Process → Ingest → Re-index RAG
- Track token costs, errors, warnings

---

### T092: Implement CLI - download_pdf command
**File**: `src/cli/download_pdf.py`
**Dependencies**: T091
**Description**: CLI command to trigger PDF ingestion pipeline
- Output: tokens used, estimated cost, latency, created markdown files

---

### T093: Unit tests for ingestion services [P]
**File**: `tests/unit/test_ingestion_services.py`
**Dependencies**: T087-T091
**Description**: Mock LLM API, test PDF extraction, validation, caching

---

### T094: Integration test - PDF to RAG flow [P]
**File**: `tests/integration/test_pdf_ingestion.py`
**Dependencies**: T092
**Description**: End-to-end test: Download mock PDF → Extract → Ingest → Query RAG

---

### T095: Budget monitoring and alerts [P]
**File**: `src/services/ingestion/budget_monitor.py`
**Dependencies**: T091
**Description**: Track monthly extraction token costs
- Alert if threshold exceeded

---

### T096: Documentation for rule update process [P]
**File**: `docs/rule-updates.md`
**Dependencies**: T092
**Description**: Guide for updating rules (download new PDFs, re-ingest, test)

---

## Parallel Execution Examples

### Setup Phase (after T001)
```bash
# Run in parallel
T002, T003, T004, T005, T006
```

### Contract Tests Phase
```bash
# All contract tests can run in parallel
T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018
```

### Data Models Phase
```bash
# All models are independent
T019, T020, T021, T022, T023, T024, T025
```

### Utilities Phase
```bash
# All utilities are independent
T026, T027, T028, T029, T030, T031
```

### LLM Adapters Phase
```bash
# All 3 adapters can be built in parallel
T041, T042, T043
```

### Integration Tests Phase
```bash
# All integration tests are independent
T057, T058, T059, T060, T061, T062
```

### CLI Tools Phase
```bash
# Most CLI commands are independent
T063, T064, T065, T066, T067
```

### Quality Phase
```bash
# Many polish tasks can run in parallel
T071, T072, T073, T074, T075, T076, T077, T078, T079, T080, T081, T082, T083, T084
```

---

## Task Summary

| Phase | Tasks | Can Parallelize |
|-------|-------|-----------------|
| Setup | T001-T006 | 5 of 6 |
| Contract Tests | T007-T018 | All 12 |
| Data Models | T019-T025 | All 7 |
| Utilities | T026-T031 | All 6 |
| RAG Pipeline | T032-T039 | 3 of 8 |
| LLM Adapters | T040-T047 | 5 of 8 |
| Discord Bot | T048-T056.1 | 4 of 10 |
| Integration Tests | T057-T062 | All 6 |
| CLI Tools | T063-T070 | 7 of 8 |
| Quality & Polish | T071-T085 | 14 of 15 |
| PDF Extraction | T086-T095 | 4 of 10 |
| **Total** | **97 tasks** | **~61 parallelizable** |

---

**Estimated Completion**: 40-50 hours with parallel execution, 120+ hours sequential
