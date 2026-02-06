# Quality Test Analysis: Prompt v4 Impact Report

**Date**: 2026-02-06
**Prompt Version**: v4 (base-prompt-template.md)
**Compared Against**: Prompt v3 results

## Executive Summary

**Prompt v4 changes had opposite effects on different models:**
- **Claude-4.5-sonnet**: Significant regression from **85.1% → 74.0%** (-11.1%)
- **GPT-5.2-chat-latest**: Slight improvement from **82.6% → 83.9%** (+1.3%)

The prompt changes appear to have broken Claude's quote extraction mechanism while actually improving GPT's consistency and efficiency.

---

## 1. Overall Score Changes

| Model | Old Version | New (v4) | Change | Variance Change |
|-------|-------------|----------|--------|-----------------|
| claude-4.5-sonnet | 85.1% (±20.1) | 74.0% (±29.2) | **-11.1%** | +9.1 (worse) |
| gpt-5.2-chat-latest | 82.6% (±20.6) | 83.9% (±19.4) | **+1.3%** | -1.2 (better) |

**Key observation**: Claude became both worse AND less consistent, while GPT became slightly better AND more consistent.

---

## 2. Claude-4.5-Sonnet: Detailed Breakdown

### Per-Test Score Changes

| Test | v3 Score | v4 Score | Change | Severity |
|------|----------|----------|--------|----------|
| strategic-double-action | 99.0% | 99.0% | 0.0% | Stable |
| action-in-strategic-phase | 98.0% | 97.8% | -0.2% | Stable |
| missing-context | 95.0% | 93.8% | -1.2% | Stable |
| chain-snare-vs-curtain-falls | 92.4% | 76.0% | **-16.4%** | Degraded |
| **teleport-counteract** | 89.6% | 36.4% | **-53.2%** | **CRITICAL** |
| non-reciprocal-blast | 83.2% | 78.0% | -5.2% | Degraded |
| timesplinter-to-control-range | 38.4% | 37.2% | -1.2% | Already poor |

### Most Affected Test: teleport-counteract

This test experienced catastrophic failure with sub-metric breakdown:

| Sub-Metric | v3 | v4 | Change |
|------------|-----|-----|--------|
| Quote Precision | 1.00 | **0.00** | -1.00 (CRITICAL) |
| Quote Recall | 1.00 | **0.00** | -1.00 (CRITICAL) |
| Quote Faithfulness | 1.00 | 1.00 | 0.00 |
| Explanation Faithfulness | 0.77 | 0.27 | -0.50 |
| Answer Correctness | 0.85 | 0.47 | -0.38 |

**Root cause**: Claude completely stopped extracting quotes for this test. The response focused on wrong aspects (AP costs) instead of the critical 2" movement restriction.

### Sub-Metric Degradation Pattern

| Metric | Tests Affected | Avg Change |
|--------|----------------|------------|
| Quote Precision | teleport-counteract | -1.00 |
| Quote Recall | teleport-counteract, chain-snare | -0.59 |
| Explanation Faithfulness | 4 tests | -0.24 |
| Answer Correctness | 3 tests | -0.14 |

**Pattern**: Quote extraction broke first, causing cascading failures in explanation and answer quality.

---

## 3. GPT-5.2-Chat-Latest: Stability Analysis

### Per-Test Comparison

| Test | Old | v4 | Change | Variance Change |
|------|-----|-----|--------|-----------------|
| timesplinter-to-control-range | 84.8% | 96.4% | **+11.6%** | ±23.4 → ±0.8 |
| missing-context | 93.8% | 95.0% | +1.2% | ±1.6 → ±0.0 |
| strategic-double-action | 98.2% | 98.6% | +0.4% | ±1.5 → ±0.8 |
| teleport-counteract | 89.0% | 88.8% | -0.2% | ±14.5 → ±13.4 |
| chain-snare-vs-curtain-falls | 86.4% | 86.2% | -0.2% | ±6.2 → ±0.4 |
| non-reciprocal-blast | 79.8% | 77.6% | -2.2% | ±18.3 → ±17.4 |
| action-in-strategic-phase | 46.0% | 44.6% | -1.4% | ±7.7 → ±6.6 |

**Key finding**: GPT's variance decreased on ALL tests - it became 32% more consistent overall.

### Sub-Metric Stability

| Metric | v3 Avg | v4 Avg | Change |
|--------|--------|--------|--------|
| Quote Precision | 0.720 | 0.760 | +5.6% |
| Quote Recall | 0.950 | 0.941 | -0.9% |
| Quote Faithfulness | 0.990 | 0.993 | +0.3% |
| Explanation Faithfulness | 0.728 | 0.766 | **+5.2%** |
| Answer Correctness | 0.832 | 0.843 | +1.3% |

**All metrics stable or improved** - GPT's quote mechanism remained robust regardless of prompt changes.

---

## 4. Answer Quality Changes (Claude)

### teleport-counteract - Catastrophic Failure

**v3 Response** (89.6% score):
- Correctly cited COUNTERACT rule with 2" movement restriction
- Correctly cited TELEPORT PAD rules
- Clear explanation of why teleportation cannot bypass the restriction

**v4 Response** (36.4% score):
- **Missing both critical quotes** (precision/recall = 0.0)
- Focused on AP costs instead of movement restrictions
- Wrong reasoning path led to incomplete answer

### non-reciprocal-blast - Degraded Reasoning

**v3**: Clear reasoning that shooter cannot be secondary target
**v4**: Added confused statement about visibility ("shooter not being visible to primary target") - muddled logic

### timesplinter-to-control-range - False Confidence

**v3**: Acknowledged ambiguity ("unclear")
**v4**: Became more confident ("unambiguous") while still being wrong

---

## 5. Root Cause Analysis

### Why Claude Regressed

1. **Quote extraction broken**: v4 prompt caused Claude to truncate or omit critical rule quotes
2. **False confidence**: When wrong, Claude became MORE confident instead of acknowledging ambiguity
3. **Wrong reasoning paths**: Focused on tangential aspects (AP costs vs movement restrictions)
4. **Cascading failures**: Missing quotes → weak explanations → wrong answers

### Why GPT Was Unaffected (or Improved)

1. **Robust quote mechanism**: GPT maintained 0.99+ faithfulness regardless of prompt phrasing
2. **Lower prompt sensitivity**: GPT's core reasoning didn't depend on specific prompt structure
3. **Variance reduction**: v4 actually made GPT more consistent (32% lower std dev)
4. **Efficiency gains**: v4 made GPT 16% faster and 10% cheaper

---

## 6. Recommendations

### Immediate Actions

1. **Investigate teleport-counteract failure**: Compare exact prompt sections that affect quote extraction
2. **Review v4 changes**: What specific changes broke Claude's quoting mechanism?
3. **Consider model-specific prompts**: v4 helps GPT but hurts Claude - may need different prompts

### Prompt Areas to Review

Based on the failure patterns, these prompt sections likely need attention:
- Quote extraction instructions (Claude stopped quoting entirely in some cases)
- Confidence calibration (Claude became falsely confident on ambiguous rules)
- Response conciseness (may have caused truncation of critical content)

### Testing Strategy

1. Run A/B test with v3 prompt on Claude only
2. Isolate which v4 change caused the quote extraction failure
3. Consider hybrid approach: v4 for GPT, v3 (or modified) for Claude

---

## 7. Data Sources

| Dataset | Location | Models | Tests |
|---------|----------|--------|-------|
| v4 (new) | `tests/quality/results/2026-02-06_12-50-37_prompt_v4` | claude-4.5-sonnet, gpt-5.2-chat-latest | 7 |
| GPT old | `tests/quality/results/2026-02-06_08-47-38_gtp_52` | gpt-5.2, gpt-5.2-chat-latest | 7 |
| v3 (old) | `tests/quality/results/2026-01-30_12-22-57_prompt_v3_top4_models_x5` | claude-4.5-sonnet + 3 others | 7 |

---

## Summary Table

| Aspect | Claude-4.5-sonnet | GPT-5.2-chat-latest |
|--------|-------------------|---------------------|
| Score change | -11.1% (regression) | +1.3% (improvement) |
| Consistency | Worse (±29.2) | Better (±19.4) |
| Quote extraction | **Broken** (0.0 on teleport) | Stable (0.99+) |
| Explanation quality | Degraded | Improved (+5.2%) |
| Cost efficiency | Unchanged | Better (-10%) |
| **Verdict** | v4 is harmful | v4 is beneficial |
