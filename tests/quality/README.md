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

### Run tests multiple times (NEW!)
Run tests N times and get aggregated statistics with averages and standard deviations:

```bash
# Run all models 3 times
python -m src.cli quality-test --all-models --runs 3 --yes

# Run specific test 5 times
python -m src.cli quality-test --test track-enemy-tacop --runs 5 --yes

# Short form
python -m src.cli quality-test --all-models -n 5 -y
```

Multi-run mode generates:
- Individual reports for each run
- Aggregated report with averaged metrics and standard deviations
- Visualization chart with error bars and individual data points

## Output

### Single Run Output

Results are saved to timestamped markdown files in `tests/quality/results/`:

```
tests/quality/results/quality_test_2025-10-04_14-30-45.md
tests/quality/results/quality_test_2025-10-04_14-30-45_chart.png
```

Each result includes:
- **Query**: The original question
- **Score**: Points earned / total points
- **Time**: Generation time in seconds
- **Tokens**: Total token count
- **Cost**: Estimated cost in USD
- **Requirements**: Breakdown of each requirement (passed/failed)
- **Response**: Full response text (saved to separate file)
- **Visualization**: Chart showing score%, time, cost, and character count per model

### Multi-Run Output

When using `--runs N`, additional aggregated files are created:

```
tests/quality/results/quality_test_2025-10-04_14-45-30_multirun_3x.md
tests/quality/results/quality_test_2025-10-04_14-45-30_chart_multirun_3x.png
```

Aggregated report includes:
- **Summary**: Averaged metrics across all runs with standard deviations
- **Visualization**: Chart with error bars and individual run data points overlaid
- **Model Comparison Table**: Averaged score%, time, cost, and characters per model
- **Individual Run Links**: Links to detailed reports for each run

The visualization chart shows:
- **Bars**: Average values across runs
- **Error bars**: Standard deviation
- **Dots**: Individual run values overlaid on bars

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
- Multi-run mode shows average cost with standard deviation

## Architecture

The quality testing framework is organized into focused modules:

- **[test_runner.py](test_runner.py)**: Main test execution and CLI
- **[models.py](models.py)**: Data models for tests, results, and multi-run suites
- **[evaluator.py](evaluator.py)**: Requirement evaluation logic (contains + LLM judge)
- **[report_generator.py](report_generator.py)**: Markdown report generation for single runs
- **[aggregator.py](aggregator.py)**: Multi-run statistics aggregation
- **[visualization.py](visualization.py)**: Single-run chart generation
- **[multi_run_visualization.py](multi_run_visualization.py)**: Multi-run chart with error bars

## LLM Error Handling

The framework gracefully handles LLM failures:
- **ContentFilterError**: When models block responses (e.g., RECITATION in Gemini)
- **Failed requirements**: Marked with 💀 skull emoji
- **Score tracking**: Points lost to LLM errors tracked separately from test failures
- **Visualization**: Grey bars show points lost to LLM judge malfunctions
