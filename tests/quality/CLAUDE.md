# Quality Testing Framework

Automated RAG + LLM response quality evaluation across models.

## Quick Start

```bash
# Test default model
python -m src.cli quality-test

# Compare all models
python -m src.cli quality-test --all-models

# Specific test, 10 runs
python -m src.cli quality-test --test banner-carrier-dies --runs 10

# Custom judge model
python -m src.cli quality-test --judge-model gpt-4o
```

**Results**: `tests/quality/results/{timestamp}/report.md`

## What It Does

Runs test queries → Evaluates responses (LLM judge) → Generates reports with charts → Tracks performance over time

## Test Case Format

YAML files in `test_cases/`:

```yaml
test_id: non-reciprocal-blast
context_file: tests/quality/test_cases/non-reciprocal-blast-context.json  # Optional
query: >
  My operative has a blast 2" weapon. Is it possible for it to be closer than 2"
  to its target, but not to be hit by the blast?

ground_truth_answers:
  - key: "Final Answer"
    text: "Yes, the operative with the blast weapon can avoid being hit by the blast."
    priority: critical
  - key: "Visibility"
    text: "Not being visible to the target allows you to avoid being hit by the blast."
    priority: critical
  - key: "Shooter identity"
    text: "Your operative is the shooter"
    priority: supporting

ground_truth_contexts:
  - key: "Blast X"
    text: "Secondary targets are other operatives visible to and within x of the primary target"
    priority: critical
```

**Required fields:**
- `test_id`: Unique identifier for the test case
- `query`: The user question to test
- `ground_truth_answers`: Expected answer components (what the response should convey)
- `ground_truth_contexts`: Rule excerpts that should be retrieved/cited

**Optional fields:**
- `context_file`: Path to cached RAG context JSON (for deterministic testing)

**GroundTruthAnswer fields:**
- `key`: Unique identifier for this answer component
- `text`: Expected answer text the response should convey
- `priority`: Weight for scoring (`critical`=10, `important`=5, `supporting`=3)

**GroundTruthContext fields:**
- `key`: Unique identifier for this context
- `text`: Exact rule text that should be quoted/cited
- `priority`: Weight for scoring (`critical`=10, `important`=5, `supporting`=3)

> **Note**: The old `requirements` format with `type: contains` and `type: llm` is deprecated. Use `ground_truth_answers` and `ground_truth_contexts` instead

## RAG Context Caching

**Use cached RAG context** for faster, cheaper, and deterministic tests:

### Generate Context Cache

```bash
# Run query with --rag-only to retrieve context, then save to file
python3 -m src.cli query "Can the Eliminator shoot twice?" \
  --rag-only \
  --context-output tests/quality/context_cache/eliminator-shoot-twice.json
```

### Use Cached Context in Test

Add `context_file` field to test case YAML:

```yaml
test_id: eliminator-shoot-twice
context_file: tests/quality/context_cache/eliminator-shoot-twice.json  # Optional
query: >
  Can the Eliminator Sniper operative shoot twice in the same turning point?

ground_truth_answers:
  - key: "Final answer"
    text: "Yes, if using Suspensor System equipment"
    priority: critical
```

### Run Tests with Cached Context

```bash
# Use cached context (default behavior when context_file is set)
python -m src.cli quality-test --test eliminator-shoot-twice

# Force RAG retrieval (ignore cached context)
python -m src.cli quality-test --test eliminator-shoot-twice --force-rag
```

### Benefits

✅ **Deterministic**: Same RAG chunks every run (eliminates RAG variance)
✅ **Faster**: Skip RAG retrieval (~1-2s saved per test)
✅ **Cheaper**: $0 RAG/embedding costs when using cache
✅ **Flexible**: Can force fresh RAG retrieval with `--force-rag`

**Best for**: Iterative prompt tuning, LLM model comparison, regression testing

## Structure

```
tests/quality/
├── test_cases/          → YAML test definitions
├── results/             → Generated reports (timestamped)
│   └── archived_results/ → Historical data
├── findings/            → Manual analysis notes
├── test_runner.py       → Main orchestrator
├── evaluator.py         → LLM judge evaluator
├── reporting/
│   ├── report_generator.py → Markdown report generation
│   └── chart_generator.py  → Matplotlib charts
└── CLAUDE.md            → This file
```

## Key Components

**[test_runner.py](test_runner.py)**: Loads test cases → Runs queries → Collects results → Generates reports

**[evaluator.py](evaluator.py)**: Evaluates responses using RAGAS-style metrics:
- Quote Precision/Recall/Faithfulness (deterministic)
- Explanation Faithfulness (LLM judge)
- Answer Correctness (LLM judge comparing to ground truth answers)
- Custom feedback (Explanation Problems, Style)

**[reporting/](reporting/)**: Aggregates results → Generates markdown + charts → Archives data

## Generated Reports

Reports are organized by test dimensionality in `results/{timestamp}/`:

### Main Report (`report.md`)

**Header section:**
- Total time, cost breakdown (Main LLM, Multi-hop, Judge, Embeddings with percentages)
- Total queries count, best score with model name
- Test cases list, judge model used

**Summary table:** Per-test-case statistics
| Test Case | Avg Score % | Avg Time (s) | Avg Cost ($) |
|-----------|-------------|--------------|--------------|
| test-name | 96.0% (±0.8) | 10.07 | $0.0357 |

**Individual results:** Per-run details with RAGAS metrics and judge feedback

### Per-Run Output Files (`output_{test_id}_{model}_{run}.md`)

Each run generates a detailed output file containing:

**Query and Response:**
- Original query text
- Full LLM response with quotes and explanation

**RAGAS Metrics breakdown:**
- **Quote Precision** (0.0-1.0): Fraction of cited quotes that are relevant
- **Quote Recall** (0.0-1.0): Fraction of ground truth contexts that were cited
  - Lists missing ground truth contexts with priority icons (⭐ critical, ⚠️ important)
- **Quote Faithfulness** (0.0-1.0): How accurately quotes are reproduced
- **Explanation Faithfulness** (0.0-1.0): How well explanation is grounded in quotes
- **Answer Correctness** (0.0-1.0): How well response matches ground truth answers
  - Per-component breakdown (e.g., "Final Answer": 1.00, "Visibility": 0.90)

**Custom Judge Feedback:**
- `Explanation Problems`: Issues with the explanation (critical errors, unsupported claims)
- `Style`: Comments on structure, clarity, and presentation

**Metadata (JSON block):**
- Test metadata (test_id, model, actual_model_id, run_num, timestamp)
- Costs (llm_generation_usd, multi_hop_usd, embedding_usd)
- Latency (llm_generation_seconds)
- Tokens (prompt, completion, total)
- Deterministic metrics (quote_precision, quote_recall, quote_faithfulness)

### Other Files

- `prompt.md`: The system prompt used for generation

## Configuration

In [src/lib/constants.py](../../src/lib/constants.py):
```python
QUALITY_TEST_JUDGE_MODEL = "gpt-4.1-mini"        # LLM judge
QUALITY_TEST_JUDGE_MAX_TOKENS = 150
QUALITY_TEST_JUDGE_TEMPERATURE = 0.0              # Deterministic

# Concurrency and rate limit handling
QUALITY_TEST_MAX_CONCURRENT_LLM_REQUESTS = 5      # Max parallel LLM requests
QUALITY_TEST_MAX_RETRIES_ON_RATE_LIMIT = 3        # Retries when rate limited
QUALITY_TEST_RATE_LIMIT_INITIAL_DELAY = 2.0       # Initial retry delay (doubles each retry)
```

**Rate Limit Protection**:
- Tests run in parallel with concurrency control via semaphore
- Maximum concurrent LLM requests limited to prevent rate limit errors
- Automatic exponential backoff retry on rate limit errors
- With 5 test cases × 5 runs × 1 model = 25 tests, only 5 run concurrently

## Adding Test Cases

1. Create YAML in `test_cases/my-test.yaml`
2. Define `test_id`, `query`, `ground_truth_answers`, and `ground_truth_contexts`
3. Optionally generate cached RAG context (see RAG Context Caching section)
4. Run: `python -m src.cli quality-test --test my-test`
5. Review results in `results/{timestamp}/`
6. Archive baseline: copy results to `archived_results/`

## Multi-Run Testing

```bash
python -m src.cli quality-test --runs 10 --all-models
```

**Purpose**: Detect consistency issues (LLMs can be non-deterministic)

**Report includes**:
- Mean ± std dev for all metrics
- Variance analysis
- Flaky test identification

## Usage Tips for Agents

### Evaluating Model Changes
```bash
# Baseline
python -m src.cli quality-test --all-models --runs 5

# Make changes to prompts/RAG/etc.

# Compare
python -m src.cli quality-test --all-models --runs 5

# Compare reports in results/
```

### Tuning RAG Impact
```bash
# Edit RAG_MAX_CHUNKS in constants.py
python -m src.cli quality-test --all-models

# Check if more/fewer chunks improves scores
```

### Adding New Provider
```bash
# After implementing provider
python -m src.cli quality-test --model my-new-provider

# Compare against existing models
python -m src.cli quality-test --all-models
```

## Best Practices

✅ **Do**:
- Run quality tests after changing prompts/RAG/LLM
- Archive results before major changes
- Use consistent judge model (gemini-2.5-flash)
- Test multiple runs (5-10) for stability

❌ **Don't**:
- Change judge model mid-experiment (invalidates comparisons)
- Delete archived results (needed for historical tracking)
- Use high temperature for judge (use 0.0 for determinism)

## Quality Metrics

**RAGAS-style metrics (per-test)**:
- **Quote Precision**: Fraction of cited quotes that match ground truth contexts
- **Quote Recall**: Fraction of ground truth contexts that were cited
- **Quote Faithfulness**: How accurately quotes are reproduced from source
- **Explanation Faithfulness**: How well explanation claims are grounded in cited quotes
- **Answer Correctness**: How well response conveys ground truth answers (weighted by priority)

**Per-test aggregates**:
- Score: Weighted combination of all metrics (0-100%)
- Pass/Fail: Based on score threshold
- Generation time: LLM response latency
- Cost: Estimated API cost (USD)

**Report aggregates**:
- Avg Score %: Average (score) with standard deviation (±)
- Model ranking: By avg score
- Consistency: Variance across runs (shown as ±std dev)

## Related Documentation

- [Root CLAUDE.md](../../CLAUDE.md) - Project overview
- [src/services/llm/CLAUDE.md](../../src/services/llm/CLAUDE.md) - LLM providers
- [src/services/rag/CLAUDE.md](../../src/services/rag/CLAUDE.md) - RAG retrieval
- [src/lib/constants.py](../../src/lib/constants.py) - Configuration
