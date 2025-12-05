# Response Quality Testing

This framework provides automated quality testing for RAG + LLM responses using RAGAS metrics and custom judge evaluation.

## Overview

Quality tests evaluate responses using:
1. **Deterministic metrics** (local, no LLM calls):
   - Quote Precision: Fraction of cited quotes that match ground truth
   - Quote Recall: Fraction of ground truth contexts found in quotes
   - Quote Faithfulness: Accuracy of quote text vs RAG chunks (fuzzy matching ≥0.98)

2. **Judge metrics** (LLM-based, via Custom Judge or RAGAS):
   - Explanation Faithfulness: Does explanation accurately reflect RAG context?
   - Answer Correctness: Do answers match ground truth? (per-answer scoring)

## Test Case Format

Test cases are YAML files in `tests/quality/test_cases/`:

```yaml
test_id: eliminator-concealed-counteract
context_file: tests/quality/context_cache/eliminator.json  # Optional cached RAG

query: >
  Can the Eliminator Sniper shoot during counteract while having Conceal order?

ground_truth_answers:
  - key: "Final Answer"
    text: "Yes, the Eliminator can shoot during counteract while having Conceal order."
    priority: critical  # critical|important|supporting (affects scoring weight)

ground_truth_contexts:
  - key: "Astartes Faction Rule"
    text: "Each friendly ANGEL OF DEATH operative can counteract regardless of its order."
    priority: critical

  - key: "Silent Weapon Rule"
    text: "An operative can perform the Shoot action with this weapon while it has a Conceal order."
    priority: important
```

**Key fields**:
- `test_id`: Unique identifier
- `query`: Question to test
- `ground_truth_answers`: Expected answers with keys and priorities (critical=5, important=3, supporting=1)
- `ground_truth_contexts`: Expected rule citations with keys and priorities
- `context_file`: Optional cached RAG context for deterministic, fast, free testing

## Usage

### Basic Commands

```bash
# Run all tests with default model
python -m src.cli quality-test

# Run specific test
python -m src.cli quality-test --test eliminator-concealed-counteract

# Test specific model
python -m src.cli quality-test --model gemini-2.5-pro

# Test all available models
python -m src.cli quality-test --all-models

# Multiple runs (for variance analysis)
python -m src.cli quality-test --all-models --runs 3 --yes

# Skip evaluation (generate outputs only)
python -m src.cli quality-test --no-eval
```

### Judge Configuration

**In `src/lib/constants.py`**:
```python
QUALITY_TEST_JUDGING = "CUSTOM"  # "CUSTOM" | "RAGAS" | "OFF"
QUALITY_TEST_JUDGE_MODEL = "gpt-4.1-mini"  # Model for judge LLM calls
```

**Judge modes**:
- **CUSTOM** (recommended): Single LLM call, structured output, unified feedback
  - Cost: ~$0.001-0.003 per test
  - Metrics: Explanation faithfulness + per-answer correctness
  - Prompt: `prompts/custom-judge-prompt.md`

- **RAGAS**: Uses RAGAS library (2 LLM calls)
  - Cost: ~$0.003-0.006 per test
  - Metrics: Same as CUSTOM but via RAGAS API

- **OFF**: Deterministic metrics only (no judge)
  - Cost: $0 (local computation)
  - Metrics: Quote precision/recall/faithfulness only

---

## Replay Feature (NEW!)

**Replay tests from saved outputs** to evaluate judges faster and cheaper without re-running LLM generation.

### Why Replay?

✅ **Judge iteration**: Test custom judges without re-running expensive LLMs
✅ **Cost savings**: $0.001/test (judge only) vs $0.05/test (full pipeline)
✅ **A/B testing**: Compare judges on identical LLM outputs
✅ **Deterministic**: Same outputs → same evaluation (with same judge)
✅ **No context dependency**: Deterministic metrics cached in metadata

### How It Works

1. **Run tests normally** → generates `output_*.md` with embedded metadata
2. **Metadata includes**:
   - LLM costs, latency, tokens (original run)
   - Deterministic metrics (quote precision/recall/faithfulness)
   - Textual feedback (missing contexts, failed quotes)
3. **Replay from folder** → skips RAG + LLM, re-runs judge only
4. **New report** shows original costs + new judge costs

### Replay Usage

```bash
# 1. Generate initial test outputs (expensive)
python -m src.cli quality-test --model claude-4.5-sonnet --runs 3
# Cost: ~$0.15 (30 tests × $0.005)
# Results: tests/quality/results/2025-12-04_08-46-37/

# 2. Iterate on judge (cheap) - edit prompts/custom-judge-prompt.md
python -m src.cli quality-test --from-output tests/quality/results/2025-12-04_08-46-37
# Cost: ~$0.03 (judge only, no LLM generation)
# Results: tests/quality/results/2025-12-04_08-46-37_replay_2025-12-04_10-15-23/

# 3. Try different judge model (cheaper)
# Edit src/lib/constants.py: QUALITY_TEST_JUDGE_MODEL = "claude-4.5-haiku"
python -m src.cli quality-test --from-output tests/quality/results/2025-12-04_08-46-37
# Cost: ~$0.01 (cheaper judge)

# 4. Filter by model
python -m src.cli quality-test --from-output tests/quality/results/2025-12-04_08-46-37 --model claude-4.5-sonnet

# Total: $0.19 vs $0.45 (3× without replay)
# Savings: 58% cost reduction for judge experimentation
```

### Metadata Structure

Output files (`output_{test_id}_{model}_{run}.md`) include embedded metadata:

```markdown
<!-- METADATA:START -->
```json
{
  "test_metadata": {
    "test_id": "eliminator-concealed-counteract",
    "model": "claude-4.5-sonnet",
    "actual_model_id": "claude-sonnet-4-5-20250929",
    "run_num": 1,
    "timestamp": "2025-12-04T08:46:37Z"
  },
  "costs": {
    "llm_generation_usd": 0.00234,
    "multi_hop_usd": 0.00012,
    "embedding_usd": 0.00001,
    "total_non_judge_usd": 0.00247
  },
  "latency": {
    "llm_generation_seconds": 1.45
  },
  "tokens": {
    "prompt": 1234,
    "completion": 456,
    "total": 1690
  },
  "deterministic_metrics": {
    "quote_precision": 0.85,
    "quote_recall": 0.92,
    "quote_faithfulness": 0.88,
    "quote_recall_feedback": "**Missing contexts:**\n- ⭐ Distance...",
    "quote_faithfulness_details": {"a1b2c3d4": 0.95},
    "llm_quotes_structured": [...]
  }
}
```
<!-- METADATA:END -->
```

**What's saved**:
- All non-judge costs (LLM generation, multi-hop, embeddings)
- LLM latency and token counts
- Deterministic metrics (quote precision/recall/faithfulness) with textual feedback
- Quote similarity scores and structured quote data

**What's NOT saved** (re-computed during replay):
- Judge metrics (explanation faithfulness, answer correctness)
- Judge costs

---

## Metrics Explained

### Deterministic Metrics (Local, No LLM)

#### Quote Precision
**What it measures**: Fraction of cited quotes that match ground truth contexts

**Calculation**: Substring matching against expected contexts
**Score**: 0-1 (1.0 = all quotes are relevant)
**Textual feedback**: None (by design)

**Example**:
- LLM cites 4 quotes, 3 match ground truth contexts → 0.75

---

#### Quote Recall
**What it measures**: Fraction of ground truth contexts found in quotes

**Calculation**: Weighted by priority (critical=5, important=3, supporting=1)
**Score**: 0-1 (1.0 = all expected contexts cited)
**Textual feedback**: Lists missing contexts with keys, priorities, weights

**Example feedback**:
```
**Missing ground truth contexts:**
  - ⭐ **Distance** (critical, weight=5): Must be set up wholly within 2"...
  - ⚠️ **Teleport rule** (important, weight=3): Teleport Pad allows removal...
  - ℹ️ **Supporting detail** (supporting, weight=1): Additional context...
```

**Scoring**:
- Missing critical context (weight=5): -50% score
- Missing important context (weight=3): -30% score
- Missing supporting context (weight=1): -10% score

---

#### Quote Faithfulness
**What it measures**: Accuracy of quote text vs RAG chunks (no hallucinated quotes)

**Calculation**: Fuzzy string matching (cosine similarity ≥0.98 threshold)
**Score**: 0-1 (1.0 = all quotes perfectly match RAG)
**Detailed breakdown**: Per-quote similarity scores in `quote_faithfulness_details`

**Example**: LLM cites quote that's 95% similar to RAG chunk → flagged as issue

---

### Judge Metrics (LLM-based)

#### Explanation Faithfulness
**What it measures**: Does explanation accurately reflect RAG context?

**Requires**: LLM judge (Custom Judge or RAGAS)
**Score**: 0-1
**Cost**: Part of judge call (~$0.001-0.003)

#### Answer Correctness
**What it measures**: Do answers match ground truth?

**Requires**: LLM judge
**Per-answer scores**: Weighted by priority (critical/important/supporting)
**Aggregate score**: 0-1 (weighted average of per-answer scores)
**Cost**: Part of judge call

**Example feedback** (Custom Judge):
```markdown
### Answer Correctness Issues

**Answer Correctness Score**: 0.67

- **Final Answer**: 1.00 ✅
- **Weapon Name**: 0.50 ⚠️ (partial match)
- **Secondary Effect**: 0.00 ❌ (missing)
```

---

## Output Files

### Results Directory Structure

```
tests/quality/results/2025-12-04_08-46-37/
├── output_eliminator-concealed-counteract_claude-4.5-sonnet_1.md
├── output_eliminator-concealed-counteract_claude-4.5-sonnet_2.md
├── output_eliminator-concealed-counteract_gpt-4.1_1.md
├── prompt.md
├── report.md
├── chart.png
└── chart_metrics.png
```

### Replay Results Directory

```
tests/quality/results/2025-12-04_08-46-37_replay_2025-12-04_10-15-23/
├── output_*.md  (copied from original)
├── prompt.md  (copied from original)
├── report.md  (NEW - with replay annotations)
├── chart.png  (NEW)
└── chart_metrics.png  (NEW)
```

---

## Architecture

### Module Organization

- **[test_runner.py](test_runner.py)**: Main test execution and replay orchestration
- **[metadata_generator.py](metadata_generator.py)**: Metadata generation for replay support
- **[output_parser.py](output_parser.py)**: Parse saved outputs for replay
- **[ragas_evaluator.py](ragas_evaluator.py)**: RAGAS metrics evaluation
- **[custom_judge.py](custom_judge.py)**: Custom judge evaluation (single LLM call)
- **[fuzzy_quote_evaluator.py](fuzzy_quote_evaluator.py)**: Fuzzy string matching for quote validation
- **[test_case_models.py](test_case_models.py)**: Data models (TestCase, GroundTruthAnswer, GroundTruthContext)
- **[reporting/](reporting/)**: Report generation, charts, aggregation

### Test Flow

```
┌─────────────────────────────────────────────┐
│ 1. LOAD TEST CASES                          │
│    • Parse YAML files                       │
│    • Load cached RAG context (if available) │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ 2. RAG RETRIEVAL (per test)                 │
│    • Hybrid search (vector + BM25)          │
│    • Multi-hop evaluation (optional)        │
│    • Cache context to JSON (optional)       │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ 3. LLM GENERATION (per model, per run)      │
│    • Generate structured response           │
│    • Track tokens, costs, latency           │
│    • Parse JSON to StructuredLLMResponse    │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ 4. EVALUATION                                │
│    • Deterministic metrics (local)          │
│    • Judge metrics (LLM, if enabled)        │
│    • Calculate aggregate score              │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ 5. OUTPUT & REPORTING                        │
│    • Save output_*.md with metadata         │
│    • Generate reports and charts            │
│    • Print console summary                  │
└─────────────────────────────────────────────┘
```

### Replay Flow

```
┌─────────────────────────────────────────────┐
│ 1. PARSE OUTPUTS                             │
│    • Extract metadata from output_*.md      │
│    • Reconstruct LLM responses              │
│    • Load deterministic metrics             │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ 2. LOAD TEST CASES                           │
│    • Match test IDs from outputs            │
│    • Load ground truth for evaluation       │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ 3. RE-RUN JUDGE ONLY                         │
│    • Skip deterministic metrics (cached)    │
│    • Run Custom Judge or RAGAS              │
│    • Calculate new aggregate score          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ 4. GENERATE REPORTS                          │
│    • Use original LLM costs from metadata   │
│    • Add new judge costs                    │
│    • Annotate as replayed                   │
└─────────────────────────────────────────────┘
```

---

## Cost Tracking

The framework tracks costs for:
1. **LLM Generation** (main cost): Per-token pricing based on actual model ID
2. **Multi-hop Evaluation**: RAG hop evaluation LLM calls (if enabled)
3. **Embeddings**: Query embedding generation
4. **Judge Evaluation**: Custom judge or RAGAS LLM calls

**Example costs** (per test):
- LLM generation: $0.003-0.008 (varies by model)
- Multi-hop (1 hop): $0.0001-0.0003
- Embeddings: $0.000001
- Judge (Custom): $0.001-0.003
- **Total**: ~$0.005-0.012 per test

**Replay costs** (per test):
- LLM generation: $0 (reused from original)
- Multi-hop: $0 (reused)
- Embeddings: $0 (reused)
- Judge (Custom): $0.001-0.003
- **Total**: ~$0.001-0.003 per test (60-80% savings)

---

## Adding New Tests

1. Create YAML file in `tests/quality/test_cases/`:
   ```yaml
   test_id: my-new-test
   query: >
     Your test question here

   ground_truth_answers:
     - key: "Final Answer"
       text: "Expected answer"
       priority: critical

   ground_truth_contexts:
     - key: "Rule Name"
       text: "Expected rule text"
       priority: important
   ```

2. Run test to validate:
   ```bash
   python -m src.cli quality-test --test my-new-test
   ```

3. (Optional) Cache RAG context for deterministic testing:
   ```bash
   python -m src.cli query "Your test question" --rag-only --context-output tests/quality/context_cache/my-new-test.json
   ```

4. Add `context_file` to YAML:
   ```yaml
   context_file: tests/quality/context_cache/my-new-test.json
   ```

---

## Best Practices

### For Test Authoring
- Use specific, unambiguous queries
- Prioritize ground truths correctly (critical > important > supporting)
- Include key rule context, not just correct answers
- Cache RAG context for deterministic testing

### For Judge Iteration
1. Run initial tests with cached RAG context (fast, deterministic)
2. Save outputs with `--no-eval` first (skip initial judge costs)
3. Iterate on judge prompts using `--from-output` (cheap)
4. Test final judge on full test suite

### For Cost Optimization
- Use cached RAG context (`context_file` in YAML)
- Use replay mode for judge iteration
- Choose cheaper judge models for iteration (haiku, mini)
- Use `--no-eval` for output generation only

---

## Troubleshooting

### "No metadata block found"
**Cause**: Trying to replay old output files (before metadata feature)
**Solution**: Re-run tests to generate new outputs with metadata

### "Test case not found"
**Cause**: Test YAML was deleted after outputs were generated
**Solution**: Restore test case YAML or remove from replay folder

### High variance in scores
**Cause**: LLM non-determinism
**Solution**: Use `--runs 5` to average scores, or use cached RAG context

### Judge evaluation fails
**Cause**: Judge model unavailable or API key missing
**Solution**: Check judge model configuration and API keys

---

## Documentation

- **Architecture**: [src/services/CLAUDE.md](../../src/services/CLAUDE.md)
- **LLM Providers**: [src/services/llm/CLAUDE.md](../../src/services/llm/CLAUDE.md)
- **RAG Pipeline**: [src/services/rag/CLAUDE.md](../../src/services/rag/CLAUDE.md)
- **Constants**: [src/lib/constants.py](../../src/lib/constants.py) ⭐ (all tunable parameters)
