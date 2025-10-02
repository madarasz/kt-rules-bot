# Research & Technical Decisions

**Feature**: Kill Team Rules Discord Bot
**Date**: 2025-10-02

## Research Areas

### 1. RAG Framework Selection

**Decision**: LangChain with LlamaIndex hybrid approach

**Rationale**:
- LangChain provides excellent LLM provider abstraction (supports Claude, Gemini, ChatGPT out-of-box)
- LlamaIndex specializes in document indexing and retrieval optimization
- Both have strong Python ecosystem support and active communities
- Combined approach: LlamaIndex for ingestion/indexing, LangChain for query orchestration and LLM switching

**Alternatives Considered**:
- **Haystack**: More opinionated, less flexible for multi-LLM support
- **Custom RAG**: High development overhead, reinventing tested patterns
- **LangChain only**: Less optimized retrieval than LlamaIndex for document-heavy use cases

### 2. Vector Database Selection

**Decision**: Chroma (local deployment) with migration path to Pinecone (cloud)

**Rationale**:
- Chroma: Free, local, excellent for MVP and development
- Simple Python API, minimal setup overhead
- Persistence to disk for durability
- Can migrate to Pinecone if scale requirements increase beyond 5 concurrent users

**Alternatives Considered**:
- **Pinecone**: Requires paid tier, overkill for initial 50-100 daily queries
- **Weaviate**: More complex deployment, unnecessary for single-instance bot
- **FAISS**: No built-in persistence, requires custom metadata management

### 3. Discord Library

**Decision**: discord.py (v2.x)

**Rationale**:
- Official Python library for Discord API
- Async/await support (essential for concurrent user handling)
- Strong typing with py.typed
- Excellent documentation and community support
- Built-in rate limiting and retry logic

**Alternatives Considered**:
- **Pycord**: Fork of discord.py, less actively maintained
- **Direct REST API**: Requires reimplementing rate limiting, WebSocket management

### 4. PDF Extraction

**Decision**: LLM-based PDF processing (via existing LLM provider APIs)

**Rationale**:
- Claude, ChatGPT, and Gemini all support native PDF upload and processing
- Better structure preservation: LLMs understand semantic structure (headers, lists, tables) vs raw text extraction
- Format resilience: Handles PDF layout changes naturally (addresses NFR-004 requirement)
- Simpler architecture: No additional parsing libraries needed
- Reuses existing LLM abstraction layer (Constitution Principle II compliance)
- Cost acceptable: Ingestion is infrequent (on-demand only, not per-query)

**Implementation**:
```python
# Upload PDF to LLM with structured extraction prompt
def extract_pdf_to_markdown(pdf_path: Path, llm_provider: LLMProvider) -> ExtractionResult:
    """
    Uses LLM API to extract PDF content to markdown format.
    Prompt enforces YAML frontmatter and section preservation.
    """
    extraction_prompt = """
    Extract this Kill Team rulebook PDF to markdown format.

    Requirements:
    1. Preserve all headings, lists, and section structure
    2. Include YAML frontmatter with:
       - source: (e.g., "Core Rules v3.1")
       - publication_date: (YYYY-MM-DD format)
       - document_type: ("base" or "faq" or "errata")
       - section: (thematic grouping)
    3. Use proper markdown syntax (##, ###, -, *, etc.)
    4. Preserve rule citations and cross-references
    """

    with open(pdf_path, 'rb') as f:
        response = llm_provider.extract_document(
            file=f,
            prompt=extraction_prompt,
            max_tokens=16000  # Large rulebook sections
        )

    return ExtractionResult(
        markdown_content=response.text,
        token_count=response.token_count,  # Track for cost monitoring
        extraction_latency_ms=response.latency_ms
    )
```

**Token Usage Tracking**:
- All PDF extractions log token counts to metrics system
- Budget alerts if monthly extraction tokens exceed threshold
- Cache PDF hash → markdown mapping to avoid re-extracting same document

**Alternatives Considered**:
- **PyMuPDF + pdfplumber**: More code complexity, worse structure preservation, requires custom markdown conversion logic
- **PyPDF2**: Less accurate for complex PDFs, layout issues
- **Manual markdown creation**: Not scalable for frequent rule updates

### 5. LLM Provider Abstraction

**Decision**: LangChain LLM interface with provider-specific adapters

**Rationale**:
- LangChain LLM base class enforces consistent interface (Constitution Principle II)
- Separate adapter modules: `src/services/llm/claude.py`, `gemini.py`, `chatgpt.py`
- Configuration-driven selection via environment variable or config file
- All adapters implement same signature: `query(prompt, context) -> (response, confidence)`

**Implementation Pattern**:
```python
# Abstract interface
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, context: List[str]) -> LLMResponse:
        pass

# Provider selection
def get_llm_provider(config: Config) -> LLMProvider:
    if config.llm_provider == "claude":
        return ClaudeAdapter(config.anthropic_api_key)
    elif config.llm_provider == "gemini":
        return GeminiAdapter(config.google_api_key)
    # ...
```

### 6. Conversation Context Tracking

**Decision**: In-memory cache with (channel_id, user_id) composite key

**Rationale**:
- Clarification: Channel + User isolation allows same user in different channels
- TTL-based expiration (30 minutes idle) to prevent memory bloat
- Redis optional for future multi-instance deployments

**Implementation**:
```python
# Key format: f"{channel_id}:{user_id}"
conversation_cache: Dict[str, ConversationContext] = {}
```

### 7. Logging & Observability Strategy

**Decision**: Structured logging with Python `structlog` + OpenTelemetry (future)

**Rationale**:
- structlog: JSON-formatted logs, automatic correlation IDs
- FR-012 requirements: debugging, analytics, compliance all need structured queryable logs
- PII redaction middleware before log emission
- OpenTelemetry SDK added (not activated initially) for future distributed tracing

**Log Levels**:
- DEBUG: RAG retrieval scores, embedding vectors
- INFO: User queries (PII redacted), bot responses, performance metrics
- WARNING: Low confidence responses, rate limit approaches
- ERROR: LLM API failures, PDF parsing errors

### 8. Testing Strategy

**Decision**: pytest with 4-tier test pyramid

**Tiers**:
1. **Unit tests** (60% coverage): Models, utilities, individual adapters
2. **Contract tests** (20%): RAG pipeline contracts, LLM adapter contracts
3. **Integration tests** (15%): Discord bot flows, PDF ingestion end-to-end
4. **E2E tests** (5%): Full user journey (mock Discord, mock LLM)

**Tools**:
- `pytest-asyncio`: Discord async testing
- `pytest-mock`: LLM API mocking
- `freezegun`: Time-based test reproducibility (GDPR retention)
- `hypothesis`: Property-based testing for input validation

### 9. Security Implementation

**Decisions**:

**Input Sanitization**:
- Discord message sanitization: Strip markdown injection, limit length (2000 chars)
- Prompt injection detection: Pattern matching for common jailbreak attempts before LLM call
- Validation library: `pydantic` for all input models

**Secrets Management**:
- Environment variables for local development
- Secrets file template: `config/.env.template` (committed)
- Actual secrets: `.env` (gitignored)
- Production: Docker secrets or cloud secrets manager

**Rate Limiting**:
- Discord: Built-in discord.py rate limiter
- LLM APIs: Token bucket per-provider (respect OpenAI/Anthropic/Google limits)
- Per-user query throttling: Max 10 queries/minute (prevent abuse)

### 10. GDPR Compliance Implementation

**Decision**: Automated data cleanup with retention tracking

**Implementation**:
- Conversation logs: 7-day retention (NFR-006)
- Nightly cleanup job: Delete logs older than 7 days
- User data deletion: On-demand CLI command for GDPR requests
- Audit trail: Deletion events logged separately (legal retention 3 years)

**Data Minimization**:
- Store only: user_id (hashed), channel_id, message_text (PII redacted), timestamp
- Do NOT store: IP addresses, email, real names

### 11. Quality Gates Configuration

**Decision**: GitHub Actions CI/CD with quality checks

**Gates**:
1. **Linting**: `ruff` (fast Python linter), `mypy` (type checking)
2. **Test Coverage**: `pytest-cov` with 60% minimum threshold
3. **Security Scanning**: `bandit` (SAST), `safety` (dependency vulnerabilities)
4. **Complexity**: `radon` (cyclomatic complexity max 10), `vulture` (dead code detection)
5. **Performance**: Latency test must complete <30s (mock LLM, real RAG)

**CI Workflow**:
```yaml
jobs:
  quality-gates:
    runs-on: ubuntu-latest
    steps:
      - Linting (ruff, mypy)
      - Unit tests (pytest)
      - Contract tests (pytest)
      - Integration tests (pytest-asyncio)
      - Coverage check (≥80%)
      - Security scan (bandit, safety)
      - Complexity check (radon)
```

### 12. Rule Contradiction Detection

**Decision**: Metadata-based version precedence with conflict logging

**Implementation**:
- Each markdown file includes YAML frontmatter:
  ```yaml
  ---
  source: "Core Rules v3.1"
  publication_date: "2024-09-01"
  document_type: "base" | "faq" | "errata"
  ---
  ```
- RAG retrieval returns metadata with each chunk
- Contradiction detection: If same semantic query retrieves chunks with different `document_type` and contradictory text
- Resolution: FR-016 - Log conflict, do NOT answer user, prompt for manual review

**Conflict Logging**:
```python
logger.warning(
    "Rule contradiction detected",
    extra={
        "query": user_query,
        "source_1": chunk_1.metadata,
        "source_2": chunk_2.metadata,
        "contradiction_id": uuid4(),
    }
)
```

## Technology Stack Summary

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.11+ |
| Discord API | discord.py | 2.x |
| RAG Framework | LangChain + LlamaIndex | Latest stable |
| Vector DB | Chroma | Latest |
| PDF Extraction | LLM-based (Claude/ChatGPT/Gemini APIs) | N/A - uses existing LLM providers |
| LLM Providers | Anthropic/OpenAI/Google SDKs | Latest |
| Testing | pytest | Latest |
| Linting | ruff + mypy | Latest |
| Security Scanning | bandit + safety | Latest |
| Logging | structlog | Latest |

## Open Questions & Risks

**Resolved**:
- All NEEDS CLARIFICATION items resolved via /clarify session

**Risks**:
1. **Warhammer Community API availability**: Games Workshop may change PDF distribution
   - Mitigation: Fallback to manual PDF upload via CLI
2. **LLM API cost**: High query volume could exceed budget
   - Mitigation: Token usage monitoring, per-user query limits
3. **RAG quality**: Markdown structure variations may degrade retrieval
   - Mitigation: Document validation during ingestion, metadata enrichment

## Next Phase

Phase 1 will generate:
- `data-model.md`: Entity definitions with validation rules
- `contracts/`: RAG pipeline contracts, LLM adapter contracts
- `quickstart.md`: Developer onboarding and manual test scenarios
