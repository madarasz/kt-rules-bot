# Contract: User Feedback Logging

**Feature**: Kill Team Rules Discord Bot - User Feedback System
**Component**: Feedback Logger
**Purpose**: Track user feedback (helpful/not helpful reactions) for response quality analytics

---

## Overview

The Feedback Logger captures user reactions (👍👎) on bot responses and logs them to structured logs (or optional database) for analytics. This enables tracking response quality, identifying problematic queries, and measuring LLM provider performance.

---

## Entity: UserFeedback

```python
@dataclass
class UserFeedback:
    """User feedback on bot responses."""

    feedback_id: UUID
    response_id: UUID  # FK to BotResponse
    query_id: UUID  # FK to UserQuery
    user_id: str  # Hashed Discord user ID (SHA-256)
    feedback_type: Literal["helpful", "not_helpful"]
    timestamp: datetime  # UTC
```

**Validation Rules**:
- `feedback_type` must be "helpful" or "not_helpful"
- `user_id` must be SHA-256 hashed (GDPR compliance)
- `response_id` must reference existing BotResponse
- Each user can provide one feedback per response (upsert behavior)

---

## Storage Options

### Option 1: Structured Logs Only (Recommended)
**Pros**:
- No additional database dependency
- GDPR-friendly (logs auto-expire per retention policy)
- Queryable via log aggregation tools (Loki, CloudWatch Insights, Datadog)

**Cons**:
- More complex analytics queries
- Limited real-time dashboard capabilities

**Log Format**:
```json
{
  "timestamp": "2025-10-03T12:34:56.789Z",
  "event_type": "user_feedback",
  "feedback_id": "a1b2c3d4-...",
  "response_id": "e5f6g7h8-...",
  "query_id": "i9j0k1l2-...",
  "user_id": "abc123...def",
  "feedback_type": "helpful",
  "correlation_id": "i9j0k1l2-..."
}
```

### Option 2: SQLite Database (Optional)
**Pros**:
- Fast SQL queries for analytics
- Easy dashboard integration
- Simple backup/restore

**Cons**:
- Additional storage dependency
- GDPR compliance requires manual cleanup scripts

**Schema**:
```sql
CREATE TABLE user_feedback (
    feedback_id TEXT PRIMARY KEY,
    response_id TEXT NOT NULL,
    query_id TEXT NOT NULL,
    user_id TEXT NOT NULL,  -- Hashed
    feedback_type TEXT CHECK(feedback_type IN ('helpful', 'not_helpful')),
    timestamp TEXT NOT NULL,
    UNIQUE(response_id, user_id)  -- One feedback per user per response
);

CREATE INDEX idx_response_id ON user_feedback(response_id);
CREATE INDEX idx_timestamp ON user_feedback(timestamp);
```

---

## Contract Methods

### 1. `async def on_reaction_add(reaction: discord.Reaction, user: discord.User) -> None`

**Purpose**: Handle reaction events and log feedback.

**Preconditions**:
- Bot must be connected to Discord
- Reaction must be on bot's own message
- Reaction emoji must be 👍 or 👎

**Business Rules**:
1. Ignore reactions on non-bot messages
2. Ignore non-feedback reactions (other emojis)
3. Map emoji to feedback type:
   - 👍 → "helpful"
   - 👎 → "not_helpful"
4. Hash user_id before logging (GDPR)
5. Extract response_id from message (embed footer or DB lookup)
6. Create UserFeedback entity
7. Log to structured logs

**Postconditions**:
- Feedback logged with all required fields
- User privacy preserved (hashed ID)
- Duplicate feedback from same user updates existing record (upsert)

**Error Handling**:
- If response_id not found: Log warning, skip feedback
- If logging fails: Log error, don't crash bot

---

## Contract Tests

### Test 1: Log helpful feedback
**Given**: User reacts 👍 to bot message
**When**: on_reaction_add is triggered
**Then**:
- UserFeedback created with feedback_type="helpful"
- Logged to structured logs
- user_id is hashed (SHA-256)

### Test 2: Log not helpful feedback
**Given**: User reacts 👎 to bot message
**When**: on_reaction_add is triggered
**Then**:
- UserFeedback created with feedback_type="not_helpful"
- Logged to structured logs

### Test 3: Ignore reactions on non-bot messages
**Given**: User reacts 👍 to another user's message
**When**: on_reaction_add is triggered
**Then**:
- No UserFeedback created
- No log entry

### Test 4: Ignore non-feedback reactions
**Given**: User reacts 🎉 to bot message
**When**: on_reaction_add is triggered
**Then**:
- No UserFeedback created
- No log entry

### Test 5: Upsert behavior (user changes feedback)
**Given**: User previously reacted 👍, now reacts 👎
**When**: on_reaction_add is triggered
**Then**:
- Existing feedback updated to "not_helpful"
- Only one feedback record exists per user per response

### Test 6: GDPR compliance
**Given**: User reacts 👍
**When**: Feedback is logged
**Then**:
- user_id is SHA-256 hash (64 hex chars)
- Original Discord user ID is NOT stored

---

## Analytics Queries

### Query 1: Overall feedback rate
```
SELECT
  feedback_type,
  COUNT(*) as count,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage
FROM user_feedback
GROUP BY feedback_type
```

### Query 2: Problematic queries (low helpful rate)
```
SELECT
  query_id,
  SUM(CASE WHEN feedback_type = 'helpful' THEN 1 ELSE 0 END) as helpful_count,
  SUM(CASE WHEN feedback_type = 'not_helpful' THEN 1 ELSE 0 END) as not_helpful_count,
  SUM(CASE WHEN feedback_type = 'helpful' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as helpful_percentage
FROM user_feedback
GROUP BY query_id
HAVING helpful_percentage < 50
ORDER BY helpful_percentage ASC
LIMIT 20
```

### Query 3: LLM provider performance
**Note**: Requires joining with BotResponse logs
```
SELECT
  llm_provider,
  AVG(CASE WHEN feedback_type = 'helpful' THEN 1 ELSE 0 END) as helpful_rate
FROM user_feedback
JOIN bot_responses ON user_feedback.response_id = bot_responses.response_id
GROUP BY llm_provider
```

### Query 4: Confidence score accuracy
**Note**: Requires joining with BotResponse logs
```
SELECT
  ROUND(confidence_score, 1) as confidence_bucket,
  AVG(CASE WHEN feedback_type = 'helpful' THEN 1 ELSE 0 END) as actual_helpful_rate
FROM user_feedback
JOIN bot_responses ON user_feedback.response_id = bot_responses.response_id
GROUP BY confidence_bucket
ORDER BY confidence_bucket DESC
```

---

## Integration Points

### Discord Bot (src/services/discord/bot.py)
- After sending response, add 👍👎 reactions to message
- Register `on_reaction_add` event handler
- Pass reaction events to FeedbackLogger

### Structured Logging (src/lib/logging.py)
- Ensure correlation_id propagates from query → response → feedback
- PII redaction middleware validates user_id is hashed

### Response Formatter (src/services/discord/formatter.py)
- Embed response_id in message footer (or DB lookup mechanism)
- Enable feedback extraction in FeedbackLogger

---

## GDPR Compliance

**Data Retention**:
- Feedback logs: 7 days (matches UserQuery/BotResponse retention)
- Auto-deletion via log rotation policy

**User Rights**:
- Right to be forgotten: Delete all logs containing hashed user_id
- Data export: Query logs for user's feedback history

**Privacy**:
- Discord user IDs are SHA-256 hashed before storage
- No usernames, display names, or other PII logged
- Correlation IDs allow tracing without PII

---

## Performance Considerations

**Logging Performance**:
- Async logging to avoid blocking Discord event loop
- Batch log writes if feedback volume is high (unlikely for current scale)

**Query Performance**:
- If using DB: Index on (response_id, timestamp)
- Log aggregation tools: Use structured fields for filtering

**Scale**:
- At 100 queries/day with 50% feedback rate: ~50 feedback logs/day
- At 1000 queries/day: ~500 feedback logs/day
- Both well within structured logging capacity

---

## Success Criteria

✅ **Functional**:
- 👍👎 reactions logged correctly
- User privacy preserved (hashed IDs)
- Upsert behavior prevents duplicates
- Non-bot messages and non-feedback reactions ignored

✅ **Quality**:
- 80%+ test coverage for feedback logger
- All 6 contract tests passing
- GDPR compliance validated

✅ **Analytics**:
- Queries 1-4 executable and return meaningful results
- Response quality trends visible over time
- Problematic queries identifiable

---

## Future Enhancements

**Phase 8+** (optional):
1. Real-time dashboard (Grafana + logs)
2. Automated alerts for low helpful rate
3. A/B testing framework (compare LLM providers)
4. Feedback sentiment analysis (why not helpful?)
5. User-specific feedback trends (frequent complainers vs helpers)

---

**Version**: 1.0
**Date**: 2025-10-03
**Status**: Ready for Implementation (T056.1)
