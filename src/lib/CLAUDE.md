# Library Utilities

Shared utility modules and application-wide configuration used across the entire codebase.

## Purpose

Centralized utilities for:
- Application constants and configuration
- Logging infrastructure
- Input validation
- GDPR compliance helpers
- Discord utilities
- Token management
- Metrics tracking

## Structure

```
src/lib/
├── constants.py        # Application-wide constants (SINGLE SOURCE OF TRUTH)
├── config.py           # Environment-based configuration management
├── logging.py          # Structured logging setup
├── validation.py       # Input sanitization and validation
├── gdpr.py             # GDPR compliance utilities
├── metrics.py          # Usage and performance metrics
├── tokens.py           # Token counting and limits
└── discord_utils.py    # Discord-specific utilities
```

## Key Modules

### constants.py
**SINGLE SOURCE OF TRUTH** for all tunable parameters:
- LLM generation parameters (timeouts, max tokens, temperature)
- RAG retrieval settings (max chunks, relevance threshold)
- Embedding and chunking limits
- Quality test configuration
- Discord bot personality settings
- File paths for prompts and personality files

**Important**: Modify values in `constants.py` to change behavior across the entire application. All other modules import from here.

### config.py
Environment-based configuration:
- Loads `.env` file using `python-dotenv`
- Provides `Config` dataclass with validated settings
- Manages API keys (Discord, Anthropic, OpenAI, Google, X/Grok)
- Defines `LLMProvider` type literal for type safety
- Default values pulled from `constants.py`

Usage:
```python
from src.lib.config import get_config

config = get_config()
api_key = config.openai_api_key
```

### logging.py
Structured logging infrastructure:
- Configurable log levels
- Consistent formatting across modules
- Supports file and console output
- Integration with asyncio

Usage:
```python
from src.lib.logging import get_logger

logger = get_logger(__name__)
logger.info("Processing query", extra={"user_id": "123"})
```

### validation.py
Input sanitization and validation:
- Discord message sanitization
- PII detection and removal
- Input length limits
- Special character handling
- XSS/injection prevention

### gdpr.py
GDPR compliance utilities:
- User ID hashing (SHA-256)
- Data deletion helpers
- PII redaction
- Right to erasure support

### tokens.py
Token counting and management:
- Token estimation for embeddings
- Chunk size validation
- Model-specific token limits
- Cost estimation helpers

### discord_utils.py
Discord-specific utilities:
- Message formatting
- Embed creation
- Rate limit handling
- Channel/user validation

### metrics.py
Usage and performance metrics:
- Query count tracking
- Response time measurement
- Error rate monitoring
- Model usage statistics

## Configuration Flow

1. `.env` file → `config.py` loads environment variables
2. `constants.py` provides default values and limits
3. Application code imports from `config.py` or `constants.py`
4. Runtime overrides possible via CLI arguments

## Development Guidelines

### Adding New Constants

1. Add to appropriate section in [constants.py](../../src/lib/constants.py)
2. Include clear comments explaining purpose
3. Group related constants together
4. Document any dependencies or tuning history

### Configuration Best Practices

- Never hardcode values in business logic
- Always import from `constants.py` or `config.py`
- Use type hints for configuration values
- Validate configuration at startup
- Log configuration values (excluding secrets)

### GDPR Compliance

When handling user data:
- Always hash user IDs using `gdpr.py` helpers
- Implement data deletion in all storage layers
- Document PII in data models
- Test deletion workflows regularly

### Logging Standards

- Use appropriate log levels (DEBUG, INFO, WARNING, ERROR)
- Include context in structured fields
- Never log PII or API keys
- Use logger names matching module paths

## Dependencies

Core dependencies:
- `python-dotenv` - Environment variable loading
- Standard library: `dataclasses`, `pathlib`, `os`, `hashlib`

Integration points:
- Used by all `src/services/` modules
- Used by all `src/cli/` commands
- Used by all `src/models/` dataclasses
- Referenced in test frameworks
