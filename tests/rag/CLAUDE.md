# RAG Testing Framework

Automated testing for RAG chunk retrieval quality - verifies that correct chunks are retrieved for queries and helps find optimal RAG parameters.

## Quick Start

```bash
# Test all RAG test cases
python -m src.cli rag-test

# Test specific case
python -m src.cli rag-test --test banner-carrier-placement

# Test with 10 runs (consistency testing)
python -m src.cli rag-test --runs 10

# Custom retrieval parameters
python -m src.cli rag-test --max-chunks 10
```

**Results**: `tests/rag/results/{timestamp}/report.md`

## What It Tests

Verifies RAG retrieval quality using standard Information Retrieval metrics:
- **Mean Average Precision (MAP)**: Overall retrieval quality across all test queries
- **Recall@5**: % of required chunks found in top 5 results
- **Recall@10**: % of required chunks found in top 10 results
- **Precision@3**: % of top 3 retrieved chunks that are relevant
- **Precision@5**: % of top 5 retrieved chunks that are relevant
- **MRR (Mean Reciprocal Rank)**: Average 1/rank of first required chunk
- **Consistency**: Variance across multiple runs

**Performance Tracking**:
- **Total Time**: Total time for all tests
- **Avg Retrieval Time**: Average time per retrieval operation
- **Total Cost**: Total embedding generation cost (OpenAI API)

## Test Case Format

**Ultra-simple YAML** - just list the chunk headers that should be retrieved:

```yaml
test_id: banner-carrier-placement
query: >
  If my plant banner is picked up by my opponent and the carrier dies,
  who places the banner, me or my opponent?

required_chunks:
  - "Place Marker"
  - "Marker Rules"
```

```yaml
test_id: overwatch-against-charge
query: "Can I use overwatch against a charge?"

required_chunks:
  - "Overwatch"
  - "Charge"
  - "Fight Phase"
```

**That's it!** The test framework matches retrieved chunks by their header field.

## Evaluation Metrics Explained

**Mean Average Precision (MAP)**:
- Gold standard IR metric
- Measures how well the system ranks relevant chunks
- Average of precision@k across all relevant chunks
- Range: 0-1 (higher is better)

**Recall@k**:
- What % of required chunks appear in top-k results
- Recall@5 and Recall@10 recommended (matches typical RAG_MAX_CHUNKS)
- Range: 0-1 (higher is better)

**Precision@k**:
- What % of top-k results are relevant
- Precision@3 and Precision@5 recommended (most important chunks first)
- Range: 0-1 (higher is better)

**MRR (Mean Reciprocal Rank)**:
- How quickly does the first relevant chunk appear
- 1/rank of first relevant chunk, averaged across queries
- Range: 0-1 (higher is better)

## Tunable RAG Parameters

Parameters that can be adjusted to optimize retrieval quality:

### 1. Retrieval Parameters

**File**: [src/lib/constants.py](../../src/lib/constants.py)

```python
RAG_MAX_CHUNKS = 15        # How many chunks to retrieve (default: 15)
RAG_MIN_RELEVANCE = 0.45   # Minimum relevance threshold 0-1 (default: 0.45)
```

**Impact**:
- Higher `RAG_MAX_CHUNKS`: Better recall, but more noise
- Lower `RAG_MIN_RELEVANCE`: Better recall, but more irrelevant chunks

### 2. Embedding Parameters

**File**: [src/lib/constants.py](../../src/lib/constants.py)

```python
EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI embedding model
```

**Options**:
- `text-embedding-3-small` (1536 dim, fast, cheaper)
- `text-embedding-3-large` (3072 dim, slower, better quality)

**Impact**: Better embeddings improve semantic matching
**Note**: Requires re-ingestion after changes

### 3. Hybrid Search Parameters

**File**: [src/services/rag/hybrid_retriever.py](../../src/services/rag/hybrid_retriever.py) (line 22)

```python
def __init__(self, k: int = 60):  # RRF constant (default: 60)
```

**Impact**:
- Lower k (e.g., 40): More weight to top-ranked results
- Higher k (e.g., 80): More balanced fusion between vector and BM25

**Enable/Disable Hybrid**:
In retrieval request: `use_hybrid=True` (default)

### 4. BM25 Parameters (Advanced)

**File**: [src/services/rag/bm25_retriever.py](../../src/services/rag/bm25_retriever.py)

Currently uses default BM25Okapi parameters:
- `k1 = 1.5` (term frequency saturation)
- `b = 0.75` (document length normalization)

**Note**: Requires code modification to adjust

## Parameter Tuning Workflow

Systematic approach to finding optimal RAG configuration:

### Step 1: Establish Baseline

```bash
# Run tests with current settings
python -m src.cli rag-test --runs 10

# Record MAP, Recall@5, Precision@3
# Save report to baseline/
```

### Step 2: Test RAG_MAX_CHUNKS

```bash
# Edit src/lib/constants.py - try these values:
# RAG_MAX_CHUNKS = 5, 10, 15, 20, 25

# For each value:
python -m src.cli rag-test --runs 10

# Compare MAP and Recall@5
# Find sweet spot (higher recall without hurting precision)
```

### Step 3: Test RAG_MIN_RELEVANCE

```bash
# Edit src/lib/constants.py - try these values:
# RAG_MIN_RELEVANCE = 0.3, 0.4, 0.45, 0.5, 0.6

# For each value:
python -m src.cli rag-test --runs 10

# Compare Recall@5 vs Precision@3
# Find threshold that balances recall and precision
```

### Step 4: Test RRF Constant

```bash
# Edit src/services/rag/hybrid_retriever.py line 22:
# k = 40, 60, 80, 100

# For each value:
python -m src.cli rag-test --runs 10

# Compare MAP (overall quality)
```

### Step 5: Test Embedding Model (Advanced)

```bash
# Edit src/lib/constants.py:
# EMBEDDING_MODEL = "text-embedding-3-large"

# Re-ingest documents (expensive!):
python -m src.cli ingest extracted-rules/ --force

# Run tests:
python -m src.cli rag-test --runs 10

# Compare MAP - worth the cost increase?
```

### Step 6: Grid Search (Optional)

Test combinations of parameters systematically:
```bash
# Example grid:
# RAG_MAX_CHUNKS: [10, 15, 20]
# RAG_MIN_RELEVANCE: [0.4, 0.45, 0.5]
# = 9 combinations

# For each combination:
python -m src.cli rag-test --runs 5
```

### Step 7: Analyze Results

Compare all test runs:
- **Maximize MAP**: Best overall quality
- **Maximize Recall@5**: Ensure required chunks appear
- **Balance Precision@3**: Avoid too much noise

## Report Structure

Each test run generates:

### Main Report (`report.md`)
- **Overall Metrics**:
  - Mean MAP across all tests
  - Average Recall@5, Recall@10
  - Average Precision@3, Precision@5
  - Average MRR

- **Performance Metrics**:
  - Total time for all tests (seconds)
  - Average retrieval time per test (seconds)
  - Total embedding cost (USD)

- **Per-Test Breakdown**:
  - Test ID and query
  - Required chunks (headers)
  - Retrieved chunks (top-k with ranks)
  - Which required chunks were found/missed
  - Metrics for this test (MAP, Recall@5, etc.)
  - Retrieval time and embedding cost for this test

- **Configuration Used**:
  - RAG_MAX_CHUNKS
  - RAG_MIN_RELEVANCE
  - EMBEDDING_MODEL
  - RRF k value
  - Hybrid enabled/disabled

- **Multi-Run Statistics** (if --runs > 1):
  - Mean ± std dev for all metrics
  - Consistency analysis
  - Variance identification

### Charts
- MAP comparison across tests
- Recall@5 and Recall@10 per test
- Precision@3 and Precision@5 per test
- MRR distribution
- Multi-run consistency plots

### Raw Data
- `retrieved_chunks_{test_id}_{run}.txt`: Full chunk text for manual review
- `summary.json`: All metrics in structured format

## Structure

```
tests/rag/
├── test_cases/          → YAML test definitions
├── results/             → Generated reports (timestamped)
├── test_runner.py       → Main orchestrator (TBD)
├── evaluator.py         → Metric calculation (TBD)
├── reporting/           → Report generation (TBD)
└── CLAUDE.md            → This file
```

## Usage for Agents

### Finding Optimal Parameters

```bash
# 1. Create baseline
python -m src.cli rag-test --runs 10 > baseline.txt

# 2. Experiment with one parameter
# Edit constants.py: RAG_MAX_CHUNKS = 20
python -m src.cli rag-test --runs 10 > experiment_chunks_20.txt

# 3. Compare MAP scores
# If improved: keep new value, else revert

# 4. Repeat for other parameters
```

### Evaluating Changes

After modifying RAG pipeline:
```bash
# Before changes
python -m src.cli rag-test --runs 10

# Make changes (new chunking strategy, etc.)
python -m src.cli ingest extracted-rules/ --force
python -m src.cli rag-test --runs 10

# Compare reports: did metrics improve?
```

### Testing Consistency

```bash
# Run many times to check variance
python -m src.cli rag-test --runs 50

# Low variance = consistent retrieval
# High variance = investigate (embedding model? query sensitivity?)
```

## Best Practices

✅ **Do**:
- Run RAG tests after changing retrieval parameters
- Test with multiple runs (10+) for statistical significance
- Archive baseline results before experiments
- Change one parameter at a time
- Re-ingest after changing chunking/embeddings

❌ **Don't**:
- Test with only 1 run (misses variance)
- Change multiple parameters simultaneously (can't isolate impact)
- Skip re-ingestion after chunking changes
- Optimize for a single test case (may overfit)
- Ignore Recall@5 (missing chunks = incomplete answers)

## Implementation Status

✅ **Implemented**:
- Test runner with multi-run support
- Metric calculators (MAP, Recall@k, Precision@k, MRR)
- Report generation with comprehensive breakdowns
- CLI command integration (`python -m src.cli rag-test`)
- Performance tracking (timing and cost)
- Example test cases

**Note**: Charts are not yet implemented in reports

## Related Documentation

- [Root CLAUDE.md](../../CLAUDE.md) - Project overview
- [src/services/rag/CLAUDE.md](../../src/services/rag/CLAUDE.md) - RAG implementation details
- [src/lib/constants.py](../../src/lib/constants.py) - All tunable parameters
- [tests/quality/CLAUDE.md](../quality/CLAUDE.md) - Quality testing (end-to-end RAG+LLM)
