#!/usr/bin/env python3
"""Analyze RAG test results across all test runs.

This script parses all report.md files in tests/rag/results/ and generates
a comprehensive report showing pass/fail rates for each test case.
"""

import re
from pathlib import Path
from collections import defaultdict


def analyze_test_results():
    """Analyze all RAG test results and generate a report."""
    # Find all report.md files
    results_dir = Path("tests/rag/results")
    if not results_dir.exists():
        print(f"Error: Directory {results_dir} not found")
        return

    report_files = sorted(results_dir.glob("*/report.md"))

    if not report_files:
        print(f"No report files found in {results_dir}")
        return

    print(f"Analyzing {len(report_files)} test run reports...\n")

    # Dictionary to track test results across all runs
    # test_id -> list of (run_name, has_missing)
    test_results = defaultdict(list)

    # Parse each report
    for report_path in report_files:
        run_name = report_path.parent.name

        try:
            content = report_path.read_text()
        except Exception as e:
            print(f"Warning: Could not read {run_name}: {e}")
            continue

        # Find the Per-Test Results section
        per_test_match = re.search(r'## Per-Test Results\s*\n(.*)', content, re.DOTALL)
        if not per_test_match:
            print(f"Warning: No Per-Test Results section in {run_name}")
            continue

        per_test_section = per_test_match.group(1)

        # Split by test case headers (### test-id)
        test_cases = re.split(r'\n### ([a-z0-9-]+)\n', per_test_section)

        # test_cases[0] is the content before the first test
        # After that, it alternates: test_id, content, test_id, content, ...
        for i in range(1, len(test_cases), 2):
            if i + 1 >= len(test_cases):
                break

            test_id = test_cases[i]
            test_content = test_cases[i + 1]

            # Check if this test case has missing chunks
            has_missing = '**Missing** ❌' in test_content

            test_results[test_id].append((run_name, has_missing))

    # Calculate statistics for each test
    test_stats = []
    for test_id, results in test_results.items():
        total_runs = len(results)
        failed_runs = sum(1 for _, has_missing in results if has_missing)
        passed_runs = total_runs - failed_runs
        pass_rate = (passed_runs / total_runs * 100) if total_runs > 0 else 0

        test_stats.append({
            'test_id': test_id,
            'total_runs': total_runs,
            'passed': passed_runs,
            'failed': failed_runs,
            'pass_rate': pass_rate
        })

    # Sort by pass rate (descending)
    test_stats.sort(key=lambda x: x['pass_rate'], reverse=True)

    # Print header
    print("=" * 100)
    print("RAG TEST RESULTS ANALYSIS")
    print("=" * 100)
    print()
    print(f"Total test runs analyzed: {len(report_files)}")
    print(f"Total unique test cases: {len(test_stats)}")
    print()

    # Print table
    print("-" * 100)
    print(f"{'Test Case ID':<45} {'Total Runs':>12} {'Passed':>10} {'Failed':>10} {'Pass Rate':>12}")
    print("-" * 100)

    for stat in test_stats:
        test_id = stat['test_id']
        total = stat['total_runs']
        passed = stat['passed']
        failed = stat['failed']
        rate = stat['pass_rate']

        # Format with color indicators
        if rate == 100.0:
            rate_str = f"{rate:>6.1f}% ✓"
        elif rate == 0.0:
            rate_str = f"{rate:>6.1f}% ✗"
        else:
            rate_str = f"{rate:>6.1f}%  "

        print(f"{test_id:<45} {total:>12} {passed:>10} {failed:>10} {rate_str:>12}")

    print("-" * 100)
    print()

    # Summary statistics
    perfect_tests = [s for s in test_stats if s['pass_rate'] == 100.0]
    failing_tests = [s for s in test_stats if s['pass_rate'] < 100.0]

    print("SUMMARY:")
    print(f"  Tests with 100% pass rate: {len(perfect_tests)}")
    print(f"  Tests with failures: {len(failing_tests)}")
    print()

    if perfect_tests:
        print("Tests that never failed (candidates for removal):")
        for stat in perfect_tests:
            print(f"  - {stat['test_id']} ({stat['total_runs']} runs)")
        print()


if __name__ == "__main__":
    analyze_test_results()
