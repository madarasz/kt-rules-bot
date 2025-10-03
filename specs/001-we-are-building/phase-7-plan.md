# Phase 7 Implementation Plan: Discord Bot Integration (Orchestrator Pattern)

**Status**: Approved - Ready for Implementation
**Dependencies**: Phases 1-6 Complete ✅
**Tasks**: T048-T056.1 (10 tasks total)
**Architecture**: Orchestrator Pattern (user decision)

---

## Overview

Phase 7 integrates the Discord bot layer using the **Orchestrator Pattern**, connecting user interactions with the RAG pipeline and LLM services. This is the user-facing layer that coordinates the complete flow from Discord message to AI-powered response with feedback tracking.

**Key Architectural Decisions** (from user):
1. **Pattern**: Orchestrator Pattern (simple linear flow, single coordinator class)
2. **Discord Events**: Raw event handlers (`on_message`, `on_reaction_add`) - NO commands framework
3. **Feedback System**: Helpful/not helpful reaction buttons (👍👎) for analytics
4. **Rate Limiting**: Current implementation (10 req/min per user) is acceptable
5. **Context Tracking**: Message history only (NOT RAG chunks in conversation state)

---

## Architecture Design

### Orchestrator Pattern Architecture

```
Discord Event (on_message)
    ↓
handlers.py (parse @ mention, sanitize, create UserQuery)
    ↓
bot.py (ORCHESTRATOR - coordinates everything)
    ↓
    ├─→ rate_limiter.py (Phase 6) - check user limits
    ├─→ context_manager.py - get message history (last 10)
    ├─→ rag/retriever.py (Phase 5) - retrieve relevant chunks
    ├─→ llm/factory.py (Phase 6) - generate answer with LLM
    ├─→ llm/validator.py (Phase 6) - validate response (FR-013)
    └─→ formatter.py - format Discord embed
    ↓
Send response to Discord
    ↓
Add 👍👎 reactions for feedback
    ↓
feedback_logger.py handles on_reaction_add event
```

**Pattern Characteristics**:
- **Single coordinator**: `bot.py` orchestrator makes all decisions
- **Linear flow**: Step-by-step execution, no complex event passing
- **Service delegation**: Orchestrator calls services, doesn't implement logic
- **Simple error handling**: Try-except at orchestrator level
```

### Data Flow

```
1. User sends: "@KillTeamBot Can I shoot through barricades?"

2. handlers.py extracts:
   - user_id (hashed for GDPR)
   - channel_id
   - message_text (sanitized)
   - conversation_context_id = f"{channel_id}:{user_id}"

3. bot.py orchestrates:
   a. Check rate_limiter (10 req/min per user)
   b. Retrieve context: RAGRetriever.retrieve()
   c. Generate answer: LLMProvider.generate()
   d. Validate: ResponseValidator.validate()
   e. Format: formatter.format_response()

4. formatter.py creates Discord embed:
   - Answer text (with citations)
   - Confidence indicator
   - Source references
   - Splits if >2000 chars

5. Send to Discord channel

6. Add feedback reactions:
   - Bot adds 👍 (helpful) reaction
   - Bot adds 👎 (not helpful) reaction
   - User clicks reaction → on_reaction_add event

7. feedback_logger.py logs feedback:
   - Create UserFeedback entity
   - Log to structured logs (or DB)
   - Track for analytics
```

---

## Task Implementation Details

### T048: Discord Client Setup (`src/services/discord/client.py`)

**Purpose**: Initialize discord.py client with proper intents and configuration.

**Key Decisions**:
- **Raw Events**: Use `discord.Client` (NOT `commands.Bot`) for raw event handlers
- **Intents**: `discord.Intents.default()` + `guild_messages`, `message_content`, `guild_reactions`
- **Token**: Load from `DISCORD_BOT_TOKEN` environment variable
- **Event Loop**: Use `asyncio` with discord.py's built-in loop
- **Graceful Shutdown**: Handle SIGINT/SIGTERM for cleanup

**Implementation Pattern**:
```python
import discord

class KillTeamBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.guild_reactions = True  # For feedback buttons

        super().__init__(intents=intents)

    async def on_ready(self):
        logger.info(f"Bot connected as {self.user}")

    async def setup_hook(self):
        # Initialize orchestrator and services here
        pass
```

**Dependencies**:
- Config: `DISCORD_BOT_TOKEN` from `.env`
- Logging: `src/lib/logging.py`

---

### T049: Message Handler (`src/services/discord/handlers.py`)

**Purpose**: Parse @ mentions, validate input, create `UserQuery` objects.

**Key Decisions**:
- **Trigger**: Only respond to messages that mention the bot
- **Validation**: Use `src/lib/validation.py` for injection detection
- **User ID Hashing**: Use `UserQuery.hash_user_id()` for GDPR
- **Context Key**: Format `{channel_id}:{user_id}` for conversation isolation

**Implementation Pattern**:
```python
async def on_message(message: discord.Message):
    # Ignore bot's own messages
    if message.author == bot.user:
        return

    # Check if bot is mentioned
    if bot.user not in message.mentions:
        return

    # Extract query text (remove @ mention)
    query_text = message.content.replace(f"<@{bot.user.id}>", "").strip()

    # Sanitize and validate
    sanitized_text, injection_detected = sanitize_discord_message(query_text)

    if injection_detected:
        await message.channel.send(
            "⚠️ Your message contains invalid characters. Please rephrase."
        )
        security_logger.log_injection_attempt(message.author.id, query_text)
        return

    # Create UserQuery
    user_query = UserQuery(
        query_id=uuid4(),
        user_id=UserQuery.hash_user_id(str(message.author.id)),
        channel_id=str(message.channel.id),
        message_text=query_text,
        sanitized_text=sanitized_text,
        timestamp=datetime.now(timezone.utc),
        conversation_context_id=f"{message.channel.id}:{message.author.id}",
        pii_redacted=False,
    )

    # Hand off to orchestrator
    await bot.process_query(message, user_query)
```

**Edge Cases**:
- Empty message after removing mention → Ask "How can I help?"
- Multi-line message → Preserve formatting
- Mentions in middle of text → Strip all mentions, keep text

---

### T050: Conversation Context Manager (`src/services/discord/context_manager.py`)

**Purpose**: Track conversation history per user+channel, TTL-based cleanup.

**Key Decisions**:
- **Storage**: In-memory dict (no persistence needed for 30min TTL)
- **Key Format**: `{channel_id}:{user_id}` (matches FR-011)
- **TTL**: 30 minutes of inactivity
- **History Limit**: Last 10 messages per conversation (user + bot turns)
- **Content**: Message history ONLY (NOT RAG chunks) per user decision
- **Cleanup**: Background task runs every 5 minutes

**Implementation Pattern**:
```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

@dataclass
class Message:
    role: str  # "user" or "bot"
    text: str
    timestamp: datetime

class ConversationContextManager:
    def __init__(self, ttl_seconds: int = 1800):
        self._contexts: Dict[str, ConversationContext] = {}
        self.ttl = timedelta(seconds=ttl_seconds)

    def get_context(self, context_key: str) -> ConversationContext:
        """Get or create conversation context."""
        if context_key not in self._contexts:
            self._contexts[context_key] = ConversationContext(
                context_key=context_key,
                message_history=[],
                last_activity=datetime.now(timezone.utc),
            )
        return self._contexts[context_key]

    def add_message(self, context_key: str, role: str, text: str):
        """Add message to conversation history."""
        context = self.get_context(context_key)
        context.message_history.append(Message(
            role=role,
            text=text,
            timestamp=datetime.now(timezone.utc),
        ))
        # Keep only last 10 messages
        context.message_history = context.message_history[-10:]
        context.last_activity = datetime.now(timezone.utc)

    async def cleanup_expired(self):
        """Remove expired contexts (background task)."""
        now = datetime.now(timezone.utc)
        expired = [
            key for key, ctx in self._contexts.items()
            if now - ctx.last_activity > self.ttl
        ]
        for key in expired:
            del self._contexts[key]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired contexts")
```

**Usage**:
- Before RAG retrieval: Get conversation history for context
- After bot response: Add both user query and bot answer

---

### T051: Response Formatter with Feedback Buttons (`src/services/discord/formatter.py`)

**Purpose**: Format `BotResponse` into Discord-friendly embeds with citations and feedback reactions.

**Key Decisions**:
- **Use Discord Embeds**: Rich formatting with colors, fields
- **Color Coding**: Green (high confidence), Yellow (medium), Red (low)
- **Citation Format**: Numbered list with `[source]` links
- **Message Splitting**: Split at sentence boundaries if >2000 chars
- **Confidence Display**: Visual indicator (🟢🟡🔴) + percentage
- **Feedback Buttons**: Add 👍👎 reactions to every bot response for user feedback

**Implementation Pattern**:
```python
import discord

def format_response(
    bot_response: BotResponse,
    validation_result: ValidationResult,
) -> List[discord.Embed]:
    """Format bot response as Discord embeds."""

    # Determine embed color based on confidence
    if bot_response.confidence_score >= 0.8:
        color = discord.Color.green()
        confidence_emoji = "🟢"
    elif bot_response.confidence_score >= 0.6:
        color = discord.Color.gold()
        confidence_emoji = "🟡"
    else:
        color = discord.Color.red()
        confidence_emoji = "🔴"

    # Create main embed
    embed = discord.Embed(
        title="Kill Team Rules Assistant",
        description=bot_response.answer_text[:2000],  # Limit
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # Add confidence field
    embed.add_field(
        name="Confidence",
        value=f"{confidence_emoji} {bot_response.confidence_score:.0%}",
        inline=True,
    )

    # Add citations
    if bot_response.citations:
        citations_text = "\n".join([
            f"{i+1}. **{c.document_name}** - {c.section}"
            for i, c in enumerate(bot_response.citations[:5])
        ])
        embed.add_field(
            name="Sources",
            value=citations_text,
            inline=False,
        )

    # Footer with metadata
    embed.set_footer(
        text=f"Provider: {bot_response.provider} | "
             f"Tokens: {bot_response.token_count} | "
             f"Latency: {bot_response.latency_ms}ms"
    )

    return [embed]
```

**Fallback Formatting**:
```python
def format_fallback_message(reason: str) -> str:
    """Format message when validation fails."""
    return (
        "⚠️ I couldn't provide a confident answer to your question.\n\n"
        f"**Reason**: {reason}\n\n"
        "💡 Try:\n"
        "• Rephrasing your question more specifically\n"
        "• Asking about a particular rule section\n"
        "• Providing more context about the situation"
    )
```

---

### T052: Main Bot Orchestrator (`src/services/discord/bot.py`)

**Purpose**: Orchestrate complete flow from query to response.

**Key Decisions**:
- **Error Isolation**: Wrap each step in try-except
- **Timeout Management**: 25s max for LLM, 30s total for user
- **Rate Limiting**: Check before processing
- **Logging**: Correlation ID per query for tracing
- **Validation**: Use ResponseValidator (FR-013)

**Implementation Pattern**:
```python
class KillTeamBotOrchestrator:
    def __init__(
        self,
        rag_retriever: RAGRetriever,
        llm_provider: LLMProvider,
        response_validator: ResponseValidator,
        rate_limiter: RateLimiter,
        context_manager: ConversationContextManager,
        formatter: ResponseFormatter,
    ):
        self.rag = rag_retriever
        self.llm = llm_provider
        self.validator = response_validator
        self.rate_limiter = rate_limiter
        self.context_manager = context_manager
        self.formatter = formatter

    async def process_query(
        self,
        message: discord.Message,
        user_query: UserQuery,
    ) -> None:
        """Process user query and send response."""
        correlation_id = str(user_query.query_id)
        logger.info(
            f"Processing query",
            extra={"correlation_id": correlation_id, "query": user_query.sanitized_text}
        )

        try:
            # 1. Rate limiting
            is_allowed, retry_after = self.rate_limiter.check_rate_limit(
                provider=self.llm.model,
                user_id=user_query.user_id,
            )

            if not is_allowed:
                await message.channel.send(
                    f"⏳ Rate limit reached. Please retry in {retry_after:.0f}s."
                )
                return

            # 2. RAG retrieval
            rag_context = self.rag.retrieve(
                RetrieveRequest(
                    query=user_query.sanitized_text,
                    max_chunks=5,
                    min_relevance=0.6,
                )
            )

            # 3. LLM generation
            llm_response = await self.llm.generate(
                GenerationRequest(
                    prompt=user_query.sanitized_text,
                    context=[chunk.text for chunk in rag_context.document_chunks],
                    config=GenerationConfig(timeout_seconds=25),
                )
            )

            # 4. Validation
            validation_result = self.validator.validate(llm_response, rag_context)

            if not validation_result.is_valid:
                # Send fallback message
                await message.channel.send(
                    self.formatter.format_fallback_message(validation_result.reason)
                )
                logger.warning(
                    f"Validation failed: {validation_result.reason}",
                    extra={"correlation_id": correlation_id}
                )
                return

            # 5. Format and send response
            embeds = self.formatter.format_response(llm_response, validation_result)
            await message.channel.send(embeds=embeds)

            # 6. Update conversation context
            self.context_manager.add_message(
                user_query.conversation_context_id,
                role="user",
                text=user_query.sanitized_text,
            )
            self.context_manager.add_message(
                user_query.conversation_context_id,
                role="bot",
                text=llm_response.answer_text,
            )

            logger.info(
                f"Query processed successfully",
                extra={
                    "correlation_id": correlation_id,
                    "confidence": llm_response.confidence_score,
                    "latency_ms": llm_response.latency_ms,
                }
            )

        except Exception as e:
            logger.error(
                f"Error processing query: {e}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            await message.channel.send(
                "❌ An error occurred while processing your request. "
                "Please try again in a moment."
            )
```

**Dependencies**:
- All previous phases (RAG, LLM, Validation, Rate Limiting)
- Message handler (T049)
- Context manager (T050)
- Formatter (T051)

---

### T053: Error Handler (`src/services/discord/error_handler.py`)

**Purpose**: Centralized error handling with user-friendly messages.

**Error Categories**:
1. **Discord API Errors**: Rate limits, permissions, network
2. **LLM Errors**: Timeouts, rate limits, auth failures
3. **RAG Errors**: Vector DB unavailable, no results
4. **Validation Errors**: Low confidence, no relevant context

**Implementation Pattern**:
```python
from discord.errors import HTTPException, Forbidden

async def handle_error(
    error: Exception,
    message: discord.Message,
    correlation_id: str,
) -> None:
    """Handle errors with appropriate user feedback."""

    # Map error types to user messages
    if isinstance(error, RateLimitError):
        await message.channel.send(
            "⏰ The AI service is currently rate limited. "
            "Please try again in a few minutes."
        )
        logger.warning(
            f"LLM rate limit hit",
            extra={"correlation_id": correlation_id}
        )

    elif isinstance(error, TimeoutError):
        await message.channel.send(
            "⏱️ Request timed out. The query might be too complex. "
            "Try breaking it into smaller questions."
        )
        logger.warning(
            f"LLM timeout",
            extra={"correlation_id": correlation_id}
        )

    elif isinstance(error, Forbidden):
        logger.error(
            f"Missing Discord permissions",
            extra={"correlation_id": correlation_id}
        )
        # Can't send message due to permissions

    elif isinstance(error, HTTPException):
        if error.status == 429:  # Discord rate limit
            await message.channel.send(
                "⏳ Discord rate limit reached. Slowing down..."
            )
        logger.warning(
            f"Discord API error: {error.status}",
            extra={"correlation_id": correlation_id}
        )

    else:
        # Generic error
        await message.channel.send(
            "❌ An unexpected error occurred. "
            "The team has been notified."
        )
        logger.error(
            f"Unexpected error: {error}",
            extra={"correlation_id": correlation_id},
            exc_info=True,
        )
```

---

### T054: Health Check [P] (`src/services/discord/health.py`)

**Purpose**: Monitor system health for operations.

**Checks**:
1. Discord connection status
2. Vector DB connectivity
3. LLM provider availability (ping endpoint)
4. Metrics collection (recent error rate, latency)

**Implementation Pattern**:
```python
@dataclass
class HealthStatus:
    is_healthy: bool
    discord_connected: bool
    vector_db_available: bool
    llm_provider_available: bool
    recent_error_rate: float
    avg_latency_ms: int
    timestamp: datetime

async def check_health() -> HealthStatus:
    """Check system health."""
    checks = await asyncio.gather(
        check_discord_connection(),
        check_vector_db(),
        check_llm_provider(),
        return_exceptions=True,
    )

    return HealthStatus(
        is_healthy=all(checks),
        discord_connected=checks[0],
        vector_db_available=checks[1],
        llm_provider_available=checks[2],
        recent_error_rate=get_error_rate(),
        avg_latency_ms=get_avg_latency(),
        timestamp=datetime.now(timezone.utc),
    )
```

---

### T055: Security Logging [P] (`src/services/discord/security.py`)

**Purpose**: Log security-sensitive events for monitoring.

**Events to Log**:
- Injection attempts (detected by validation)
- Rate limit violations
- Unusual query patterns
- Permission violations
- Failed authentication attempts

**Implementation Pattern**:
```python
security_logger = get_logger("security")

def log_injection_attempt(user_id: str, message: str):
    """Log potential injection attempt."""
    security_logger.warning(
        "Injection attempt detected",
        extra={
            "event_type": "injection_attempt",
            "user_id": user_id[:16],  # Partial hash for privacy
            "message_length": len(message),
            "patterns_detected": detect_patterns(message),
        }
    )

def log_rate_limit_violation(user_id: str, provider: str):
    """Log rate limit hit."""
    security_logger.info(
        "Rate limit reached",
        extra={
            "event_type": "rate_limit",
            "user_id": user_id[:16],
            "provider": provider,
        }
    )
```

---

### T056.1: Feedback Logging Service [P] (`src/services/discord/feedback_logger.py`)

**Purpose**: Log user feedback from reaction buttons for analytics.

**Key Decisions**:
- **Event**: Handle `on_reaction_add` for 👍👎 emojis on bot messages
- **Logging Target**: Structured logs (OR optional lightweight DB like SQLite)
- **Entity**: UserFeedback from data-model.md
- **Deduplication**: One feedback per user per response (upsert behavior)
- **Privacy**: Hash user_id (GDPR compliance)

**Implementation Pattern**:
```python
class FeedbackLogger:
    def __init__(self, logger):
        self.logger = logger

    async def on_reaction_add(
        self,
        reaction: discord.Reaction,
        user: discord.User,
    ) -> None:
        """Log feedback from reaction buttons."""

        # Only process bot's own messages
        if reaction.message.author.id != bot.user.id:
            return

        # Only process thumbs up/down
        if reaction.emoji not in ["👍", "👎"]:
            return

        # Map emoji to feedback type
        feedback_type = "helpful" if reaction.emoji == "👍" else "not_helpful"

        # Extract response_id from message (embedded in footer or DB lookup)
        response_id = extract_response_id(reaction.message)

        # Create UserFeedback entity
        feedback = UserFeedback(
            feedback_id=uuid4(),
            response_id=response_id,
            query_id=get_query_id_from_response(response_id),
            user_id=UserQuery.hash_user_id(str(user.id)),
            feedback_type=feedback_type,
            timestamp=datetime.now(timezone.utc),
        )

        # Log to structured logs
        self.logger.info(
            "User feedback received",
            extra={
                "event_type": "user_feedback",
                "response_id": str(feedback.response_id),
                "feedback_type": feedback.feedback_type,
                "user_id": feedback.user_id[:16],  # Partial hash
            }
        )

        # Optional: Store in DB for analytics queries
        # await self.db.upsert_feedback(feedback)
```

**Analytics Use Cases**:
1. **Response Quality**: Track helpful/not_helpful ratio over time
2. **Problematic Queries**: Identify questions with low helpful rate
3. **LLM Provider Performance**: Compare feedback across Claude/ChatGPT/Gemini
4. **Confidence Score Accuracy**: Correlate confidence with feedback

**Storage Options**:
- **Logs only**: Query with log aggregation tools (Loki, CloudWatch Insights)
- **Optional SQLite DB**: Enable SQL queries for analytics dashboard

---

### T056: Unit Tests [P] (`tests/unit/test_discord_services.py`)

**Test Coverage**:
1. **Message Handler**:
   - Parse @ mentions correctly
   - Detect injection attempts
   - Create UserQuery with hashed ID
   - Handle empty messages

2. **Context Manager**:
   - Create new contexts
   - Add messages to history
   - Limit to 10 messages
   - Cleanup expired contexts

3. **Response Formatter**:
   - Format embeds correctly
   - Color based on confidence
   - Split long messages
   - Handle missing citations
   - Add 👍👎 reactions after sending

4. **Orchestrator**:
   - Full flow with mocked services
   - Rate limit enforcement
   - Validation failure handling
   - Error propagation

5. **Feedback Logger** (NEW):
   - Handle 👍 reaction correctly
   - Handle 👎 reaction correctly
   - Ignore reactions on non-bot messages
   - Ignore non-feedback reactions
   - Create UserFeedback entity
   - Log to structured logs

**Example Test**:
```python
@pytest.fixture
def mock_discord_message():
    message = Mock(spec=discord.Message)
    message.author.id = 123456789
    message.channel.id = 987654321
    message.content = "<@bot_id> Can I shoot through barricades?"
    return message

async def test_process_query_success(mock_discord_message):
    # Setup mocks
    rag_retriever = Mock()
    rag_retriever.retrieve.return_value = create_mock_rag_context()

    llm_provider = AsyncMock()
    llm_provider.generate.return_value = create_mock_llm_response()

    validator = Mock()
    validator.validate.return_value = ValidationResult(
        is_valid=True,
        llm_confidence=0.9,
        rag_score=0.8,
        reason="Valid",
    )

    # Create orchestrator
    orchestrator = KillTeamBotOrchestrator(
        rag_retriever=rag_retriever,
        llm_provider=llm_provider,
        response_validator=validator,
        rate_limiter=Mock(),
        context_manager=Mock(),
        formatter=Mock(),
    )

    # Process query
    user_query = create_test_user_query()
    await orchestrator.process_query(mock_discord_message, user_query)

    # Assertions
    assert rag_retriever.retrieve.called
    assert llm_provider.generate.called
    assert validator.validate.called
    assert mock_discord_message.channel.send.called
```

---

## Implementation Order

```
Sequential Tasks (must be done in order):
1. T048 - Discord client setup (foundation)
2. T049 - Message handler (entry point)
3. T050 - Context manager (state management)
4. T051 - Response formatter with feedback buttons (output)
5. T052 - Bot orchestrator (integration)
6. T053 - Error handler (robustness)

Parallel Tasks (can be done concurrently):
7. T054 - Health check [P]
8. T055 - Security logging [P]
9. T056 - Unit tests [P]
10. T056.1 - Feedback logger [P]
```

---

## Configuration Requirements

### Environment Variables
```bash
# Discord
DISCORD_BOT_TOKEN=your_bot_token_here

# Already configured from previous phases:
# - ANTHROPIC_API_KEY
# - OPENAI_API_KEY
# - GOOGLE_API_KEY
# - DEFAULT_LLM_PROVIDER
# - VECTOR_DB_PATH
```

### Discord Bot Permissions
Required intents:
- `guilds` - Access guild information
- `guild_messages` - Read messages in guilds
- `message_content` - Read message content (privileged)
- `guild_reactions` - Read reactions on messages (for feedback)

Required permissions:
- `View Channels`
- `Send Messages`
- `Send Messages in Threads`
- `Embed Links`
- `Add Reactions` - Required for feedback buttons
- `Read Message History`

---

## Testing Strategy

### Unit Tests (T056)
- Mock all Discord events
- Test each component in isolation
- Verify error handling paths
- Check message parsing edge cases

### Integration Tests (Phase 8)
- Test full Discord → RAG → LLM → Response flow
- Verify conversation context tracking
- Test concurrent user scenarios
- Validate rate limiting

### Manual Testing Checklist
- [ ] Bot connects to Discord successfully
- [ ] Bot responds to @ mentions
- [ ] Bot ignores messages without mentions
- [ ] Citations are properly formatted
- [ ] Long messages are split correctly
- [ ] Confidence indicators show correctly
- [ ] Rate limiting prevents spam
- [ ] Error messages are user-friendly
- [ ] Bot handles server restarts gracefully
- [ ] **Feedback buttons**: 👍👎 reactions appear on bot responses
- [ ] **Feedback logging**: Clicking reactions logs UserFeedback
- [ ] **Feedback deduplication**: Same user can change feedback

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Discord rate limits | Bot becomes unresponsive | Implement backoff, queue messages |
| Long RAG/LLM latency | User timeout | Show "typing" indicator, set 25s timeout |
| Concurrent user conflicts | Mixed responses | Proper context isolation with channel_id:user_id |
| Memory leak from contexts | Bot crashes | TTL-based cleanup, max history limit |
| Injection attacks | Security breach | Input validation, security logging |

---

## Success Criteria

✅ **Functional**:
- Bot responds to @ mentions within 30 seconds
- Responses include citations and confidence scores
- Multiple users can interact concurrently without conflicts
- Rate limiting prevents abuse (10 req/min per user)

✅ **Quality**:
- 80%+ test coverage for Discord services
- All error conditions have user-friendly messages
- Security events are logged for monitoring
- Health check endpoint shows system status

✅ **Non-Functional**:
- Graceful degradation when services are unavailable
- Proper GDPR compliance (hashed user IDs, 7-day retention)
- Observable via structured logs with correlation IDs
- Constitution principles maintained (test-first, LLM-independent, secure)

---

## Next Steps After Approval

1. **Review this plan** - Provide feedback on architecture decisions
2. **Implement sequentially** - T048 → T049 → T050 → T051 → T052 → T053
3. **Parallel tasks** - T054, T055, T056 can be done concurrently
4. **Test & validate** - Run unit tests, manual Discord testing
5. **Phase 8 ready** - Move to integration tests

---

**User Decisions Incorporated**:
1. ✅ **Orchestrator Pattern** confirmed (simple linear flow)
2. ✅ **Raw events** (`on_message`, `on_reaction_add`) - NO commands framework
3. ✅ **Feedback buttons** (👍👎 reactions) for analytics
4. ✅ **Rate limiting** 10 req/min per user is acceptable
5. ✅ **Message history only** in context (NOT RAG chunks)
