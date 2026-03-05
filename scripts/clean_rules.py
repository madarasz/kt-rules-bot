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


WEAPON_RULE_PATTERNS = (
    re.compile(r"^Accurate \d+$", re.IGNORECASE),
    re.compile(r"^Balanced$", re.IGNORECASE),
    re.compile(r'^Blast \d+["″]$', re.IGNORECASE),
    re.compile(r"^Brutal$", re.IGNORECASE),
    re.compile(r"^Ceaseless$", re.IGNORECASE),
    re.compile(r'^(?:\d+["″]\s+)?Dev(?:a|e)stating \d+$', re.IGNORECASE),
    re.compile(r"^Heavy(?: \([^\)]+\))?$", re.IGNORECASE),
    re.compile(r"^Hot$", re.IGNORECASE),
    re.compile(r"^Lethal \d+\+$", re.IGNORECASE),
    re.compile(r"^Limited \d+$", re.IGNORECASE),
    re.compile(r"^Piercing \d+$", re.IGNORECASE),
    re.compile(r"^Piercing Crits \d+$", re.IGNORECASE),
    re.compile(r"^Punishing$", re.IGNORECASE),
    re.compile(r'^Range \d+["″]$', re.IGNORECASE),
    re.compile(r"^Relentless$", re.IGNORECASE),
    re.compile(r"^Rending$", re.IGNORECASE),
    re.compile(r"^Saturate$", re.IGNORECASE),
    re.compile(r"^Seek(?: Light)?$", re.IGNORECASE),
    re.compile(r"^Severe$", re.IGNORECASE),
    re.compile(r"^Shock$", re.IGNORECASE),
    re.compile(r"^Silent$", re.IGNORECASE),
    re.compile(r"^Stun$", re.IGNORECASE),
    re.compile(r'^Torrent \d+["″]$', re.IGNORECASE),
)


@dataclass
class CleaningStats:
    """Statistics for cleaning operations."""
    apostrophes: int = 0
    bullets: int = 0
    table_lines: int = 0
    trailing_spaces: int = 0
    weapon_type_lowercased: int = 0
    weapon_keywords_bolded: int = 0
    empty_cells_normalized: int = 0
    ocr_fixes: int = 0
    within_unbolded: int = 0
    distance_bolded: int = 0

    @property
    def total(self) -> int:
        return (
            self.apostrophes + self.bullets + self.table_lines + self.trailing_spaces +
            self.weapon_type_lowercased + self.weapon_keywords_bolded +
            self.empty_cells_normalized + self.ocr_fixes +
            self.within_unbolded + self.distance_bolded
        )

    def __add__(self, other: "CleaningStats") -> "CleaningStats":
        return CleaningStats(
            apostrophes=self.apostrophes + other.apostrophes,
            bullets=self.bullets + other.bullets,
            table_lines=self.table_lines + other.table_lines,
            trailing_spaces=self.trailing_spaces + other.trailing_spaces,
            weapon_type_lowercased=self.weapon_type_lowercased + other.weapon_type_lowercased,
            weapon_keywords_bolded=self.weapon_keywords_bolded + other.weapon_keywords_bolded,
            empty_cells_normalized=self.empty_cells_normalized + other.empty_cells_normalized,
            ocr_fixes=self.ocr_fixes + other.ocr_fixes,
            within_unbolded=self.within_unbolded + other.within_unbolded,
            distance_bolded=self.distance_bolded + other.distance_bolded,
        )


def clean_apostrophes(content: str) -> tuple[str, int]:
    """Replace curly apostrophes with straight apostrophes."""
    count = content.count("’")
    return content.replace("’", "'"), count


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
                # Format each part - empty cells get single space, others get padding
                formatted_parts = []
                for p in parts:
                    if p == "":
                        formatted_parts.append(" ")  # Single space for empty cells
                    else:
                        formatted_parts.append(f" {p} ")
                new_line = "|" + "|".join(formatted_parts) + "|"

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


def normalize_weapon_type_lowercase(content: str) -> tuple[str, int]:
    """
    Normalize weapon type labels in tables.

    Convert "Ranged" and "Melee" type cells to lowercase.
    """
    ranged_count = content.count("| Ranged |")
    melee_count = content.count("| Melee |")

    content = content.replace("| Ranged |", "| ranged |")
    content = content.replace("| Melee |", "| melee |")

    return content, ranged_count + melee_count


def is_weapon_keyword(token: str) -> bool:
    """Return whether a token matches a core weapon rule keyword pattern."""
    normalized = re.sub(r"\s+", " ", token.strip())
    return any(pattern.fullmatch(normalized) for pattern in WEAPON_RULE_PATTERNS)


def bold_weapon_keywords_in_tables(content: str) -> tuple[str, int]:
    """
    Bold weapon rule keywords in weapon rule table cells.

    Example: "Range 8\", Rending" -> "**Range 8\"**, **Rending**"
    """
    lines = content.split("\n")
    result_lines = []
    count = 0

    for line in lines:
        stripped = line.strip()
        # Check if it's a table data row (starts with | and has content)
        if stripped.startswith("|") and "|" in stripped[1:] and not re.match(r"^\|[\s\-:|]+\|?$", stripped):
            # This is a data row - bold recognized weapon rules in the last cell
            parts = stripped.split("|")
            if len(parts) >= 7:  # Has weapon rules column
                last_cell = parts[-2].strip()  # Second to last (before trailing |)
                if last_cell and last_cell != "-":
                    tokens = [token.strip() for token in last_cell.split(",")]
                    new_tokens = []
                    token_changed = False

                    for token in tokens:
                        if token.startswith("**") and token.endswith("**"):
                            new_tokens.append(token)
                            continue

                        if is_weapon_keyword(token):
                            new_tokens.append(f"**{token}**")
                            count += 1
                            token_changed = True
                        else:
                            new_tokens.append(token)

                    if token_changed:
                        parts[-2] = f" {', '.join(new_tokens)} "
                        new_line = "|".join(parts)
                        result_lines.append(new_line)
                        continue
        result_lines.append(line)

    return "\n".join(result_lines), count


def normalize_empty_weapon_cells(content: str) -> tuple[str, int]:
    """
    Normalize empty weapon rule cells.

    Convert "| - |" or "| — |" to "| |" for empty weapon rules.
    """
    count = 0
    # Match table cells that only contain - or — (dash placeholder)
    pattern = r"\| - \|"
    matches = re.findall(pattern, content)
    count = len(matches)
    content = re.sub(pattern, "| |", content)

    # Also handle em-dash
    pattern2 = r"\| — \|"
    matches2 = re.findall(pattern2, content)
    count += len(matches2)
    content = re.sub(pattern2, "| |", content)

    return content, count


def fix_ocr_errors(content: str) -> tuple[str, int]:
    """
    Fix common OCR errors.

    - "OCP" (letter O) -> "0CP" (digit zero)
    """
    count = 0
    # Fix OCP -> 0CP (letter O to digit 0)
    pattern = r"\bOCP\b"
    matches = re.findall(pattern, content)
    count = len(matches)
    content = re.sub(pattern, "0CP", content)

    return content, count


def unbold_within(content: str) -> tuple[str, int]:
    """
    Remove bold from "within" - only the target should be bolded.

    "**within**" -> "within"
    "**within control range**" -> "within **control range**"
    "**within 6"**" -> "within **6"**" (but this is complex)
    """
    count = 0

    # Simple case: standalone **within**
    pattern1 = r"\*\*within\*\*"
    matches1 = re.findall(pattern1, content)
    count += len(matches1)
    content = re.sub(pattern1, "within", content)

    # Case: **within control range** -> within **control range**
    pattern2 = r"\*\*within control range\*\*"
    matches2 = re.findall(pattern2, content)
    count += len(matches2)
    content = re.sub(pattern2, "within **control range**", content)

    # Case: **within X"** where X is a number -> within **X"**
    # But be careful not to break "**within 6"** horizontally" patterns

    return content, count


def bold_distance_expressions(content: str) -> tuple[str, int]:
    """
    Bold distance expressions for within-range phrases.

    "within 6\"" -> "**within 6\"**"
    "wholly within 3\"" -> "**wholly within 3\"**"

    Do not re-bold expressions that are already bold.
    """
    whole_pattern = re.compile(r'(?<!\*)\bwholly within \d+["″](?!\*)', re.IGNORECASE)
    within_pattern = re.compile(r'(?<!\*)(?<!wholly )\bwithin \d+["″](?!\*)', re.IGNORECASE)

    content, whole_count = whole_pattern.subn(lambda match: f"**{match.group(0)}**", content)
    content, within_count = within_pattern.subn(lambda match: f"**{match.group(0)}**", content)

    return content, whole_count + within_count


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
        content, stats.weapon_type_lowercased = normalize_weapon_type_lowercase(content)
        content, stats.weapon_keywords_bolded = bold_weapon_keywords_in_tables(content)
        content, stats.empty_cells_normalized = normalize_empty_weapon_cells(content)
        content, stats.ocr_fixes = fix_ocr_errors(content)
        content, stats.within_unbolded = unbold_within(content)
        content, stats.distance_bolded = bold_distance_expressions(content)
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
            if stats.weapon_type_lowercased:
                details.append(f"{stats.weapon_type_lowercased} weapon types lowercased")
            if stats.weapon_keywords_bolded:
                details.append(f"{stats.weapon_keywords_bolded} weapon keywords bolded")
            if stats.empty_cells_normalized:
                details.append(f"{stats.empty_cells_normalized} empty cells")
            if stats.ocr_fixes:
                details.append(f"{stats.ocr_fixes} OCR fixes")
            if stats.within_unbolded:
                details.append(f"{stats.within_unbolded} within unbolded")
            if stats.distance_bolded:
                details.append(f"{stats.distance_bolded} distance bolded")
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
        print(f"  Weapon types lowercased: {stats.weapon_type_lowercased}")
        print(f"  Weapon keywords bolded: {stats.weapon_keywords_bolded}")
        print(f"  Empty cells normalized: {stats.empty_cells_normalized}")
        print(f"  OCR fixes: {stats.ocr_fixes}")
        print(f"  Within unbolded: {stats.within_unbolded}")
        print(f"  Distance bolded: {stats.distance_bolded}")
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
        print(f"  Weapon types lowercased: {grand_total_stats.weapon_type_lowercased}")
        print(f"  Weapon keywords bolded: {grand_total_stats.weapon_keywords_bolded}")
        print(f"  Empty cells normalized: {grand_total_stats.empty_cells_normalized}")
        print(f"  OCR fixes: {grand_total_stats.ocr_fixes}")
        print(f"  Within unbolded: {grand_total_stats.within_unbolded}")
        print(f"  Distance bolded: {grand_total_stats.distance_bolded}")
        print(f"  Trailing spaces: {grand_total_stats.trailing_spaces}")
    else:
        print("No changes needed - all files are clean!")


if __name__ == "__main__":
    main()
