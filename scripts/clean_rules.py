#!/usr/bin/env python3
"""
Clean rules files by replacing curly apostrophes with straight apostrophes.

This script processes:
- All .md files in the extracted-rules directory
- All .yaml files in tests/quality/test_cases/
- All .yaml files in tests/rag/test_cases/

Replaces all ' (U+2019, right single quotation mark) characters with
' (ASCII apostrophe).
"""

import os
from pathlib import Path
from typing import Tuple, List


def clean_file(file_path: Path) -> Tuple[bool, int]:
    """
    Replace curly apostrophes with straight apostrophes in a file.

    Args:
        file_path: Path to the markdown file

    Returns:
        Tuple of (was_modified, replacement_count)
    """
    try:
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Replace curly apostrophes with straight apostrophes
        modified_content = content.replace("’", "'")

        # Check if any changes were made
        replacement_count = content.count("’")

        if replacement_count > 0:
            # Write back to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            return True, replacement_count

        return False, 0

    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")
        return False, 0


def process_directory(directory: Path, pattern: str, project_root: Path) -> Tuple[int, int, int]:
    """
    Process all files matching pattern in directory.

    Args:
        directory: Directory to search
        pattern: File pattern (e.g., "*.md", "*.yaml")
        project_root: Project root for relative paths

    Returns:
        Tuple of (total_files, modified_files, total_replacements)
    """
    if not directory.exists():
        return 0, 0, 0

    # Find all matching files
    files = list(directory.rglob(pattern))

    if not files:
        return 0, 0, 0

    # Process each file
    modified_count = 0
    replacement_count = 0

    for file_path in files:
        was_modified, count = clean_file(file_path)

        if was_modified:
            relative_path = file_path.relative_to(project_root)
            print(f"✏️  {relative_path}: {count} replacements")
            modified_count += 1
            replacement_count += count

    return len(files), modified_count, replacement_count


def main():
    """Main function to process all markdown and YAML files."""
    # Get the project root (parent of scripts directory)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Define directories and patterns to process
    targets = [
        (project_root / "extracted-rules", "*.md", "Rules files"),
        (project_root / "tests" / "quality" / "test_cases", "*.yaml", "Quality test cases"),
        (project_root / "tests" / "rag" / "test_cases", "*.yaml", "RAG test cases"),
    ]

    # Track overall statistics
    grand_total_files = 0
    grand_total_modified = 0
    grand_total_replacements = 0

    # Process each target
    for directory, pattern, description in targets:
        if not directory.exists():
            continue

        print(f"\n📂 {description} ({directory.relative_to(project_root)})")
        print("─" * 60)

        total_files, modified_files, replacements = process_directory(
            directory, pattern, project_root
        )

        if total_files > 0:
            print(f"   Found {total_files} {pattern} files")
            grand_total_files += total_files
            grand_total_modified += modified_files
            grand_total_replacements += replacements
        else:
            print(f"   No {pattern} files found")

    # Summary
    print(f"\n{'='*60}")
    print(f"✅ Processed {grand_total_files} files total")
    print(f"✏️  Modified {grand_total_modified} files")
    print(f"🔄 Total replacements: {grand_total_replacements}")

    if grand_total_modified == 0:
        print("✨ No curly apostrophes found - all files are clean!")


if __name__ == "__main__":
    main()
