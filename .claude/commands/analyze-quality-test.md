---
description: Analyze quality test results to explain why different LLM models received different scores for a specific test case.
---

Analyze quality test results to explain why different LLM models received different Average Score metrics.

**Input format**: `<results_directory> <test_id>`

Example: `tests/quality/results/2026-01-28_13-52-13_top4_models_x3 chain-snare-vs-curtain-falls`

User input:

$ARGUMENTS

---

## Execution Steps

1. **Parse input arguments**:
   - Extract `RESULTS_DIR` (first argument) and `TEST_ID` (second argument)
   - If arguments are missing or malformed, ask the user to provide them in the format: `<results_directory> <test_id>`

2. **Locate and read files**:
   - Report files: `{RESULTS_DIR}/report_{TEST_ID}_*.md` - contain score summaries and RAGAS metrics per model
   - Output files: `{RESULTS_DIR}/output_{TEST_ID}_*.md` - contain actual LLM responses and detailed metadata
   - Test case definition: `tests/quality/test_cases/{TEST_ID}.yaml` - contains ground truth answers and expected contexts

3. **Extract key data from each file**:
   - From report files: Average Score, individual run scores, RAGAS metrics (Quote Precision, Quote Recall, Quote Faithfulness, Explanation Faithfulness, Answer Correctness)
   - From output files: The actual LLM response text, quoted rules, explanation quality
   - From test case YAML: `ground_truth_answers` and `ground_truth_contexts` that define expected content

4. **Analyze score differences** by examining:
   - **Answer Correctness**: Did the model provide the correct final answer? (0.0 = wrong/refused, 1.0 = correct)
   - **Quote Recall**: How many of the expected `ground_truth_contexts` were cited? Higher = better coverage
   - **Quote Precision**: Were all provided quotes relevant? Lower values indicate irrelevant quotes included
   - **Quote Faithfulness**: Were quotes accurate/verbatim? Lower values indicate paraphrasing or truncation
   - **Explanation Faithfulness**: Was the reasoning logically sound and supported by evidence?

5. **Produce analysis report** with:
   - Score summary table (model, avg score, individual runs)
   - Explanation of which metrics caused score differences
   - Specific examples of response behaviors that led to metric differences
   - Highlight any failed runs (Answer Correctness = 0) and explain why they failed

## Output Format

### Score Summary
| Model | Avg Score | Individual Runs |
|-------|-----------|-----------------|
| ... | ... | ... |

### Why Scores Differ

For each significant metric difference, explain:
1. Which metric differed
2. What the models did differently
3. Concrete examples from the output files

### Key Takeaways
- Bullet points summarizing the main reasons for score differences
- Any patterns or model-specific behaviors observed

---

## Behavior Rules

- NEVER modify any files - this is a READ-ONLY analysis
- Focus ONLY on score differences - ignore Average Time and Average Cost
- If a model had a failed run, prioritize explaining why it failed
- Use concrete quotes from the output files to support observations
- If test case YAML is missing, note that ground truth context is unavailable but continue with available data
