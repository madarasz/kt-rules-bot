# Quality Testing Framework Improvements

**Status**: Design Phase
**Created**: 2025-11-21
**Goal**: Improve model comparison capabilities through weighted scoring, ground truth prioritization, and custom LLM judge

---

## Table of Contents
1. [Overview](#overview)
2. [Current Issues](#current-issues)
3. [Proposed Improvements](#proposed-improvements)
4. [Implementation Details](#implementation-details)
5. [Migration Guide](#migration-guide)
6. [Examples](#examples)

---

## Overview

The quality testing framework evaluates RAG+LLM responses using 5 Ragas metrics to compare different LLM models. This document outlines improvements to make model comparisons more meaningful and actionable.

### Current Metrics
1. **Quote Precision** (local): % of cited quotes that are relevant
2. **Quote Recall** (local): % of ground truth contexts found in citations
3. **Quote Faithfulness** (Ragas): whether quotes are grounded in RAG context
4. **Explanation Faithfulness** (Ragas): whether explanation is grounded in quotes
5. **Answer Correctness** (Ragas): semantic similarity to ground truth answers

### Framework Purpose
- **Primary goal**: Compare LLM models for Kill Team rules bot
- **Not a quality gate**: No pass/fail thresholds needed
- **Key requirement**: Verbatim rule quoting (substring matching is correct)

---

## Current Issues

### Issue 1: Equal Metric Weighting
**Problem**: All 5 metrics weighted equally (20% each) in aggregate score

**Example**:
```
Model A scores:
- Answer Correctness: 100% (correct answer)
- Quote Recall: 40% (missing critical rules)
- Quote Faithfulness: 100%
- Explanation Faithfulness: 100%
- Quote Precision: 100%
→ Aggregate: 88% (looks good, but missing key rules!)
```

**Impact**: Can't distinguish between "correct answer with poor quotes" vs "correct answer with good quotes"

### Issue 2: No Ground Truth Prioritization
**Problem**: All ground truth contexts treated equally

**Example**: `eliminator-concealed-counteract` test
```yaml
ground_truth_contexts:
  # CRITICAL - these are the exceptions that make "Yes" correct
  - "Each friendly ANGEL OF DEATH operative can counteract regardless of its order"
  - "An operative can perform the Shoot action with this weapon while it has a Conceal order"

  # SUPPORTING - baseline rule for context
  - "The operative cannot perform Shoot and Charge actions, and it cannot counteract"
```

Missing "Astartes" (critical) vs missing "Conceal baseline" (supporting) both hurt quote recall equally, but have vastly different impact on answer quality.

### Issue 3: Generic Ragas Judge
**Problem**: Ragas uses generic prompts not optimized for Kill Team domain

**Issues**:
- Generic prompts don't understand game mechanics
- Black box - can't tune judge behavior
- Inconsistent - content filter issues (RECITATION errors)
- One-size-fits-all - same prompts for all test types

**Need**: Domain-specific judge with controllable prompts

### Issue 4: Single Aggregate Score Hides Trade-offs
**Problem**: One number (0-100) can't show different failure modes

**Example**:
```
Model A: 85% (great quotes, weak explanation)
Model B: 85% (weak quotes, great explanation)
```

Same score, completely different characteristics. Need multi-dimensional view.

---

## Proposed Improvements

### Phase 1: Core Scoring Improvements

#### 1.1 Weighted Aggregate Scoring
Add configurable metric weights reflecting importance:

```python
# In src/lib/constants.py
RAGAS_METRIC_WEIGHTS = {
    "answer_correctness": 0.30,       # Must get answer right
    "quote_recall": 0.30,             # Must cite all key rules
    "explanation_faithfulness": 0.20, # Explanation must be grounded
    "quote_faithfulness": 0.15,       # No hallucinated citations
    "quote_precision": 0.05,          # Nice to have (prefer concise)
}
```

**Rationale**:
- Answer Correctness + Quote Recall = 60% (these are equally critical)
- Explanation Faithfulness = 20% (reasoning matters)
- Quote Faithfulness = 15% (hallucinations are bad)
- Quote Precision = 5% (least important - verbosity is minor issue)

#### 1.2 Ground Truth Prioritization
Allow marking ground truths as critical vs supporting:

```yaml
# In test case YAML
ground_truth_contexts:
  - text: "Each friendly ANGEL OF DEATH operative can counteract regardless of its order"
    priority: critical  # Default - can be omitted

  - text: "An operative can perform the Shoot action with this weapon while it has a Conceal order"
    priority: critical

  - text: "The operative cannot perform Shoot and Charge actions, and it cannot counteract"
    priority: supporting
```

**Priority weights**:
- `critical`: weight = 10 (default)
- `supporting`: weight = 3

**New quote recall calculation**:
```python
total_weight = sum(gt.weight for gt in ground_truths)
found_weight = sum(gt.weight for gt in ground_truths if found_in_quotes(gt))
quote_recall = found_weight / total_weight
```

#### 1.3 Custom LLM Judge
Replace Ragas with domain-specific judge for 3 metrics:

**Quote Faithfulness Judge**:
```
You are a Kill Team rules expert evaluating if a quoted rule is accurately cited.

Retrieved RAG Context:
{rag_contexts}

Quoted by LLM:
{quote}

Is this quote a verbatim substring of the RAG context? Ignore markdown formatting.
Answer: YES or NO
Reason: [one sentence explaining why]
```

**Explanation Faithfulness Judge**:
```
You are evaluating if an explanation is grounded in the cited quotes.

Quotes cited:
{quotes}

Explanation given:
{explanation}

Does the explanation only make claims supported by the quotes? Check if all
statements are directly supported without adding unsupported facts.

Answer: YES or NO
Reason: [one sentence]
```

**Answer Correctness Judge**:
```
You are a Kill Team rules expert evaluating answer correctness.

Question: {query}

Ground truth answer:
{ground_truth}

LLM answer:
{llm_answer}

Is the LLM answer semantically correct compared to ground truth? The exact
wording does not need to match, but the conclusion must be the same.

Answer: CORRECT or INCORRECT
Reason: [one sentence]
```

**Keep local calculations**:
- Quote Precision: substring matching (no LLM needed)
- Quote Recall: substring matching with priority weights

### Phase 2: Better Comparison Reporting

#### 2.1 Multi-Dimensional Model Profiles
Show metrics grouped by dimension:

```markdown
## Model Comparison

| Model | Overall | Quote Quality | Reasoning | Correctness | Speed | Cost |
|-------|---------|---------------|-----------|-------------|-------|------|
| Claude Sonnet | 85% | 88% | 85% | 82% | 6.2s | $0.02 |
| GPT-4.1 | 82% | 75% | 90% | 85% | 6.3s | $0.02 |
| Grok-3 | 68% | 60% | 72% | 70% | 7.1s | $0.03 |

**Dimensions:**
- Overall = weighted aggregate (using RAGAS_METRIC_WEIGHTS)
- Quote Quality = 0.5×quote_recall + 0.3×quote_faithfulness + 0.2×quote_precision
- Reasoning = explanation_faithfulness
- Correctness = answer_correctness
```

**Benefits**: Quickly see trade-offs - Model A has better quotes, Model B has better reasoning.

#### 2.2 Quote Coverage Visualization
Show which ground truths each model found:

```markdown
### Quote Coverage: eliminator-concealed-counteract

| Ground Truth | Priority | Claude | GPT-4.1 | Grok-3 |
|--------------|----------|--------|---------|--------|
| Astartes rule | ⭐ Critical | ✅ | ✅ | ✅ |
| Silent rule | ⭐ Critical | ✅ | ❌ | ❌ |
| Conceal baseline | Supporting | ✅ | ✅ | ✅ |

**Legend**: ⭐ Critical rules have 3.3x weight in quote recall calculation
```

**Benefits**: Instantly see which models miss which rules.

### Phase 3: Judge Validation

#### 3.1 Judge Validation Tracking
Add optional human review to validate judge decisions:

```python
# In IndividualTestResult
human_review: dict | None = None  # Optional human scores

# Example usage
{
  "answer_correctness_human": 0.50,
  "answer_correctness_judge": 0.38,
  "notes": "Judge too harsh - answer was partially correct"
}
```

**Benefits**: Track judge accuracy, identify and fix bad judge prompts over time.

---

## Implementation Details

### File Changes

#### 1. `src/lib/constants.py`
Add new configuration constants:

```python
# Quality Testing - Metric Weights
RAGAS_METRIC_WEIGHTS = {
    "answer_correctness": 0.30,
    "quote_recall": 0.30,
    "explanation_faithfulness": 0.20,
    "quote_faithfulness": 0.15,
    "quote_precision": 0.05,
}

# Quality Testing - Ground Truth Priorities
GROUND_TRUTH_PRIORITY_WEIGHTS = {
    "critical": 10,
    "supporting": 3,
}
DEFAULT_GROUND_TRUTH_PRIORITY = "critical"

# Quality Testing - Custom Judge
CUSTOM_JUDGE_MODEL = "gpt-4.1-mini"  # Model for custom judge
CUSTOM_JUDGE_MAX_TOKENS = 150
CUSTOM_JUDGE_TEMPERATURE = 0.0
```

#### 2. `tests/quality/test_case_models.py`
Update data models:

```python
@dataclass
class GroundTruthContext:
    """A ground truth context with priority."""
    text: str
    priority: str = "critical"  # "critical" or "supporting"

    @property
    def weight(self) -> int:
        return GROUND_TRUTH_PRIORITY_WEIGHTS.get(
            self.priority,
            GROUND_TRUTH_PRIORITY_WEIGHTS["critical"]
        )

@dataclass
class TestCase:
    """Test case definition."""
    test_id: str
    query: str
    ground_truth_answers: list[str]
    ground_truth_contexts: list[str] | list[GroundTruthContext]  # Support both formats
    requirements: list[dict] | None = None  # Legacy, deprecated

    def get_contexts_with_weights(self) -> list[GroundTruthContext]:
        """Convert ground_truth_contexts to GroundTruthContext objects."""
        if not self.ground_truth_contexts:
            return []

        if isinstance(self.ground_truth_contexts[0], GroundTruthContext):
            return self.ground_truth_contexts

        # Legacy format - convert strings to GroundTruthContext
        return [
            GroundTruthContext(text=ctx, priority="critical")
            for ctx in self.ground_truth_contexts
        ]
```

#### 3. `tests/quality/custom_judge.py` (NEW FILE)
Create custom LLM judge:

```python
"""Custom LLM judge for quality testing.

Provides domain-specific evaluation for Kill Team rules bot:
- Quote Faithfulness: Verbatim substring matching
- Explanation Faithfulness: Claims grounded in quotes
- Answer Correctness: Semantic correctness
"""

from dataclasses import dataclass
from src.lib.constants import (
    CUSTOM_JUDGE_MODEL,
    CUSTOM_JUDGE_MAX_TOKENS,
    CUSTOM_JUDGE_TEMPERATURE,
)
from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.factory import LLMProviderFactory
from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class JudgeResult:
    """Result from custom judge evaluation."""
    score: float  # 0.0 or 1.0
    reason: str
    error: str | None = None


class CustomJudge:
    """Custom LLM judge for quality testing."""

    def __init__(self, model: str = CUSTOM_JUDGE_MODEL):
        self.model = model
        self._provider = None

    def _get_provider(self):
        """Lazy-load LLM provider."""
        if self._provider is None:
            self._provider = LLMProviderFactory.create(self.model)
        return self._provider

    async def evaluate_quote_faithfulness(
        self, quote: str, rag_contexts: list[str]
    ) -> JudgeResult:
        """Evaluate if quote is verbatim from RAG context."""
        prompt = f"""You are a Kill Team rules expert evaluating if a quoted rule is accurately cited.

Retrieved RAG Context:
{chr(10).join(f"[{i+1}] {ctx}" for i, ctx in enumerate(rag_contexts))}

Quoted by LLM:
{quote}

Is this quote a verbatim substring of the RAG context? Ignore markdown formatting like bold/italics.

Answer: YES or NO
Reason: [one sentence explaining why]"""

        return await self._evaluate(prompt, "YES")

    async def evaluate_explanation_faithfulness(
        self, explanation: str, quotes: list[str]
    ) -> JudgeResult:
        """Evaluate if explanation is grounded in quotes."""
        prompt = f"""You are evaluating if an explanation is grounded in the cited quotes.

Quotes cited:
{chr(10).join(f"[{i+1}] {q}" for i, q in enumerate(quotes))}

Explanation given:
{explanation}

Does the explanation only make claims supported by the quotes? Check if all statements are directly supported without adding unsupported facts or conclusions.

Answer: YES or NO
Reason: [one sentence]"""

        return await self._evaluate(prompt, "YES")

    async def evaluate_answer_correctness(
        self, query: str, llm_answer: str, ground_truth: str
    ) -> JudgeResult:
        """Evaluate if answer is semantically correct."""
        prompt = f"""You are a Kill Team rules expert evaluating answer correctness.

Question: {query}

Ground truth answer:
{ground_truth}

LLM answer:
{llm_answer}

Is the LLM answer semantically correct compared to ground truth? The exact wording does not need to match, but the conclusion must be the same.

Answer: CORRECT or INCORRECT
Reason: [one sentence]"""

        return await self._evaluate(prompt, "CORRECT")

    async def _evaluate(self, prompt: str, positive_keyword: str) -> JudgeResult:
        """Run judge evaluation and parse result."""
        try:
            provider = self._get_provider()
            config = GenerationConfig(
                max_tokens=CUSTOM_JUDGE_MAX_TOKENS,
                temperature=CUSTOM_JUDGE_TEMPERATURE,
                system_prompt="You evaluate text. Be concise and consistent.",
                include_citations=False,
            )

            response = await provider.generate(
                GenerationRequest(prompt=prompt, context=[], config=config)
            )

            answer_text = response.answer_text.strip()

            # Parse: first line should be YES/NO or CORRECT/INCORRECT
            lines = answer_text.split('\n')
            first_line = lines[0].upper()
            reason = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""

            # Check if positive keyword in first line
            passed = positive_keyword in first_line
            score = 1.0 if passed else 0.0

            return JudgeResult(score=score, reason=reason or answer_text)

        except Exception as e:
            logger.error(f"Custom judge evaluation failed: {e}", exc_info=True)
            return JudgeResult(score=0.0, reason="", error=str(e))
```

#### 4. `tests/quality/ragas_evaluator.py`
Update to use custom judge and weighted scoring:

```python
# Add import
from tests.quality.custom_judge import CustomJudge
from src.lib.constants import RAGAS_METRIC_WEIGHTS, CUSTOM_JUDGE_MODEL

class RagasEvaluator:
    def __init__(self, llm_model: str | None = None):
        self.llm_model = llm_model or QUALITY_TEST_JUDGE_MODEL
        self._ragas_llm = None
        self.custom_judge = CustomJudge(model=CUSTOM_JUDGE_MODEL)  # NEW

    async def evaluate(self, ...):
        # ... existing code ...

        # Replace Ragas evaluation with custom judge
        # Keep local quote_precision and quote_recall calculations

        # Custom judge for quote faithfulness
        quotes_combined = " ".join(quotes_text) if quotes_text else ""
        qf_result = await self.custom_judge.evaluate_quote_faithfulness(
            quote=quotes_combined,
            rag_contexts=context_chunks
        )

        # Custom judge for explanation faithfulness
        ef_result = await self.custom_judge.evaluate_explanation_faithfulness(
            explanation=answer_text,
            quotes=quotes_text
        )

        # Custom judge for answer correctness
        ac_result = await self.custom_judge.evaluate_answer_correctness(
            query=query,
            llm_answer=answer_text,
            ground_truth=" ".join(normalized_ground_truth_answers)
        )

        metrics = RagasMetrics(
            quote_precision=retrieval_metrics.context_precision,
            quote_recall=retrieval_metrics.context_recall,
            quote_faithfulness=qf_result.score,
            explanation_faithfulness=ef_result.score,
            answer_correctness=ac_result.score,
            quote_faithfulness_feedback=qf_result.reason,
            explanation_faithfulness_feedback=ef_result.reason,
            answer_correctness_feedback=ac_result.reason,
        )

        # Calculate costs...
        return metrics

    def calculate_aggregate_score(self, metrics: RagasMetrics) -> float:
        """Calculate weighted aggregate score."""
        if metrics.error:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        metric_values = {
            "answer_correctness": metrics.answer_correctness,
            "quote_recall": metrics.quote_recall,
            "explanation_faithfulness": metrics.explanation_faithfulness,
            "quote_faithfulness": metrics.quote_faithfulness,
            "quote_precision": metrics.quote_precision,
        }

        for metric_name, value in metric_values.items():
            if value is not None and not (isinstance(value, float) and math.isnan(value)):
                weight = RAGAS_METRIC_WEIGHTS.get(metric_name, 0.0)
                weighted_sum += value * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        # Scale to 0-100
        return (weighted_sum / total_weight) * 100
```

#### 5. `src/lib/ragas_adapter.py`
Update quote recall to use priority weights:

```python
def evaluate_retrieval(
    retrieved_contexts: list[str],
    ground_truth_contexts: list[GroundTruthContext],  # Changed type
) -> RagasRetrievalMetrics:
    """Evaluate retrieval with priority-weighted recall."""

    # Quote Recall with priority weights
    total_weight = sum(gt.weight for gt in ground_truth_contexts)
    found_weight = 0

    for gt_context in ground_truth_contexts:
        for retrieved_context in retrieved_contexts:
            if ground_truth_matches_text(gt_context.text, retrieved_context):
                found_weight += gt_context.weight
                break

    context_recall_value = found_weight / total_weight if total_weight > 0 else 0.0

    # Quote Precision (unchanged - no priority weighting)
    relevant_retrieved_count = 0
    for retrieved_context in retrieved_contexts:
        for gt_context in ground_truth_contexts:
            if ground_truth_matches_text(gt_context.text, retrieved_context):
                relevant_retrieved_count += 1
                break

    context_precision_value = (
        relevant_retrieved_count / len(retrieved_contexts) if retrieved_contexts else 0.0
    )

    return RagasRetrievalMetrics(
        context_precision=context_precision_value,
        context_recall=context_recall_value
    )
```

#### 6. `tests/quality/reporting/report_generator.py`
Add multi-dimensional profiles and quote coverage:

```python
def _get_model_comparison_table(self, summaries=None):
    """Generate model comparison with dimensions."""
    # ... existing code ...

    # Add dimension columns
    table_header = "| Model | Overall | Quote Quality | Reasoning | Correctness | Speed | Cost |"

    for summary in summaries:
        quote_quality = self._calculate_quote_quality_dimension(summary)
        reasoning = self._get_metric_avg(summary, "explanation_faithfulness") * 100
        correctness = self._get_metric_avg(summary, "answer_correctness") * 100

        # ... format row ...

    return table

def _calculate_quote_quality_dimension(self, summary: ModelSummary) -> float:
    """Calculate quote quality dimension score."""
    recall = self._get_metric_avg(summary, "quote_recall")
    faithfulness = self._get_metric_avg(summary, "quote_faithfulness")
    precision = self._get_metric_avg(summary, "quote_precision")

    return (0.5 * recall + 0.3 * faithfulness + 0.2 * precision) * 100

def _generate_quote_coverage_matrix(self, test_id: str, results: list):
    """Generate quote coverage visualization."""
    # Group results by model
    by_model = {}
    for result in results:
        if result.model not in by_model:
            by_model[result.model] = []
        by_model[result.model].append(result)

    # Extract ground truths from test case
    # ... implementation ...
```

---

## Migration Guide

### Backward Compatibility

**Old format (still supported)**:
```yaml
test_id: my-test
query: "..."
ground_truth_contexts:
  - "Rule text 1"
  - "Rule text 2"
```
→ All contexts treated as `priority: critical` (default)

**New format (recommended)**:
```yaml
test_id: my-test
query: "..."
ground_truth_contexts:
  - text: "Critical rule 1"
    priority: critical
  - text: "Critical rule 2"
    priority: critical
  - text: "Supporting context"
    priority: supporting
```

### Updating Test Cases

Only update tests where some contexts are supporting (not critical):

```bash
# Example: banner-carrier-dies test
# Before:
ground_truth_contexts:
  - "If an operative carrying a marker is incapacitated..."

# After (if all are critical - NO CHANGE NEEDED):
ground_truth_contexts:
  - "If an operative carrying a marker is incapacitated..."

# After (if some are supporting):
ground_truth_contexts:
  - text: "If an operative carrying a marker is incapacitated..."
    priority: critical
  - text: "Place marker is a free action"
    priority: supporting
```

### Running Tests

No changes to CLI:
```bash
# Same commands work
python -m src.cli quality-test
python -m src.cli quality-test --all-models
```

### Expected Score Changes

Scores will change due to:
1. **Weighted aggregate** - models with better quote_recall/answer_correctness will score higher
2. **Priority weights** - missing critical ground truths will hurt more
3. **Custom judge** - may evaluate differently than Ragas

**Action**: Run baseline tests before and after implementation to document score changes.

---

## Examples

### Example 1: Simple Test (No Changes Needed)

```yaml
test_id: banner-carrier-dies
query: >
  If my plant banner is picked up by my opponent and the carrier dies,
  who places the banner, me or my opponent?
ground_truth_answers:
  - My opponent places the banner.
  - The operative carrying the marker must place the marker if it's incapacitated.
ground_truth_contexts:
  - "If an operative carrying a marker is incapacitated, it must perform this action before being removed from the killzone"
```

**No change needed** - single critical ground truth (default priority).

### Example 2: Complex Test with Priorities

```yaml
test_id: eliminator-concealed-counteract
query: >
  Can the Eliminator Sniper shoot during counteract while having Conceal order?
ground_truth_answers:
  - Yes, the Eliminator Sniper can shoot during counteract regardless of its order.
  - The Eliminator Sniper's weapon, the Bolt Sniper Rifle, has the Silent weapon rule.
  - The Silent weapon rule allows an operative to perform the Shoot action with this weapon while it has a Conceal order.
  - The Astartes rule allows the Eliminator Sniper to counteract regardless of its order.
ground_truth_contexts:
  - text: "Each friendly ANGEL OF DEATH operative can counteract regardless of its order"
    priority: critical
  - text: "An operative can perform the Shoot action with this weapon while it has a Conceal order"
    priority: critical
  - text: "The operative cannot perform Shoot and Charge actions, and it cannot counteract"
    priority: supporting
```

**Quote Recall calculation**:
```
Total weight = 10 + 10 + 3 = 23

Scenario 1: Found all 3 contexts
→ Quote Recall = 23/23 = 100%

Scenario 2: Found only critical contexts (Astartes + Silent)
→ Quote Recall = 20/23 = 87%

Scenario 3: Found only Astartes + Conceal baseline (missing Silent)
→ Quote Recall = 13/23 = 57%

Old system: All scenarios would be 100%, 67%, 67% respectively
→ New system better captures importance of critical rules
```

### Example 3: Model Comparison Report

**Before (equal weights)**:
```markdown
| Model | Avg Score |
|-------|-----------|
| Claude Sonnet | 85% |
| GPT-4.1 | 85% |
| Grok-3 | 72% |
```

**After (weighted + dimensions)**:
```markdown
| Model | Overall | Quote Quality | Reasoning | Correctness | Speed | Cost |
|-------|---------|---------------|-----------|-------------|-------|------|
| Claude Sonnet | 87% | 92% | 85% | 88% | 6.2s | $0.02 |
| GPT-4.1 | 83% | 78% | 90% | 85% | 6.3s | $0.02 |
| Grok-3 | 68% | 58% | 72% | 70% | 7.1s | $0.03 |

**Analysis**:
- Claude Sonnet: Best quote quality (92%) and overall winner
- GPT-4.1: Best reasoning (90%) but weaker quotes (78%)
- Grok-3: Lags behind on all dimensions
```

**Quote Coverage Matrix**:
```markdown
### eliminator-concealed-counteract Coverage

| Ground Truth | Priority | Claude | GPT-4.1 | Grok-3 |
|--------------|----------|--------|---------|--------|
| Astartes rule | ⭐ Critical | ✅ | ✅ | ✅ |
| Silent rule | ⭐ Critical | ✅ | ❌ | ❌ |
| Conceal baseline | Supporting | ✅ | ✅ | ✅ |

**Impact**: GPT-4.1 and Grok-3 both missed the critical Silent rule,
significantly hurting their quote recall scores.
```

---

## Implementation Checklist

### Phase 1: Core Improvements
- [ ] Add constants to `src/lib/constants.py`
- [ ] Update `TestCase` model in `tests/quality/test_case_models.py`
- [ ] Create `tests/quality/custom_judge.py`
- [ ] Update `RagasEvaluator` to use custom judge and weighted scoring
- [ ] Update `evaluate_retrieval()` to use priority weights
- [ ] Test with existing test cases (backward compatibility)
- [ ] Update 1-2 test cases to use new priority format
- [ ] Run baseline comparison (before/after scores)

### Phase 2: Reporting
- [ ] Add dimension calculation methods to report generator
- [ ] Update model comparison table to show dimensions
- [ ] Add quote coverage matrix to per-test reports
- [ ] Generate test reports to verify formatting

### Phase 3: Documentation
- [ ] Update `tests/quality/CLAUDE.md` with new features
- [ ] Add example test cases with priorities
- [ ] Document score changes from baseline

### Phase 4: Validation
- [ ] Run quality tests on all models with new system
- [ ] Compare results to findings.md observations
- [ ] Validate custom judge decisions align with human judgment
- [ ] Add human review tracking (optional)

---

## Open Questions

1. Should we allow custom weights per test case? (e.g., some tests emphasize correctness more)
   - **Current**: Global weights in constants.py
   - **Possible**: Per-test weights in YAML

2. Should quote precision also use priority weights?
   - **Current**: No - precision treats all quotes equally
   - **Rationale**: Precision measures "noise" (citing irrelevant rules), priority doesn't apply

3. Should we keep Ragas as fallback option?
   - **Current**: Completely replace with custom judge
   - **Alternative**: Keep both, make it configurable

---

## Related Issues

- See `tests/quality/findings/findings.md` for historical test results
- See `tests/quality/CLAUDE.md` for current framework documentation

---

## Future Enhancements (Out of Scope)

- Judge validation dashboard (Streamlit UI to review judge decisions)
- Automated test case generation from user queries
- A/B testing framework for prompt changes
- Integration with CI/CD for regression detection
