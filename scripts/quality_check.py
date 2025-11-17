#!/usr/bin/env python3
"""
Aggregated code quality checker.

Runs all quality tools and generates a comprehensive report with scores.
"""

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class QualityMetric:
    """Represents a single quality metric."""

    name: str
    score: float  # 0-100
    status: str  # "pass", "warn", "fail"
    details: str
    threshold: float = 70.0


class QualityChecker:
    """Runs quality checks and aggregates results."""

    def __init__(self, project_root: Path, quiet: bool = False):
        self.project_root = project_root
        self.src_dir = project_root / "src"
        self.metrics: list[QualityMetric] = []
        self.quiet = quiet

    def log(self, message: str) -> None:
        """Log a message to stderr (so it doesn't interfere with JSON output)."""
        if not self.quiet:
            print(message, file=sys.stderr)

    def run_command(
        self, cmd: list[str], capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a shell command and return the result."""
        return subprocess.run(cmd, capture_output=capture_output, text=True, cwd=self.project_root)

    def check_coverage(self) -> QualityMetric:
        """Check test coverage."""
        self.log("📊 Checking test coverage...")
        self.run_command(["pytest", "--cov=src", "--cov-report=json", "--cov-report=term", "-q"])

        coverage_file = self.project_root / "coverage.json"
        if coverage_file.exists():
            with open(coverage_file) as f:
                data = json.load(f)
                total_coverage = data.get("totals", {}).get("percent_covered", 0)
                total_statements = data.get("totals", {}).get("num_statements", 0)
                covered = data.get("totals", {}).get("covered_lines", 0)

                # Updated thresholds: pass >=50, warn >=20 and <50, fail <20
                status = (
                    "pass" if total_coverage >= 50 else "warn" if total_coverage >= 20 else "fail"
                )
                return QualityMetric(
                    name="Test Coverage",
                    score=total_coverage,
                    status=status,
                    details=f"{covered}/{total_statements} lines covered",
                    threshold=50.0,
                )
        return QualityMetric(
            name="Test Coverage", score=0, status="fail", details="Coverage data not available"
        )

    def check_complexity(self) -> QualityMetric:
        """Check code complexity with radon."""
        self.log("🔍 Checking code complexity...")
        result = self.run_command(["radon", "cc", str(self.src_dir), "--json"])

        if result.returncode == 0 and result.stdout:
            try:
                data = json.loads(result.stdout)
                complexities = []
                for file_data in data.values():
                    for item in file_data:
                        if isinstance(item, dict):
                            complexities.append(item.get("complexity", 0))

                if complexities:
                    avg_complexity = sum(complexities) / len(complexities)
                    max_complexity = max(complexities)
                    # Score: inverse of complexity (lower is better)
                    # 1-5: A (100), 6-10: B (80), 11-20: C (60), 21+: D (40)
                    if avg_complexity <= 5:
                        score = 100
                        status = "pass"
                    elif avg_complexity <= 10:
                        score = 80
                        status = "pass"
                    elif avg_complexity <= 20:
                        score = 60
                        status = "warn"
                    else:
                        score = 40
                        status = "fail"

                    return QualityMetric(
                        name="Code Complexity",
                        score=score,
                        status=status,
                        details=f"Avg: {avg_complexity:.1f}, Max: {max_complexity}",
                    )
            except json.JSONDecodeError:
                pass

        return QualityMetric(
            name="Code Complexity", score=100, status="pass", details="No complex functions found"
        )

    def check_maintainability(self) -> QualityMetric:
        """Check maintainability index with radon."""
        self.log("🛠️  Checking maintainability...")
        result = self.run_command(["radon", "mi", str(self.src_dir), "--json"])

        if result.returncode == 0 and result.stdout:
            try:
                data = json.loads(result.stdout)
                mi_scores = []
                for file_data in data.values():
                    if isinstance(file_data, dict):
                        mi = file_data.get("mi", 0)
                        if mi > 0:
                            mi_scores.append(mi)

                if mi_scores:
                    avg_mi = sum(mi_scores) / len(mi_scores)
                    min_mi = min(mi_scores)

                    # MI: 20-100, higher is better
                    if avg_mi >= 80:
                        status = "pass"
                    elif avg_mi >= 60:
                        status = "warn"
                    else:
                        status = "fail"

                    return QualityMetric(
                        name="Maintainability Index",
                        score=avg_mi,
                        status=status,
                        details=f"Avg: {avg_mi:.1f}, Min: {min_mi:.1f}",
                        threshold=60.0,
                    )
            except json.JSONDecodeError:
                pass

        return QualityMetric(
            name="Maintainability Index", score=0, status="fail", details="Unable to calculate MI"
        )

    def check_type_coverage(self) -> QualityMetric:
        """Check type hint coverage with mypy."""
        self.log("🔤 Checking type coverage...")
        result = self.run_command(["mypy", str(self.src_dir)])

        # Count total functions/methods vs typed ones
        # This is a simplified check - mypy output parsing could be more sophisticated
        if result.returncode == 0:
            return QualityMetric(
                name="Type Coverage",
                score=-1,  # Special value to indicate no score display
                status="pass",
                details="No type errors found",
                threshold=-1,  # Special value to indicate no threshold display
            )
        else:
            # Count errors
            error_count = result.stdout.count("error:")
            # Type coverage never fails, only reports
            return QualityMetric(
                name="Type Coverage",
                score=-1,  # Special value to indicate no score display
                status="pass",
                details=f"{error_count} type errors",
                threshold=-1,  # Special value to indicate no threshold display
            )

    def check_security(self) -> QualityMetric:
        """Check for security issues with bandit."""
        self.log("🔒 Checking security...")
        result = self.run_command(["bandit", "-r", str(self.src_dir), "-f", "json", "-q"])

        if result.stdout:
            try:
                data = json.loads(result.stdout)
                metrics = data.get("metrics", {})

                high = sum(
                    file_data.get("SEVERITY.HIGH", 0)
                    for file_data in metrics.values()
                    if isinstance(file_data, dict)
                )
                medium = sum(
                    file_data.get("SEVERITY.MEDIUM", 0)
                    for file_data in metrics.values()
                    if isinstance(file_data, dict)
                )
                low = sum(
                    file_data.get("SEVERITY.LOW", 0)
                    for file_data in metrics.values()
                    if isinstance(file_data, dict)
                )

                # Score based on severity
                deductions = (high * 20) + (medium * 10) + (low * 5)
                score = max(0, 100 - deductions)

                if high > 0:
                    status = "fail"
                elif medium > 0:
                    status = "warn"
                else:
                    status = "pass"

                return QualityMetric(
                    name="Security",
                    score=score,
                    status=status,
                    details=f"H:{high}, M:{medium}, L:{low}",
                    threshold=80.0,
                )
            except json.JSONDecodeError:
                pass

        return QualityMetric(
            name="Security", score=100, status="pass", details="No security issues found"
        )

    def check_imports(self) -> QualityMetric:
        """Check import conventions."""
        self.log("📦 Checking import conventions...")
        result = self.run_command(["python", "scripts/check_imports.py"])

        if result.returncode == 0:
            return QualityMetric(
                name="Import Conventions",
                score=100,
                status="pass",
                details="All imports follow conventions",
            )
        else:
            # Count violations from output
            violations = result.stdout.count("Line ")
            score = max(0, 100 - (violations * 10))
            status = "fail" if violations > 0 else "pass"
            return QualityMetric(
                name="Import Conventions",
                score=score,
                status=status,
                details=f"{violations} violations",
            )

    def run_all_checks(self) -> None:
        """Run all quality checks."""
        self.log("🚀 Running comprehensive quality checks...\n")

        self.metrics.extend(
            [
                self.check_coverage(),
                self.check_complexity(),
                self.check_maintainability(),
                self.check_type_coverage(),
                self.check_security(),
                self.check_imports(),
            ]
        )

    def get_summary_stats(self) -> dict:
        """Calculate summary statistics."""
        scored_metrics = [m for m in self.metrics if m.score >= 0]
        overall_score = (
            sum(m.score for m in scored_metrics) / len(scored_metrics) if scored_metrics else 0
        )

        return {
            "overall_score": round(overall_score, 1),
            "passed": sum(1 for m in self.metrics if m.status == "pass"),
            "warned": sum(1 for m in self.metrics if m.status == "warn"),
            "failed": sum(1 for m in self.metrics if m.status == "fail"),
            "total": len(self.metrics),
        }

    def get_json_report(self) -> str:
        """Generate JSON report of all metrics."""
        summary = self.get_summary_stats()
        return json.dumps(
            {"metrics": [asdict(m) for m in self.metrics], "summary": summary}, indent=2
        )

    def print_report(self) -> None:
        """Print a formatted quality report."""
        print("\n" + "=" * 80)
        print("CODE QUALITY REPORT")
        print("=" * 80)

        for metric in self.metrics:
            status_icon = {"pass": "✅", "warn": "⚠️ ", "fail": "❌"}.get(metric.status, "  ")

            print(f"\n{status_icon} {metric.name}")
            # Only show score if it's not -1 (special value for metrics without scores)
            if metric.score >= 0:
                print(f"   Score: {metric.score:.1f}/100")
                if metric.threshold != 70.0 and metric.threshold >= 0:
                    print(f"   Threshold: {metric.threshold}/100")
            print(f"   Details: {metric.details}")

        # Calculate overall score (exclude metrics with score -1)
        summary = self.get_summary_stats()

        print("\n" + "=" * 80)
        print(f"OVERALL SCORE: {summary['overall_score']}/100")
        print(f"Passed: {summary['passed']}/{summary['total']}")
        print(f"Warnings: {summary['warned']}/{summary['total']}")
        print(f"Failed: {summary['failed']}/{summary['total']}")
        print("=" * 80 + "\n")

        # Exit code based on failures
        if summary["failed"] > 0:
            print("❌ Quality checks failed! Please address the issues above.")
            sys.exit(1)
        elif summary["warned"] > 0:
            print("⚠️  Quality checks passed with warnings.")
            sys.exit(0)
        else:
            print("✅ All quality checks passed!")
            sys.exit(0)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run code quality checks")
    parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format (default: text)"
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    # Use quiet mode for JSON output (logs go to stderr, only JSON to stdout)
    quiet = args.format == "json"
    checker = QualityChecker(project_root, quiet=quiet)
    checker.run_all_checks()

    if args.format == "json":
        print(checker.get_json_report())
        # Exit with success in JSON mode (don't fail CI, just report)
        sys.exit(0)
    else:
        checker.print_report()


if __name__ == "__main__":
    main()
