# Refactor RAG-Test and Quality-Test to Use Ragas Framework

## Overview
Integrate the ragas framework to replace custom evaluation metrics with industry-standard RAG evaluation methods, maintaining backward compatibility while adding more sophisticated metrics.

## Current State Analysis

**RAG-Test** ([tests/rag/](./)):
- Tests retrieval quality only (no LLM)
- Custom IR metrics: MAP, Recall@k, Precision@k, MRR
- YAML format: `test_id`, `query`, `required_chunks` (headers)
- Uses substring matching to find required chunks
- Parameter sweeps for optimization

**Quality-Test** ([tests/quality/](../quality/)):
- Tests full pipeline (RAG + LLM)
- Custom evaluation: "contains" (text matching) + "llm" (LLM judge with gpt-4o)
- YAML format: `test_id`, `query`, `requirements` (with check, type, description, points)
- Generates LLM responses and evaluates against requirements
- Multi-model testing support

## Ragas Framework Capabilities

**Retrieval Metrics**:
- Context Precision: Measures precision of retrieved documents
- Context Recall: Assesses coverage of relevant information
- Context Entities Recall: Entity-level recall
- Noise Sensitivity: Measures irrelevant content impact

**Generation Metrics**:
- Faithfulness: Factual accuracy against retrieved context
- Answer Relevancy: Relevance to the query
- Response Groundedness: Grounding in source material

**Key Benefits**:
- Reference-free evaluation (uses LLM judges internally)
- Industry-standard metrics from research literature
- Active development and maintenance (Apache 2.0 license)
- Better hallucination detection

## Proposed Implementation

### Phase 1: Setup & Dependencies (Est: 30 min) ✅

**1.1 Add ragas to requirements.txt** ✅
```python
ragas>=0.1.0  # RAG evaluation framework
```

**1.2 Create adapter module: `src/lib/ragas_adapter.py`** ✅
- Wrapper functions to convert our data formats to ragas format
- Configuration for ragas LLM judge (reuse existing LLM providers)
- Helper functions for metric calculation

**1.3 Update constants.py** ✅
```python
# Ragas Configuration
RAGAS_ENABLED = False  # Feature flag for gradual rollout
RAGAS_JUDGE_MODEL = "gpt-4o"  # Model for ragas internal evaluation
RAGAS_METRICS_RETRIEVAL = ["context_precision", "context_recall"]
RAGAS_METRICS_GENERATION = ["faithfulness", "answer_relevancy"]
```

### Phase 2: Refactor RAG-Test (Retrieval Only) (Est: 3 hours) ✅

**2.1 Extend test case models** ([test_case_models.py](test_case_models.py)) ✅

Add optional fields for ragas (backward compatible):
```python
@dataclass
class RAGTestCase:
    test_id: str
    query: str
    required_chunks: List[str]  # Legacy: headers for substring matching
    # New fields (optional):
    ground_truth_contexts: Optional[List[str]] = None  # Full text of expected chunks
```

**2.2 Update YAML format** (backward compatible) ✅

Existing format still works:
```yaml
test_id: eliminator-concealed-counteract
query: "Can the Eliminator Sniper shoot?"
required_chunks:  # Legacy - still supported
  - "During each friendly ANGEL OF DEATH"
  - "ELIMINATOR SNIPER"
```

New format with ragas support:
```yaml
test_id: eliminator-concealed-counteract
query: "Can the Eliminator Sniper shoot?"
required_chunks:  # Keep for legacy metrics
  - "During each friendly ANGEL OF DEATH"
ground_truth_contexts:  # Add for ragas metrics
  - "Full chunk text 1..."
  - "Full chunk text 2..."
```

**2.3 Create ragas evaluator** (new file: `ragas_evaluator.py`) ✅

New module:
```python
class RagasRAGEvaluator:
    """Evaluates RAG retrieval using ragas framework."""

    def evaluate(
        self,
        test_case: RAGTestCase,
        retrieved_chunks: List[DocumentChunk],
        use_ragas: bool = False,
    ) -> RAGTestResult:
        """Run evaluation with both custom + ragas metrics."""
        # Calculate custom metrics (existing)
        custom_metrics = self._calculate_custom_metrics(...)

        # Calculate ragas metrics (if enabled and ground truth available)
        ragas_metrics = None
        if use_ragas and test_case.ground_truth_contexts:
            ragas_metrics = self._calculate_ragas_metrics(...)

        return RAGTestResult(
            # ... existing fields ...
            ragas_context_precision=ragas_metrics.context_precision if ragas_metrics else None,
            ragas_context_recall=ragas_metrics.context_recall if ragas_metrics else None,
        )
```

**2.4 Update RAGTestResult model** ✅

Add optional ragas fields:
```python
@dataclass
class RAGTestResult:
    # Existing fields...
    map_score: float
    recall_at_5: float
    # ... etc ...

    # New ragas fields (optional)
    ragas_context_precision: Optional[float] = None
    ragas_context_recall: Optional[float] = None
    ragas_noise_sensitivity: Optional[float] = None
```

**2.5 Update test runner** ([test_runner.py](test_runner.py)) ✅

Add `--use-ragas` flag support, integrate ragas evaluator

**2.6 Update reports** ([reporting/](reporting/)) ✅

Add ragas metrics to markdown and charts (when available)

### Phase 3: Refactor Quality-Test (RAG + LLM) (Est: 3 hours)

**3.1 Extend test case models** ([../quality/test_case_models.py](../quality/test_case_models.py))

```python
@dataclass
class TestCase:
    test_id: str
    query: str
    requirements: List[TestRequirement]  # Legacy evaluation
    # New fields (optional):
    ground_truth_answer: Optional[str] = None  # Reference answer for ragas
    ground_truth_contexts: Optional[List[str]] = None  # Expected contexts
```

**3.2 Update YAML format** (backward compatible)

```yaml
test_id: banner-carrier-dies
query: "If my plant banner is picked up by my opponent and the carrier dies, who places it?"

# Legacy format (still supported)
requirements:
  - check: Correct final answer
    type: llm
    description: The final answer is that your opponent places it.
    points: 10

# New format (for ragas)
ground_truth_answer: |
  Your opponent places the banner within the carrier's control range
  before the operative is removed from the killzone.
ground_truth_contexts:
  - "If an operative carrying a marker is incapacitated..."
```

**3.3 Create ragas evaluator** (new file: `../quality/ragas_evaluator.py`)

```python
class RagasQualityEvaluator:
    """Evaluates RAG+LLM quality using ragas framework."""

    async def evaluate(
        self,
        test_case: TestCase,
        response: str,
        retrieved_contexts: List[str],
        use_ragas: bool = False,
    ) -> QualityTestResult:
        """Run evaluation with both custom + ragas metrics."""
        # Calculate custom metrics (existing)
        custom_results = await self._evaluate_custom(...)

        # Calculate ragas metrics (if enabled)
        ragas_results = None
        if use_ragas and test_case.ground_truth_answer:
            ragas_results = await self._evaluate_ragas(
                query=test_case.query,
                response=response,
                contexts=retrieved_contexts,
                ground_truth=test_case.ground_truth_answer,
            )

        return QualityTestResult(
            # ... existing fields ...
            ragas_faithfulness=ragas_results.faithfulness if ragas_results else None,
            ragas_answer_relevancy=ragas_results.answer_relevancy if ragas_results else None,
        )
```

**3.4 Update test result models**

Add ragas fields to `IndividualTestResult` in [../quality/reporting/report_models.py](../quality/reporting/report_models.py)

**3.5 Update test runner** ([../quality/test_runner.py](../quality/test_runner.py))

Integrate ragas evaluation alongside existing evaluation

**3.6 Update reports** ([../quality/reporting/](../quality/reporting/))

Show both custom and ragas scores in reports

### Phase 4: CLI Integration (Est: 1 hour) 

**4.1 Update rag-test command** ✅

Add flags:
```bash
python -m src.cli rag-test --use-ragas  # Run both custom + ragas
python -m src.cli rag-test --ragas-only  # Only ragas metrics
```

**4.2 Update quality-test command**

Add flags:
```bash
python -m src.cli quality-test --use-ragas
python -m src.cli quality-test --ragas-only
```

**4.3 Update sweep commands** ✅

Support ragas metrics in parameter sweeps

### Phase 5: Reporting & Visualization (Est: 2 hours)

**5.1 Update report generators** ✅

Both test frameworks:
- Add ragas metrics section to markdown reports
- Show comparison table (custom vs ragas)
- Add interpretation guide for ragas metrics

**5.2 Update chart generators** ✅

- Add ragas metric charts
- Add comparison charts (custom vs ragas side-by-side)
- Update multi-metric comparisons

**5.3 Update CSV/JSON exports** ✅

Include ragas metrics in exports for analysis

### Phase 6: Documentation (Est: 1 hour)

**6.1 Update [CLAUDE.md](CLAUDE.md)**

- Document ragas integration
- Explain new test case format
- Show migration examples
- Document ragas metrics

**6.2 Update [../quality/CLAUDE.md](../quality/CLAUDE.md)**

- Document ragas metrics
- Migration guide for test cases
- Comparison: custom vs ragas approaches

**6.3 Create migration guide**

New file: `tests/RAGAS_MIGRATION_GUIDE.md`
- Why ragas?
- How to migrate test cases
- Running both systems in parallel
- Interpreting differences

**6.4 Update root [../../CLAUDE.md](../../CLAUDE.md)**

Mention ragas integration in testing section

### Phase 7: Testing & Validation (Est: 2 hours)

**7.1 Test with existing test cases**

- Run all RAG tests with `--use-ragas`
- Run all quality tests with `--use-ragas`
- Compare custom vs ragas outputs
- Verify backward compatibility

**7.2 Create example test cases**

- Add 1-2 test cases with full ground truth
- Document expected ragas scores

**7.3 Update unit tests**

- Test ragas adapter functions
- Test backward compatibility
- Test error handling (missing ground truth, etc.)

## Migration Strategy

### Week 1: Parallel Execution
- Deploy with `RAGAS_ENABLED=False` (default)
- Manual testing with `--use-ragas` flag
- Compare outputs, validate ragas scores
- Collect feedback

### Week 2: Test Case Migration
- Migrate 2-3 test cases to include ground truth
- Run comparison reports
- Document any discrepancies
- Refine ragas configuration

### Week 3: Gradual Rollout
- Set `RAGAS_ENABLED=True` (default)
- Both metrics shown in reports
- Monitor for issues

### Month 2: Full Migration
- Deprecate custom metrics (mark as legacy)
- Ragas becomes primary evaluation method
- Keep custom metrics as fallback
- Archive comparison data

## Benefits

1. **Industry Standards**: Aligns with RAG research community
2. **Better Detection**: Superior hallucination and faithfulness detection
3. **Reference-Free**: Can evaluate without perfect ground truth
4. **Maintained**: Active open-source project with ongoing improvements
5. **Backward Compatible**: Existing tests continue working
6. **Gradual Migration**: Low-risk, reversible changes
7. **Side-by-Side Comparison**: Can validate ragas against custom metrics

## Risks & Mitigation

**Risk**: Ragas scores differ significantly from custom metrics
- **Mitigation**: Run both in parallel, investigate differences, tune if needed

**Risk**: Ragas requires API calls (additional cost)
- **Mitigation**: Make it opt-in initially, monitor costs, add rate limiting

**Risk**: Ragas metrics may be slower
- **Mitigation**: Keep custom metrics as fast path, add caching for ragas

**Risk**: Breaking changes in ragas library
- **Mitigation**: Pin version, abstract behind adapter layer, easy to swap

## Estimated Effort

| Phase | Task | Time |
|-------|------|------|
| 1 | Setup & Dependencies | 30 min |
| 2 | RAG-Test Refactor | 3 hours |
| 3 | Quality-Test Refactor | 3 hours |
| 4 | CLI Integration | 1 hour |
| 5 | Reporting & Charts | 2 hours |
| 6 | Documentation | 1 hour |
| 7 | Testing & Validation | 2 hours |
| **Total** | | **~13 hours** |

## Implementation Order

1. ✅ Research ragas (done)
2. Add dependency + adapter layer
3. RAG-test integration (retrieval metrics)
4. Quality-test integration (generation metrics)
5. CLI flags and commands
6. Reports and charts
7. Documentation
8. Testing and validation
9. Gradual rollout

## Success Criteria

- ✅ All existing tests pass without changes
- ✅ New `--use-ragas` flag works for both test suites
- ✅ Reports show both custom and ragas metrics
- ✅ Migration guide completed
- ✅ At least 2 test cases fully migrated with ground truth
- ✅ Ragas scores correlate reasonably with custom scores
- ✅ No significant performance degradation

## References

- **Ragas Documentation**: https://docs.ragas.io/
- **Ragas Paper**: https://arxiv.org/abs/2309.15217
- **Available Metrics**: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- **Getting Started**: https://docs.ragas.io/en/stable/getstarted/rag_eval/

## Notes

- This is a **gradual migration** - not a rewrite
- All existing functionality is preserved
- Ragas is additive - provides additional metrics alongside custom ones
- Feature flags allow easy rollback if needed
- Backward compatibility is a hard requirement
