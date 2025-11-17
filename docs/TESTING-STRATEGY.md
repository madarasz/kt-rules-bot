# Testing Strategy

**Last Updated**: 2025-11-17

This document defines the testing methodology for the Kill Team Rules Bot, focusing on meaningful behavior tests over code coverage metrics.

## Philosophy

### Core Principles

1. **Test Behaviors, Not Implementation** - Tests should verify what the system does, not how it does it
2. **Quick Feedback on Critical Paths** - Prioritize tests that detect breakage in the "user asks question" flow
3. **Meaningful Over Coverage** - 30% coverage of critical paths beats 90% coverage of boilerplate
4. **Integration Over Heavy Mocking** - Prefer testing 2-3 real components together over mocking everything
5. **Proper Mocking Boundaries** - Mock external APIs and third-party services, not your own code or frameworks

### Test Priorities (In Order)

1. **Critical Path Coverage** - Can the user ask a question and get an answer?
2. **Behavior Verification** - Does the system behave correctly in key scenarios?
3. **Error Handling** - What happens when things go wrong?
4. **Edge Cases** - Only test edge cases that reveal actual bugs
5. **Code Coverage** - We don't care about coverage metrics

---

## Test Structure

### Directory Organization

```
tests/
├── smoke/                    # Fast smoke tests for critical components
│   └── test_components_load.py
├── integration/              # Integration tests (2-3 components working together)
│   ├── test_mocked_e2e_flow.py       # Fully mocked end-to-end (orchestration only)
│   └── test_real_rag_retrieval.py    # Real ChromaDB, real chunker
├── unit/                     # Unit tests for business logic
│   ├── models/               # Model business logic (not trivial dataclass tests)
│   ├── services/             # Service layer tests
│   └── test_*.py             # Other unit tests
├── contract/                 # Contract/interface compliance tests
│   └── test_llm_structured_output.py
└── quality/                  # End-to-end quality tests (not run in CI)
└── rag/                      # RAG tests (not run in CI)
```

### Test Categories and Markers

Use pytest markers to categorize tests:

```python
@pytest.mark.fast       # < 100ms, no I/O
@pytest.mark.slow       # > 1s, uses ChromaDB or network
@pytest.mark.integration # Tests 2+ components together
@pytest.mark.smoke      # Critical path smoke test (run on every commit)
@pytest.mark.contract   # Tests interface/contract compliance
@pytest.mark.llm_api    # Requires API keys, costs money (skip in CI)
```

Run specific test suites:
```bash
pytest -m smoke                    # Quick smoke test (3-4s)
pytest -m "fast"                   # All fast tests
pytest -m "not slow and not llm_api"  # Exclude slow/expensive tests
pytest -m integration              # Integration tests only
```

---

## What TO Test

### 1. Business Logic ✅

**Test decision-making code, state transitions, and critical calculations.**

```python
# ✅ GOOD - Tests business logic
def test_should_send_low_confidence():
    """Test should_send rejects responses below threshold."""
    response = BotResponse(
        confidence_score=0.5,  # Below threshold
        rag_score=0.8,
        validation_passed=False,
        # ... other required fields
    )

    assert response.should_send() is False
```

**Why**: This tests actual business logic - the decision whether to send a response.

### 2. Critical Paths ✅

**Test the main user flows end-to-end.**

```python
# ✅ GOOD - Tests critical path
@pytest.mark.smoke
@pytest.mark.fast
def test_llm_factory_available():
    """Test LLM factory can list available providers."""
    from src.services.llm.factory import LLMProviderFactory

    providers = LLMProviderFactory.get_available_providers()

    assert len(providers) > 0
    assert "claude-4.5-sonnet" in providers
```

**Why**: Catches basic configuration/import issues that break the entire system.

### 3. Integration Tests ✅

**Test 2-3 real components working together.**

```python
# ✅ GOOD - Real integration test
@pytest.mark.slow
@pytest.mark.integration
def test_real_rag_retrieval_basic(temp_chroma_db, temp_rules_dir):
    """Test real RAG retrieval with ChromaDB."""
    # Real ingestor
    ingestor = RAGIngestor(db_path=temp_chroma_db)
    stats = ingestor.ingest_directory(temp_rules_dir)

    # Real retriever
    retriever = MultiHopRetriever(db_path=temp_chroma_db)
    context = retriever.retrieve(request)

    # Verify real behavior
    assert context.total_chunks > 0
    assert any("barricade" in chunk.text.lower()
               for chunk in context.document_chunks)
```

**Why**: Tests actual component interaction, not mocked orchestration.

### 4. Error Handling ✅

**Test what happens when things fail.**

```python
# ✅ GOOD - Tests error handling
async def test_generate_rate_limit(self, claude_adapter):
    """Test rate limit error handling."""
    claude_adapter.client.messages.create = AsyncMock(
        side_effect=Exception("rate_limit exceeded")
    )

    request = GenerationRequest(prompt="test", context=[])

    with pytest.raises(Exception, match="rate_limit"):
        await claude_adapter.generate(request)
```

**Why**: Verifies the system handles failures gracefully.

### 5. Property-Based Tests ✅

**Test invariants that should always hold.**

```python
# ✅ GOOD - Property-based test
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=5000))
def test_chunker_never_loses_content(markdown_text):
    """Property: chunking never loses significant content."""
    chunker = MarkdownChunker()
    chunks = chunker.chunk(markdown_text)

    reconstructed = "".join(chunk.text for chunk in chunks)

    # Property: content length preserved (allowing YAML frontmatter removal)
    assert len(reconstructed) >= len(markdown_text) * 0.7
```

**Why**: Tests invariants across many inputs, catches edge cases.

### 6. State Transitions ✅

**Test state changes and side effects.**

```python
# ✅ GOOD - Tests state transition
def test_context_manager_limits_history():
    """Test that context manager limits history to 10 messages."""
    manager = ConversationContextManager()

    # Add 15 messages
    for i in range(15):
        manager.add_message("ctx", role="user", text=f"Message {i}")

    context = manager.get_context("ctx")

    # Verify limit enforced
    assert len(context.message_history) == 10
    assert context.message_history[0].text == "Message 5"  # First 5 dropped
```

**Why**: Tests the actual behavior of message history trimming.

### 7. Factory Methods ✅

**Test complex object construction.**

```python
# ✅ GOOD - Tests factory method integration
def test_from_discord_message():
    """Test creating UserQuery from Discord message."""
    query = UserQuery.from_discord_message(
        discord_user_id="123456789",
        channel_id="channel123",
        message_text="Can I shoot?",
        sanitized_text="Can I shoot?"
    )

    assert isinstance(query.query_id, UUID)
    assert query.user_id == UserQuery.hash_user_id("123456789")
    assert query.conversation_context_id == f"channel123:{query.user_id}"
```

**Why**: Tests integration of multiple operations in factory method.

---

## What NOT to Test

### 1. Framework/Library Behavior ❌

**Don't test Python, third-party libraries, or frameworks.**

```python
# ❌ BAD - Tests hashlib library
def test_hash_user_id_unique():
    """Test that different IDs produce different hashes."""
    hash1 = UserQuery.hash_user_id("user123")
    hash2 = UserQuery.hash_user_id("user456")

    assert hash1 != hash2
```

**Why**: You're testing that `hashlib.sha256()` works. This is Python's job, not yours.

**Fix**: Remove this test. If hashing is critical, test it as part of a larger behavior (e.g., privacy compliance).

### 2. Trivial Dataclass Fields ❌

**Don't test that field assignment works.**

```python
# ❌ BAD - Tests dataclass field assignment
def test_citation_creation():
    """Test creating a citation."""
    citation = Citation(
        document_name="faq.md",
        section="Charge Phase",
        quote="A charge requires line of sight.",
        document_type="faq",
        last_update_date=date(2024, 10, 1),
    )

    assert citation.document_name == "faq.md"
    assert citation.section == "Charge Phase"
    assert citation.document_type == "faq"
```

**Why**: You're testing that Python dataclasses work. No business logic here.

**Fix**: Remove this test. If Citation is used correctly in integration tests, it works.

### 3. String Formatting ❌

**Don't test that f-strings or format() work.**

```python
# ❌ BAD - Tests string formatting precision
def test_time_precision():
    """Test that times are formatted with 2 decimal places."""
    result = format_statistics_summary(
        total_time=1.234567,
        initial_retrieval_time=0.987654,
        query="test"
    )

    assert "1.23s" in result
    assert "0.99s" in result
```

**Why**: You're testing Python's string formatting. This provides no value.

**Fix**: Remove this test. If the output format is critical, test it once as a smoke test.

### 4. Getter Methods ❌

**Don't test methods that just return fields.**

```python
# ❌ BAD - Tests getter method
def test_get_stats():
    """Test getting rate limit stats."""
    rate_limiter.check_rate_limit("claude", "user1")
    rate_limiter.check_rate_limit("claude", "user1")

    stats = rate_limiter.get_stats("claude", "user1")

    assert "tokens_remaining" in stats
    assert "last_update" in stats
    assert stats["tokens_remaining"] < 10
```

**Why**: You're testing that a dict has keys. No business logic.

**Fix**: Remove this test. Test the rate limiting behavior instead.

### 5. Validation Success ❌

**Don't test that valid data passes validation.**

```python
# ❌ BAD - Tests validation succeeds
def test_validate_success():
    """Test successful validation."""
    query = UserQuery(
        query_id=uuid4(),
        user_id="hashed_user_id",
        channel_id="channel123",
        # ... all required fields
    )

    query.validate()  # Should not raise
```

**Why**: If validation passes, it passes. No assertion, no value.

**Fix**: Keep only tests that verify validation **fails** for invalid data.

### 6. Redundant Negative Tests ❌

**Don't test the same guard clause multiple times.**

```python
# ❌ BAD - Redundant tests
async def test_feedback_logger_ignores_non_bot_messages():
    # ... assert feedback not logged

async def test_feedback_logger_ignores_other_reactions():
    # ... assert feedback not logged

async def test_feedback_logger_ignores_bot_own_reactions():
    # ... assert feedback not logged
```

**Why**: All three tests check the same guard clause: "if not valid, ignore". Test it once.

**Fix**: Combine into one parametrized test:
```python
@pytest.mark.parametrize("scenario", [
    "non_bot_message", "other_reaction", "bot_own_reaction"
])
def test_feedback_logger_ignores_invalid_input(scenario):
    # ... one test with multiple scenarios
```

### 7. Circular Mocking ❌

**Don't mock everything then assert on mocks.**

```python
# ❌ BAD - Circular mocking
async def test_generate_success(self, claude_adapter):
    """Test successful generation."""
    # Mock everything
    mock_response = Mock()
    mock_response.content = [Mock(type='tool_use', input={...})]
    claude_adapter.client.messages.create = AsyncMock(return_value=mock_response)

    response = await claude_adapter.generate(request)

    # Assert on mocked data
    assert isinstance(response, LLMResponse)
    assert response.provider == "claude"
```

**Why**: You mocked the API, so of course it returns what you told it to. No real behavior tested.

**Fix**: Remove "success" tests with full mocking. Test error handling only (rate limits, auth failures).

### 8. Presentation Logic ❌

**Don't test CSS-like styling or emoji placement.**

```python
# ❌ BAD - Tests emoji in string
def test_format_fallback_message():
    """Test fallback message formatting."""
    message = format_fallback_message("Low confidence")

    assert "⚠️" in message
    assert "Low confidence" in message
    assert "Try:" in message
```

**Why**: You're testing string composition. If the formatter breaks, integration tests will fail.

**Fix**: Remove this test. Keep one smoke test that formatter doesn't crash.

---

## Test Patterns

### Pattern 1: Single Assertion for Structure

```python
# ❌ BAD - Multiple assertions
assert sent_message.add_reaction.call_count == 2
reactions = [call[0][0] for call in sent_message.add_reaction.call_args_list]
assert "👍" in reactions
assert "👎" in reactions

# ✅ GOOD - Single assertion
from unittest.mock import call
assert sent_message.add_reaction.call_args_list == [call("👍"), call("👎")]
```

### Pattern 2: Test Entire Structure

```python
# ❌ BAD - Multiple assertions
assert len(result) == 1
assert result[0].header == "Movement Phase"
assert result[0].text == "Content here"

# ✅ GOOD - Single assertion
assert result == [
    MarkdownChunk(
        header="Movement Phase",
        text="Content here",
        header_level=2,
        token_count=5
    )
]
```

### Pattern 3: Property-Based Testing

```python
# Instead of testing specific examples
def test_chunker_with_5_sections():
    # ...

def test_chunker_with_10_sections():
    # ...

# ✅ GOOD - Test the property
from hypothesis import given, strategies as st

@given(st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=20))
def test_chunker_multiple_sections(section_texts):
    """Property: chunker handles any number of sections."""
    content = "\n\n".join([f"## Section {i}\n\n{text}"
                           for i, text in enumerate(section_texts)])
    chunks = chunker.chunk(content)

    assert len(chunks) >= 1
    assert len(chunks) <= len(section_texts)
```

### Pattern 4: Proper Mocking Boundaries

```python
# ✅ GOOD - Mock external APIs
@pytest.fixture
def mock_anthropic():
    """Mock Anthropic API client."""
    with patch("anthropic.AsyncAnthropic") as mock:
        yield mock

# ✅ GOOD - Mock third-party libraries
@pytest.fixture
def mock_httpx():
    """Mock httpx for Grok API."""
    with patch("httpx.AsyncClient") as mock:
        yield mock

# ❌ BAD - Don't mock discord.py framework
message = Mock(spec=discord.Message)  # Testing discord.py, not your code

# ❌ BAD - Don't mock your own models
mock_rag_context = Mock(spec=RAGContext)  # Test real RAGContext instead
```

---

## Integration Test Guidelines

### Level 1: Smoke Tests (Fastest)

**Purpose**: Verify critical components load without errors.

```python
@pytest.mark.smoke
@pytest.mark.fast
def test_llm_factory_available():
    """Smoke test: LLM factory loads."""
    from src.services.llm.factory import LLMProviderFactory
    providers = LLMProviderFactory.get_available_providers()
    assert len(providers) > 0
```

**Run**: Every commit (3-4 seconds)

### Level 2: Mocked Integration (Fast)

**Purpose**: Test orchestration logic with all components mocked.

```python
@pytest.mark.integration
@pytest.mark.fast
async def test_basic_query_flow_end_to_end(mock_rag, mock_llm):
    """Test orchestration: RAG → LLM → Response (all mocked)."""
    orchestrator = KillTeamBotOrchestrator(
        rag_retriever=mock_rag,
        llm_provider_factory=mock_llm,
        # ...
    )

    await orchestrator.process_query(message, user_query)

    # Verify components called in correct order
    mock_rag.retrieve.assert_called_once()
    mock_llm.generate.assert_called_once()
```

**Run**: Every commit (fast, no I/O)

### Level 3: Real Integration (Slow)

**Purpose**: Test 2-3 real components together.

```python
@pytest.mark.slow
@pytest.mark.integration
def test_real_rag_retrieval_basic(temp_chroma_db, temp_rules_dir):
    """Test real RAG: ingestor + retriever + ChromaDB."""
    # Real components
    ingestor = RAGIngestor(db_path=temp_chroma_db)
    ingestor.ingest_directory(temp_rules_dir)

    retriever = MultiHopRetriever(db_path=temp_chroma_db)
    context = retriever.retrieve(request)

    # Verify real behavior
    assert context.total_chunks > 0
    assert any("barricade" in chunk.text.lower()
               for chunk in context.document_chunks)
```

**Run**: Pre-commit, CI (slower, uses real DB)

### Level 4: Contract Tests (Expensive)

**Purpose**: Test real API contracts (costs money).

```python
@pytest.mark.contract
@pytest.mark.llm_api
async def test_provider_structured_output_compliance(provider):
    """Test provider returns valid JSON (real API call)."""
    llm = LLMProviderFactory.create(provider)
    response = await llm.generate(request)  # Real API call

    # Verify contract
    data = json.loads(response.answer_text)
    assert "short_answer" in data
    assert "quotes" in data
```

**Run**: Manually, not in CI (costs money)

---

## When to Write Tests

### Write Tests For:

✅ **New Features**: Test the happy path and 2-3 error cases
✅ **Bug Fixes**: Add a test that reproduces the bug, then fix it
✅ **Refactoring**: Ensure behavior tests pass before and after
✅ **Critical Paths**: User registration, query processing, payment flows
✅ **Complex Logic**: State machines, calculations, decision trees

### Don't Write Tests For:

❌ **Boilerplate**: Getters, setters, simple properties
❌ **Framework Code**: Unless you're testing your usage of it
❌ **Presentation**: String formatting, CSS-like layout
❌ **External Libraries**: You don't test pytest, don't test discord.py
❌ **Coverage Goals**: "We need 80% coverage" is not a reason

---

## Test Metrics That Matter

### Good Metrics ✅

1. **Smoke Test Pass Rate**: 100% = system boots correctly
2. **Critical Path Coverage**: Can users complete core workflows?
3. **Time to Detect Breakage**: How quickly do tests fail when code breaks?
4. **Test Run Time**: Fast tests = faster feedback
5. **False Positive Rate**: How often do tests fail incorrectly?

### Bad Metrics ❌

1. **Code Coverage %**: 30% of critical paths > 90% of everything
2. **Number of Tests**: 100 meaningful tests > 1000 trivial tests
3. **Lines of Test Code**: Less test code = easier maintenance
4. **Mocking Coverage**: Heavy mocking = not testing real behavior

---

## Migration Strategy

### From Old Tests to New Tests

**Before** (Heavy mocking, low value):
```python
def test_hash_user_id():
    result = UserQuery.hash_user_id("123")
    assert len(result) == 64  # Testing hashlib

def test_hash_user_id_consistent():
    r1 = UserQuery.hash_user_id("123")
    r2 = UserQuery.hash_user_id("123")
    assert r1 == r2  # Testing hashlib again
```

**After** (Behavior-focused):
```python
def test_from_discord_message():
    """Test factory method hashes user_id and creates context_id."""
    query = UserQuery.from_discord_message(
        discord_user_id="123456789",
        channel_id="channel123",
        message_text="Test",
        sanitized_text="Test"
    )

    # Test actual behavior: user_id is hashed, context_id is created
    assert query.user_id != "123456789"  # Should be hashed
    assert query.user_id == UserQuery.hash_user_id("123456789")
    assert query.conversation_context_id == f"channel123:{query.user_id}"
```

---

## Quick Reference

### Test Creation Checklist

Before writing a test, ask:

1. ☑️ **Does this test business logic?** (Not framework/library behavior)
2. ☑️ **Will this test fail if behavior breaks?** (Not just if code changes)
3. ☑️ **Is this the simplest way to test this?** (Avoid over-mocking)
4. ☑️ **Does this test one behavior?** (Not testing multiple things)
5. ☑️ **Is the test name descriptive?** (Explains what behavior is tested)

If you answer "no" to any question, reconsider the test.

### Test Deletion Checklist

Delete a test if:

- ☑️ It tests framework/library behavior (hashlib, string concat, dict access)
- ☑️ It tests trivial field assignment (dataclass fields)
- ☑️ It's redundant with another test (same behavior, different data)
- ☑️ It's all mocks with no real behavior (circular mocking)
- ☑️ It tests presentation/formatting (emoji placement, decimal precision)
- ☑️ It provides no failure signal (test passes even if code is wrong)

---

## Examples from Codebase

### Good Tests to Keep ✅

- `tests/smoke/test_components_load.py` - Critical component smoke tests
- `tests/integration/test_real_rag_retrieval.py` - Real ChromaDB integration
- `tests/unit/test_chunker_properties.py` - Property-based invariants
- `tests/unit/models/test_user_query.py::test_is_expired` - Business logic
- `tests/unit/test_discord_services.py::test_context_manager_limits_history` - State transitions

---

## Summary

**Good tests**:
- Focus on behavior over implementation
- Test critical paths first
- Use real components when possible
- Have clear failure signals
- Run fast

**Bad tests**:
- Test framework/library code
- Test trivial field assignment
- Mock everything
- Test string formatting
- Run slow without providing value

**Remember**: The goal is not 100% code coverage. The goal is confidence that the system works correctly. A few well-written behavior tests are worth more than hundreds of trivial tests.

**"If deleting a test doesn't make you nervous, delete it."**
