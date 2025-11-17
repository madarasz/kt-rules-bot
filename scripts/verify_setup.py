#!/usr/bin/env python3
"""
Verify that all code quality tools are installed and configured correctly.
"""

import subprocess
import sys
from pathlib import Path


def check_command(cmd: list[str], name: str) -> tuple[bool, str]:
    """
    Check if a command is available and working.

    Args:
        cmd: Command to run
        name: Display name of the tool

    Returns:
        Tuple of (success, message)
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        # Most --version commands return 0, but some return non-zero
        return True, f"✅ {name} installed"
    except FileNotFoundError:
        return False, f"❌ {name} not found"
    except subprocess.TimeoutExpired:
        return False, f"⚠️  {name} timed out"
    except Exception as e:
        return False, f"❌ {name} error: {e}"


def check_file(filepath: Path, description: str) -> tuple[bool, str]:
    """
    Check if a file exists.

    Args:
        filepath: Path to check
        description: Description of the file

    Returns:
        Tuple of (success, message)
    """
    if filepath.exists():
        return True, f"✅ {description}"
    else:
        return False, f"❌ {description} not found"


def main() -> int:
    """
    Main verification function.

    Returns:
        0 if all checks pass, 1 otherwise
    """
    print("🔍 Verifying Code Quality Setup...\n")

    project_root = Path(__file__).parent.parent
    checks: list[tuple[bool, str]] = []

    # Check Python version
    print("Python Version:")
    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        checks.append((True, f"✅ Python {version.major}.{version.minor}.{version.micro}"))
    else:
        checks.append((False, f"❌ Python {version.major}.{version.minor} (need 3.11+)"))
    print(checks[-1][1])
    print()

    # Check core tools
    print("Core Tools:")
    tools = [
        (["ruff", "--version"], "ruff"),
        (["mypy", "--version"], "mypy"),
        (["pytest", "--version"], "pytest"),
        (["coverage", "--version"], "coverage"),
    ]
    for cmd, name in tools:
        result = check_command(cmd, name)
        checks.append(result)
        print(result[1])
    print()

    # Check quality tools
    print("Quality Tools:")
    quality_tools = [
        (["bandit", "--version"], "bandit"),
        (["radon", "--version"], "radon"),
        (["vulture", "--version"], "vulture"),
        (["flake8", "--version"], "flake8"),
        (["safety", "--version"], "safety"),
        (["pip-audit", "--version"], "pip-audit"),
    ]
    for cmd, name in quality_tools:
        result = check_command(cmd, name)
        checks.append(result)
        print(result[1])
    print()

    # Check optional tools
    print("Optional Tools:")
    optional_tools = [
        (["jscpd", "--version"], "jscpd (code duplication)"),
        (["pre-commit", "--version"], "pre-commit"),
    ]
    for cmd, name in optional_tools:
        result = check_command(cmd, name)
        # Don't count optional tools as failures
        if result[0]:
            checks.append(result)
            print(result[1])
        else:
            print(f"⚠️  {name} not installed (optional)")
    print()

    # Check configuration files
    print("Configuration Files:")
    config_files = [
        (project_root / "pyproject.toml", "pyproject.toml"),
        (project_root / ".coveragerc", ".coveragerc"),
        (project_root / ".flake8", ".flake8"),
        (project_root / ".pre-commit-config.yaml", ".pre-commit-config.yaml"),
        (project_root / "Makefile", "Makefile"),
    ]
    for filepath, description in config_files:
        result = check_file(filepath, description)
        checks.append(result)
        print(result[1])
    print()

    # Check scripts
    print("Custom Scripts:")
    scripts = [
        (project_root / "scripts" / "check_imports.py", "check_imports.py"),
        (project_root / "scripts" / "quality_check.py", "quality_check.py"),
    ]
    for filepath, description in scripts:
        result = check_file(filepath, description)
        checks.append(result)
        if result[0] and filepath.stat().st_mode & 0o111:
            print(f"{result[1]} (executable)")
        elif result[0]:
            print(f"{result[1]} (not executable - run: chmod +x {filepath})")
        else:
            print(result[1])
    print()

    # Check GitHub Actions
    print("CI/CD:")
    result = check_file(
        project_root / ".github" / "workflows" / "quality.yml", "GitHub Actions workflow"
    )
    checks.append(result)
    print(result[1])
    print()

    # Check documentation
    print("Documentation:")
    docs = [
        (project_root / "docs" / "CODE_QUALITY.md", "CODE_QUALITY.md"),
        (project_root / "docs" / "QUALITY_QUICK_START.md", "QUALITY_QUICK_START.md"),
        (project_root / "docs" / "SETUP_QUALITY.md", "SETUP_QUALITY.md"),
    ]
    for filepath, description in docs:
        result = check_file(filepath, description)
        checks.append(result)
        print(result[1])
    print()

    # Summary
    print("=" * 60)
    passed = sum(1 for success, _ in checks if success)
    total = len(checks)
    percentage = (passed / total) * 100 if total > 0 else 0

    print(f"\nSetup Verification: {passed}/{total} checks passed ({percentage:.1f}%)")

    if passed == total:
        print("\n✅ All checks passed! Your setup is complete.")
        print("\nNext steps:")
        print("  1. Run 'make install' to install pre-commit hooks")
        print("  2. Run 'make all' to verify all tools work")
        print("  3. Read docs/QUALITY_QUICK_START.md")
        return 0
    else:
        print("\n⚠️  Some checks failed. Please review the errors above.")
        print("\nTo fix:")
        print("  1. Run 'pip install -r requirements.txt'")
        print("  2. Run this script again")
        print("  3. See docs/SETUP_QUALITY.md for detailed setup")
        return 1


if __name__ == "__main__":
    sys.exit(main())
