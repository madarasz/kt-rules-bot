# Decisions
Best so far:
- Claude Sonnet
- gemini-2.5-flash

Get rid of:
- GPT-5, GTP-5-mini: VERY SLOW, often times out
- GPT-4.1-mini: not smart enough
- Claude Opus: Expensive, logic might be broken

## claude-sonnet
- factual: CORRECT
- speed: fast, ~10s
- cost: medium, ~0.03$
## claude-opus
- factual: WRONG
    - rewrites Seek rule, compacting Light into first sentence
    - contradicting statements
- speed: fast, ~10s
- cost: expensive, ~0.25$
## gemini-2.5-pro
- factual: WRONG
    - didn't quote Seek Light rule, quoted Markerlight instead
- speed: medium, ~15s
- cost: medium, ~0.03$
## gemini-2.5-flash
- factual: CORRECT
- speed: fast, ~10s
- cost: cheep, ~0.001$
## gpt-5
- SOMETIMES TIMES OUT
- factual: CORRECT
- speed: slow, ~35s
- cost: medium, ~0.03$
## gpt-5-mini
- SOMETIMES TIMES OUT
- factual: CORRECT
- speed: slow, ~30s
- cost: cheep, ~0.007$
## gpt-4.1
- factual: CORRECT
- speed: fast, ~10s
- cost: medium, ~0.03$
## gpt-4.1-mini
- factual: WRONG
    - Thinks 6" is important and thus Seek Light and Vantage do not affect
- speed: fast, ~10s
- cost: cheep, ~0.005$
- length: long
## gpt-4o
- factual: CORRECT
- speed: fast, ~10s
- cost: medium, ~0.03$
- length: very short, no real explanation, summary = short answer