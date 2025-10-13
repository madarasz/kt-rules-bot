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
test_id: banner-carrier-dies
query: >
  If my plant banner is picked up by my opponent and the carrier dies,
  who places the banner, me or my opponent?

requirements:
  - check: Quote Place marker rule
    type: contains                    # Exact text match
    description: >
      If an operative carrying a marker is incapacitated,
      it must perform this action...
    points: 5

  - check: Correct final answer
    type: llm                         # LLM judge evaluation
    description: The final answer is that your opponent places it.
    points: 10
```

**Requirement types**:
- `contains`: Exact text match (normalized, case-insensitive)
- `llm`: LLM judge evaluates if description is accurate

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

**[evaluator.py](evaluator.py)**: Evaluates requirements using:
- `contains`: Normalized text matching
- `llm`: LLM judge (default: `gpt-4o`)

**[reporting/](reporting/)**: Aggregates results → Generates markdown + charts → Archives data

## Generated Reports

**Main report** (`report.md`):
- Overall summary (pass rates, avg scores)
- Per-test breakdown
- Per-model comparison
- Requirement-level details

**Charts**:
- Score distribution heatmaps
- Model comparison bar charts
- Multi-run consistency plots

**Raw data** (`summary.json`): Full results for custom analysis

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
2. Define query and requirements (contains + llm types)
3. Run: `python -m src.cli quality-test --test my-test`
4. Review results in `results/{timestamp}/`
5. Archive baseline: copy results to `archived_results/`

**Tips**:
- Use `contains` for exact rule quotes
- Use `llm` for semantic correctness
- Weight points by importance (10 for core answer, 3-5 for details)
- Test across all models to identify provider differences

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

**Per-test**:
- Score: Sum of requirement points earned
- Pass: All requirements met (score == max_score)
- Generation time: LLM response latency
- Cost: Estimated API cost (USD)

**Aggregated**:
- Pass rate: % of tests passed
- Avg score %: Average (score/max_score)
- Model ranking: By avg score
- Consistency: Variance across runs

## Troubleshooting

**Low scores**: Check retrieved chunks (may need RAG tuning), review LLM responses in `output_*.md`

**Inconsistent scores**: Increase judge temperature to 0.0, verify test cases are well-defined

**Judge errors**: Judge model may refuse violent content → retry logic handles this

**Slow tests**: Reduce `--runs`, test subset with `--test`, use faster models

## Related Documentation

- [Root CLAUDE.md](../../CLAUDE.md) - Project overview
- [src/services/llm/CLAUDE.md](../../src/services/llm/CLAUDE.md) - LLM providers
- [src/services/rag/CLAUDE.md](../../src/services/rag/CLAUDE.md) - RAG retrieval
- [src/lib/constants.py](../../src/lib/constants.py) - Configuration
