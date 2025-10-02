# Data Model

**Feature**: Kill Team Rules Discord Bot
**Date**: 2025-10-02

## Entity Definitions

### 1. UserQuery

**Description**: A question from a Discord user about Kill Team rules

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| query_id | UUID | Required, unique | Unique identifier for tracking |
| user_id | str (hashed) | Required | Discord user ID (hashed for GDPR) |
| channel_id | str | Required | Discord channel ID |
| message_text | str | Required, max 2000 chars | Original question text |
| sanitized_text | str | Required | Sanitized version (no injection patterns) |
| timestamp | datetime | Required, UTC | When query was received |
| conversation_context_id | str | Required | Composite key: `{channel_id}:{user_id}` |
| pii_redacted | bool | Required, default False | Flag if PII was detected and redacted |

**Validation Rules**:
- `message_text` must not contain markdown injection patterns
- `user_id` must be cryptographically hashed (SHA-256) before storage
- `timestamp` must be within last 7 days for GDPR retention

**State Transitions**:
1. Received → Sanitized → Processed → Logged
2. Retention: Auto-deleted after 7 days

**Relationships**:
- 1 UserQuery → 1+ RAGContext (retrieval results)
- 1 UserQuery → 1 BotResponse

---

### 2. RuleDocument

**Description**: A markdown file in extracted-rules/ representing Kill Team rules

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| document_id | UUID | Required, unique | Unique identifier |
| filename | str | Required, unique | e.g., "rules-1-phases.md" |
| content | str | Required | Full markdown content |
| metadata | dict | Required | YAML frontmatter parsed |
| version | str | Required | From metadata: source version |
| publication_date | date | Required | From metadata |
| document_type | enum | Required | "base", "faq", "errata" |
| last_updated | datetime | Required | File modification timestamp |
| hash | str | Required | SHA-256 of content for change detection |

**Metadata Schema** (YAML frontmatter):
```yaml
---
source: "Core Rules v3.1"
publication_date: "2024-09-01"
document_type: "base"  # or "faq", "errata"
section: "Phases"  # Optional: thematic grouping
---
```

**Validation Rules**:
- `filename` must match pattern: `[a-z0-9-]+\.md`
- `document_type` must be one of: {"base", "faq", "errata"}
- `publication_date` must be parseable date format
- Markdown content must not contain executable code blocks

**State Transitions**:
1. Discovered → Validated → Ingested → Indexed
2. Update flow: Modified → Re-validated → Re-indexed

**Relationships**:
- 1 RuleDocument → N RAGContext (embedded chunks)
- 1 RuleDocument → 1 PDFUpdate (source PDF)

---

### 3. RAGContext

**Description**: Retrieved rule sections relevant to a user query

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| context_id | UUID | Required, unique | Unique identifier |
| query_id | UUID | Required, FK | Reference to UserQuery |
| document_chunks | List[DocumentChunk] | Required, min 1 | Retrieved text segments |
| relevance_scores | List[float] | Required | Cosine similarity scores (0-1) |
| total_chunks | int | Required | Number of retrieved chunks |
| avg_relevance | float | Required | Mean relevance score |
| meets_threshold | bool | Required | True if avg_relevance ≥0.6 |

**DocumentChunk Schema**:
```python
@dataclass
class DocumentChunk:
    chunk_id: UUID
    document_id: UUID  # FK to RuleDocument
    text: str  # ~500 token segment
    metadata: Dict[str, Any]  # source, doc_type, publication_date
    relevance_score: float
    position_in_doc: int  # For citation: "Section 3, paragraph 2"
```

**Validation Rules**:
- `relevance_scores` must be between 0 and 1
- `document_chunks` ordered by relevance_score DESC
- All chunks must reference valid `RuleDocument` entities

**Relationships**:
- 1 RAGContext → 1 UserQuery
- 1 RAGContext → N RuleDocument (via chunks)

---

### 4. BotResponse

**Description**: An answer to a user query with rule citations

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| response_id | UUID | Required, unique | Unique identifier |
| query_id | UUID | Required, FK | Reference to UserQuery |
| answer_text | str | Required, max 4000 chars | Generated answer |
| citations | List[Citation] | Required, min 1 | Source rule references |
| confidence_score | float | Required, 0-1 | LLM confidence |
| rag_score | float | Required, 0-1 | RAG avg relevance |
| validation_passed | bool | Required | FR-013 combined validation |
| llm_provider | str | Required | "claude", "gemini", "chatgpt" |
| token_count | int | Required | Total tokens used (prompt + completion) |
| latency_ms | int | Required | Response time in milliseconds |
| timestamp | datetime | Required, UTC | When response was generated |

**Citation Schema**:
```python
@dataclass
class Citation:
    document_name: str  # "rules-1-phases.md"
    section: str  # "Movement Phase"
    quote: str  # Relevant excerpt (max 200 chars)
    document_type: str  # "base", "faq", "errata"
    publication_date: date
```

**Validation Rules**:
- `answer_text` must not exceed Discord message limit (2000 chars per message, use embeds if longer)
- `confidence_score` ≥ threshold (e.g., 0.7) for validation
- `rag_score` ≥ 0.6 for validation
- `validation_passed` = (confidence_score ≥ threshold) AND (rag_score ≥ 0.6)
- `citations` must reference actual RuleDocument chunks

**State Transitions**:
1. Generated → Validated → Sent → Logged
2. If validation fails: Generated → Rejected → User notified

**Relationships**:
- 1 BotResponse → 1 UserQuery
- 1 BotResponse → 1 RAGContext (implicit via query_id)

---

### 5. PDFUpdate

**Description**: An official Kill Team rules document (PDF)

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| update_id | UUID | Required, unique | Unique identifier |
| pdf_filename | str | Required | Original PDF filename |
| pdf_url | str | Required | Source URL from Warhammer Community API |
| download_date | datetime | Required, UTC | When PDF was downloaded |
| publication_date | date | Required | From PDF metadata or API |
| version | str | Required | e.g., "3.1", "FAQ-2024-10" |
| file_size_bytes | int | Required | PDF file size |
| file_hash | str | Required | SHA-256 for duplicate detection |
| extraction_status | enum | Required | "pending", "success", "failed" |
| error_message | str | Optional | If extraction_status = "failed" |

**Validation Rules**:
- `pdf_url` must be HTTPS
- `file_hash` must be unique (prevent re-downloading same PDF)
- `version` must follow semver or date-based format

**State Transitions**:
1. Discovered → Downloaded → Extracted → Processed
2. Failure path: Downloaded → Extraction Failed → Manual Review

**Relationships**:
- 1 PDFUpdate → N RuleDocument (1 PDF may generate multiple markdown files)
- 1 PDFUpdate → 1 IngestionJob

---

### 6. IngestionJob

**Description**: Automated process that converts PDFs to markdown and updates RAG

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| job_id | UUID | Required, unique | Unique identifier |
| update_id | UUID | Required, FK | Reference to PDFUpdate |
| status | enum | Required | "running", "success", "failed" |
| started_at | datetime | Required, UTC | Job start time |
| completed_at | datetime | Optional | Job completion time |
| processed_files | List[str] | Required | List of generated markdown filenames |
| errors | List[str] | Optional | Error messages if any |
| warnings | List[str] | Optional | Non-fatal issues (e.g., ambiguous formatting) |
| documents_created | int | Required, default 0 | Count of new RuleDocument entities |
| documents_updated | int | Required, default 0 | Count of updated RuleDocument entities |
| reingestion_triggered | bool | Required | True if RAG re-indexing was triggered |

**Validation Rules**:
- `status` transition: running → (success | failed)
- `completed_at` must be after `started_at`
- `errors` must be non-empty if `status` = "failed"

**State Transitions**:
1. Created → Running → Success/Failed
2. Retry logic: Failed jobs can be re-run manually via CLI

**Relationships**:
- 1 IngestionJob → 1 PDFUpdate
- 1 IngestionJob → N RuleDocument (created or updated)

---

### 7. ConversationContext

**Description**: Transient in-memory state for user conversations (not persisted to DB)

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| context_key | str | Required, unique | `{channel_id}:{user_id}` |
| user_id | str | Required | Discord user ID |
| channel_id | str | Required | Discord channel ID |
| message_history | List[Message] | Required, max 10 | Last 10 messages in conversation |
| last_activity | datetime | Required, UTC | Timestamp of last interaction |
| ttl_seconds | int | Required, default 1800 | Time-to-live: 30 minutes |

**Message Schema**:
```python
@dataclass
class Message:
    role: str  # "user" or "bot"
    text: str
    timestamp: datetime
```

**Validation Rules**:
- `message_history` limited to last 10 messages (prevent memory bloat)
- Context auto-expires if `now() - last_activity > ttl_seconds`
- `context_key` must be unique composite key

**State Transitions**:
1. Created on first user message → Updated on each interaction → Expired after TTL
2. Cleanup: Periodic sweep removes expired contexts

---

## Relationships Diagram

```
UserQuery 1──1 RAGContext
    │             │
    │             └──N RuleDocument
    │
    └──1 BotResponse

PDFUpdate 1──1 IngestionJob
    │
    └──N RuleDocument

RuleDocument N──N RAGContext (via document_chunks)
```

## Validation Summary

**Global Rules**:
1. All UUIDs generated using `uuid4()`
2. All timestamps in UTC
3. All user-facing text sanitized before storage
4. PII (Discord usernames, emails) redacted before logging
5. GDPR: UserQuery and BotResponse auto-deleted after 7 days

**Consistency Constraints**:
- BotResponse.query_id must reference existing UserQuery
- RAGContext.query_id must reference existing UserQuery
- DocumentChunk.document_id must reference existing RuleDocument
- IngestionJob.update_id must reference existing PDFUpdate
