#!/usr/bin/env python3
"""
Validate all markdown documents in extracted-rules directory.
Usage: python3 scripts/validate_documents.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.rag.validator import DocumentValidator


def main():
    validator = DocumentValidator()
    rules_dir = project_root / "extracted-rules"

    if not rules_dir.exists():
        print(f"❌ Directory not found: {rules_dir}")
        sys.exit(1)

    # Find all markdown files
    md_files = list(rules_dir.glob("**/*.md"))

    if not md_files:
        print(f"❌ No markdown files found in {rules_dir}")
        sys.exit(1)

    print(f"Found {len(md_files)} markdown files\n")

    valid_count = 0
    invalid_count = 0

    for md_file in sorted(md_files):
        relative_path = md_file.relative_to(project_root)
        content = md_file.read_text(encoding="utf-8")

        is_valid, error, metadata = validator.validate_content(content, str(relative_path))

        if is_valid:
            print(f"✅ {relative_path}")
            valid_count += 1
        else:
            print(f"❌ {relative_path}")
            print(f"   - {error}")
            invalid_count += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {valid_count} valid, {invalid_count} invalid")
    print(f"{'=' * 60}")

    sys.exit(0 if invalid_count == 0 else 1)


if __name__ == "__main__":
    main()
