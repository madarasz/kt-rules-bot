.PHONY: help install verify quality test coverage lint format security complexity duplication dead-code imports clean all

# Default target
help:
	@echo "Kill Team Rules Bot - Code Quality Targets"
	@echo ""
	@echo "Available targets:"
	@echo "  make install        - Install all dependencies including dev tools"
	@echo "  make verify         - Verify that all quality tools are installed"
	@echo "  make quality        - Run all quality checks (recommended before commit)"
	@echo "  make test           - Run unit tests with coverage"
	@echo "  make coverage       - Generate HTML coverage report"
	@echo "  make lint           - Run linting checks (ruff + mypy + flake8)"
	@echo "  make format         - Auto-format code with ruff"
	@echo "  make security       - Run security checks (bandit + safety + pip-audit)"
	@echo "  make complexity     - Check code complexity with radon"
	@echo "  make duplication    - Check for duplicate code"
	@echo "  make dead-code      - Find unused/dead code with vulture"
	@echo "  make imports        - Validate import conventions"
	@echo "  make clean          - Remove generated files"
	@echo "  make all            - Run everything (quality + test + security)"
	@echo ""

# Install dependencies
install:
	pip install -r requirements.txt
	pre-commit install

# Verify setup
verify:
	@echo "Verifying code quality setup..."
	python scripts/verify_setup.py

# Run all quality checks (fast, for pre-commit)
quality: lint imports complexity
	@echo ""
	@echo "✅ All quality checks passed!"

# Run comprehensive checks (slower, includes security scans)
all: quality test security dead-code duplication
	@echo ""
	@echo "✅ All checks completed successfully!"

# Run tests with coverage
test:
	@echo "Running tests with coverage..."
	pytest

# Generate HTML coverage report and open it
coverage:
	@echo "Generating coverage report..."
	pytest --cov-report=html
	@echo "Opening coverage report..."
	@which open > /dev/null && open htmlcov/index.html || xdg-open htmlcov/index.html || echo "Open htmlcov/index.html in your browser"

# Linting
lint:
	@echo "Running ruff linter..."
	ruff check src tests
	@echo ""
	@echo "Running mypy type checker..."
	mypy src
	@echo ""
	@echo "Running flake8..."
	flake8 src tests --max-line-length=100 --extend-ignore=E203,W503

# Auto-format code
format:
	@echo "Formatting code with ruff..."
	ruff check --fix src tests
	ruff format src tests
	@echo "✅ Code formatted!"

# Security checks
security:
	@echo "Running bandit security scan..."
	bandit -c pyproject.toml -r src
	@echo ""
	@echo "Checking for vulnerable dependencies with safety..."
	safety check --json || true
	@echo ""
	@echo "Running pip-audit for package vulnerabilities..."
	pip-audit || true
	@echo ""
	@echo "⚠️  Review security findings above"

# Complexity analysis
complexity:
	@echo "Checking cyclomatic complexity..."
	radon cc src --min B --show-complexity
	@echo ""
	@echo "Checking maintainability index..."
	radon mi src --min B --show
	@echo ""
	@echo "Complexity summary:"
	radon cc src --average
	@echo ""
	@echo "Maintainability summary:"
	radon mi src

# Check for code duplication
duplication:
	@echo "Checking for duplicate code..."
	@echo "Note: Install jscpd globally for duplication detection:"
	@echo "  npm install -g jscpd"
	@which jscpd > /dev/null && jscpd src --min-lines 5 --min-tokens 50 || echo "⚠️  jscpd not installed, skipping duplication check"

# Find dead/unused code
dead-code:
	@echo "Scanning for dead code with vulture..."
	vulture src --min-confidence 80 || true
	@echo ""
	@echo "⚠️  Review findings above - some may be false positives"

# Validate import conventions
imports:
	@echo "Validating import conventions..."
	python scripts/check_imports.py

# Clean generated files
clean:
	@echo "Cleaning generated files..."
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✅ Cleaned!"

# Quick check before commit
pre-commit: format quality imports
	@echo ""
	@echo "✅ Ready to commit!"
