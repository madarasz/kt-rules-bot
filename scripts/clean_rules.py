#!/usr/bin/env python3
"""
Clean rules files by normalizing formatting.

This script processes:
- All .md files in the extracted-rules directory

Transformations:
- Replace curly apostrophes (') with straight apostrophes (')
- Normalize bullet points to `-` with 4-space indentation per nesting level
- Clean table formatting (single space padding, `---` separators)
- Trim trailing whitespace from lines
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CleaningStats:
    """Statistics for cleaning operations."""
    apostrophes: int = 0
    bullets: int = 0
    table_lines: int = 0
    trailing_spaces: int = 0

    @property
    def total(self) -> int:
        return self.apostrophes + self.bullets + self.table_lines + self.trailing_spaces

    def __add__(self, other: "CleaningStats") -> "CleaningStats":
        return CleaningStats(
            apostrophes=self.apostrophes + other.apostrophes,
            bullets=self.bullets + other.bullets,
            table_lines=self.table_lines + other.table_lines,
            trailing_spaces=self.trailing_spaces + other.trailing_spaces,
        )


def clean_apostrophes(content: str) -> tuple[str, int]:
    """Replace curly apostrophes with straight apostrophes."""
    count = content.count("'")
    return content.replace("'", "'"), count


def clean_bullet_points(content: str) -> tuple[str, int]:
    """
    Normalize bullet points to `-` with 4-space indentation per nesting level.

    Detects nesting by leading whitespace, not by bullet character type.
    """
    # Common bullet characters used by LLMs (excluding * and - which need special handling)
    special_bullets = r"[•○◦▪▸►‣⁃↘]"

    # Pattern for special bullet chars: optional whitespace + bullet + optional space + content
    special_bullet_pattern = re.compile(rf"^(\s*)({special_bullets})\s*(.*)")

    # Pattern for * or - bullets: must be followed by space to avoid matching --- or **bold**
    # Also avoid matching - in table cells or at start of YAML front matter
    standard_bullet_pattern = re.compile(r"^(\s*)([\*\-])\s+(.+)")

    count = 0
    lines = content.split("\n")
    result_lines = []

    for line in lines:
        # Skip YAML front matter delimiters and horizontal rules
        stripped = line.strip()
        if stripped == "---" or stripped == "***" or re.match(r"^-{3,}$", stripped):
            result_lines.append(line)
            continue

        # Skip table rows
        if stripped.startswith("|"):
            result_lines.append(line)
            continue

        # Try special bullet characters first
        match = special_bullet_pattern.match(line)
        if match:
            leading_spaces = len(match.group(1))
            bullet_content = match.group(3)

            # Determine nesting level based on leading whitespace
            if leading_spaces <= 1:
                nesting_level = 0
            else:
                nesting_level = (leading_spaces + 2) // 4

            indent = "    " * nesting_level
            new_line = f"{indent}- {bullet_content}"

            if new_line != line:
                count += 1
            result_lines.append(new_line)
            continue

        # Try standard bullet pattern (* or - followed by space)
        match = standard_bullet_pattern.match(line)
        if match:
            leading_spaces = len(match.group(1))
            bullet_content = match.group(3)

            # Determine nesting level
            if leading_spaces <= 1:
                nesting_level = 0
            else:
                nesting_level = (leading_spaces + 2) // 4

            indent = "    " * nesting_level
            new_line = f"{indent}- {bullet_content}"

            if new_line != line:
                count += 1
            result_lines.append(new_line)
            continue

        result_lines.append(line)

    return "\n".join(result_lines), count


def clean_table_formatting(content: str) -> tuple[str, int]:
    """
    Clean markdown table formatting.

    - Cells have single space before and after content
    - Separator rows use `---` between pipes
    """
    lines = content.split("\n")
    result_lines = []
    count = 0

    for line in lines:
        # Check if line looks like a table row (starts with | and contains |)
        stripped = line.strip()
        if stripped.startswith("|") and "|" in stripped[1:]:
            # Check if it's a separator row (contains only |, -, :, and spaces)
            if re.match(r"^\|[\s\-:|\s]+\|?\s*$", stripped):
                # Count the number of columns by counting | characters
                num_pipes = stripped.count("|")
                # Generate clean separator
                new_line = "|" + "---|" * (num_pipes - 1)
                if stripped.endswith("|"):
                    pass  # Already has trailing pipe
                else:
                    new_line = new_line.rstrip("|")
            else:
                # Data row - clean cell padding
                parts = [p.strip() for p in stripped.split("|")]
                # Remove empty first/last if line starts/ends with |
                if parts and parts[0] == "":
                    parts = parts[1:]
                if parts and parts[-1] == "":
                    parts = parts[:-1]
                new_line = "| " + " | ".join(parts) + " |"

            if new_line != stripped:
                count += 1
            result_lines.append(new_line)
        else:
            result_lines.append(line)

    return "\n".join(result_lines), count


def trim_trailing_whitespace(content: str) -> tuple[str, int]:
    """Remove trailing whitespace from each line."""
    lines = content.split("\n")
    count = 0
    result_lines = []

    for line in lines:
        stripped = line.rstrip()
        if stripped != line:
            count += 1
        result_lines.append(stripped)

    return "\n".join(result_lines), count


def clean_file(file_path: Path) -> tuple[bool, CleaningStats]:
    """
    Apply all cleaning transformations to a file.

    Args:
        file_path: Path to the file

    Returns:
        Tuple of (was_modified, cleaning_stats)
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        stats = CleaningStats()

        # Apply transformations in order
        content, stats.apostrophes = clean_apostrophes(content)
        content, stats.bullets = clean_bullet_points(content)
        content, stats.table_lines = clean_table_formatting(content)
        content, stats.trailing_spaces = trim_trailing_whitespace(content)

        if stats.total > 0:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True, stats

        return False, stats

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False, CleaningStats()


def process_directory(
    directory: Path, pattern: str, project_root: Path
) -> tuple[int, int, CleaningStats]:
    """
    Process all files matching pattern in directory.

    Returns:
        Tuple of (total_files, modified_files, total_stats)
    """
    if not directory.exists():
        return 0, 0, CleaningStats()

    files = list(directory.rglob(pattern))
    if not files:
        return 0, 0, CleaningStats()

    modified_count = 0
    total_stats = CleaningStats()

    for file_path in files:
        was_modified, stats = clean_file(file_path)
        total_stats = total_stats + stats

        if was_modified:
            relative_path = file_path.relative_to(project_root)
            details = []
            if stats.apostrophes:
                details.append(f"{stats.apostrophes} apostrophes")
            if stats.bullets:
                details.append(f"{stats.bullets} bullets")
            if stats.table_lines:
                details.append(f"{stats.table_lines} table lines")
            if stats.trailing_spaces:
                details.append(f"{stats.trailing_spaces} trailing spaces")
            print(f"  {relative_path}: {', '.join(details)}")
            modified_count += 1

    return len(files), modified_count, total_stats


def process_single_file(file_path: Path) -> None:
    """Process a single file and print results."""
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return

    if not file_path.is_file():
        print(f"Error: Not a file: {file_path}")
        return

    print(f"Processing: {file_path}")
    was_modified, stats = clean_file(file_path)

    if was_modified:
        print(f"  Apostrophes replaced: {stats.apostrophes}")
        print(f"  Bullets normalized: {stats.bullets}")
        print(f"  Table lines cleaned: {stats.table_lines}")
        print(f"  Trailing spaces trimmed: {stats.trailing_spaces}")
        print(f"  Total changes: {stats.total}")
    else:
        print("  No changes needed - file is clean!")


def main():
    """Main function to process markdown and YAML files."""
    parser = argparse.ArgumentParser(
        description="Clean rules files by normalizing formatting."
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        help="Optional: single file to process. If not provided, processes all rule files.",
    )
    args = parser.parse_args()

    # Get the project root (parent of scripts directory)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Single file mode
    if args.file:
        file_path = args.file
        if not file_path.is_absolute():
            file_path = project_root / file_path
        process_single_file(file_path)
        return

    # Batch mode - process all target directories
    targets = [
        (project_root / "extracted-rules", "*.md", "Rules files"),
    ]

    grand_total_files = 0
    grand_total_modified = 0
    grand_total_stats = CleaningStats()

    for directory, pattern, description in targets:
        if not directory.exists():
            continue

        print(f"\n{description} ({directory.relative_to(project_root)})")
        print("-" * 60)

        total_files, modified_files, stats = process_directory(
            directory, pattern, project_root
        )

        if total_files > 0:
            print(f"  Found {total_files} {pattern} files")
            grand_total_files += total_files
            grand_total_modified += modified_files
            grand_total_stats = grand_total_stats + stats
        else:
            print(f"  No {pattern} files found")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Processed {grand_total_files} files total")
    print(f"Modified {grand_total_modified} files")
    if grand_total_stats.total > 0:
        print(f"  Apostrophes: {grand_total_stats.apostrophes}")
        print(f"  Bullets: {grand_total_stats.bullets}")
        print(f"  Table lines: {grand_total_stats.table_lines}")
        print(f"  Trailing spaces: {grand_total_stats.trailing_spaces}")
    else:
        print("No changes needed - all files are clean!")


if __name__ == "__main__":
    main()
