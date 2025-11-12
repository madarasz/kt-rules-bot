# Code Quality Guide

This document describes the code quality tools, metrics, and standards for the Kill Team Rules Bot project.

## Quick Start

```bash
# Install dependencies (including dev tools)
make install

# Run all quality checks before committing
make quality

# Run comprehensive checks (includes security, coverage, etc.)
make all

# View coverage report in browser
make coverage
```

## Table of Contents

- [Quality Tools](#quality-tools)
- [Quality Metrics](#quality-metrics)
- [Running Checks](#running-checks)
- [CI/CD Integration](#cicd-integration)
- [Code Standards](#code-standards)
- [Troubleshooting](#troubleshooting)

## Quality Tools

### Linting & Formatting

#### Ruff
Modern Python linter and formatter (replaces flake8, isort, pyupgrade).

```bash
# Check for issues
ruff check src tests

# Auto-fix issues
ruff check --fix src tests

# Format code
ruff format src tests
```

**Configuration:** `pyproject.toml` → `[tool.ruff]`

#### Flake8
Additional linting with plugins for bug-prone patterns.

```bash
flake8 src tests --max-line-length=100
```

**Plugins:**
- `flake8-bugbear`: Catches common bugs
- `flake8-simplify`: Suggests code simplifications
- `flake8-import-conventions`: Enforces import patterns

### Type Checking

#### MyPy
Static type checker with strict mode enabled.

```bash
mypy src
```

**Configuration:** `pyproject.toml` → `[tool.mypy]`

**Standard:** All functions must have type hints.

### Testing & Coverage

#### Pytest + Coverage
Unit testing with branch coverage tracking.

```bash
# Run tests with coverage
pytest

# Generate HTML report
pytest --cov-report=html
open htmlcov/index.html
```

**Configuration:** `pyproject.toml` → `[tool.pytest.ini_options]`, `.coveragerc`

**Targets:**
- Minimum coverage: **70%**
- Goal: **80%+**
- Branch coverage: **Enabled**

### Security

#### Bandit
Security issue scanner for Python code.

```bash
bandit -r src -c pyproject.toml
```

**Configuration:** `pyproject.toml` → `[tool.bandit]`

**Checks:** SQL injection, hardcoded passwords, insecure functions, etc.

#### Safety
Dependency vulnerability scanner.

```bash
safety check
```

Checks installed packages against the safety database of known security vulnerabilities.

#### Pip-audit
Python package security auditor.

```bash
pip-audit
```

Scans dependencies for known CVEs.

### Code Complexity

#### Radon
Code complexity and maintainability analyzer.

```bash
# Cyclomatic complexity
radon cc src --min B --show-complexity

# Maintainability index
radon mi src --min B --show
```

**Targets:**
- Cyclomatic complexity: **≤ 10 per function** (grade A-B)
- Maintainability index: **≥ 60** (grade A-B)

**Complexity Grades:**
- **A**: 1-5 (simple)
- **B**: 6-10 (moderate)
- **C**: 11-20 (complex)
- **D**: 21-50 (very complex)
- **F**: 51+ (unmaintainable)

### Dead Code Detection

#### Vulture
Finds unused code.

```bash
vulture src --min-confidence=80
```

**Note:** May produce false positives. Review carefully.

### Import Conventions

#### Custom Check Script
Validates project-specific import rules.

```bash
python scripts/check_imports.py
```

**Enforced Rules:**
- ✅ All imports must be at the top level (module scope)
- ❌ No imports inside `try/except` blocks (no fallback imports)
- ❌ No imports inside functions or methods

**Why:** Consistent imports improve:
- Code readability
- Dependency tracking
- Static analysis accuracy
- IDE auto-completion

## Quality Metrics

### Current Targets

| Metric | Target | Current |
|--------|--------|---------|
| Test Coverage | ≥ 70% | TBD |
| Type Coverage | 100% (strict mypy) | TBD |
| Cyclomatic Complexity | ≤ 10 avg | TBD |
| Maintainability Index | ≥ 60 avg | TBD |
| Security Issues (High) | 0 | TBD |
| Import Violations | 0 | TBD |

### Scoring System

The `scripts/quality_check.py` script generates an overall quality score (0-100) based on:

- **Test Coverage** (0-100%): % of code covered by tests
- **Code Complexity** (0-100): Inverse score based on cyclomatic complexity
- **Maintainability Index** (0-100): Direct MI score from radon
- **Type Coverage** (0-100): Based on mypy errors
- **Security** (0-100): Deductions for vulnerabilities (High: -20, Medium: -10, Low: -5)
- **Import Conventions** (0-100): Deductions per violation (-10 each)

**Overall Score:** Average of all metrics

**Status:**
- ✅ **Pass**: Score ≥ 80
- ⚠️  **Warning**: Score 60-79
- ❌ **Fail**: Score < 60

## Running Checks

### Local Development

```bash
# Before every commit
make quality              # Fast checks (lint, imports, complexity)
make pre-commit          # Format + quality + imports

# Periodically
make all                 # Everything (quality + tests + security)
make coverage            # View detailed coverage report

# Individual checks
make lint                # Linting only
make test                # Tests with coverage
make security            # Security scans
make complexity          # Complexity analysis
make imports             # Import validation
make dead-code           # Find unused code
```

### Pre-commit Hooks

Automatically run checks before each commit:

```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files

# Update hook versions
pre-commit autoupdate
```

**Hooks run on commit:**
1. Ruff linter (auto-fix)
2. Ruff formatter
3. MyPy type checker
4. Bandit security scanner
5. Flake8 linter
6. Vulture dead code detector
7. Custom import validator

### Quality Report

Generate a comprehensive quality report:

```bash
python scripts/quality_check.py
```

**Output:**
```
CODE QUALITY REPORT
================================================================================

✅ Test Coverage
   Score: 85.0/100
   Details: 1234/1450 lines covered

✅ Code Complexity
   Score: 90.0/100
   Details: Avg: 5.2, Max: 12

⚠️  Maintainability Index
   Score: 65.0/100
   Details: Avg: 65.3, Min: 52.1

...

OVERALL SCORE: 78.5/100
Passed: 4/6
Warnings: 2/6
Failed: 0/6
```

## CI/CD Integration

### GitHub Actions

The `.github/workflows/quality.yml` workflow runs on:
- Push to `master`, `main`, `develop`
- Pull requests
- Manual trigger

**Jobs:**
1. **Lint**: Ruff + MyPy + Flake8
2. **Test**: Pytest with coverage (uploads to Codecov)
3. **Security**: Bandit + Safety + Pip-audit
4. **Complexity**: Radon complexity + MI
5. **Imports**: Custom import validator
6. **Dead Code**: Vulture scan
7. **Quality Report**: Aggregate report + PR comment

**Coverage Integration:**
- Reports uploaded to Codecov
- Coverage badge available for README
- PR comments with coverage delta

### Status Badges

Add to README.md:

```markdown
![Quality](https://github.com/USERNAME/REPO/workflows/Code%20Quality/badge.svg)
![Coverage](https://codecov.io/gh/USERNAME/REPO/branch/master/graph/badge.svg)
```

## Code Standards

### Import Conventions

**✅ Good:**
```python
# All imports at top of file
import os
import sys
from typing import Optional

from anthropic import Anthropic
from discord.ext import commands

# Rest of code...
```

**❌ Bad:**
```python
def my_function():
    import os  # Import inside function
    ...

try:
    import optional_lib  # Fallback import
except ImportError:
    import alternative_lib
```

### Type Hints

**✅ Good:**
```python
def process_query(query: str, max_results: int = 10) -> List[str]:
    """Process a query and return results."""
    results: List[str] = []
    # ...
    return results
```

**❌ Bad:**
```python
def process_query(query, max_results=10):  # No type hints
    results = []
    return results
```

### Complexity Guidelines

**If function complexity > 10:**
1. Break into smaller functions
2. Extract conditionals into functions
3. Use early returns to reduce nesting
4. Consider refactoring to strategy pattern

**✅ Good:**
```python
def validate_input(data: dict) -> bool:
    """Simple validation with early returns."""
    if not data:
        return False
    if "required_field" not in data:
        return False
    return True
```

**❌ Bad:**
```python
def validate_input(data):
    """Complex nested validation."""
    if data:
        if "required_field" in data:
            if data["required_field"]:
                if isinstance(data["required_field"], str):
                    if len(data["required_field"]) > 0:
                        return True
    return False
```

### Security Best Practices

1. **Never hardcode secrets**
   - Use environment variables
   - Use `.env` files (gitignored)

2. **Validate user input**
   - Sanitize Discord messages
   - Validate API responses

3. **Use parameterized queries**
   - No string concatenation for SQL
   - Use ORM or prepared statements

4. **Keep dependencies updated**
   - Run `pip-audit` regularly
   - Monitor Dependabot alerts

## Troubleshooting

### Common Issues

#### "Module has no attribute" from mypy
- Ensure all dependencies are in `requirements.txt`
- Add type stubs if available: `pip install types-<package>`
- Add `# type: ignore` comment if stubs unavailable

#### Vulture false positives
- Add to exclusion list in `pyproject.toml`
- Use `# noqa: vulture` comment
- Create `whitelist.py` for intentionally unused code

#### Coverage not meeting threshold
- Add unit tests for uncovered code
- Check `htmlcov/index.html` for details
- Exclude non-critical code in `.coveragerc`

#### Bandit false positives
- Review and suppress with `# nosec` comment
- Add justification: `# nosec B603 - subprocess is safe here`

#### Import validator errors
- Move imports to top of file
- Remove try/except around imports
- Use optional dependencies via importlib

### Getting Help

- Check tool documentation:
  - [Ruff](https://docs.astral.sh/ruff/)
  - [MyPy](https://mypy.readthedocs.io/)
  - [Pytest](https://docs.pytest.org/)
  - [Bandit](https://bandit.readthedocs.io/)
  - [Radon](https://radon.readthedocs.io/)

- Project-specific questions: Create an issue in the repository

## Continuous Improvement

### Monthly Tasks

- [ ] Run `make all` and review report
- [ ] Update dependencies: `pip list --outdated`
- [ ] Run `pip-audit` and address vulnerabilities
- [ ] Review Codecov trends
- [ ] Update quality thresholds if improving

### Before Major Releases

- [ ] 100% test coverage on critical paths
- [ ] Zero high/medium security issues
- [ ] All complexity scores grade A-B
- [ ] Documentation updated
- [ ] CHANGELOG updated

---

**Last Updated:** 2025-11-12
**Maintainers:** See CLAUDE.md
