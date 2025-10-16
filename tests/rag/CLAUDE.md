# RAG Testing Framework

Automated testing for RAG chunk retrieval quality - verifies that correct chunks are retrieved for queries and helps find optimal RAG parameters.

## Quick Start

### Single Test Run
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

### Parameter Sweep (Find Optimal Parameters)
```bash
# Sweep single parameter
python -m src.cli rag-test-sweep --param rrf_k --values 40,60,80,100 --runs 10

# Grid search (test all combinations)
python -m src.cli rag-test-sweep --grid \
  --max-chunks 10,15,20 \
  --min-relevance 0.4,0.45,0.5 \
  --runs 5
```

**Results**:
- Single test: `tests/rag/results/{timestamp}/report.md`
- Parameter sweep: `tests/rag/results/{param}_sweep_{timestamp}/comparison_report.md`
- Grid search: `tests/rag/results/grid_search_{timestamp}/comparison_report.md`

## What It Tests

Verifies RAG retrieval quality using standard Information Retrieval metrics:
- **Mean Average Precision (MAP)**: Overall retrieval quality across all test queries
- **Recall@5**: % of required chunks found in top 5 results
- **Recall@All**: % of required chunks found, regardless of position (total coverage)
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
- Recall@5 and Recall@All recommended (matches typical RAG_MAX_CHUNKS)
- Range: 0-1 (higher is better)

**Recall@All**:
- What % of required chunks were found, regardless of rank position
- Measures total coverage: did we find the chunks at all?
- Useful for debugging when Recall@5 is low but chunks exist further down
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

```python
def __init__(self, k1: float = 1.5, b: float = 0.75):  # BM25 parameters
```

Parameters:
- `k1 = 1.5` (term frequency saturation, typical range: 1.2-2.0)
  - Higher values give more weight to term frequency
- `b = 0.75` (document length normalization, typical range: 0.5-1.0)
  - 0 = no normalization, 1 = full normalization

**Impact**:
- Lower k1: Less emphasis on term frequency
- Higher k1: More emphasis on term frequency
- Lower b: Favors longer documents
- Higher b: Normalizes for document length

**Note**: Can now be tuned via parameter sweeps (see below)

## Parameter Sweep & Optimization

The `rag-test-sweep` command automatically runs tests across multiple parameter values and generates comparison charts. This replaces manual parameter tuning.

### Available Parameters

1. **max_chunks** (5-25): Number of chunks to retrieve
2. **min_relevance** (0.3-0.7): Minimum similarity threshold
3. **rrf_k** (40-100): RRF fusion constant for hybrid search
4. **bm25_k1** (1.2-2.0): BM25 term frequency saturation
5. **bm25_b** (0.5-1.0): BM25 document length normalization

### Single Parameter Sweep

Test one parameter with multiple values:

```bash
# Sweep RAG_MAX_CHUNKS
python -m src.cli rag-test-sweep \
  --param max_chunks \
  --values 5,10,15,20,25 \
  --runs 10

# Sweep RRF constant
python -m src.cli rag-test-sweep \
  --param rrf_k \
  --values 40,50,60,70,80 \
  --runs 10

# Sweep BM25 k1 parameter
python -m src.cli rag-test-sweep \
  --param bm25_k1 \
  --values 1.2,1.5,1.8,2.0 \
  --runs 10
```

**Output**: Charts showing MAP, Recall@5, Precision@3, etc. vs parameter value

### Grid Search (Multiple Parameters)

Test all combinations of multiple parameters:

```bash
# 2D grid search
python -m src.cli rag-test-sweep \
  --grid \
  --max-chunks 10,15,20 \
  --min-relevance 0.4,0.45,0.5 \
  --runs 5
# Tests 3×3 = 9 configurations

# 3D grid search
python -m src.cli rag-test-sweep \
  --grid \
  --max-chunks 10,15,20 \
  --min-relevance 0.4,0.5 \
  --rrf-k 50,60,70 \
  --runs 3
# Tests 3×2×3 = 18 configurations

# BM25 parameter optimization
python -m src.cli rag-test-sweep \
  --grid \
  --bm25-k1 1.2,1.5,1.8 \
  --bm25-b 0.5,0.75,1.0 \
  --runs 10
# Tests 3×3 = 9 configurations
```

**Output**: Heatmaps (for 2D grids) showing parameter interactions

### Recommended Workflow

**Step 1: Quick Sweep** (find ballpark values)
```bash
# Test each parameter individually with fewer runs
python -m src.cli rag-test-sweep --param max_chunks --values 5,10,15,20 --runs 3
python -m src.cli rag-test-sweep --param rrf_k --values 40,60,80 --runs 3
python -m src.cli rag-test-sweep --param bm25_k1 --values 1.2,1.5,1.8 --runs 3
```

**Step 2: Fine-tune** (narrow range with more runs)
```bash
# If max_chunks=15 was best, test nearby values
python -m src.cli rag-test-sweep --param max_chunks --values 13,14,15,16,17 --runs 10
```

**Step 3: Grid Search** (find optimal combination)
```bash
# Test best values from Step 1-2 in combination
python -m src.cli rag-test-sweep \
  --grid \
  --max-chunks 14,15,16 \
  --min-relevance 0.4,0.45,0.5 \
  --rrf-k 50,60,70 \
  --runs 10
```

**Step 4: Verify**
```bash
# Run final test with optimal parameters
python -m src.cli rag-test --runs 30
```

### Interpreting Results

**Charts Generated**:
- `map_comparison.png`: MAP score across parameter values (maximize this)
- `recall5_comparison.png`: Recall@5 across values
- `precision3_comparison.png`: Precision@3 across values
- `time_comparison.png`: Performance impact
- `cost_comparison.png`: Cost impact
- `multi_metric_comparison.png`: All metrics together
- `*_heatmap.png`: Grid search heatmaps (2D only)

**CSV Export**: All metrics in `comparison_metrics.csv` for statistical analysis

**Best Configuration**: Automatically reported with highest MAP score

### Analysis Guidelines

- **Maximize MAP**: Best overall retrieval quality
- **Maximize Recall@5**: Ensures all required chunks are found
- **Balance Precision@3**: Reduces noise in top results
- **Monitor Time/Cost**: Some parameters increase computational cost

## Report Structure

Each test run generates:

### Main Report (`report.md`)
- **Overall Metrics**:
  - Mean MAP across all tests
  - Average Recall@5, Recall@All
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
- Recall@5 and Recall@All per test
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

Use parameter sweeps instead of manual testing:

```bash
# 1. Quick sweep all parameters
python -m src.cli rag-test-sweep --param max_chunks --values 5,10,15,20,25 --runs 5
python -m src.cli rag-test-sweep --param min_relevance --values 0.3,0.4,0.45,0.5 --runs 5
python -m src.cli rag-test-sweep --param rrf_k --values 40,60,80 --runs 5

# 2. Grid search with best values
python -m src.cli rag-test-sweep --grid --max-chunks 15,20 --rrf-k 60,80 --runs 10

# 3. Check comparison_report.md for optimal configuration
# Charts show which values maximize MAP

# 4. Update constants.py with optimal values
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

✅ **Fully Implemented**:
- Test runner with multi-run support
- Metric calculators (MAP, Recall@k, Precision@k, MRR)
- Report generation with comprehensive breakdowns
- CLI command integration (`python -m src.cli rag-test`)
- Performance tracking (timing and cost)
- Example test cases
- **Parameter sweep functionality** (`python -m src.cli rag-test-sweep`)
- **Matplotlib chart generation** (line charts, bar charts, heatmaps)
- **Grid search** for multi-parameter optimization
- **CSV export** for external analysis
- **BM25 parameter tuning** (k1, b)
- **RRF parameter tuning** (k)

**All RAG parameters now tunable without code modification!**

## Related Documentation

- [Root CLAUDE.md](../../CLAUDE.md) - Project overview
- [src/services/rag/CLAUDE.md](../../src/services/rag/CLAUDE.md) - RAG implementation details
- [src/lib/constants.py](../../src/lib/constants.py) - All tunable parameters
- [tests/quality/CLAUDE.md](../quality/CLAUDE.md) - Quality testing (end-to-end RAG+LLM)
