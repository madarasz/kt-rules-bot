# LLM Model Comparison Analysis Report

**Test Run:** 2026-01-30_12-22-57_prompt_v3_top4_models_x5 (updated 2026-02-06)
**Models Tested:** claude-4.5-sonnet, claude-4.6-opus, gpt-5.2-chat-latest, gpt-4.1, grok-4-1-fast-reasoning, grok-4-1-fast-non-reasoning, gemini-2.5-flash
**Test Cases:** 7 (140 total queries across 5 runs each)
**Judge Model:** claude-4.5-haiku (CUSTOM mode)

---

## Executive Summary
![chart](quality_test_2026-01-30_12-22-57_prompt_v3_top4_models_x5.png)
| Model | Avg Score % | Avg Time/Query | Avg Cost/Query | Key Characteristic |
|-------|-------------|----------------|----------------|-------------------|
| **claude-4.5-sonnet** | 85.1% (±20.1) | 12.67s | $0.0293 | Most accurate overall, but has blind spots |
| **gpt-5.2-chat-latest** | 82.6% (±20.6) | 11.08s | $0.0213 | Fixed hallucination issue, fails on phase separation |
| **claude-4.6-opus** | 81.7% (±19.2) | 16.76s | $0.0647 | Most expensive, fails on phase separation |
| **grok-4-1-fast-reasoning** | 80.4% (±24.4) | 21.38s | $0.0018 | Cheapest reasoning model, highest variance, overthinks |
| **grok-4-1-fast-non-reasoning** | 78.9% (±N/A) | 5.6s | $0.0018 | Cheapest & fastest, refuses to synthesize rules |
| **gpt-4.1** | 78.3% (±22.5) | 7.25s | $0.0182 | Fastest legacy model, confident even when wrong |
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

### Claude 4.6 Opus

**Test Run:** 2026-02-05_20-44-41_opus-4.6

**Strengths:**
- **Strong on complex rule interactions** - 99% on strategic-double-action (matching Sonnet)
- **Excellent at recognizing missing information** - 94% on missing-context test (near Sonnet's 95%, far better than GPT's 35%)
- **Good chain reasoning** - 90.33% on chain-snare-vs-curtain-falls
- **Improved timesplinter performance** - 77.67% (better than Sonnet's catastrophic 38.4%)

**Weaknesses:**
- **Catastrophic failure on action-in-strategic-phase (47%)** - Worst of all models tested (Sonnet/GPT achieved 98%)
- **Most expensive** - $0.0647/query (2.2x more than Sonnet, 36x more than Grok)
- **Slow** - 16.76s average (slower than Sonnet's 12.67s)
- **High variance on timesplinter (±25.93)** - Inconsistent reasoning, contradicted itself in one run
- **Lower than Sonnet on non-reciprocal-blast** - 74.67% vs Sonnet's 83.2%

**Failure Pattern Analysis:**
On action-in-strategic-phase, Opus fundamentally misunderstands the distinction between Strategy Phase and Activation. The correct answer is "Yes" because Return to Darkness happens in the Strategy Phase (outside activation), so "same activation" restrictions don't apply. Opus incorrectly treats the Strategy Phase action as occurring within the same activation, leading to the wrong conclusion. This is a critical logic failure for game phase separation.

On timesplinter (77.67% ±25.93), Opus showed high variance. In one run, Opus stated "No" in the headline answer but reasoned to "Yes" in the explanation—a direct self-contradiction. Got the correct answer in 2/3 runs, but the inconsistency is concerning.

---

### GPT-5.2 Chat Latest

**Test Run:** 2026-02-06_gpt-5.2-chat-latest

**Strengths:**
- **Fixed hallucination problem** - 93.8% on missing-context (massive improvement over GPT-4.1's catastrophic 35%)
- **Excellent on straightforward rules** - 98.2% on strategic-double-action (best performer)
- **Strong teleport reasoning** - 89.0% on teleport-counteract
- **Good timesplinter performance** - 84.8% (better than Sonnet's 38.4%, similar to Opus's 77.67%)

**Weaknesses:**
- **Catastrophic failure on action-in-strategic-phase (46%)** - Worst performer along with Opus (47%) and Gemini (48.6%)
- **High variance** - ±20.6 overall, with some tests showing ±23.4 variance
- **Moderate cost** - $0.0213/query (7x cheaper than Opus, but 12x more than Grok)
- **Moderate speed** - 11.08s average

**Failure Pattern Analysis:**
On action-in-strategic-phase, GPT-5.2 makes the same fundamental error as Opus and Gemini: it fails to understand the distinction between Strategy Phase actions and actions during Activation. The correct answer is "Yes" because Return to Darkness happens in the Strategy Phase (outside activation), so "same activation" restrictions don't apply. GPT-5.2 incorrectly treats phase boundaries as transparent to action restrictions.

Notably, GPT-5.2 has completely fixed the hallucination tendency that plagued GPT-4.1. On missing-context, it correctly recognizes when rules are insufficient and refuses to fabricate answers, improving from 35% to 93.8%.

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

### Grok 4.1 Fast Non-Reasoning

**Test Run:** 2026-02-06_grok-4-1-fast-non-reasoning

**Strengths:**
- **Cheapest model** - $0.0018/query (tied with reasoning variant, 16x cheaper than Claude Sonnet)
- **Fastest model** - ~5.6s average (4x faster than reasoning variant, faster than GPT-4.1's 7.25s)
- **Excellent at recognizing missing information** - 96.0% on missing-context (best performer)
- **Strong on strategic-double-action** - 96.2% (near top tier)
- **Great chain reasoning** - 90.4% on chain-snare-vs-curtain-falls

**Weaknesses:**
- **Catastrophic failure on teleport-counteract (37.6%)** - Worst performer by far (GPT-4.1 achieved 93.6%)
- **High variance on some tests** - timesplinter at 67.0% ±23.5
- **Refuses to synthesize rules** - Says "I cannot provide an answer" even when rules are sufficient
- **No extended reasoning** - Lacks the deliberation of reasoning variant

**Failure Pattern Analysis:**
On teleport-counteract, the non-reasoning Grok refuses to provide an answer even when all necessary rules are cited and the logic is straightforward. Example response: "I cannot provide an answer based on the available rules" despite having the teleport rule and counteract timing rule in context. This represents excessive caution—the model won't synthesize multiple rules into a conclusion even when the synthesis is trivial.

**Comparison to Reasoning Variant:**
| Metric | Reasoning | Non-Reasoning |
|--------|-----------|---------------|
| Avg Score | 80.4% | 78.9% |
| Avg Time | 21.38s | 5.6s |
| Cost | $0.0018 | $0.0018 |
| teleport-counteract | 89.1% | 37.6% |
| non-reciprocal-blast | 41% | 74.0% |

The non-reasoning variant is 4x faster at equal cost, but trades accuracy on complex rule synthesis. It actually performs *better* on non-reciprocal-blast (74% vs 41%) where the reasoning variant overthinks.

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
| strategic-double-action | 93.2% | GPT-4.1 (81%) | GPT-5.2 (98.2%), Claude Sonnet/Opus (99%) |
| teleport-counteract | 89.1% | Grok Non-Reasoning (37.6%) | GPT-4.1 (93.6%) |
| chain-snare-vs-curtain-falls | 88.1% | Gemini (80.4%) | Grok Reasoning (93.2%) |
| action-in-strategic-phase | 77.1% | GPT-5.2 (46%), Opus (47%), Gemini (48.6%) | GPT-4.1/Sonnet (98%) |
| timesplinter-to-control-range | 72.4% | Sonnet (38.4%) | Gemini (93.2%) |
| missing-context | 71.5% | GPT-4.1 (35%) | Grok Non-Reasoning (96%), Sonnet (95%) |
| non-reciprocal-blast | 67.5% | Grok Reasoning (41%) | Sonnet (83.2%) |

**Notes:**
- Opus performs middle-ground on timesplinter (77.67% ±25.93), better than Sonnet but with high variance.
- GPT-5.2 fixed GPT-4.1's hallucination issue (35% → 93.8% on missing-context) but introduced phase separation failure (46%).
- Grok Non-Reasoning is catastrophically worse on teleport-counteract (37.6% vs 89.1% reasoning) but better on non-reciprocal-blast (74% vs 41%).

---

## Key Findings

### 1. No Model Dominates All Tests
Each model has significant blind spots:
- Claude Sonnet fails catastrophically on timesplinter (38.4%)
- Claude Opus fails catastrophically on action-in-strategic-phase (47%)
- GPT-5.2 fails catastrophically on action-in-strategic-phase (46%) - **same weakness as Opus**
- GPT-4.1 fails on missing-context (35%)
- Gemini fails on action-in-strategic-phase (48.6%)
- Grok Reasoning fails on non-reciprocal-blast (41%)
- Grok Non-Reasoning fails catastrophically on teleport-counteract (37.6%) - **refuses to synthesize rules**

### 2. Phase Separation Is a Common Blind Spot
Three models (GPT-5.2, Opus, Gemini) fail catastrophically on action-in-strategic-phase (46-48.6%), suggesting LLMs struggle with game phase separation logic. Only GPT-4.1 and Claude Sonnet handle this correctly (98%).

### 3. Confidence vs Accuracy Trade-off
- **GPT-4.1**: High confidence, sometimes wrong (dangerous for rules bot)
- **GPT-5.2**: Fixed hallucination, but still overconfident on phase questions
- **Claude**: Moderate confidence, admits uncertainty appropriately
- **Grok Reasoning**: Low confidence, often says "I don't know" even when answer is clear
- **Grok Non-Reasoning**: Extremely conservative, refuses to synthesize even simple rule combinations

### 4. Reasoning Style Differences
- **Claude**: Conservative, quotes rules carefully, sometimes over-cautious
- **GPT-4.1**: Fast, direct, minimal reasoning shown
- **GPT-5.2**: More deliberative than GPT-4.1, improved uncertainty handling
- **Gemini**: Comparative, uses counter-examples well
- **Grok Reasoning**: Extended reasoning, explores many pathways (sometimes too many)
- **Grok Non-Reasoning**: Direct answers, but refuses complex synthesis

### 5. Cost-Effectiveness
- Best accuracy: Claude Sonnet ($0.029/query, 85.1%)
- Best value: Gemini ($0.0037/query, 75.5%)
- Cheapest + Fastest: Grok Non-Reasoning ($0.0018/query, 5.6s, 78.9%)
- Budget with reasoning: Grok Reasoning ($0.0018/query, but 21.38s)
- Improved GPT: GPT-5.2 ($0.0213/query, 82.6%) - fixed hallucination issues
- Worst value: Claude Opus ($0.0647/query, 81.7%) - 2.2x more expensive than Sonnet but 3.4% lower accuracy

---

## Recommendations

### For Production Use
1. **Primary recommendation: Claude 4.5 Sonnet** - Best overall accuracy (85.1%) despite higher cost
2. **Budget alternative: Gemini 2.5 Flash** - 8x cheaper with acceptable accuracy (75.5%)
3. **Speed + budget alternative: Grok 4.1 Fast Non-Reasoning** - Cheapest ($0.0018) and fastest (5.6s), good for simple queries (78.9%)
4. **Avoid GPT-4.1 for rules queries** - Confident hallucinations are dangerous (35% on missing-context)
5. **Consider GPT-5.2 over GPT-4.1** - Fixed hallucination problem (93.8% vs 35%), but fails on phase separation (46%)
6. **Avoid Claude 4.6 Opus** - Too expensive ($0.0647/query), lower accuracy than Sonnet, and catastrophic failure on phase separation (47%)
7. **Avoid Grok Non-Reasoning for complex rule synthesis** - Refuses to synthesize rules (37.6% on teleport-counteract)

### For Quality Improvement
1. Add more test cases for edge cases where Claude fails (e.g., "absence of prohibition" reasoning)
2. Consider ensemble approach for critical questions
3. The missing-context test should be a standard benchmark - it reveals hallucination tendencies
4. The action-in-strategic-phase test is now a critical benchmark - reveals phase separation understanding failures (GPT-5.2: 46%, Opus: 47%, Gemini: 48.6%)
5. The teleport-counteract test discriminates between models that can/cannot synthesize multiple rules

### Test Cases to Add/Retire
- **Retire**: eliminator-concealed-counteract (all models >97%)
- **Keep**: non-reciprocal-blast (best discriminator, 67.5% avg)
- **Keep**: missing-context (reveals hallucination patterns)
- **Keep**: teleport-counteract (reveals rule synthesis capability - Grok Non-Reasoning: 37.6%)
- **Keep**: action-in-strategic-phase (reveals phase separation understanding - 3 models fail at 46-48.6%)
