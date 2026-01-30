# LLM Model Comparison Analysis Report

**Test Run:** 2026-01-30_12-22-57_prompt_v3_top4_models_x5
**Models Tested:** claude-4.5-sonnet, grok-4-1-fast-reasoning, gpt-4.1, gemini-2.5-flash
**Test Cases:** 7 (140 total queries across 5 runs each)
**Judge Model:** claude-4.5-haiku (CUSTOM mode)

---

## Executive Summary
![chart](quality_test_2026-01-30_12-22-57_prompt_v3_top4_models_x5.png)
| Model | Avg Score % | Avg Time/Query | Avg Cost/Query | Key Characteristic |
|-------|-------------|----------------|----------------|-------------------|
| **claude-4.5-sonnet** | 85.1% (±20.1) | 12.67s | $0.0293 | Most accurate overall, but has blind spots |
| **grok-4-1-fast-reasoning** | 80.4% (±24.4) | 21.38s | $0.0018 | Cheapest, highest variance, overthinks |
| **gpt-4.1** | 78.3% (±22.5) | 7.25s | $0.0182 | Fastest, confident even when wrong |
| **gemini-2.5-flash** | 75.5% (±22.5) | 9.52s | $0.0037 | Good value, struggles with inference |

---

## Model-by-Model Analysis

### Claude 4.5 Sonnet

**Strengths:**
- **Highest overall accuracy (85.1%)** - Best at synthesizing multiple rules correctly
- **Excellent at recognizing missing information** - Scored 95% on missing-context test, correctly refusing to answer when rules were incomplete
- **Strong on complex rule interactions** - 99% on strategic-double-action, 92.4% on chain-snare-vs-curtain-falls
- **Highest quote faithfulness** - Rarely paraphrases or misquotes rules
- **Most consistent response format** - Low variance in output structure

**Weaknesses:**
- **Catastrophic failure on timesplinter-to-control-range (38.4%)** - Said "No" when the correct answer is "Yes". Consistently failed all 5 runs with nearly identical wrong reasoning
- **Over-cautious reasoning** - Sometimes adds unnecessary caveats that undermine correct answers
- **Most expensive** - $0.029/query (16x more than Grok)
- **Moderate speed** - 12.67s average

**Failure Pattern Analysis:**
On timesplinter test, Claude said the operative "must be set up in a location it can be placed" and incorrectly concluded this creates an ambiguity about control range placement. Gemini correctly used comparative reasoning (Reanimation Protocols explicitly prohibits control range placement, Timesplinter does not) to reach the correct "Yes" answer.

---

### Grok 4.1 Fast Reasoning

**Strengths:**
- **Extremely cheap** - $0.0018/query (16x cheaper than Claude)
- **Strong on edge cases** - 93.8% on missing-context, 93.2% on chain-snare-vs-curtain-falls
- **Good at explicit rule quoting** - High quote recall scores
- **Can handle nuanced rule interactions** - Scored 97.4% on strategic-double-action

**Weaknesses:**
- **Highest variance (±24.4)** - Inconsistent performance across runs
- **Very slow** - 21.38s average (3x slower than GPT-4.1)
- **Overthinks simple questions** - Often says "I cannot provide an answer" when the answer is clear
- **Worst on non-reciprocal-blast (41%)** - Couldn't reason about visibility and blast mechanics
- **High variance on action-in-strategic-phase (63.6% ±29.1)** - Sometimes perfect, sometimes "I don't know"

**Failure Pattern Analysis:**
On non-reciprocal-blast, Grok got confused about whether the shooter can be a secondary target. Instead of applying the simple logic (shooter isn't "visible to the target" from target's perspective), it over-analyzed control range rules and declared uncertainty. The reasoning model seems to explore too many irrelevant pathways.

---

### GPT-4.1

**Strengths:**
- **Fastest response time** - 7.25s average (44% faster than Gemini)
- **High confidence** - Gives definitive answers quickly
- **Strong on straightforward rule applications** - 98.2% on action-in-strategic-phase, 93.6% on teleport-counteract
- **Consistent performance** - Lower variance on most tests

**Weaknesses:**
- **Worst on missing-context (35%)** - Confidently gave wrong answer when rules were incomplete
- **Hallucinates when uncertain** - Instead of admitting missing information, fabricates reasoning
- **Lower quote precision** - Sometimes cites less relevant rules

**Failure Pattern Analysis:**
On missing-context, GPT-4.1 confidently stated "You place the banner" without any rule support. The test explicitly tests whether models hallucinate when RAG context is incomplete. Claude correctly said "I cannot provide an answer" while GPT-4.1 invented an answer. This is a critical flaw for a rules bot where wrong confident answers are worse than admitted uncertainty.

---

### Gemini 2.5 Flash

**Strengths:**
- **Best value for money** - $0.0037/query with decent 75.5% accuracy
- **Excellent comparative reasoning** - 93.2% on timesplinter test (best performer)
- **Fast** - 9.52s average
- **Good at finding counter-examples** - Used Reanimation Protocols to prove Timesplinter has no control range restriction

**Weaknesses:**
- **Struggles with inference** - 48.6% on action-in-strategic-phase (worst performer)
- **Paraphrasing issues** - Lower quote faithfulness, sometimes changes rule wording
- **High variance on some tests** - 62.4% ±28.9 on missing-context (inconsistent)
- **Over-explains sometimes** - More verbose than necessary

**Failure Pattern Analysis:**
On action-in-strategic-phase, Gemini incorrectly concluded that using Fall Back in the Strategy Phase limits what actions can be taken during normal activation. This shows difficulty with understanding game phase separation and action limitations.

---

## Test Case Difficulty Analysis

| Test Case | Avg Score | Hardest For | Easiest For |
|-----------|-----------|-------------|-------------|
| strategic-double-action | 93.2% | GPT-4.1 (81%) | Claude (99%) |
| teleport-counteract | 89.1% | Gemini (83%) | GPT-4.1 (93.6%) |
| chain-snare-vs-curtain-falls | 88.1% | Gemini (80.4%) | Grok (93.2%) |
| action-in-strategic-phase | 77.1% | Gemini (48.6%) | GPT/Claude (98%) |
| timesplinter-to-control-range | 72.4% | Claude (38.4%) | Gemini (93.2%) |
| missing-context | 71.5% | GPT-4.1 (35%) | Claude (95%) |
| non-reciprocal-blast | 67.5% | Grok (41%) | Claude (83.2%) |

---

## Key Findings

### 1. No Model Dominates All Tests
Each model has significant blind spots:
- Claude fails catastrophically on timesplinter (38.4%)
- GPT-4.1 fails on missing-context (35%)
- Gemini fails on action-in-strategic-phase (48.6%)
- Grok fails on non-reciprocal-blast (41%)

### 2. Confidence vs Accuracy Trade-off
- **GPT-4.1**: High confidence, sometimes wrong (dangerous for rules bot)
- **Claude**: Moderate confidence, admits uncertainty appropriately
- **Grok**: Low confidence, often says "I don't know" even when answer is clear

### 3. Reasoning Style Differences
- **Claude**: Conservative, quotes rules carefully, sometimes over-cautious
- **GPT-4.1**: Fast, direct, minimal reasoning shown
- **Gemini**: Comparative, uses counter-examples well
- **Grok**: Extended reasoning, explores many pathways (sometimes too many)

### 4. Cost-Effectiveness
- Best accuracy: Claude ($0.029/query)
- Best value: Gemini ($0.0037/query, 75.5%)
- Cheapest: Grok ($0.0018/query, but slow and inconsistent)

---

## Recommendations

### For Production Use
1. **Primary recommendation: Claude 4.5 Sonnet** - Best overall accuracy despite higher cost
2. **Budget alternative: Gemini 2.5 Flash** - 8x cheaper with acceptable accuracy
3. **Avoid GPT-4.1 for rules queries** - Confident hallucinations are dangerous

### For Quality Improvement
1. Add more test cases for edge cases where Claude fails (e.g., "absence of prohibition" reasoning)
2. Consider ensemble approach for critical questions
3. The missing-context test should be a standard benchmark - it reveals hallucination tendencies

### Test Cases to Add/Retire
- **Retire**: eliminator-concealed-counteract (all models >97%)
- **Keep**: non-reciprocal-blast (best discriminator, 67.5% avg)
- **Keep**: missing-context (reveals hallucination patterns)
