"""Report generation utilities for quality test results.

Handles markdown report generation for test suites.
"""

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from tests.quality.models import QualityTestSuite
from src.lib.logging import get_logger

logger = get_logger(__name__)


def generate_markdown_report(
    test_suite: QualityTestSuite, output_file: Optional[str] = None, chart_path: Optional[str] = None
) -> str:
    """Generate markdown report from test suite results.

    Args:
        test_suite: Test suite results
        output_file: Optional file path to write report to
        chart_path: Optional path to visualization chart PNG

    Returns:
        Markdown report as string
    """
    # Generate timestamp for filename
    dt = datetime.fromisoformat(test_suite.timestamp)
    timestamp_str = dt.strftime("%Y-%m-%d_%H-%M-%S")

    if output_file is None:
        output_dir = Path("tests/quality/results")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"quality_test_{timestamp_str}.md"

    # Build markdown report
    lines = []
    lines.append(f"# Quality Test Results - {timestamp_str}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total tests**: {test_suite.total_tests}")
    lines.append(f"- **Total queries**: {test_suite.total_queries}")
    lines.append(f"- **Total time**: {test_suite.total_time_seconds:.2f}s")
    lines.append(f"- **Total cost**: ${test_suite.total_cost_usd:.4f}")
    lines.append(f"- **Response characters**: {test_suite.total_response_chars}")
    lines.append(f"- **Judge model**: {test_suite.judge_model}")

    # Add LLM error statistics if any occurred
    if test_suite.total_llm_error_points > 0:
        error_pct = (test_suite.total_llm_error_points / test_suite.total_possible_points) * 100
        lines.append(f"- **Points lost to LLM errors**: {test_suite.total_llm_error_points} / {test_suite.total_possible_points} ({error_pct:.1f}%) 💀")

    lines.append("")

    # Add visualization if provided
    if chart_path:
        chart_filename = Path(chart_path).name
        lines.append("## Model Performance Visualization")
        lines.append("")
        lines.append(f"![Model Performance]({chart_filename})")
        lines.append("")
        lines.append("The chart shows four key metrics for each model:")
        lines.append("- **Score %**: Stacked bars showing earned points (green) and points lost to LLM judge errors (grey)")
        lines.append("- **Time**: Total generation time in seconds (blue bars)")
        lines.append("- **Cost**: Total cost in USD (red bars)")
        lines.append("- **Characters**: Total response characters (brown bars)")
        lines.append("")
        lines.append("Test queries are listed at the bottom of the chart.")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Add per-model summary (one-line format)
    lines.append("### Results by Model")
    lines.append("")
    for result in test_suite.test_results:
        status = "✅" if result.passed else "❌"
        lines.append(
            f"- {status} **{result.test_id}** [{result.model}]: "
            f"{result.score}/{result.max_score} "
            f"({result.generation_time_seconds:.2f}s, ${result.cost_usd:.4f}, {result.response_chars} chars)"
        )
    lines.append("")

    # Group results by test_id
    results_by_test = defaultdict(list)
    for result in test_suite.test_results:
        results_by_test[result.test_id].append(result)

    # Individual test results
    lines.append("## Individual Test Results")
    lines.append("")

    for test_id, results in results_by_test.items():
        # Use first result for query (same across models)
        first_result = results[0]

        lines.append(f"### Test: {test_id}")
        lines.append("")
        lines.append(f"**Query:** {first_result.query}")
        lines.append("")

        # Results for each model
        for result in results:
            # Check if any requirement had judge malfunction
            has_malfunction = any(r.judge_malfunction for r in result.requirements)
            error_message = ""

            if has_malfunction:
                pass_mark = "💀"
                error_message = " (Judge malfunction detected)"
            elif result.passed:
                pass_mark = "✅"
            else:
                pass_mark = "❌"

            lines.append(f"**Model: {result.model}**")
            lines.append("")
            lines.append(
                f"- Score: {result.score}/{result.max_score} {pass_mark} ({result.pass_rate:.1f}%) {error_message}"
            )
            lines.append(f"- Time: {result.generation_time_seconds:.2f}s")
            lines.append(f"- Tokens: {result.token_count}")
            lines.append(f"- Cost: ${result.cost_usd:.4f}")
            lines.append("")

            # Requirements breakdown
            lines.append("#### Requirements:")
            lines.append("")
            for req_result in result.requirements:
                # Use skull emoji for judge malfunction, otherwise standard pass/fail
                if req_result.judge_malfunction:
                    status = "💀"
                else:
                    status = "✅" if req_result.passed else "❌"

                # Build requirement line with optional check title
                req_line = f"- {status} "
                if req_result.requirement.check:
                    req_line += f"**{req_result.requirement.check}** "
                req_line += (
                    f"*({req_result.requirement.type.upper()})* "
                    f"({req_result.points_earned}/{req_result.requirement.points} pts): "
                    f"{req_result.requirement.description}"
                )
                lines.append(req_line)
                if req_result.details:
                    # Format LLM judge responses differently
                    if req_result.requirement.type == "llm" and not req_result.judge_malfunction:
                        # Split on first newline to separate YES/NO from explanation
                        details_parts = req_result.details.split('\n', 1)
                        if len(details_parts) == 2:
                            verdict = details_parts[0].strip()
                            explanation = details_parts[1].strip()
                            lines.append(f"  - _{verdict}_")
                            lines.append("")
                            lines.append(f"> {explanation}")
                        else:
                            # Fallback if no newline
                            lines.append(f"  - _{req_result.details}_")
                    else:
                        lines.append(f"  - _{req_result.details}_")
                lines.append("")

            lines.append("---")
            lines.append("")

            # Save response to separate file with context
            response_filename = f"{timestamp_str}_{result.test_id}_{result.model}.md"
            response_filepath = Path(output_file).parent / response_filename

            # Build formatted output with question, response, and prompt
            response_content = f"""---
# Question
---

{result.query}

---
# Response
---

{result.response}

---
# System Prompt
---

{result.system_prompt}

---
"""

            with open(response_filepath, "w") as f:
                f.write(response_content)

            lines.append(f"#### Response:")
            lines.append("")
            lines.append(f"See [{response_filename}]({response_filename})")
            lines.append("")
            lines.append("---")
            lines.append("")

    # Write to file
    markdown = "\n".join(lines)
    with open(output_file, "w") as f:
        f.write(markdown)

    logger.info(f"Report written to {output_file}")
    return markdown
