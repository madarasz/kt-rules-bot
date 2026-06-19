# System Context

You are evaluating a **Discord bot that answers Warhammer 40K Kill Team tabletop game rules questions**. This bot helps players understand complex game mechanics during gameplay.

## How the Bot Works

The bot uses **Retrieval-Augmented Generation (RAG)**:
1. User asks a rules question (e.g., "Can I shoot while concealed?")
2. Bot retrieves relevant rule sections from a vector database
3. Bot generates a structured response with three parts:
   - **Short Answer**: 1-2 sentence conclusion (Yes/No + key point)
   - **Rule Quotes**: Verbatim citations from official rules (exact text with sources)
   - **Explanation**: How the quoted rules answer the question

## What We Value

In order of priority:

1. **Correctness** (50%): Getting the right answer matters most
2. **Citation Completeness** (20%): Citing all critical rules (especially exceptions that change the answer)
3. **Explanation Quality** (15%): Clear reasoning that connects rules to answer without hallucinating
4. **Citation Accuracy** (10%): Quotes must be verbatim from official rules
5. **Conciseness** (5%): Avoid citing irrelevant rules (nice to have, least important)

**Critical insight**: Kill Team has many exceptions to baseline rules. Missing a faction-specific exception (e.g., "Space Marines can shoot while concealed") will produce a wrong answer even if baseline rules are cited correctly.

---

# Evaluation Task

Evaluate the bot's response on two dimensions and provide actionable feedback for model comparison. The response and ground truth you must evaluate are provided at the very end of this prompt, inside `<evaluation_input>`.

## Required JSON Output

```json
{{
  "explanation_faithfulness": 0.0,
  "feedback": "Bullet-point markdown in 2 sections: Explanation Problems (list ALL issues), Style (1-3 bullets)",
  "answer_correctness_details": [
    {{"answer_key": "Final Answer", "score": 1.0}},
    {{"answer_key": "Weapon", "score": 1.0}}
  ]
}}
```

**Important**:
- You MUST provide per-item scores in `answer_correctness_details` field as **arrays of objects**
- The backend will calculate `answer_correctness` aggregate from this array
- Each answer score has: `answer_key` (from ground truth) and `score` (0.0-1.0)
- Even if there are no answers, provide empty array `[]` for the `answer_correctness_details` field
- **Note**: Quote faithfulness is evaluated separately using fuzzy string matching, not by this LLM judge

## Scoring Guidelines

**IMPORTANT - Proportional Scoring**: Scores must be proportional to the number of items evaluated.

- If evaluating N items (e.g., 3 answers) and M are correct, **start with base score M/N**
- Only deduct from the remaining score based on severity of issues in incorrect items
- Example: 3 answers, 2 perfect + 1 partially correct → start at 0.67 (2/3), then score the problematic answer proportionally

### 1. Explanation Faithfulness (0.0 - 1.0)
**Question**: Is the bot's explanation grounded only in the cited quotes?

**CRITICAL — faithfulness is INDEPENDENT of answer correctness. Read carefully:**
- Faithfulness measures ONLY whether each claim is supported by the cited quotes. It does NOT measure whether the final answer is right or wrong — that is scored separately in Answer Correctness. Do not double-penalize.
- A **WRONG** conclusion can still be **fully faithful** (high score) if every claim it makes follows from the quotes — e.g. the quotes were simply incomplete, so the bot reasoned correctly from what it had but reached the wrong answer.
- A **CORRECT** conclusion can be **unfaithful** (low score) if it relies on facts not present in the quotes.
- The ONE way a wrong answer loses faithfulness: a claim **contradicts, ignores, or misapplies a rule the bot itself quoted** (e.g. it quotes a "must be set up wholly within 2\"" restriction, then concludes the action is allowed without ever addressing that restriction). Penalize THAT specific unfaithful step — not the whole explanation, and not merely because the answer is wrong.

**Worked anchors** (apply the same logic to converge on consistent scores):
- *Wrong answer, every claim grounded in the (incomplete) quotes* → **0.9–1.0**. The reasoning faithfully follows the quotes; the quotes just didn't contain the overriding exception. Faithfulness is high even though Answer Correctness will be low.
- *Wrong answer that QUOTES the controlling rule then ignores/misapplies it* → **~0.4**. One central claim is unfaithful (it skips a restriction the bot itself cited); other grounded claims keep partial credit. Not 0.0 — most claims are still grounded.
- *Correct answer that rests on "no rule prohibits this" (argument from silence)* → **~0.8**. The conclusion is a reasonable inference from the absence of a restriction in the quotes, but it is an inference rather than an explicit statement, so dock slightly.

**Evaluation approach**:
- Identify each factual claim in the explanation
- Verify each claim is supported by a cited quote
- Score based on proportion of supported vs unsupported claims

**Scoring rubric**:
- **1.0**: All claims explicitly present in quotes (no assumptions)
- **0.8**: Minor connecting statements that logically follow from quotes (e.g., "therefore", "this means")
- **0.5**: Some inferences or conclusions that go beyond quotes
- **0.0**: Explanation adds unsupported facts, rules, or conclusions not in quotes

**Example**: If explanation makes 4 claims and 3 are supported by quotes, start at 0.75 and score the unsupported claim proportionally.

**Check**: Every factual claim in the explanation should be directly supported by a cited quote.

**Feedback requirement**: In the "Explanation Problems" section, list EACH ungrounded claim as a separate bullet point. When score < 1.0, your feedback must identify ALL issues, not just the most obvious one.

### 2. Answer Correctness (0.0 - 1.0)
**Question**: Does the bot's conclusion match the ground truth?

**Evaluation approach**:
- Compare bot's conclusion against EACH ground truth answer individually
- Provide per-answer scores in `answer_correctness_details`
- The backend will weight by priority when calculating aggregate (you just provide simple average)

**Individual answer scoring** (provide in `answer_correctness_details`):
- **Key**: ground_truth_answer.key (e.g., "Final Answer", "Weapon", "Shoot regardless of order")
- **Value**: Score for that specific answer point
  - **1.0**: Answer semantically matches this ground truth point (exact wording doesn't matter)
  - **0.7**: Partially addresses this point but missing nuances
  - **0.5**: Weakly addresses or only implied
  - **0.0**: Doesn't address this point or contradicts it

**Binary rule for Yes/No ruling components** (usually the "Final Answer"):
- A component that states a **Yes/No / allowed-or-not ruling is BINARY**: score **1.0 if it matches** the ground truth ruling, **0.0 if it contradicts or inverts** it. Do NOT give 0.5–0.7 partial credit to a ruling component just because nearby sub-facts are described correctly. A confidently wrong ruling is dangerous for players and must score 0.0.
- **Cascade rule**: if the ruling is wrong, every OTHER component whose correctness *depends on* that ruling also scores **0.0**. Components that describe **independent** facts (e.g. "how teleportation mechanically works", a definition) keep their own score on their own merit.
- Reserve the 0.7 / 0.5 partial tiers for genuinely partial **non-ruling** components.
- (The backend then weights every component by its priority — critical/important/supporting — so zeroing the critical ruling already drives the aggregate toward 0. You only provide the per-component scores.)

**What you provide**:
- For each ground truth answer, assign individual score in `answer_correctness_details`
- The backend will calculate the priority-weighted aggregate (you don't need to)

**Example**:
```json
{{
  "answer_correctness_details": [
    {{"answer_key": "Final Answer", "score": 1.0}},
    {{"answer_key": "Weapon", "score": 0.7}},
    {{"answer_key": "Shoot regardless of order", "score": 1.0}},
    {{"answer_key": "Counteract regardless of order", "score": 0.7}}
  ]
}}
```
Backend calculates weighted average using priority weights

**Example — INVERTED ruling** (bot answered "Yes, allowed" but the correct ruling is "No"). The ruling and everything depending on it are 0.0; an independent mechanical fact keeps its own score:
```json
{{
  "answer_correctness_details": [
    {{"answer_key": "Final Answer", "score": 0.0}},
    {{"answer_key": "Distance requirement", "score": 0.0}},
    {{"answer_key": "How teleportation works", "score": 1.0}}
  ]
}}
```
Here "Final Answer" (critical) and "Distance requirement" (depends on the ruling) are 0.0, while "How teleportation works" is an independent fact the bot described correctly. The priority-weighted aggregate stays near 0 because the critical ruling is 0.0.

**Important**: The ground truth answers are provided with their keys and priorities in the `<ground_truth_answers>` block. Use those exact keys in your `answer_correctness_details`.

**Check**: Compare the "Short Answer" and overall conclusion against all ground truth answers. Evaluate each answer point independently.

## Feedback Format

Write **concise bullet-point lists** organized into two sections using markdown headers. Separate each section for clarity.

### Explanation Problems
**What to include**: List ALL ungrounded claims, hallucinations, incorrect conclusions, and logic errors as separate bullets. If explanation_faithfulness = 1.0, this section can be empty or state "None".

**Format**: One bullet per issue (0-6 bullets depending on number of problems found)
- Be specific: Reference exact claims from the explanation and identify which quote should have supported it
- Exhaustive: When score < 1.0, list EVERY ungrounded claim, not just the most obvious one
- Prioritize: Focus on claims not supported by quotes, hallucinated rules, incorrect logic
- Example bullet: "Claims operative gets 'free Dash action' but no cited rule grants this"
- Example bullet: "States 'counteract is always available' without grounding in cited Astartes rule"

### Style
**What to evaluate**: Clarity, logical flow, conciseness, specificity of the `short_answer` and `explanation` (1-3 bullets maximum).

**Note**: In-character persona flair has already been removed from the response before you see it. Evaluate ONLY the factual `short_answer` and `explanation`. Do NOT comment on persona, tone, or in-character phrasing — and do not invent such criticism.

**Format**: Brief bullets assessing presentation quality
- **Good style indicators**: Short answer is specific/unambiguous, explanation follows logical flow, no superfluous wording
- **Bad style indicators**: Vague answer, convoluted explanation, excessive verbosity, irrelevant details
- Example bullet: "Clear logical structure connecting Astartes rule to conclusion"
- Example bullet: "Short answer is vague; could state the Yes/No ruling more directly"

---

**Complete Example** (note how each section uses bullets and is distinct):
```
### Explanation Problems
- Missing the 'Silent' ground truth context which explains why shooting during Conceal is allowed
- Incorrectly concludes "cannot shoot" without considering weapon-specific exceptions
- Claims "Conceal order prevents all shooting" but this contradicts the Silent weapon rule

### Style
- Clear logical structure connecting rules
- Could be more concise (some repetitive phrasing)
```

**Good Example** (perfect score):
```
### Explanation Problems
None

### Style
- Clear and specific short answer
- Logical flow connecting Astartes rule to conclusion
```

**Bad Example** (not following format):
```
### Explanation Problems
The bot failed to cite the Silent weapon rule and got the wrong answer.  ❌ (Should be separate bullets)

### Style
The answer was wrong because of the missing rule.  ❌ (This belongs in Explanation Problems, not Style)
```

---

# Key Reminders

- **Exact wording doesn't matter for answers**: "Yes, you can shoot" and "Shooting is allowed" are semantically equivalent
- **Missing critical rules is worse than extra rules**: Missing an exception that changes the answer (e.g., faction rule) is a major problem
- **Faithfulness is independent of correctness**: a wrong-but-grounded answer scores high on faithfulness; do not double-penalize
- **Ruling components are binary**: a wrong Yes/No ruling is 0.0, and cascades to every component that depends on it
- **Focus on actionability**: Your feedback will be used to compare models and tune retrieval systems

<!--CACHE_BREAK-->
---

# Evaluation Input

Everything below is the specific case to evaluate. Apply the rubric and key reminders above.

<evaluation_input>

The user's question:
<user_query>
{query}
</user_query>

The correct conclusions the bot should reach (with keys and priorities):
<ground_truth_answers>
{ground_truth_answers}
</ground_truth_answers>

The official rules the bot should cite (verbatim):
<ground_truth_contexts>
{ground_truth_contexts}
</ground_truth_contexts>

The full structured response generated by the bot:
<bot_response>
{llm_response_text}
</bot_response>

The rule quotes the bot cited (with chunk_ids):
<bot_quotes>
{llm_quotes}
</bot_quotes>
</evaluation_input>

---

# Your Output

Evaluate the `<bot_response>` above against the ground truth, then return **valid JSON only**, matching the schema shown earlier. Before scoring, remember:

- Score one entry in `answer_correctness_details` per key in `<ground_truth_answers>`, using those exact keys.
- Apply the **binary rule** to Yes/No ruling components (1.0 match / 0.0 contradiction), and cascade 0.0 to dependent components.
- Keep `explanation_faithfulness` **independent** of whether the final answer is correct.
