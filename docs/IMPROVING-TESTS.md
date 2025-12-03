# Test Quality Improvement Guide

**Last Updated**: 2025-12-03
**Overall Test Suite Score**: 7.1/10

## Executive Summary

The Kill Team Rules Bot test suite demonstrates strong fundamentals with excellent examples of behavior-driven testing, but contains ~20% waste in boilerplate tests and over-mocked integration tests that won't catch real bugs.

**Key Strengths:**
- ✅ Contract tests ensure LLM provider interchangeability
- ✅ Orchestration tests focus on delegation, not implementation
- ✅ Complex business logic well-tested (team filtering, query expansion, quote validation)
- ✅ Property-based testing with Hypothesis
- ✅ Real integration tests with ChromaDB

**Key Weaknesses:**
- ❌ Some integration tests over-mocked (won't catch real bugs)
- ❌ ~20% of unit tests are boilerplate (testing constructors, field assignment)
- ❌ Circular mocking (mock the thing, then test the mock)

---

## Test Quality Assessment by Directory

### tests/contract/ - ✅ EXCELLENT (9/10)

**File**: `test_llm_structured_output.py` (234 lines + new Pydantic tests)

This is the **best test file** in the suite - a model for how contract tests should work:

**What it tests:**
- All LLM providers return valid JSON conforming to schema
- Pydantic-native providers (Claude, ChatGPT) populate `structured_output` field
- JSON-only providers (Gemini, Grok, DeepSeek) validate with post-processing
- All schema variants (Answer, HopEvaluation, CustomJudgeResponse)
- Direct Pydantic model validation

**Why it's excellent:**
- ✅ Tests actual behavior with real API calls
- ✅ Parameterized across all providers
- ✅ Tests real API contracts, not mocks
- ✅ **Would catch real bugs**: Invalid JSON, missing fields, provider quirks
- ✅ Enables provider swapping with confidence

**Key takeaway**: Contract tests should verify interfaces that enable system flexibility.

---

### tests/integration/ - ⚠️ MIXED (6.5/10)

#### ✅ GOOD: `test_real_rag_retrieval.py` (8/10)

**What it tests**: RAG retrieval with real ChromaDB

**Why it's good:**
- Uses real ChromaDB (temporary)
- Tests actual retrieval behavior
- Tests keyword normalization with real indexing
- **Would catch**: Vector search failures, normalization bugs, ChromaDB issues

#### ✅ GOOD: `test_chunk_summary_e2e.py` (7/10)

**What it tests**: Chunk summary generation pipeline

**Why it's good:**
- Real OpenAI API calls (`@pytest.mark.llm_api`)
- Tests cost tracking, metadata storage, error handling
- **Would catch**: API failures, cost calculation errors

#### ❌ NEEDS REWRITE: `test_mocked_e2e_flow.py` (4/10)

**Problem**: Everything is mocked - won't catch real bugs

```python
# Current: Over-mocked
orchestrator = KillTeamBotOrchestrator(
    rag_retriever=mock_rag_retriever,  # Mocked
    llm_provider_factory=mock_factory,  # Mocked
)
# Then just checks that mocks were called
assert message.channel.send.called  # Tests nothing useful
```

**Won't catch:**
- RAG retrieval bugs
- LLM generation issues
- Discord API problems
- Message formatting errors

**Should be**: Use real RAG with test DB, HTTP mocking for LLM (realistic responses), real Discord message formatting.

---

### tests/smoke/ - ✅ GOOD (8/10)

**File**: `test_components_load.py` (148 lines)

Perfect smoke tests - fast, catch import/configuration errors on every commit.

---

### tests/unit/ - ⚠️ MIXED (6.8/10)

#### ✅ EXCELLENT Unit Tests (Models to Follow)

**1. `test_orchestrator.py` (750 lines) - 9/10**
- Tests delegation, not implementation
- Tests parameter passing between services
- Even has comments: "Excludes RAG internals, LLM internals, boilerplate"
- **Would catch**: Orchestration logic errors, parameter passing bugs, race conditions

**2. `test_query_expander.py` (261 lines) - 9/10**
- Comprehensive synonym expansion testing
- Tests edge cases: empty query, punctuation, unicode, word boundaries
- **Would catch**: All synonym expansion bugs

**3. `test_database.py` (414 lines) - 8/10**
- All CRUD operations, GDPR cleanup, filtering, search
- Uses temporary database for isolation
- **Would catch**: Database schema issues, query bugs, retention policy failures

**4. `test_team_filter.py` + `test_strategies.py` (472 + 311 lines) - 8/10**
- Complex matching algorithms, fuzzy matching, aliases
- **Would catch**: False positives/negatives in team filtering

**5. `test_quote_validator.py` (170 lines) - 9/10**
- Fuzzy quote matching with real-world examples
- Tests case-insensitive, whitespace normalization, similarity threshold
- **Would catch**: Quote validation failures in production

**6. `test_chunker_properties.py` (128 lines) - 9/10**
- Property-based testing with Hypothesis
- Tests invariants: content never lost, chunks always valid
- **Would catch**: Edge cases with unusual markdown structures

#### ❌ ANTI-PATTERN Tests (Should be Simplified/Deleted)

**1. `test_user_query.py` (78 lines) - 4/10**

70% tests field assignment (boilerplate):

```python
def test_from_discord_message(self):
    query = UserQuery.from_discord_message(...)
    assert query.user_id == UserQuery.hash_user_id(...)  # Just tests assignment
    assert query.channel_id == channel_id  # Just tests assignment
```

**Keep**: `test_is_expired_expired()` - actual date logic
**Delete**: All field assignment tests
**Reduction**: 78 lines → ~20 lines

**2. `test_bot_response.py` (148 lines) - 5/10**

Mixed quality:
- ✅ Keep: `should_send()` threshold logic, `split_for_discord()` chunking
- ❌ Delete: `test_create()` - just tests a factory that assigns fields

**3. `test_cli_commands.py` (276 lines) - 5/10**

Tests CLI routing, but just verifies mocks were called. Doesn't test actual command behavior.

#### ⚠️ OVER-MOCKED Unit Tests

**1. `test_llm_adapters.py` (413 lines) - 6/10**

Tests error handling but mocks everything:
- Pattern: Mock Anthropic client, then test error mapping
- **Better**: Use `@pytest.mark.llm_api` for real API tests (like contract tests)

**2. `test_multi_hop_retriever.py` (594 lines) - 7/10**

Tests hop evaluation logic (good), but everything is mocked (LLM, base retriever).
- **Would catch**: Logic bugs in orchestration, NOT actual retrieval bugs

---

## Testing Philosophy: 15 Core Principles

### 1. Test Outcomes, Not Implementation

❌ **Bad**: Test that a method was called
```python
def test_process_query_calls_rag(self):
    orchestrator.process_query(query)
    assert mock_rag.retrieve.called  # Tests wiring, not outcome
```

✅ **Good**: Test the outcome
```python
def test_process_query_includes_relevant_chunks(self):
    response = orchestrator.process_query("Can I overwatch a charge?")
    assert "overwatch" in response.rag_context.chunks[0].text
    assert response.confidence > 0.7
```

---

### 2. Don't Test What You Don't Own

❌ **Bad**: Test library behavior
```python
def test_uuid_is_unique(self):
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()
    assert id1 != id2  # Testing Python's uuid library
```

✅ **Good**: Test your logic that uses the library
```python
def test_query_ids_are_unique_across_users(self):
    query1 = UserQuery.from_discord("user1", "question")
    query2 = UserQuery.from_discord("user2", "question")
    assert query1.query_id != query2.query_id
```

---

### 3. Prefer Real Dependencies in Integration Tests

**Hierarchy of test doubles** (prefer earlier):
1. **Real dependency** (temporary DB, test API)
2. **HTTP mocking** (realistic responses)
3. **Fake implementation** (in-memory DB)
4. **Stub** (returns fixed data)
5. **Mock** (verifies calls) ← Use as last resort

❌ **Bad**: Mock everything
```python
def test_e2e_flow(self):
    orchestrator = KillTeamBotOrchestrator(
        rag_retriever=Mock(),  # Not testing real retrieval
        llm_provider=Mock(),   # Not testing real generation
    )
    orchestrator.process_query("test")
    assert True  # What did we test?
```

✅ **Good**: Use real dependencies where possible
```python
def test_e2e_flow_with_real_rag(self):
    # Real ChromaDB with test data
    rag = RagRetriever(create_test_chroma_db())

    # HTTP mock for LLM (realistic responses)
    with mock_llm_http_response({"content": "Based on chunk [C1]..."}):
        response = orchestrator.process_query("Can I overwatch?")

    # Tests real retrieval + LLM integration
    assert response.rag_context.chunks  # Real chunks retrieved
    assert "[C1]" in response.answer  # LLM used chunks
```

---

### 4. Don't Test Constructors/Getters/Setters

❌ **Bad**: Test field assignment
```python
def test_create_user_query(self):
    query = UserQuery(
        query_id=uuid.uuid4(),
        text="question",
        user_id="user123"
    )
    assert query.query_id is not None  # Trivial
    assert query.text == "question"     # Trivial
    assert query.user_id == "user123"   # Trivial
```

✅ **Good**: Test computed properties or business logic
```python
def test_query_expires_after_15_minutes(self):
    query = UserQuery(text="question", timestamp=now() - timedelta(minutes=20))
    assert query.is_expired()

    recent_query = UserQuery(text="question", timestamp=now())
    assert not recent_query.is_expired()
```

---

### 5. Test Edge Cases, Not Just Happy Path

❌ **Bad**: Only test normal input
```python
def test_split_message(self):
    chunks = split_for_discord("Hello world")
    assert len(chunks) == 1
```

✅ **Good**: Test boundaries and edge cases
```python
@pytest.mark.parametrize("length,expected_chunks", [
    (1000, 1),           # Normal
    (2000, 1),           # Boundary
    (2001, 2),           # Just over boundary
    (4000, 2),           # Multiple chunks
    (0, 0),              # Empty
])
def test_split_message_at_discord_limit(length, expected_chunks):
    message = "x" * length
    chunks = split_for_discord(message)
    assert len(chunks) == expected_chunks
    assert all(len(chunk) <= 2000 for chunk in chunks)
```

---

### 6. Test One Behavior Per Test

❌ **Bad**: Test multiple behaviors
```python
def test_orchestrator(self):
    response = orchestrator.process_query("question")
    assert response.answer  # Tests generation
    assert response.rag_context.chunks  # Tests retrieval
    assert response.confidence > 0.5  # Tests confidence
    assert response.source_documents  # Tests attribution
```

✅ **Good**: Separate tests for each behavior
```python
def test_orchestrator_retrieves_relevant_chunks(self):
    response = orchestrator.process_query("overwatch rules")
    assert any("overwatch" in chunk.text.lower()
               for chunk in response.rag_context.chunks)

def test_orchestrator_generates_answer_with_chunk_attribution(self):
    response = orchestrator.process_query("question")
    # Check that answer references chunks
    chunk_ids = {c.chunk_id for c in response.rag_context.chunks}
    assert any(f"[{cid}]" in response.answer for cid in chunk_ids)
```

---

### 7. Use Descriptive Test Names That Explain Intent

❌ **Bad**: Vague names
```python
def test_query(self):
def test_error(self):
def test_basic(self):
```

✅ **Good**: Names that document behavior
```python
def test_query_expansion_replaces_lowercase_keywords_with_proper_case(self):
def test_llm_provider_retries_on_rate_limit_with_exponential_backoff(self):
def test_discord_message_splits_at_2000_chars_on_sentence_boundary(self):
```

**Format**: `test_<component>_<action>_<expected_outcome>_<conditions>`

---

### 8. Avoid Circular Mocking

❌ **Bad**: Mock the thing, then test the mock
```python
def test_anthropic_handles_rate_limit(self):
    mock_client = Mock()
    mock_client.messages.create.side_effect = RateLimitError()

    provider = AnthropicProvider(client=mock_client)
    with pytest.raises(RateLimitError):
        provider.generate("test")

    # What did we test? That Mock() works?
```

✅ **Good**: Test with real HTTP responses or real API
```python
@pytest.mark.llm_api
def test_anthropic_handles_rate_limit(self):
    # Use real API or HTTP mocking library with realistic response
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            "https://api.anthropic.com/v1/messages",
            status=429,
            json={"error": {"message": "Rate limit exceeded"}},
        )

        provider = AnthropicProvider()
        with pytest.raises(RateLimitError):
            provider.generate("test")
```

---

### 9. Test Error Paths, Not Just Success Paths

❌ **Bad**: Only test success
```python
def test_query_processing(self):
    response = orchestrator.process_query("valid question")
    assert response.answer
```

✅ **Good**: Test failure modes
```python
def test_query_processing_handles_rag_retrieval_failure(self):
    with mock_chroma_connection_error():
        response = orchestrator.process_query("question")
        assert "unable to retrieve" in response.answer.lower()
        assert response.confidence == 0.0

def test_query_processing_handles_llm_timeout(self):
    with mock_llm_timeout():
        response = orchestrator.process_query("question")
        assert response.answer == "Request timed out"
```

---

### 10. Use Property-Based Testing for Algorithms

❌ **Bad**: Only test specific examples
```python
def test_chunker(self):
    chunks = chunk_document("# Header\nContent")
    assert len(chunks) == 1
```

✅ **Good**: Test properties that should always hold
```python
@given(st.text(min_size=1, max_size=10000))
def test_chunker_preserves_all_content(document):
    chunks = chunk_document(document)
    reconstructed = "".join(chunk.text for chunk in chunks)
    assert reconstructed == document  # No content lost

@given(st.text(min_size=1, max_size=10000))
def test_chunker_respects_max_size(document):
    chunks = chunk_document(document, max_size=500)
    assert all(len(chunk.text) <= 500 for chunk in chunks)
```

---

### 11. Test Contracts, Not Implementations

❌ **Bad**: Test internal implementation
```python
def test_retriever_uses_cosine_similarity(self):
    retriever = VectorRetriever()
    assert retriever._distance_metric == "cosine"  # Tests implementation
```

✅ **Good**: Test the contract/interface
```python
def test_retriever_returns_most_relevant_chunks_first(self):
    retriever = VectorRetriever()
    chunks = retriever.retrieve("overwatch rules")

    # First chunk should have highest relevance
    assert all(chunks[i].score >= chunks[i+1].score
               for i in range(len(chunks)-1))

    # Top result should be semantically relevant
    assert "overwatch" in chunks[0].text.lower()
```

---

### 12. Integration Tests Should Test Integration, Not Units

❌ **Bad**: Integration test that's really a unit test
```python
def test_e2e_flow(self):
    # Everything mocked → not testing integration
    rag = Mock(return_value=[chunk1, chunk2])
    llm = Mock(return_value="answer")

    orchestrator = Orchestrator(rag=rag, llm=llm)
    response = orchestrator.process("question")

    assert rag.called  # Testing units, not integration
    assert llm.called
```

✅ **Good**: Test actual component integration
```python
def test_e2e_flow_rag_to_llm_integration(self):
    # Real RAG with test database
    rag = RagRetriever(create_test_chroma_db())

    # Real or HTTP-mocked LLM
    llm = ClaudeProvider()

    orchestrator = Orchestrator(rag=rag, llm=llm)
    response = orchestrator.process("Can I overwatch a charge?")

    # Tests that:
    # 1. RAG actually retrieves relevant chunks
    # 2. LLM receives chunks in correct format
    # 3. LLM generates answer using chunks
    # 4. Attribution is preserved
    assert response.rag_context.chunks
    assert response.answer
    assert any("[C" in response.answer)  # Chunk attribution present
```

---

### 13. Don't Test Logging/Formatting (Unless Critical to UX)

❌ **Bad**: Test log messages
```python
def test_logging(self, caplog):
    process_query("question")
    assert "Processing query" in caplog.text
```

✅ **Good**: Test user-facing behavior
```python
def test_discord_message_formats_chunks_as_quoted_text(self):
    response = BotResponse(
        answer="The rule states...",
        source_chunks=[chunk1, chunk2]
    )

    formatted = format_for_discord(response)

    # Tests user-visible formatting
    assert "> " in formatted  # Quotes are preserved
    assert "**Source:**" in formatted  # Attribution header
```

---

### 14. Use Fixtures for Common Setup, Not for Test Logic

❌ **Bad**: Fixture contains test assertions
```python
@pytest.fixture
def processed_query(orchestrator):
    response = orchestrator.process("question")
    assert response.answer  # DON'T assert in fixtures
    return response
```

✅ **Good**: Fixture only does setup
```python
@pytest.fixture
def test_chroma_db(tmp_path):
    """Creates isolated test database with sample data."""
    db_path = tmp_path / "test_chroma"
    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.create_collection("test")

    # Add test data
    collection.add(
        documents=["Overwatch rule text..."],
        ids=["chunk1"],
    )

    yield client
    # Cleanup happens automatically with tmp_path
```

---

### 15. Test Fast, Deterministic, Isolated, Repeatable (F.I.R.S.T.)

**Fast:** Unit tests <100ms, integration tests <5s
- Use `tmp_path` fixtures, not real files
- Use in-memory databases where possible
- Mark slow tests: `@pytest.mark.slow`

**Isolated:** Tests don't affect each other
- Use temporary databases
- Clean up state after each test
- Don't share mutable fixtures

**Repeatable:** Same input = same output
- Don't use `datetime.now()` → use fixed timestamps or freezegun
- Don't use random data → use fixed seeds
- Don't depend on external services → use HTTP mocking

**Self-Validating:** Pass/fail, no manual inspection
- ❌ `print(response)` → manual inspection
- ✅ `assert response.confidence > 0.7` → automatic

**Timely:** Write tests with code, not after
- TDD: Write test first (documents intent)
- Or: Write test immediately after implementation

---

## Pytest Markers

The project uses custom pytest markers to categorize tests:

```ini
# Run tests with: pytest -m "marker_name"
# Skip tests with: pytest -m "not marker_name"

fast          # < 100ms, no I/O
slow          # > 1s, uses ChromaDB
integration   # End-to-end pipeline tests
smoke         # Critical path tests
contract      # Interface compliance tests
llm_api       # Requires LLM API keys, costs money
embedding     # Creates embeddings via OpenAI API, costs money
```

**Examples:**
```bash
# Run fast tests only
pytest -m "fast"

# Run integration tests but skip expensive API calls
pytest -m "integration and not llm_api and not embedding"

# Run all tests except slow ones
pytest -m "not slow"

# Run contract tests only
pytest tests/contract/ -m "contract"
```

**When to use each marker:**

- `@pytest.mark.fast`: Unit tests with no I/O (<100ms)
- `@pytest.mark.slow`: Integration tests with ChromaDB (>1s)
- `@pytest.mark.integration`: Tests that integrate multiple components
- `@pytest.mark.smoke`: Critical path tests for CI/CD
- `@pytest.mark.contract`: Interface compliance tests (LLM providers, schemas)
- `@pytest.mark.llm_api`: Tests that call LLM APIs (Claude, GPT, Gemini, Grok, DeepSeek)
- `@pytest.mark.embedding`: Tests that create embeddings (OpenAI text-embedding-3-small/large)

---

## Test Quality Checklist

Before merging a test, ask:

- [ ] **Would this catch a real bug?** (Not just typos/signatures)
- [ ] **Does it test behavior, not structure?** (Outcomes, not calls)
- [ ] **Is it testing my code, not libraries?** (Own your tests)
- [ ] **Would it still pass if I refactored?** (Not brittle)
- [ ] **Does it use real dependencies where practical?** (Not over-mocked)
- [ ] **Does the test name explain what it tests?** (Documentation)
- [ ] **Does it test edge cases, not just happy path?** (Boundaries)
- [ ] **Is it fast, isolated, and deterministic?** (FIRST principles)

**If 6+ checkboxes are ✅** → Good test
**If <4 checkboxes are ✅** → Consider deleting

---

## Action Items by Priority

### 🔥 High Priority

**1. Rewrite `test_mocked_e2e_flow.py`** (Effort: Medium, 2-3 hours)
- Use real RAG with test database
- Use HTTP-mocked LLM with realistic responses
- Test actual Discord message formatting
- **Impact**: Actually catch integration bugs

**2. Simplify `test_user_query.py`** (Effort: Low, 30 minutes)
- Delete field assignment tests
- Keep only `is_expired` logic tests
- **Impact**: Remove noise, improve signal (78 lines → ~20 lines)

**3. Add missing edge case tests** (Effort: Medium, 2-3 hours)
- Discord formatting: Messages >2000 chars, embed limits, markdown escaping
- Multi-server configuration: Per-guild API key handling
- **Impact**: Catch production bugs

### ✅ Keep These as Reference Implementations

Use these as models when writing new tests:

- `test_llm_structured_output.py` → Contract testing
- `test_orchestrator.py` → Orchestration testing
- `test_query_expander.py` → Behavior testing
- `test_chunker_properties.py` → Property-based testing
- `test_real_rag_retrieval.py` → Integration testing with real dependencies

### 📊 Test Quality Scorecard

| Category | Files | Lines | Quality | Status |
|----------|-------|-------|---------|--------|
| **Contract** | 1 | 234+ | 9/10 | ✅ Keep (model) |
| **Integration** | 4 | 855 | 6.5/10 | ⚠️ Rewrite 1 file |
| **Smoke** | 1 | 148 | 8/10 | ✅ Keep |
| **Unit** | 19 | ~4800 | 6.8/10 | ⚠️ Simplify 3 files |
| **Overall** | **25** | **~6000** | **7.1/10** | **80% keep, 20% improve** |

---

## Examples from This Codebase

### ✅ Excellent Test: `test_orchestrator.py`

```python
def test_orchestrator_with_rag_only_mode(self):
    """Test RAG-only mode without LLM generation."""
    query = UserQuery(
        query_id=uuid.uuid4(),
        text="What is overwatch?",
        user_id="user123",
        channel_id="channel456"
    )

    # Mock RAG retriever to return test chunks
    mock_retriever = Mock()
    mock_retriever.retrieve.return_value = RAGContext(
        chunks=[test_chunk],
        total_chunks=1,
        avg_relevance=0.9
    )

    orchestrator = KillTeamBotOrchestrator(
        rag_retriever=mock_retriever,
        llm_provider_factory=None,  # No LLM needed
    )

    # Execute with rag_only=True
    response = orchestrator.execute_query(query, rag_only=True)

    # Verify RAG was called but LLM was not
    mock_retriever.retrieve.assert_called_once()
    assert response.rag_context.total_chunks == 1
    assert response.answer_text == ""  # No LLM generation
```

**Why it's good:**
- Tests delegation behavior, not implementation details
- Tests a specific mode (RAG-only)
- Clear test name explains intent
- Asserts on outcomes, not just mock calls

---

### ❌ Poor Test: `test_user_query.py`

```python
def test_from_discord_message(self):
    """Test creating UserQuery from Discord message."""
    discord_user_id = "123456789"
    channel_id = "987654321"
    query_text = "Can I shoot twice?"

    query = UserQuery.from_discord_message(
        discord_user_id=discord_user_id,
        channel_id=channel_id,
        query_text=query_text
    )

    # All these just test field assignment (boilerplate)
    assert isinstance(query.query_id, UUID)
    assert query.user_id == UserQuery.hash_user_id(discord_user_id)
    assert query.channel_id == channel_id
    assert query.text == query_text
```

**Why it's poor:**
- Tests field assignment (boilerplate)
- Would only catch typos in variable names
- Breaks on constructor signature changes
- No business logic being tested

**Better version** (only test actual behavior):
```python
def test_query_expires_after_timeout(self):
    """Test that queries expire after CONVERSATION_TIMEOUT."""
    old_timestamp = datetime.now() - timedelta(minutes=20)
    query = UserQuery(text="question", timestamp=old_timestamp)
    assert query.is_expired()
```

---

## Common Anti-Patterns to Avoid

### 1. Testing Private Methods

❌ **Don't do this:**
```python
def test_orchestrator_validate_input(self):
    orchestrator = KillTeamBotOrchestrator()
    assert orchestrator._validate_input("test")  # Testing private method
```

✅ **Do this instead:**
```python
def test_orchestrator_rejects_empty_query(self):
    orchestrator = KillTeamBotOrchestrator()
    with pytest.raises(ValueError):
        orchestrator.execute_query(UserQuery(text=""))
```

---

### 2. Testing Constants

❌ **Don't do this:**
```python
def test_constants(self):
    assert MAX_CHUNKS == 10
    assert RELEVANCE_THRESHOLD == 0.7
```

✅ **Do this instead**: Use the constants in behavior tests:
```python
def test_retriever_respects_max_chunks_limit(self):
    retriever = RAGRetriever()
    context = retriever.retrieve("query")
    assert len(context.chunks) <= MAX_CHUNKS
```

---

### 3. Snapshot Testing Everything

❌ **Don't do this:**
```python
def test_format_response(snapshot):
    response = format_response(data)
    assert response == snapshot  # Brittle, breaks on any formatting change
```

✅ **Do this instead**:
```python
def test_format_response_includes_required_fields(self):
    response = format_response(data)
    assert "answer" in response
    assert "sources" in response
    assert len(response["sources"]) > 0
```

---

## Resources

- [Martin Fowler on Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html)
- [Google Testing Blog](https://testing.googleblog.com/)
- [Hypothesis (Property-Based Testing)](https://hypothesis.readthedocs.io/)
- [pytest Documentation](https://docs.pytest.org/)

---

## Conclusion

The Kill Team Rules Bot has a solid test foundation with room for improvement. Focus on:

1. **Testing behavior, not structure**
2. **Using real dependencies in integration tests**
3. **Deleting boilerplate tests**
4. **Writing descriptive test names**
5. **Testing edge cases and error paths**

By following these principles, we can improve the test suite from **7.1/10 to 8.5/10** with 1-2 days of focused effort.

**Remember**: A test that doesn't catch bugs is worse than no test at all - it creates false confidence and maintenance burden.
