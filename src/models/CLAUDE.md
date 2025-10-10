# Data Models

Domain models and data structures used throughout the application. All models use Python dataclasses for type safety and clarity.

## Purpose

Defines core domain entities for:
- User queries and conversation tracking
- RAG context and retrieval results
- Bot responses and formatting
- Rule documents and ingestion
- PDF updates and metadata

## Structure

```
src/models/
├── user_query.py           # Discord user questions
├── conversation_context.py # Multi-turn conversation state
├── rag_context.py          # RAG retrieval results
├── bot_response.py         # Formatted bot responses
├── rule_document.py        # Rule document metadata
├── ingestion_job.py        # Ingestion task tracking
└── pdf_update.py           # PDF update metadata
```

## Key Models

### UserQuery
Represents a question from a Discord user about Kill Team rules.

Fields:
- `query_id`: UUID - Unique query identifier
- `user_id`: str - **Hashed** Discord user ID (SHA-256 for GDPR)
- `channel_id`: str - Discord channel ID
- `message_text`: str - Original message text
- `sanitized_text`: str - Cleaned/validated text
- `timestamp`: datetime - Query timestamp
- `conversation_context_id`: str - Composite key for conversation tracking
- `pii_redacted`: bool - PII removal flag

Helper methods:
- `hash_user_id(discord_user_id)` - Hash user ID for GDPR compliance
- `create_context_id(channel_id, user_id)` - Generate conversation key

Defined in: [user_query.py](../../src/models/user_query.py)

### ConversationContext
Manages multi-turn conversation state for Discord threads.

Fields:
- `context_id`: str - Composite key: `{channel_id}:{user_id}`
- `user_id`: str - Hashed Discord user ID
- `channel_id`: str - Discord channel ID
- `history`: List[Message] - Conversation history
- `last_updated`: datetime - Last activity timestamp
- `metadata`: dict - Additional context data

Defined in: [conversation_context.py](../../src/models/conversation_context.py)

### RAGContext
RAG retrieval results with source documents.

Fields:
- `query`: str - Original query text
- `retrieved_chunks`: List[DocumentChunk] - Relevant document chunks
- `relevance_scores`: List[float] - Similarity scores
- `metadata`: dict - Retrieval metadata (model, threshold, etc.)

Defined in: [rag_context.py](../../src/models/rag_context.py)

### BotResponse
Formatted response ready for Discord delivery.

Fields:
- `text`: str - Main response text
- `source_citations`: List[str] - Referenced rule sections
- `confidence`: Optional[str] - Confidence level indicator
- `metadata`: dict - Response metadata (model, tokens, etc.)
- `error`: Optional[str] - Error message if applicable

Defined in: [bot_response.py](../../src/models/bot_response.py)

### RuleDocument
Metadata for a rule document in the vector database.

Fields:
- `document_id`: str - Unique document identifier
- `title`: str - Document title
- `source`: str - Source file path
- `content`: str - Document content
- `chunk_index`: int - Chunk number (for multi-chunk docs)
- `metadata`: dict - Additional metadata

Defined in: [rule_document.py](../../src/models/rule_document.py)

### IngestionJob
Tracks rule ingestion tasks.

Fields:
- `job_id`: UUID - Job identifier
- `source_path`: Path - Source directory
- `status`: str - Job status (pending, running, completed, failed)
- `documents_processed`: int - Count of processed documents
- `errors`: List[str] - Error messages
- `started_at`: datetime - Job start time
- `completed_at`: Optional[datetime] - Job completion time

Defined in: [ingestion_job.py](../../src/models/ingestion_job.py)

### PDFUpdate
Tracks PDF downloads and version metadata.

Fields:
- `team_name`: str - Kill Team name
- `pdf_url`: str - Source PDF URL
- `download_date`: datetime - Download timestamp
- `version`: str - Rule version/date
- `extracted_path`: Path - Extracted markdown path

Defined in: [pdf_update.py](../../src/models/pdf_update.py)

## Design Principles

### GDPR Compliance
All user identifiers are **hashed** using SHA-256:
- Never store raw Discord user IDs
- Use `UserQuery.hash_user_id()` for all user data
- Support data deletion via `conversation_context_id`

### Immutability
Models use dataclasses with frozen=True where appropriate:
- Prevents accidental mutation
- Ensures thread safety
- Makes data flow explicit

### Type Safety
All models use:
- Type hints for all fields
- Optional types for nullable fields
- Enums for constrained values
- UUIDs for unique identifiers

### Validation
Input validation is handled in:
- [src/lib/validation.py](../../src/lib/validation.py) - Input sanitization
- [src/services/*/validator.py](../../src/services/) - Service-specific validation

## Usage Examples

### Creating a User Query
```python
from src.models.user_query import UserQuery
from uuid import uuid4
from datetime import datetime, timezone

query = UserQuery(
    query_id=uuid4(),
    user_id=UserQuery.hash_user_id(discord_user_id),
    channel_id=channel_id,
    message_text=raw_text,
    sanitized_text=sanitized_text,
    timestamp=datetime.now(timezone.utc),
    conversation_context_id=UserQuery.create_context_id(channel_id, hashed_user_id),
)
```

### Building a Bot Response
```python
from src.models.bot_response import BotResponse

response = BotResponse(
    text="Overwatch can be used...",
    source_citations=["Core Rules p.42", "Tactical Ops p.15"],
    confidence="high",
    metadata={"model": "claude-sonnet", "tokens": 234},
)
```

## Development Guidelines

### Adding New Models

1. Create new file in `src/models/`
2. Use `@dataclass` decorator
3. Add type hints for all fields
4. Include docstrings for class and complex fields
5. Add helper methods if needed (e.g., validation, serialization)
6. Update this CLAUDE.md with model description

### Model Evolution

When modifying existing models:
- Add fields with default values (backward compatibility)
- Deprecate fields before removal
- Update all usages across codebase
- Add migration logic if persisting to disk/DB

### Testing Models

- Models are data containers, minimal logic
- Test helper methods (e.g., `hash_user_id`)
- Validate type safety with mypy/pyright
- Test serialization if applicable
