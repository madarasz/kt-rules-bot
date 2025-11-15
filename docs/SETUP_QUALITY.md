# Setting Up Code Quality Tools

This guide walks you through setting up all code quality tools for the Kill Team Rules Bot.

## Prerequisites

- Python 3.11+
- pip
- git
- (Optional) Node.js for jscpd (code duplication detection)

## Step 1: Install Python Dependencies

```bash
# Install all dependencies including dev tools
pip install -r requirements.txt
```

This installs:
- ✅ ruff - Linter and formatter
- ✅ mypy - Type checker
- ✅ pytest + pytest-cov - Testing and coverage
- ✅ bandit - Security scanner
- ✅ radon - Complexity analyzer
- ✅ vulture - Dead code detector
- ✅ safety - Dependency vulnerability scanner
- ✅ pip-audit - Package security auditor
- ✅ flake8 + plugins - Additional linting

## Step 2: Install Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Test that hooks work
pre-commit run --all-files
```

This sets up automatic quality checks before every commit.

## Step 3: (Optional) Install jscpd for Duplication Detection

```bash
# Install via npm globally
npm install -g jscpd

# Or use npx without installing
npx jscpd src
```

## Step 4: Verify Installation

```bash
# Run all checks
make all
```

If this completes without errors, you're all set!

## Step 5: Configure Your IDE

### VS Code

Install extensions:
- **Python** (ms-python.python)
- **Ruff** (charliermarsh.ruff)
- **Mypy Type Checker** (ms-python.mypy-type-checker)

Add to `.vscode/settings.json`:
```json
{
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "python.testing.pytestEnabled": true,
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff"
  }
}
```

### PyCharm

1. Go to **Settings** → **Tools** → **External Tools**
2. Add tools for ruff, mypy, pytest
3. Enable **Tools** → **Actions on Save** → **Reformat code**

## Step 6: Set Up GitHub Integration (Optional)

### Codecov

1. Sign up at [codecov.io](https://codecov.io)
2. Add your repository
3. Copy the upload token
4. Add as GitHub secret: `CODECOV_TOKEN`

### GitHub Actions

The workflow is already configured in `.github/workflows/quality.yml`.

It will run automatically on:
- Push to master/main/develop
- Pull requests

## Daily Workflow

### Before Starting Work

```bash
# Update dependencies
pip install -r requirements.txt

# Pull latest changes
git pull
```

### While Coding

```bash
# Auto-format frequently
make format

# Run tests as you go
pytest tests/unit/test_mymodule.py -v
```

### Before Committing

```bash
# Run quality checks
make quality

# If issues found, fix them
make format  # Auto-fix formatting
# Then manually fix any remaining issues
```

### Committing

```bash
git add .
git commit -m "Your message"
# Pre-commit hooks run automatically
```

If hooks fail:
1. Review the errors
2. Fix the issues
3. Stage the fixes: `git add .`
4. Commit again

### Before Creating PR

```bash
# Run comprehensive checks
make all

# View coverage report
make coverage

# Ensure all tests pass
pytest -v
```

## Makefile Commands Reference

| Command | Description | When to Use |
|---------|-------------|-------------|
| `make help` | Show all commands | When you forget a command |
| `make install` | Install dependencies + hooks | Initial setup, after pulling |
| `make quality` | Fast quality checks | Before every commit |
| `make all` | All checks (slow) | Before creating PR |
| `make test` | Run tests with coverage | While developing |
| `make coverage` | View HTML coverage report | To find untested code |
| `make lint` | Linting only | To check style issues |
| `make format` | Auto-format code | Frequently while coding |
| `make security` | Security scans | Weekly or before release |
| `make complexity` | Complexity analysis | When refactoring |
| `make imports` | Import validation | If import errors |
| `make dead-code` | Find unused code | During cleanup |
| `make clean` | Remove generated files | When disk space low |

## Troubleshooting

### "Command not found: make"

**macOS/Linux:**
```bash
# macOS
xcode-select --install

# Ubuntu/Debian
sudo apt-get install build-essential
```

**Windows:**
```bash
# Use Git Bash, WSL, or install make for Windows
choco install make
```

### "Pre-commit hook failed"

```bash
# See what failed
pre-commit run --all-files

# Skip hooks temporarily (not recommended)
git commit --no-verify

# Update hooks
pre-commit autoupdate
```

### "Coverage below threshold"

```bash
# See which files lack coverage
make coverage  # Opens HTML report

# Run tests for specific file
pytest tests/unit/test_mymodule.py --cov=src.mymodule --cov-report=html

# Add more tests to increase coverage
```

### "MyPy type errors"

```bash
# Run mypy to see errors
mypy src

# Common fixes:
# 1. Add type hints
# 2. Install type stubs: pip install types-<package>
# 3. Add '# type: ignore' comment (last resort)
```

### "Bandit security warnings"

```bash
# See details
bandit -r src -v

# Suppress false positives
# Add comment: # nosec B603 - subprocess is safe here

# Fix real issues before committing
```

### "Import validation failed"

```bash
# See violations
python scripts/check_imports.py

# Fix by moving imports to top of file
# Remove try/except around imports
# Don't import inside functions
```

## Advanced Configuration

### Adjusting Coverage Threshold

Edit `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = [
    "--cov-fail-under=70",  # Change this number
]
```

### Excluding Files from Coverage

Edit `.coveragerc`:
```ini
[run]
omit =
    */tests/*
    */venv/*
    src/cli/admin_dashboard.py  # Add files here
```

### Adjusting Complexity Thresholds

Edit `Makefile`:
```makefile
complexity:
    radon cc src --min B  # Change B to A, C, D, etc.
```

### Custom Vulture Whitelist

Create `vulture_whitelist.py`:
```python
# Intentionally unused - part of public API
def public_api_method():
    pass
```

Run vulture:
```bash
vulture src vulture_whitelist.py
```

## CI/CD Customization

### Skip Security Checks in CI

Edit `.github/workflows/quality.yml`:
```yaml
- name: Run safety dependency check
  run: safety check --json || true
  continue-on-error: true  # Don't fail build
```

### Add Slack Notifications

Add to workflow:
```yaml
- name: Notify Slack
  if: failure()
  uses: 8398a7/action-slack@v3
  with:
    status: ${{ job.status }}
    webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

## Quality Gates

Recommended quality gates for different stages:

### Development (Local)
- ✅ Linting passes
- ✅ Type checking passes
- ✅ Import conventions followed

### Pre-commit
- ✅ All of the above
- ✅ Complexity ≤ 10
- ✅ No critical security issues

### Pull Request
- ✅ All of the above
- ✅ Coverage ≥ 70%
- ✅ All tests pass
- ✅ No high/medium security issues

### Release
- ✅ All of the above
- ✅ Coverage ≥ 80%
- ✅ Maintainability Index ≥ 60
- ✅ Zero security vulnerabilities
- ✅ No dead code

## Next Steps

1. ✅ Read [CODE_QUALITY.md](CODE_QUALITY.md) for detailed tool documentation
2. ✅ Review [QUALITY_QUICK_START.md](QUALITY_QUICK_START.md) for quick reference
3. ✅ Run `make all` to establish baseline metrics
4. ✅ Set up your IDE integration
5. ✅ Enable GitHub Actions
6. ✅ Start writing quality code!

---

**Need help?** Check the [troubleshooting section](#troubleshooting) or create an issue.
