# Test Suite (tests/)

Comprehensive test suite for the Kill Team Rules Discord Bot, covering unit tests, integration tests, contract tests, and quality evaluation.

## Purpose

Ensures reliability, correctness, and maintainability through:
- **Unit tests** - Individual module and function testing
- **Integration tests** - End-to-end pipeline validation
- **Contract tests** - Interface compliance verification
- **Quality tests** - LLM response quality evaluation

## Directory Structure

```
tests/
├── unit/           # Unit tests for individual modules
├── integration/    # Integration tests for full pipeline
├── contract/       # Contract tests for interface compliance
└── quality/        # Quality evaluation framework
```

## Test Categories

### [unit/](unit/) - Unit Tests
Tests individual modules and functions in isolation.

**Test files:**
- `test_cli_commands.py` - CLI command parsing and routing
- `test_discord_services.py` - Discord bot handlers and utilities
- `test_llm_adapters.py` - LLM provider implementations
- `test_rag_services.py` - RAG retrieval and chunking

**Coverage:**
- Input validation and sanitization
- Data model creation and helpers
- Utility functions (hashing, formatting, etc.)
- Configuration loading
- Error handling

**Running:**
```bash
pytest tests/unit/ -v
pytest tests/unit/test_llm_adapters.py  # Single file
```

### [integration/](integration/) - Integration Tests
Tests complete workflows with real or mocked external services.

**Test files:**
- `test_basic_query.py` - End-to-end query processing

**Coverage:**
- RAG + LLM pipeline integration
- Discord message handling flow
- Vector database operations
- Multi-turn conversations

**Running:**
```bash
pytest tests/integration/ -v
```

**Note:** Integration tests may require:
- Vector database (ChromaDB) running
- API keys in environment
- Ingested test data

### [contract/](contract/) - Contract Tests
Verifies interface compliance and provider independence.

**Test files:**
- `test_llm_adapter.py` - LLM provider interface contracts
- `test_rag_pipeline.py` - RAG retrieval interface contracts

**Coverage:**
- Abstract base class implementations
- Interface method signatures
- Response format consistency
- Error handling contracts

**Running:**
```bash
pytest tests/contract/ -v
```

**Purpose:**
Ensures all LLM providers implement the same interface correctly, enabling provider-agnostic code and easy provider swapping.

### [quality/](quality/CLAUDE.md) - Quality Evaluation
Automated quality testing framework for evaluating RAG + LLM response quality across models.

See [quality/CLAUDE.md](quality/CLAUDE.md) for detailed documentation.

**Key features:**
- Test case definitions with expected answers
- LLM-based response evaluation (judge models)
- Multi-model comparison
- Historical tracking and visualization
- Comprehensive reporting

**Running:**
```bash
python -m src.cli quality-test                    # Default model
python -m src.cli quality-test --all-models       # All models
python -m src.cli quality-test --test track-enemy # Specific test
python -m src.cli quality-test --runs 5           # Multiple runs
```

## Test Configuration

### Environment Setup
```bash
# Copy template
cp config/.env.template config/.env

# Set required keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
```

### Test Data
Some tests require ingested rules:
```bash
python -m src.cli ingest extracted-rules/
```

### pytest Configuration
Configured in `pyproject.toml` or `pytest.ini`:
- Test discovery patterns
- Coverage reporting
- Parallel execution
- Fixtures and markers

## Test Fixtures

Common fixtures used across tests:
- `mock_config` - Mocked configuration
- `mock_llm_provider` - Mocked LLM provider
- `mock_vector_db` - Mocked vector database
- `sample_query` - Sample user query
- `sample_chunks` - Sample RAG chunks

## Running Tests

### All tests
```bash
pytest
```

### Specific category
```bash
pytest tests/unit/
pytest tests/integration/
pytest tests/contract/
```

### With coverage
```bash
pytest --cov=src --cov-report=html
```

### Verbose output
```bash
pytest -v
pytest -vv  # Extra verbose
```

### Run specific test
```bash
pytest tests/unit/test_llm_adapters.py::test_claude_generation
```

### Quality tests (via CLI)
```bash
python -m src.cli quality-test --all-models
```

## Test Development Guidelines

### Writing Unit Tests
- Test one function/method per test
- Use mocks for external dependencies
- Keep tests fast and deterministic
- Follow AAA pattern (Arrange, Act, Assert)

```python
def test_hash_user_id():
    """Test user ID hashing for GDPR compliance."""
    # Arrange
    discord_id = "123456789"

    # Act
    hashed = UserQuery.hash_user_id(discord_id)

    # Assert
    assert len(hashed) == 64  # SHA-256 hex length
    assert hashed != discord_id
```

### Writing Integration Tests
- Test complete workflows
- Use real services where possible (or realistic mocks)
- Clean up resources after tests
- Test error scenarios

```python
async def test_query_pipeline():
    """Test end-to-end query processing."""
    # Arrange
    query = "Can I use overwatch?"

    # Act
    response = await process_query(query)

    # Assert
    assert response.text
    assert response.source_citations
    assert not response.error
```

### Writing Contract Tests
- Test interface compliance
- Verify all providers implement same behavior
- Test error handling contracts

```python
@pytest.mark.parametrize("provider", ["claude-sonnet", "gpt-4.1", "gemini-2.5-pro"])
async def test_llm_generation_contract(provider):
    """All LLM providers must implement generate() correctly."""
    llm = LLMProviderFactory.create(provider)
    response = await llm.generate(request)

    assert isinstance(response, str)
    assert len(response) > 0
```

### Writing Quality Tests
- Define clear expected answers
- Tag with difficulty and category
- Store in `tests/quality/test_cases/`
- Use YAML or JSON format

See [quality/CLAUDE.md](quality/CLAUDE.md) for quality test guidelines.

## Continuous Integration

Tests run automatically on:
- Pull requests
- Commits to main branch
- Scheduled nightly runs

GitHub Actions workflow:
- Runs all unit and contract tests
- Generates coverage reports
- Runs quality tests (nightly)
- Reports failures

## Coverage Goals

Target coverage by category:
- **Unit tests**: 80%+ coverage
- **Integration tests**: Critical paths covered
- **Contract tests**: All interfaces verified
- **Quality tests**: Key scenarios tested across models

## Test Maintenance

### Regular tasks:
1. Update tests when changing code
2. Add tests for new features
3. Review and update quality test cases
4. Archive old quality test results
5. Update mocks when external APIs change

### When tests fail:
1. Check if bug in code (fix code)
2. Check if test is outdated (update test)
3. Check if contract changed (update interface)
4. Check if quality regression (investigate model/prompt)

## Dependencies

Test dependencies:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting
- `pytest-mock` - Mocking utilities
- Application dependencies from `requirements.txt`

## Documentation

Subdirectory documentation:
- [quality/CLAUDE.md](quality/CLAUDE.md) - Quality testing framework

Test documentation in docstrings:
```python
def test_feature():
    """Test feature X under condition Y.

    Verifies that feature X behaves correctly when condition Y is met,
    including edge cases A, B, and C.
    """
```
