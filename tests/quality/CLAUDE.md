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

**Reasoning effort**: `--model` and `--judge-model` accept a `#effort` postfix
(e.g. `--model grok-4.3#high`, `--judge-model claude-4.8-opus#low`). The CLI
validates the level against the model and **exits with an error** if unsupported —
see [src/services/llm/CLAUDE.md](../../src/services/llm/CLAUDE.md#reasoning-effort-model-name-postfix).

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
├── quality_evaluator.py → Metric calculation + judge orchestration
├── custom_judge.py      → Unified LLM judge (single call)
├── fuzzy_quote_evaluator.py → Quote faithfulness via fuzzy matching
├── reporting/
│   ├── report_generator.py → Markdown report generation
│   └── chart_generator.py  → Matplotlib charts
└── CLAUDE.md            → This file
```

## Key Components

**[test_runner.py](test_runner.py)**: Loads test cases → Runs queries → Collects results → Generates reports

**[quality_evaluator.py](quality_evaluator.py)**: Evaluates responses using RAGAS-style metrics.
These are **our own implementation**, not the `ragas` library — nothing here calls out to it:
- Quote Precision/Recall — substring matching with priority weights ([src/lib/retrieval_metrics.py](../../src/lib/retrieval_metrics.py))
- Quote Faithfulness — fuzzy matching against the retrieved chunks ([fuzzy_quote_evaluator.py](fuzzy_quote_evaluator.py))
- Explanation Faithfulness + Answer Correctness + feedback — one [custom_judge.py](custom_judge.py) LLM call

The judge always runs; use `--no-eval` to generate outputs without scoring.

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

**Individual results:** Per-run details with quality metrics and judge feedback

### Per-Run Output Files (`output_{test_id}_{model}_{run}.md`)

Each run generates a detailed output file containing:

**Query and Response:**
- Original query text
- Full LLM response with quotes and explanation

**Quality Metrics breakdown:**
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
QUALITY_TEST_JUDGE_MODEL = "grok-4.3"             # LLM judge
QUALITY_METRIC_WEIGHTS = {...}                    # Aggregate score weights

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

## Caching

Quality tests use the caching functionality of LLM APIs which can save up to 50% of costs. Savings metric is visible in the report.

## Batch API workflow (opt-in, ~50% cheaper)

For large matrices (`--all-models --runs 10`) you can run generation through the
provider **Batch APIs** at 50% token cost (≤24h turnaround). Split into two
commands; `batch-collect` is single-pass and re-run by hand until the report is
produced. State lives in `batch_state.json` in the results dir (idempotent, resumable).

```bash
# 1. Submit — submits batches first, then runs any non-batch models live (overlapping
#    provider batch queue time), prints batch IDs, exits
python -m src.cli quality-test --batch-submit --test eliminator-concealed-counteract \
  --model claude-4.6-sonnet --judge-model gpt-4.1-mini

# 2. Collect — one status check + one step; re-run until "Phase: done"
python -m src.cli quality-test --batch-collect tests/quality/results/<timestamp>
```

**Coverage:** Anthropic (`claude-*`), OpenAI (`gpt-*`, `o3*`), **Kimi**
(`moonshot`), **Mistral**, **Gemini**, and **Grok** (`x`) generate via batch.
**DeepSeek** (no native batch API) and **every Qwen model in the registry** (see
below) fall back to **live async at submit time** and land in the same report.
Kimi reuses the OpenAI-compatible `/v1/batches` backend; Mistral and Grok use
httpx REST (no new SDK deps); Gemini uses `google-genai` inline batches with a
persisted sentence map so verbatim quote extraction survives into `batch-collect`.

**Qwen is live-only in practice:** DashScope's `/v1/batches` accepts only the
stable aliases `qwen-flash` / `qwen-plus` / `qwen-max` / `qwen-turbo`. Every
versioned snapshot (`qwen3.6-flash-2026-04-16`) and every `qwen3.x` name is
rejected with `model_not_found` — and DashScope fails the **whole batch**, not the
offending line, so a single bad model wipes out every request in it.
`QwenAdapter.BATCH_SUPPORTED_MODELS` allowlists the four aliases; since none of the
registry's Qwen entries are among them, they all route live. The `alibaba` backend
stays wired for whenever a batchable alias is registered.

**One model per OpenAI-compat batch:** OpenAI's `/v1/batches` (and the compat hosts
Kimi/Qwen) reject a batch mixing models (`mismatched_model`), so those backends
submit **one batch per model** — the manifest groups them by a `name::model` key
(`batch_group_key`, `tests/quality/batch/backends.py`), not the bare backend name.
Mixed-model batches are fine on Anthropic/Gemini/Grok/Mistral (one batch per backend).
OpenAI also rejects its own `*-chat-latest` aliases from the Batch API
(`model_not_found`); `ChatGPTAdapter.batch_supports_model` excludes them so they route
to the **live path** instead. A batch-capable provider can exclude specific models via
`LLMProvider.batch_supports_model`; `resolve_backend` returns `None` for excluded ones.

**Judge round:** batches whenever the judge model is batchable — including the
default `grok-4-1-fast-reasoning` — so reaching `done` normally takes **two
collects** (gen batch, then judge batch). A non-batchable judge (e.g. DeepSeek)
runs live inside the first collect and a single collect finishes the run.

**Discounts:** per-backend in `src/lib/pricing.py` (`BATCH_DISCOUNT`). Anthropic,
OpenAI, Mistral, Qwen/DashScope, Gemini default to 50%. Grok (`x`) confirmed at
20%. **Kimi (`moonshot`) publishes "reduced pricing" without a confirmed
percentage** — its `batch_savings_usd` is an estimate until the rate is
confirmed against the provider pricing page and corrected in `BATCH_DISCOUNT`.

**Reporting:** `report.md` gains a **Batch net savings** line next to the existing
cache-savings line, plus a combined total. Per-result savings are stored in each
`output_*.md` metadata (`batch`, `batch_savings_usd`) and re-derived on collect.

**Error tolerance:** individual batch items (generation **and** judge) that fail are
classified transient vs permanent (`tests/quality/batch/errors.py`) and the transient
ones are **re-requested**, bounded by `QUALITY_TEST_MAX_BATCH_ITEM_RETRIES` (default 2,
in `src/lib/constants.py`). Each re-request is a fresh small batch picked up on the next
`batch-collect`, so the backoff is the gap between collect passes (no in-process sleep).

- **Transient (retried):** rate limit / 429, overloaded / 529 / 503, other 5xx, timeouts,
  item `expired`, and insufficient-credits / quota / billing (credits are retried because
  you can top up between collects). An unrecognized error also defaults to transient.
- **Permanent (not retried):** auth / 401, permission / 403, invalid_request / 400,
  content filter / blocked / recitation / refusal, not_found / 404, canceled.

Per-item state (`status`, `attempts`, `error`, `error_class`) lives on each
`batch_state.json` request row; a whole-backend `failed` status is resubmitted once then
salvaged (succeeded items kept) instead of aborting the run. A permanently-failed item
becomes a score-0 `💀` result rather than silently vanishing.

A whole-batch rejection reports its reason on the batch object's `errors` field, never
in an error file. `OpenAICompatBatchBackend.poll` reads it into `last_error`, logs it,
and the collect loop classifies it: a **permanent** rejection (e.g. `model_not_found`)
skips the pointless resubmit and goes straight to salvage, and the reason is stored on
each failed row so `report.md` shows *why* instead of a bare "backend batch failed".

`report.md` gains an **Error & Recovery Log** table (test / model / run / class / attempts /
recovered? / message) plus an **Errors** summary line in the header. In the score chart the
stacked bar is now **green** (earned) + **gold** (score recovered by re-request) + **grey**
(score lost to unrecoverable errors); green+gold equals the old earned total, grey unchanged.

> **Live fidelity note:** the Mistral/Grok result-line shapes and the Gemini
> inline-result surface are marked `# ponytail:` in the code — they are exercised
> offline (transport/poll/scaffold) but confirmed against a live run only by the
> paid smoke test.

**When to use:** cost-sensitive CI where a multi-hour (worst case ~48h, two rounds)
turnaround is fine. Not for interactive iteration — use the live path (default) there.

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

**RAGAS-style metrics (per-test, our own implementation)**:
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
