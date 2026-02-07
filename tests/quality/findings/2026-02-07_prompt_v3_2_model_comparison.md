# LLM Model Comparison Report

**Test Date:** 2026-02-07
**Prompt Version:** v32
**Judge Model:** claude-4.5-haiku (CUSTOM mode)
**Test Cases:** 7 tests, 5 models, 5 runs each

## Overall Rankings

| Rank | Model | Avg Score | Consistency (±std) | Avg Time | Cost/Query |
|------|-------|-----------|-------------------|----------|------------|
| 1 | **grok-4-1-fast-reasoning** | 85.5% | ±19.1 | 16.46s | $0.0018 |
| 2 | **claude-4.5-sonnet** | 84.7% | ±15.6 | 11.89s | $0.0302 |
| 3 | **gpt-5.2-chat-latest** | 84.7% | ±19.5 | 8.01s | $0.0212 |
| 4 | **grok-4-1-fast-non-reasoning** | 81.0% | ±25.3 | 4.07s | $0.0018 |
| 5 | **gemini-2.5-flash** | 75.7% | ±23.9 | 8.30s | $0.0038 |

---

## Model Strengths & Weaknesses

### Claude 4.5 Sonnet
**Strengths:**
- **Most consistent performer** - lowest variance across runs (±15.6%)
- **Excellent on reasoning-heavy tests** - 98.6% on strategic-double-action, 98.6% on action-in-strategic-phase
- **Strong quote citation** - consistently high Quote Precision and Recall
- **Best at uncertainty acknowledgment** - 94.6% on missing-context (correctly refuses to answer when rules are incomplete)

**Weaknesses:**
- **Critical failure on timesplinter-to-control-range** - only 38.0% (all 5 runs answered "No" when correct answer is "Yes")
- **Inconsistent on non-reciprocal-blast** - 75.4% (±14.5) with runs ranging from 57% to 94%
- **Highest cost** - $0.0302/query (17x more than Grok models)

**Key Pattern:** Claude tends to be overly conservative when rules don't explicitly state a permission - it interprets absence of prohibition as prohibition.

---

### GPT-5.2-chat-latest
**Strengths:**
- **Best on timesplinter-to-control-range** - 97.0% (correctly interprets permissive principle)
- **Good balance** of speed (8.01s) and quality (84.7%)
- **Strong on complex rule interactions** - handles multi-rule scenarios well

**Weaknesses:**
- **High variance on action-in-strategic-phase** - 69.4% (±35.5) - swings wildly between runs
- **Inconsistent reasoning** - sometimes applies permissive principle, sometimes doesn't
- **Second-highest cost** - $0.0212/query

**Key Pattern:** GPT-5.2 shows excellent rule comprehension but inconsistent application of logical principles.

---

### Grok-4-1-fast-reasoning
**Strengths:**
- **Highest overall score** - 85.5%
- **Best on non-reciprocal-blast** - 76.6% (handles visibility edge cases better)
- **Excellent on strategic-double-action** - 98.8%
- **Ultra-low cost** - $0.0018/query

**Weaknesses:**
- **Slowest model** - 16.46s average (reasoning tokens add latency)
- **High variance** - ±19.1% overall
- **Weak on teleport-counteract** - 72.6% (struggles with rule precedence)

**Key Pattern:** Reasoning mode helps with complex multi-step logic but adds significant latency.

---

### Grok-4-1-fast-non-reasoning
**Strengths:**
- **Fastest model** - 4.07s average
- **Ultra-low cost** - $0.0018/query
- **Best on action-in-strategic-phase** - 98.6%
- **Excellent on timesplinter** - 95.6%

**Weaknesses:**
- **Highest variance** - ±25.3% (most inconsistent)
- **Catastrophic failure on teleport-counteract** - 28.0% (gets the answer wrong most of the time)
- **Weak on non-reciprocal-blast** - 62.6%

**Key Pattern:** Fast but unreliable on complex rule interactions; great for simple temporal reasoning.

---

### Gemini-2.5-flash
**Strengths:**
- **Lowest cost of premium models** - $0.0038/query
- **Good on timesplinter** - 94.4%
- **Solid on strategic-double-action** - 96.6%

**Weaknesses:**
- **Lowest overall score** - 75.7%
- **Worst on action-in-strategic-phase** - 41.2% (±6.0)
- **Weak on teleport-counteract** - 77.8%
- **High variance** - ±23.9%

**Key Pattern:** Struggles with temporal/phase-based reasoning; better on spatial/proximity questions.

---

## Per-Test Case Analysis

| Test Case | Claude | GPT-5.2 | Grok-R | Grok-NR | Gemini |
|-----------|--------|---------|--------|---------|--------|
| strategic-double-action | **98.6%** | 96.2% | **98.8%** | 96.4% | 96.6% |
| non-reciprocal-blast | 75.4% | 70.8% | **76.6%** | 62.6% | 68.4% |
| teleport-counteract | **95.4%** | 82.4% | 72.6% | 28.0% | 77.8% |
| timesplinter-control | 38.0% | **97.0%** | 77.0% | 95.6% | 94.4% |
| chain-snare-vs-curtain | **92.0%** | - | - | - | - |
| missing-context | **94.6%** | - | - | - | - |
| action-in-strategic-phase | **98.6%** | 69.4% | 86.4% | **98.6%** | 41.2% |

**Best performer per test bolded**

---

## Key Findings

### 1. **No Clear Winner**
Each model excels in different areas. The "best" choice depends on priorities:
- **Quality + Consistency:** Claude 4.5 Sonnet
- **Speed + Cost:** Grok-4-1-fast-non-reasoning
- **Balance:** GPT-5.2 or Grok-4-1-fast-reasoning

### 2. **Problematic Test Cases**
- **timesplinter-to-control-range:** Claude fails completely (38%) while GPT-5.2 excels (97%) - reveals fundamental difference in how models interpret "permissive principle"
- **teleport-counteract:** All models except Claude struggle (28-82%) - rule precedence is hard
- **non-reciprocal-blast:** All models have trouble (62-77%) - complex visibility + blast mechanics

### 3. **Cost vs Quality Tradeoff**
| Model | Quality | Cost Multiplier vs Cheapest |
|-------|---------|----------------------------|
| Claude | 84.7% | 17x |
| GPT-5.2 | 84.7% | 12x |
| Grok-R | 85.5% | 1x |
| Grok-NR | 81.0% | 1x |
| Gemini | 75.7% | 2x |

Grok models offer best value; Claude/GPT premium not justified by score alone.

### 4. **Consistency Matters**
Claude's lower variance (±15.6%) vs Grok-NR's high variance (±25.3%) means:
- Claude: More predictable user experience
- Grok-NR: Cheaper but users may get very wrong answers

---

## Recommendations

1. **For Production Use:** Consider **Grok-4-1-fast-reasoning** for best balance of cost, quality, and acceptable latency.

2. **For Premium Tier:** **Claude 4.5 Sonnet** offers best consistency but fix the permissive principle interpretation issue.

3. **Prompt Engineering Needed:** The timesplinter test case reveals all models need better guidance on "absence of restriction = permission" principle.

4. **Avoid for Rules Bot:** Gemini-2.5-flash - too inconsistent on temporal reasoning critical for Kill Team rules.
