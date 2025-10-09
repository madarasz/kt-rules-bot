# Decisions
## LLM models removed from consideration
- `GPT-5`, `grok-4-0709`: VERY SLOW (often around 2 mins or more)
- `Claude Opus 4.1`: 5-8x more expensive than other models, and does not preform well either

## To improve
- Gemini models often fail with RECITATION error, blocking the response

# Test results
## Comparing OpenAI models - 2025-10-08
- `GPT-4.1` is the most promising, 77% score, 6s to reply, $0.02 cost
- `GTP-o3` is also nice, 80% score, $0.01 cost, unfortunately slower: 24s to reply
- `GPT-5` is extremely slow, usually 2 minutes is not enough to get a reply
- `GPT-5-mini` is also slow, more than 40s in average, sometimes timing out

![report](quality_test_2025-10-08_12-27-54_chart_multirun_3x.png)

| Model | Avg Score | Avg Time | Avg Cost | Avg Chars |
|-------|-----------|----------|----------|-----------|
| gpt-4.1 | 76.9% (±34.3%) | 6.27s (±1.63s) | $0.0216 (±$0.0057) | 1221 (±388) |
| gpt-4o | 44.1% (±37.8%) | 6.93s (±1.87s) | $0.0267 (±$0.0073) | 888 (±242) |
| gpt-5-mini | 65.9% (±44.7%) | 37.70s (±16.99s) | $0.0056 (±$0.0024) | 1661 (±830) |
| o3 | 79.5% (±32.3%) | 23.63s (±11.97s) | $0.0135 (±$0.0041) | 1021 (±252) |
| o3-mini | 56.2% (±39.6%) | 15.92s (±4.93s) | $0.0138 (±$0.0037) | 921 (±169) |
| o4-mini | 57.5% (±45.0%) | 19.03s (±8.66s) | $0.0138 (±$0.0038) | 851 (±266) |

