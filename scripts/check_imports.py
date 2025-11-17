#!/usr/bin/env python3
"""
Custom import validation script.

Checks for anti-patterns:
1. Imports inside try/except blocks (fallback imports)
2. Imports inside functions/methods (non-top-level imports)

Only top-level imports are allowed.
"""

import ast
import sys
from pathlib import Path


class ImportChecker(ast.NodeVisitor):
    """AST visitor that checks for import anti-patterns."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.errors: list[tuple[int, str]] = []
        self.in_try_block = False
        self.in_function = False
        self.current_scope_level = 0

    def visit_Try(self, node: ast.Try) -> None:
        """Track when we're inside a try block."""
        old_in_try = self.in_try_block
        self.in_try_block = True
        self.generic_visit(node)
        self.in_try_block = old_in_try

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track when we're inside a function."""
        old_in_function = self.in_function
        self.in_function = True
        self.generic_visit(node)
        self.in_function = old_in_function

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track when we're inside an async function."""
        old_in_function = self.in_function
        self.in_function = True
        self.generic_visit(node)
        self.in_function = old_in_function

    def visit_Import(self, node: ast.Import) -> None:
        """Check regular imports."""
        if self.in_try_block:
            modules = ", ".join(alias.name for alias in node.names)
            self.errors.append(
                (node.lineno, f"Import in try/except block: {modules}")
            )
        if self.in_function:
            modules = ", ".join(alias.name for alias in node.names)
            self.errors.append(
                (node.lineno, f"Import inside function/method: {modules}")
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check 'from X import Y' imports."""
        if self.in_try_block:
            module = node.module or ""
            items = ", ".join(alias.name for alias in node.names)
            self.errors.append(
                (node.lineno, f"Import in try/except block: from {module} import {items}")
            )
        if self.in_function:
            module = node.module or ""
            items = ", ".join(alias.name for alias in node.names)
            self.errors.append(
                (node.lineno, f"Import inside function/method: from {module} import {items}")
            )
        self.generic_visit(node)


def check_file(filepath: Path) -> list[tuple[int, str]]:
    """
    Check a single Python file for import anti-patterns.

    Args:
        filepath: Path to the Python file to check

    Returns:
        List of (line_number, error_message) tuples
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except SyntaxError as e:
        return [(e.lineno or 0, f"Syntax error: {e.msg}")]

    checker = ImportChecker(str(filepath))
    checker.visit(tree)
    return checker.errors


def main() -> int:
    """
    Main entry point.

    Returns:
        0 if no errors found, 1 otherwise
    """
    # Find all Python files in src/
    src_dir = Path(__file__).parent.parent / "src"
    if not src_dir.exists():
        print(f"Error: {src_dir} does not exist", file=sys.stderr)
        return 1

    python_files = list(src_dir.rglob("*.py"))
    if not python_files:
        print(f"Warning: No Python files found in {src_dir}", file=sys.stderr)
        return 0

    total_errors = 0
    for filepath in sorted(python_files):
        errors = check_file(filepath)
        if errors:
            print(f"\n{filepath}:")
            for line_no, message in sorted(errors):
                print(f"  Line {line_no}: {message}")
                total_errors += 1

    if total_errors > 0:
        print(f"\n❌ Found {total_errors} import anti-pattern(s)")
        print("\nImport conventions:")
        print("  ✅ All imports must be at the top level (module scope)")
        print("  ❌ No imports inside try/except blocks (no fallback imports)")
        print("  ❌ No imports inside functions or methods")
        return 1
    else:
        print("✅ All imports follow conventions (top-level only)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
