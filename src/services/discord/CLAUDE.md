# Discord Service

Bot interaction layer handling all Discord-related functionality.

## Purpose

Manages the Discord bot lifecycle, message handling, conversation context tracking, security, and response formatting. Acts as the frontend interface between users and the bot's backend services (RAG + LLM).

## Key Components

### Bot Orchestrator ([bot.py](bot.py))
Main orchestrator coordinating all services:
- Receives user queries from Discord handlers
- Coordinates RAG retrieval and LLM generation
- Manages rate limiting and response validation
- Handles acknowledgements and typing indicators
- Dependencies: RAGRetriever, LLMProviderFactory, RateLimiter, ConversationContextManager

**Pattern**: Orchestrator Pattern - single point coordinating multiple services

### Message Handlers ([handlers.py](handlers.py))
Discord message event processing:
- Handles @ mentions to the bot
- Sanitizes and validates user input
- Detects injection attempts
- Routes valid queries to orchestrator
- Sends formatted responses back to Discord

### Conversation Context ([context_manager.py](context_manager.py))
Tracks multi-turn conversations:
- Context keyed by `{channel_id}:{user_id}`
- In-memory storage with TTL expiration
- GDPR-compliant user ID hashing
- Automatic cleanup of stale contexts
- Thread-safe context access

### Security & Validation ([security.py](security.py))
Protection and validation layers:
- Rate limiting per user/channel
- Input sanitization (XSS, injection detection)
- Message length validation
- Security event logging

### Response Formatting ([formatter.py](formatter.py))
Discord-specific response formatting:
- Markdown formatting for Discord
- Citation formatting with sources
- Error message formatting
- Chunking long responses to fit Discord limits

### Error Handling ([error_handler.py](error_handler.py))
Centralized error management:
- Discord API errors
- Service timeout errors
- User-friendly error messages
- Error logging with context

### Health Monitoring ([health.py](health.py))
Service health checks:
- Discord connection status
- Service availability verification
- Health endpoint for monitoring

### Feedback Logging ([feedback_logger.py](feedback_logger.py))
User feedback collection:
- Thumbs up/down reactions
- Feedback aggregation
- Quality monitoring

## Request Flow

```
User Message → Discord Event
    ↓
handlers.py (validate, sanitize)
    ↓
bot.py orchestrator
    ├→ Check rate limits
    ├→ Retrieve conversation context
    ├→ Call RAG service
    ├→ Call LLM service
    ├→ Validate response
    └→ Format response
    ↓
Discord Response → User
```

## Key Data Models

From [src/models/](../../models/):
- **UserQuery**: Sanitized user query with metadata
- **BotResponse**: Formatted response with citations
- **ConversationContext**: Multi-turn conversation state

## Configuration

From [src/lib/constants.py](../../lib/constants.py):
- `DISCORD_BOT_TOKEN`: Bot authentication token
- `CONTEXT_TTL_SECONDS`: How long to keep conversation context
- `MAX_MESSAGE_LENGTH`: Discord message size limit
- `RATE_LIMIT_*`: Rate limiting thresholds

## Common Tasks

### Adding a New Message Handler

1. Add handler function in [handlers.py](handlers.py):
```python
async def handle_new_event(bot, event_data, orchestrator):
    # Process event
    # Call orchestrator if needed
    pass
```

2. Register handler in [client.py](client.py):
```python
@bot.event
async def on_new_event(event_data):
    await handle_new_event(bot, event_data, orchestrator)
```

### Modifying Response Format

Edit [formatter.py](formatter.py) functions:
- `format_response()` - Main response formatting
- `format_citations()` - Citation formatting
- `format_error()` - Error message formatting

### Adjusting Rate Limits

Update constants in [security.py](security.py) or [src/lib/constants.py](../../lib/constants.py):
```python
RATE_LIMIT_PER_USER = 10  # requests per minute
RATE_LIMIT_PER_CHANNEL = 20
```

### Testing Discord Integration

```bash
# Start bot in dev mode
python -m src.cli run --mode dev

# Health check (requires running bot)
python -m src.cli health --wait-for-discord -v
```

## Error Handling Strategy

1. **Input validation errors**: Return user-friendly message, log security events
2. **Service timeouts**: Return timeout message, don't leak internal details
3. **Discord API errors**: Retry with exponential backoff, log errors
4. **LLM failures**: Return graceful error, suggest retry

## Security Considerations

- All user input sanitized before processing
- User IDs hashed for GDPR compliance
- Rate limiting prevents abuse
- Injection attempts logged to security logger
- No sensitive data in error messages sent to users

## Dependencies

- `discord.py` - Discord API client
- `src/services/rag` - RAG retrieval service
- `src/services/llm` - LLM generation service
- `src/lib/validation` - Input validation utilities
- `src/lib/logging` - Structured logging

## Monitoring & Debugging

Enable verbose logging in [src/lib/constants.py](../../lib/constants.py):
```python
LOG_LEVEL = "DEBUG"
```

Key logs to watch:
- `event_type: injection_attempt` - Security issues
- `event_type: rate_limit_exceeded` - Abuse patterns
- `event_type: orchestration_failed` - Service failures

## Related Documentation

- [src/services/CLAUDE.md](../CLAUDE.md) - Service architecture overview
- [src/services/rag/CLAUDE.md](../rag/CLAUDE.md) - RAG retrieval details
- [src/services/llm/CLAUDE.md](../llm/CLAUDE.md) - LLM provider details
