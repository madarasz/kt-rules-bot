# Response Quality Testing

This framework provides automated quality testing for RAG + LLM responses. It evaluates responses against predefined requirements using both exact string matching and LLM-based evaluation.

## Overview

Quality tests verify that:
1. Responses contain specific required text (using "contains" requirements)
2. Responses satisfy semantic conditions (using "llm" requirements evaluated by an LLM judge)

## Test Case Format

Test cases are defined in YAML files in `tests/quality/test_cases/`. Each test case includes:

```yaml
test_id: unique-test-identifier
query: >
  The question to ask the RAG + LLM system

requirements:
  - type: contains
    description: Text that must appear in the response
    points: 5

  - type: llm
    description: Statement that must be true about the response
    points: 10
```

### Requirement Types

**contains**: Exact substring match (case-insensitive, markdown-stripped)
- The response must contain the specified text
- Markdown formatting is stripped before comparison

**llm**: LLM-based evaluation
- An LLM judge evaluates whether the statement is true about the response
- Uses configurable judge model (default: gpt-4.1-mini)

## Usage

### Run all tests with default model
```bash
python -m src.cli quality-test
```

### Run specific test
```bash
python -m src.cli quality-test --test track-enemy-tacop
```

### Test all available models
Currently limited to: *claude-sonnet, gemini-2.5-pro, gemini-2.5-flash, gpt-4.1, gpt-4o*
```bash
python -m src.cli quality-test --all-models
```

### Test specific model
```bash
python -m src.cli quality-test --model gemini-2.5-pro
```

### Use different judge model
```bash
python -m src.cli quality-test --judge-model claude-sonnet
```

### Skip confirmation prompt
```bash
python -m src.cli quality-test --yes
```

## Output

Results are saved to timestamped markdown files in `tests/quality/results/`:

```
tests/quality/results/quality_test_2025-10-04_14-30-45.md
```

Each result includes:
- **Query**: The original question
- **Score**: Points earned / total points
- **Time**: Generation time in seconds
- **Tokens**: Total token count
- **Cost**: Estimated cost in USD
- **Requirements**: Breakdown of each requirement (passed/failed)
- **Response**: Full response text (in collapsible section)

## Example Test Case

See [test_cases/track-enemy-tacop.yaml](test_cases/track-enemy-tacop.yaml) for a complete example.

## Adding New Tests

1. Create a new YAML file in `tests/quality/test_cases/`
2. Follow the format shown above
3. Run the test to verify it works

## Cost Tracking

The system automatically tracks costs using model-specific pricing:
- Estimates token usage (70% prompt, 30% completion)
- Calculates cost using `src.lib.tokens.estimate_cost()`
- Provides per-query and total costs in results
