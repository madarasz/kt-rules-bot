# Testing Strategy

**Last Updated**: 2025-12-03

This document defines the high-level testing strategy for the Kill Team Rules Bot, covering unit tests, RAG tests, and quality tests. For detailed implementation guidelines, see [IMPROVING-TESTS.md](IMPROVING-TESTS.md).

---

## Overview

The Kill Team Rules Bot testing strategy prioritizes **meaningful behavior verification** over code coverage metrics. We employ three complementary testing approaches:

1. **Unit Tests (pytest)** - Fast feedback on business logic and critical paths
2. **RAG Tests** - Validate retrieval accuracy and relevance
3. **Quality Tests** - Compare LLM model performance on domain-specific scenarios

---

## Unit Tests (pytest)

### Purpose

Unit tests provide rapid feedback during development by verifying that individual components behave correctly. They focus on business logic, state transitions, and critical paths rather than framework or library behavior.

### Philosophy

**Test Behaviors, Not Implementation**

Tests should verify *what* the system does, not *how* it does it. A good test:
- Fails when behavior breaks (not just when code changes)
- Tests outcomes, not method calls
- Uses real dependencies where practical
- Runs fast (<100ms for unit tests)

**Priorities (In Order)**

1. **Critical Path Coverage** - Can users complete core workflows?
2. **Business Logic** - Do decision points work correctly?
3. **Error Handling** - Does the system fail gracefully?
4. **Edge Cases** - Only test edge cases that reveal actual bugs

**Anti-Patterns to Avoid**

- Testing framework/library code (hashlib, string formatting, discord.py)
- Testing trivial dataclass field assignment
- Over-mocking (mock external APIs, not your own code)
- Circular mocking (mock everything, then assert on mocks)

### Test Categories

Tests are organized using pytest markers:

```bash
pytest -m smoke              # Critical path smoke tests (3-4s)
pytest -m fast               # Fast unit tests (<100ms, no I/O)
pytest -m slow               # Slower tests using ChromaDB (>1s)
pytest -m integration        # Multi-component integration tests
pytest -m contract           # Interface compliance tests
pytest -m llm_api            # Tests requiring LLM API keys (costs money)
pytest -m embedding          # Tests creating embeddings (costs money)
```

### Structure

```
tests/
├── smoke/           # Critical component smoke tests
├── unit/            # Fast unit tests for business logic
├── integration/     # Multi-component integration tests
└── contract/        # Interface compliance (e.g., LLM providers)
```

**Smoke Tests**: Run on every commit. Verify critical components load without errors (factories, imports, configuration).

**Unit Tests**: Test business logic in isolation (state management, calculations, decision trees).

**Integration Tests**: Test 2-3 real components together (RAG ingestor + retriever + ChromaDB).

**Contract Tests**: Verify interfaces that enable system flexibility (e.g., all LLM providers return valid structured JSON).

### Key Metrics

**Good Metrics:**
- ✅ Smoke test pass rate (100% = system boots correctly)
- ✅ Time to detect breakage (fast tests = fast feedback)
- ✅ Test run time (optimize for developer experience)

**Avoid:**
- ❌ Code coverage percentage (30% of critical paths > 90% of everything)
- ❌ Number of tests (100 meaningful > 1000 trivial)
- ❌ Mocking coverage (heavy mocking ≠ testing real behavior)

For comprehensive testing principles and examples, see [IMPROVING-TESTS.md](IMPROVING-TESTS.md).

---

## RAG Tests

### Purpose

RAG tests validate that the retrieval-augmented generation pipeline correctly retrieves relevant rule excerpts for user queries. These tests focus on retrieval accuracy, not LLM generation quality.

### Structure

```
tests/rag/
├── test_cases/      # YAML test cases with queries and expected chunks
├── test_runner.py   # RAG test execution engine
└── sweep_runner.py  # Parameter sweep for optimization
```

### Test Types

**Retrieval Accuracy Tests**
- Verify that relevant rule chunks are retrieved for queries
- Test keyword normalization (case-insensitive matching)
- Validate BM25 + vector hybrid retrieval fusion
- Check multi-hop retrieval for complex queries

**Expected Output**
- Pass/fail based on whether expected chunks are in top-K results
- Precision/recall metrics for retrieval quality
- Chunk relevance scores

### Running RAG Tests

```bash
# Run specific test case
python -m src.cli rag-test --test banner-carrier-dies

# Run all test cases
python -m src.cli rag-test --all

# Parameter sweep for optimization
python -m src.cli rag-test-sweep
```

### Key Differences from Quality Tests

| Aspect | RAG Tests | Quality Tests |
|--------|-----------|---------------|
| **Focus** | Retrieval accuracy | LLM generation quality |
| **Evaluation** | Chunk matching | Ragas metrics + custom judge |
| **LLM Calls** | None (RAG only) | Yes (full pipeline) |
| **Cost** | Embedding API only | Embedding + LLM APIs |
| **Purpose** | Optimize retrieval | Compare LLM models |

---

## Quality Tests

### Purpose

Quality tests evaluate the complete RAG + LLM pipeline using domain-specific test cases. They measure model performance across 5 dimensions to enable informed model selection.

### Evaluation Metrics

**Core Metrics (Weighted)**

1. **Answer Correctness** (30%) - Does the conclusion match ground truth?
2. **Quote Recall** (30%) - Are all critical rules cited?
3. **Explanation Faithfulness** (20%) - Is reasoning grounded in quotes?
4. **Quote Faithfulness** (15%) - Are quotes verbatim (no hallucinations)?
5. **Quote Precision** (5%) - Are citations concise (minimal irrelevant quotes)?

**Aggregate Score** = Weighted sum of the 5 metrics (0-100%)

### Ground Truth Prioritization

Test cases distinguish between critical and supporting contexts:

```yaml
ground_truth_contexts:
  - text: "Exception rule that makes answer correct"
    priority: critical      # Weight = 10

  - text: "Supporting baseline context"
    priority: supporting    # Weight = 3
```

Missing critical contexts hurts quote recall 3.3x more than missing supporting contexts.

### Custom Judge

Quality tests use a custom LLM judge optimized for Kill Team rules:

- **Domain-specific prompts** - Understands game mechanics and rule interactions
- **Verbatim quote validation** - Checks for exact substring matches
- **Per-item feedback** - Identifies which specific quotes/answers are problematic
- **Priority-weighted scoring** - Critical ground truths weighted 3.3x more

See [QUALITY-TESTING-IMPROVEMENTS.md](QUALITY-TESTING-IMPROVEMENTS.md) for implementation details.

### Running Quality Tests

```bash
# Test single model on single test case
python -m src.cli quality-test --test eliminator-concealed-counteract

# Compare all models on single test case
python -m src.cli quality-test --test eliminator-concealed-counteract --all-models

# Run all test cases on default model
python -m src.cli quality-test --all-tests

# Run complete benchmark (all tests, all models)
python -m src.cli quality-test --all-tests --all-models --runs 3
```

### Test Case Structure

```
tests/quality/
├── test_cases/          # YAML test definitions
│   ├── eliminator-concealed-counteract.yaml
│   ├── banner-carrier-dies.yaml
│   └── ...
├── findings/            # Historical test results
├── reporting/           # Report generation
├── test_runner.py       # Test execution engine
└── custom_judge.py      # Custom LLM judge
```

### Output

**Per-Test Reports**: Individual model performance on each test case
- Aggregate score (0-100%)
- Breakdown by metric
- Per-quote and per-answer feedback
- Quote coverage matrix (which ground truths were cited)

**Model Comparison Reports**: Cross-model performance
- Multi-dimensional profiles (overall, quote quality, reasoning, correctness)
- Speed and cost metrics
- Trade-off analysis (e.g., Model A has better quotes, Model B has better reasoning)

### Use Cases

1. **Model Selection** - Choose best LLM for production (Claude vs GPT vs Gemini vs Grok)
2. **Regression Detection** - Detect degradation after prompt/RAG changes
3. **Prompt Optimization** - A/B test prompt variations
4. **RAG Tuning** - Validate that RAG improvements help LLM generation

---

## Test Execution Strategy

### Development Workflow

```bash
# 1. Quick smoke test (every commit)
pytest -m smoke                          # 3-4 seconds

# 2. Fast unit tests (before push)
pytest -m fast                           # 10-20 seconds

# 3. Full unit + integration (pre-commit)
pytest -m "not llm_api and not embedding"  # 1-2 minutes

# 4. Contract tests (manual, costs money)
pytest -m contract                       # 2-3 minutes

# 5. RAG tests (after RAG changes)
python -m src.cli rag-test --all        # 30 seconds

# 6. Quality tests (after prompt/model changes)
python -m src.cli quality-test --all-tests  # 5-10 minutes
```

### CI/CD Strategy

**On Every Commit:**
- ✅ Smoke tests
- ✅ Fast unit tests
- ❌ Skip: Slow tests, LLM API tests, embedding tests

**On Pull Request:**
- ✅ All unit tests (including slow)
- ✅ Integration tests (real ChromaDB)
- ❌ Skip: LLM API tests, embedding tests (cost)

**Manual/Scheduled:**
- Contract tests (verify LLM provider compliance)
- RAG tests (optimize retrieval parameters)
- Quality tests (benchmark model performance)

---

## Test Maintenance Principles

### When to Write Tests

**Write tests for:**
- ✅ New features (happy path + 2-3 error cases)
- ✅ Bug fixes (reproduce bug, then fix)
- ✅ Complex business logic (state machines, calculations)
- ✅ Critical paths (query processing, response generation)

**Don't write tests for:**
- ❌ Boilerplate (getters, setters, field assignment)
- ❌ Framework code (testing discord.py, ChromaDB APIs)
- ❌ Presentation logic (string formatting, emoji placement)
- ❌ Library behavior (testing Python's hashlib, uuid)

### When to Delete Tests

Delete a test if:
- It tests framework/library behavior
- It tests trivial field assignment
- It's redundant with another test
- It's all mocks with no real behavior
- It provides no failure signal (passes even when code is wrong)

**"If deleting a test doesn't make you nervous, delete it."**

### Test Quality Checklist

Before merging a test, verify:
- [ ] Would this catch a real bug?
- [ ] Does it test behavior, not structure?
- [ ] Would it still pass if I refactored?
- [ ] Does it use real dependencies where practical?
- [ ] Is the test name descriptive?
- [ ] Does it run fast?

For detailed guidelines, see [IMPROVING-TESTS.md](IMPROVING-TESTS.md).

---

## Summary

**Good Tests:**
- Focus on behavior over implementation
- Test critical paths first
- Use real components when possible
- Have clear failure signals
- Run fast

**Test Layers:**
1. **Unit Tests** - Business logic, fast feedback (pytest)
2. **RAG Tests** - Retrieval accuracy optimization
3. **Quality Tests** - End-to-end LLM model comparison

**Remember**: The goal is not 100% code coverage. The goal is confidence that the system works correctly. A few well-written behavior tests are worth more than hundreds of trivial tests.

---

## Related Documentation

- [IMPROVING-TESTS.md](IMPROVING-TESTS.md) - Detailed testing guidelines and principles
- [QUALITY-TESTING-IMPROVEMENTS.md](QUALITY-TESTING-IMPROVEMENTS.md) - Quality testing framework design
- [tests/quality/CLAUDE.md](../tests/quality/CLAUDE.md) - Quality testing framework usage
- [tests/rag/CLAUDE.md](../tests/rag/CLAUDE.md) - RAG testing framework usage
