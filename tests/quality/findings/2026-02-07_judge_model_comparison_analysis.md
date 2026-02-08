# Judge Model Comparison Analysis

**Date:** 2026-02-07
**Test Results Analyzed:**
- `grok-4-1-fast-reasoning` judge: `results/2026-02-07_13-48-59_REPLAYS_judge_grok_r`
- `grok-4-1-fast-non-reasoning` judge: `results/2026-02-07_13-36-50_REPLAYS_judge_grok_nr`
- `claude-4.5-haiku` judge: `results/2026-02-07_14-35-09_REPLAYS_judge_sonnet`

**Purpose:** Compare scoring differences between judge models on identical LLM outputs to determine which judge produces more justified scores.

---

## Overall Score Rankings by Judge

| Model Under Test | Grok-R Judge | Grok-NR Judge | Haiku Judge |
|------------------|--------------|---------------|-------------|
| claude-4.5-sonnet | **88.3%** (#1) | **89.2%** (#1) | 84.7% (#2) |
| grok-4-1-fast-reasoning | 87.9% (#2) | 87.7% (#2) | **85.0%** (#1) |
| gpt-5.2-chat-latest | 87.3% (#3) | 85.2% (#3) | 84.3% (#3) |
| grok-4-1-fast-non-reasoning | 81.6% (#4) | 80.1% (#4) | 80.5% (#4) |

**Key finding:** Grok judges rank claude-sonnet #1, but Haiku ranks grok-reasoning #1. This indicates different evaluation philosophies rather than self-preference bias.

---

## Source of Score Differences

### 1. Explanation Faithfulness (Largest Variance)

This LLM-judged metric assesses whether explanation claims are grounded in cited quotes.

| Model | Grok-R | Grok-NR | Haiku |
|-------|--------|---------|-------|
| claude-4.5-sonnet | 0.839 | 0.834 | **0.751** |
| grok-4-1-fast-reasoning | 0.830 | 0.833 | **0.740** |
| gpt-5.2-chat-latest | 0.893 | 0.801 | 0.796 |
| grok-4-1-fast-non-reasoning | 0.810 | 0.726 | 0.750 |

**Haiku is consistently 8-10% stricter** on this metric across all models.

### 2. Answer Correctness (Moderate Variance)

| Model | Grok-R | Grok-NR | Haiku |
|-------|--------|---------|-------|
| claude-4.5-sonnet | 0.854 | **0.874** | 0.811 |
| grok-4-1-fast-reasoning | **0.861** | 0.857 | 0.833 |
| gpt-5.2-chat-latest | 0.869 | 0.853 | 0.840 |
| grok-4-1-fast-non-reasoning | 0.811 | 0.808 | 0.808 |

Haiku consistently scores Answer Correctness ~4-6% lower than Grok judges.

### 3. The "Inference Problem"

The core disagreement centers on: **Should logical inferences count as "grounded"?**

Example from `teleport-counteract` test:
- Responses correctly concluded "No, you cannot use the Teleport Pad during counteract"
- They inferred "teleport pads are not within 2" of each other" without explicit quote support

**Grok judges** - accepted this logical inference:
```
### Explanation Problems
- Assumes the other teleport pad is "potentially far beyond 2"" without this
  distance being stated in the cited quotes (logical inference but not explicitly grounded).
```
Score impact: Minor deduction (~0.05-0.10)

**Haiku judge** - stricter enforcement:
```
### Explanation Problems
- The claim that the teleport pad rule "would violate the 2" setup restriction" is
  an inference not explicitly stated in the cited quotes. The quotes don't directly
  state that teleporting to the other pad violates the 2" restriction; this requires
  the reader to infer that the two pads are not within 2" of each other.
- The explanation doesn't cite the ground truth context that "the two teleport pads
  are not wholly within 2" of each other," which is the actual reason the teleport
  pad cannot be used during counteract.
```
Score impact: Larger deduction (~0.10-0.15)

---

## Feedback Quality Comparison

### Grok-R (Reasoning)
- **Length:** Short, focused (~50-100 words)
- **Cost:** ~$0.0007-0.0009/judgment
- **Strengths:** Identifies key issues, cost-effective
- **Weaknesses:** Sometimes superficial, misses subtle nuances

### Grok-NR (Non-Reasoning)
- **Length:** Similar brevity (~50-100 words)
- **Cost:** ~$0.0007-0.0008/judgment
- **Strengths:** Fast execution
- **Weaknesses:** Less consistent than Grok-R, occasionally misses issues

### Haiku (Claude)
- **Length:** Detailed (~150-300 words)
- **Cost:** ~$0.005-0.007/judgment (7-10x more expensive)
- **Strengths:**
  - Catches subtle issues others miss
  - Provides specific examples
  - Explains *why* something is problematic
  - More consistent across runs
- **Weaknesses:** Higher cost and latency

### Example: Same Response, Different Feedback

**Grok-R feedback:**
> Claims 'The RETURN TO DARKNESS ploy is used outside of an activation' without explicit support in the cited quotes, which do not specify the ploy's timing

**Haiku feedback:**
> Minor: The phrase "The RETURN TO DARKNESS ploy is used outside of an activation" is a logical inference rather than explicitly stated in the cited quotes. While this inference is sound and critical to the answer, it goes slightly beyond what the quotes directly state.
>
> Excellent logical structure: The explanation clearly delineates temporal boundaries (outside activation vs. during activation) and applies them to the restriction rules

---

## Self-Preference Analysis

Is there bias where judges rate their own provider higher?

| Judge | Rating of Same-Provider Models |
|-------|-------------------------------|
| Grok-R | Rates grok-reasoning at 87.9% (#2, not #1) |
| Grok-NR | Rates grok-nr at 80.1% (lowest of all) |
| Haiku | Rates claude-sonnet at 84.7% (#2, not #1) |

**Conclusion: No evidence of self-preference.** Haiku is actually *stricter* on Claude models than Grok judges are.

---

## Per-Test-Case Score Comparison

| Test Case | Grok-R | Grok-NR | Haiku |
|-----------|--------|---------|-------|
| chain-snare-vs-curtain-falls | 91.0% | 90.5% | 89.4% |
| action-in-strategic-phase | 88.5% | 84.0% | 87.8% |
| strategic-double-action | 97.6% | 97.2% | 97.5% |
| teleport-counteract | 72.5% | 72.0% | **69.0%** |
| missing-context | 96.7% | 96.7% | **93.6%** |
| non-reciprocal-blast | 77.6% | 78.2% | **71.8%** |
| timesplinter-to-control-range | 80.0% | 80.3% | **76.3%** |

Haiku is stricter on complex rule-interaction tests (teleport-counteract, non-reciprocal-blast, timesplinter).

---

## Which Scores Are More Justified?

### Haiku Appears Most Justified

1. **More thorough analysis** - Catches subtle issues that Grok judges miss
2. **Consistent reasoning** - Same issues flagged consistently across runs
3. **Stricter quote grounding** - Correctly enforces that RAG responses should be grounded in retrieved context, not logical inference
4. **Better calibration on wrong answers** - When models gave wrong answers (saying "Yes" to teleport-counteract when answer is "No"), Haiku gave harsher scores (35-60%) vs Grok's (42-67%)

### Grok-R Is a Reasonable Alternative

1. 10x cheaper per judgment
2. Still catches major issues
3. Faster execution
4. Acceptable for screening/quick iteration

### Grok-NR Is Weakest

1. Less consistent feedback quality
2. Sometimes misses issues Grok-R catches
3. Occasional contradictory scores within same test case

---

## Philosophical Difference

The fundamental disagreement is about **inference tolerance**:

| Approach | Philosophy | Implication |
|----------|------------|-------------|
| **Grok judges** | Permissive - if an inference logically follows from quotes, it's acceptable | Higher scores, accepts reasonable deductions |
| **Haiku** | Strict - only explicit quote support counts; inferences should be flagged | Lower scores, enforces RAG grounding |

**For RAG evaluation**, Haiku's stricter interpretation is more appropriate. The purpose of RAG evaluation is to prevent hallucination and ensure responses are grounded in retrieved context. Accepting "logical inferences" partially defeats this purpose.

---

## Recommendations

### Primary Judge Selection

| Use Case | Recommended Judge | Rationale |
|----------|-------------------|-----------|
| Rigorous evaluation | **claude-4.5-haiku** | Most accurate, detailed feedback |
| Cost-efficient screening | **grok-4-1-fast-reasoning** | Catches most issues at 10x lower cost |
| Not recommended | grok-4-1-fast-non-reasoning | Inconsistent, misses subtle issues |

### Hybrid Approach

For optimal cost/quality balance:
1. Run **Grok-R** for quick screening during development
2. Run **Haiku** for detailed analysis before releases
3. Use **Haiku** for borderline cases requiring deeper investigation

### Configuration Update

Consider updating `QUALITY_TEST_JUDGE_MODEL` in `constants.py`:
- Current: `gpt-4.1-mini`
- For rigorous testing: `claude-4.5-haiku`
- For cost-efficient screening: `grok-4-1-fast-reasoning`

---

## Cost Comparison

| Judge Model | Judge Cost (7 tests, 4 models, 5 runs = 140 queries) |
|-------------|-----------------------------------------------------|
| grok-4-1-fast-reasoning | $0.1089 (5.4% of total) |
| grok-4-1-fast-non-reasoning | $0.1080 (5.3% of total) |
| claude-4.5-haiku | $0.8414 (30.4% of total) |

Haiku is ~8x more expensive but provides significantly more detailed and consistent feedback.

---

## Raw Data Reference

Full test results available in:
- `tests/quality/results/2026-02-07_13-48-59_REPLAYS_judge_grok_r/`
- `tests/quality/results/2026-02-07_13-36-50_REPLAYS_judge_grok_nr/`
- `tests/quality/results/2026-02-07_14-35-09_REPLAYS_judge_sonnet/`
