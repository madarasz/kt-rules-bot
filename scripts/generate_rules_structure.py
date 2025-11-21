#!/usr/bin/env python3
"""
Generate rules-structure.yml and teams-structure.yml from extracted-rules directory.

This script scans the extracted-rules directory and creates hierarchical YAML structures:
- rules-structure.yml: Core rules, ops, killzones, equipment
- teams-structure.yml: Team faction rules and operatives only

Usage:
    python scripts/generate_rules_structure.py
"""

import re
import sys
from pathlib import Path
from typing import Any

import yaml

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lib.constants import RULES_STRUCTURE_PATH, TEAMS_STRUCTURE_PATH, MARKDOWN_CHUNK_HEADER_LEVEL

# Configuration
EXTRACTED_RULES_DIR = Path(__file__).parent.parent / "extracted-rules"
RULES_OUTPUT_FILE = Path(__file__).parent.parent / RULES_STRUCTURE_PATH
TEAMS_OUTPUT_FILE = Path(__file__).parent.parent / TEAMS_STRUCTURE_PATH
# TEAMS_EXCLUDE_CATEGORIES = ['Operative Selection', 'Strategy Ploys', 'Firefight Ploys', 'Faction Equipment']
TEAMS_EXCLUDE_CATEGORIES = ["Operative Selection"]
EXCLUDE_HEADERS = ["WEAPON RULES"]
TRIM_HEADER_TEXT = [
    "BHETA-DECIMA - ",
    "GALLOWDARK - ",
    "GALLOWDARK CLOSE QUARTERS RULES - ",
    "TOMB WORLD - ",
    "VOLKUS - ",
    "UNIVERSAL EQUIPMENT - ",
]

def trim_leaf_text(text: str) -> str:
    """Remove unwanted prefixes from leaf text (list items).

    Args:
        text: Original text (e.g., "UNIVERSAL EQUIPMENT - 1X AMMO CACHE")

    Returns:
        Trimmed text (e.g., "1X AMMO CACHE")
    """
    for prefix in TRIM_HEADER_TEXT:
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def clean_header(header: str) -> str:
    """Remove markdown formatting and unwanted suffixes from headers."""
    # Remove markdown bold markers
    cleaned = re.sub(r"\*+", "", header)

    # Remove category suffixes
    for suffix in [
        " - Faction Rule",
        " - Strategy Ploy",
        " - Firefight Ploy",
        " - Faction Equipment",
    ]:
        if cleaned.endswith(suffix):
            return cleaned[: -len(suffix)].strip()

    return cleaned.strip()


def extract_headers(file_path: Path, max_level: int = None) -> list[dict[str, Any]]:
    """Extract headers up to max_level and build hierarchical structure.

    Args:
        file_path: Path to markdown file
        max_level: Maximum header level to extract (2 = ##, 3 = ###, etc.)
                  If None, uses MARKDOWN_CHUNK_HEADER_LEVEL

    Returns:
        List of header dicts with 'title' and 'children' keys
    """
    if max_level is None:
        max_level = MARKDOWN_CHUNK_HEADER_LEVEL

    headers = []
    stack = []  # Stack to track parent headers at each level

    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                # Match headers from ## to ######
                match = re.match(r"^(#{2,6})\s+(.+)$", line.strip())
                if not match:
                    continue

                level = len(match.group(1))  # Count # symbols
                title = re.sub(r"\*+", "", match.group(2)).strip()  # Remove markdown bold

                # Skip if beyond max level or in exclude list
                if level > max_level or title.upper() in EXCLUDE_HEADERS:
                    continue

                # Apply trimming to remove unwanted prefixes
                title = trim_leaf_text(title)

                # Create header node
                node = {"title": title, "children": []}

                # Build hierarchy
                if level == 2:
                    # Top-level header (##)
                    headers.append(node)
                    stack = [node]
                else:
                    # Child header (###, ####, etc.)
                    # Trim stack to parent level (for level 3, parent is at index 0)
                    parent_index = level - 3
                    stack = stack[:parent_index + 1]

                    if stack:
                        # Add to parent's children
                        stack[-1]["children"].append(node)
                        stack.append(node)
                    else:
                        # Orphaned header (e.g., ### without ##), treat as top-level
                        headers.append(node)
                        stack = [node]

    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")

    return headers


def categorize_tacops(headers: list[dict[str, Any]]) -> dict[str, Any]:
    """Categorize tactical ops by archetype (RECON, INFILTRATION, etc.).

    Args:
        headers: List of header dicts with 'title' and 'children' keys

    Returns:
        Dict of archetypes with hierarchical tac op structures
    """
    categories: dict[str, list[Any]] = {"RECON": [], "INFILTRATION": [], "SECURITY": [], "SEEK & DESTROY": []}

    def process_node(node: dict[str, Any]) -> None:
        """Recursively process nodes to find and categorize tac ops."""
        title = node["title"]
        categorized = False

        if " - TAC OP - " in title.upper():
            tacop_name, _, archetype = title.partition(" - TAC OP - ")
            archetype = archetype.strip().upper()
            if archetype in categories:
                # Create tac op node with cleaned name and any children
                tacop_node = {
                    "title": clean_header(tacop_name.strip()),
                    "children": node["children"]
                }
                categories[archetype].append(tacop_node)
                categorized = True

        # Only process children recursively if this node wasn't categorized
        if not categorized:
            for child in node.get("children", []):
                process_node(child)

    # Process all top-level headers
    for header in headers:
        process_node(header)

    # Filter out empty categories and return
    return {k: v for k, v in categories.items() if v}


def categorize_team(
    headers: list[dict[str, Any]], team_name: str, exclude: list[str] = None
) -> dict[str, Any]:
    """Categorize team headers into faction rules, operatives, ploys, equipment.

    Args:
        headers: List of header dicts with 'title' and 'children' keys
        team_name: Name of the team
        exclude: Categories to exclude from output

    Returns:
        Dict of categories with hierarchical item structures
    """
    exclude = exclude or []
    normalized_team = team_name.upper().replace("_", " ")

    categories: dict[str, list[Any]] = {
        "Operative Selection": [],
        "Faction Rules": [],
        "Operatives": [],
        "Strategy Ploys": [],
        "Firefight Ploys": [],
        "Faction Equipment": [],
    }

    def process_node(node: dict[str, Any]) -> None:
        """Recursively process nodes to categorize team items."""
        title = node["title"]
        upper = title.upper()

        # Skip FAQ items
        if upper.startswith(("FAQ", "[FAQ]")):
            return

        # Track if this node was categorized
        categorized = False

        # Categorize based on keywords
        if "OPERATIVE SELECTION" in upper:
            categories["Operative Selection"].append({
                "title": "Operative Selection",
                "children": node["children"]
            })
            categorized = True
        elif "FACTION RULE" in upper or upper.endswith("- ARCHETYPES"):
            categories["Faction Rules"].append({
                "title": clean_header(title),
                "children": node["children"]
            })
            categorized = True
        elif "STRATEGY PLOY" in upper:
            categories["Strategy Ploys"].append({
                "title": clean_header(title),
                "children": node["children"]
            })
            categorized = True
        elif "FIREFIGHT PLOY" in upper:
            categories["Firefight Ploys"].append({
                "title": clean_header(title),
                "children": node["children"]
            })
            categorized = True
        elif "FACTION EQUIPMENT" in upper:
            categories["Faction Equipment"].append({
                "title": clean_header(title),
                "children": node["children"]
            })
            categorized = True
        elif is_operative_header(title, upper, normalized_team):
            operative_name = remove_team_prefix(title, normalized_team)
            categories["Operatives"].append({
                "title": operative_name,
                "children": node["children"]
            })
            categorized = True

        # Only process children recursively if this node wasn't categorized
        # (children of categorized nodes are already included in the node's structure)
        if not categorized:
            for child in node.get("children", []):
                process_node(child)

    # Process all top-level headers
    for header in headers:
        process_node(header)

    # Return only non-empty, non-excluded categories
    return {k: v for k, v in categories.items() if v and k not in exclude}


def nodes_to_yaml_format(nodes: list[dict[str, Any]], parent_title: str = None) -> list[Any]:
    """Convert hierarchical node structure to YAML-friendly format.

    Args:
        nodes: List of dicts with 'title' and 'children' keys
        parent_title: Optional parent title to strip from children (e.g., "SPACE MARINE CAPTAIN")

    Returns:
        List suitable for YAML output (strings for leaf nodes, dicts for parents)
    """
    result = []
    for node in nodes:
        title = node["title"]

        # Remove redundant parent prefix if present
        if parent_title:
            # Pattern 1: Simple prefix "PARENT - Child" -> "Child"
            simple_prefix = f"{parent_title} - "
            if title.startswith(simple_prefix):
                title = title[len(simple_prefix):]
            else:
                # Pattern 2: Nested prefix "TEAM - PARENT - Child" -> "Child"
                # Look for " - PARENT - " anywhere in the string
                nested_pattern = f" - {parent_title} - "
                if nested_pattern in title:
                    # Remove everything up to and including the pattern
                    _, _, suffix = title.partition(nested_pattern)
                    title = suffix

        if not node.get("children"):
            # Leaf node: just add the title string
            result.append(title)
        else:
            # Parent node: create dict with title as key and children as value
            # Pass the original (unprefixed) title as parent for recursive calls
            result.append({
                title: nodes_to_yaml_format(node["children"], parent_title=node["title"])
            })
    return result


def is_operative_header(header: str, upper: str, team: str) -> bool:
    """Check if header represents an operative."""
    if " - " not in header:
        return False

    # Must not contain exclusion keywords
    exclusions = ["FACTION RULE", "PLOY", "EQUIPMENT", "SELECTION", "ARCHETYPE"]
    return not any(ex in upper for ex in exclusions)


def normalize_for_matching(text: str) -> str:
    """Normalize text for matching by converting hyphens and underscores to spaces.

    This allows matching "VOID-DANCER TROUPE" against "VOID_DANCER_TROUPE" or "VOID DANCER TROUPE".

    Args:
        text: Text to normalize (e.g., "VOID-DANCER TROUPE" or "void_dancer_troupe")

    Returns:
        Normalized text with hyphens and underscores replaced by spaces
    """
    return text.replace("-", " ").replace("_", " ")


def normalize_plural(text: str) -> str:
    """Normalize plural/singular variations for flexible matching.

    Handles common plural patterns (case-insensitive):
    - "Ratlings" -> "Ratling"
    - "Brood Brothers" -> "Brood Brother"
    - "Sanctifiers" -> "Sanctifier"
    - "Operatives" -> "Operative"

    Args:
        text: Text to normalize (e.g., "BROOD BROTHERS" or "Ratlings")

    Returns:
        Text with plural suffixes removed from the last word
    """
    text = text.strip()
    if not text:
        return text

    words = text.split()
    if not words:
        return text

    # Normalize the last word for plural (case-insensitive matching)
    last_word = words[-1]
    last_word_lower = last_word.lower()

    # Handle common plural patterns (case-insensitive)
    if last_word_lower.endswith("ies") and len(last_word) > 3:
        # "Operatives" -> "Operative", "OPERATIVES" -> "OPERATIVE"
        # Preserve original casing for the "y"
        is_upper = last_word[-3:].isupper()
        words[-1] = last_word[:-3] + ("Y" if is_upper else "y")
    elif last_word_lower.endswith("es") and len(last_word) > 2:
        # Check if it's likely a plural (not "axes" -> "ax")
        # Common patterns: "ches" -> "ch", "shes" -> "sh", "ses" -> "s", "xes" -> "x"
        if last_word_lower.endswith(("ches", "shes", "sses", "xes", "zes")):
            words[-1] = last_word[:-2]
        else:
            # Try removing just "s" first (e.g., "Marines" -> "Marine")
            words[-1] = last_word[:-1] if last_word_lower.endswith("s") else last_word
    elif last_word_lower.endswith("s") and len(last_word) > 1:
        # Simple plural: "Brothers" -> "Brother", "RATLINGS" -> "RATLING"
        words[-1] = last_word[:-1]

    return " ".join(words)


def remove_team_prefix(header: str, team: str) -> str:
    """Remove 'TEAM_NAME - ' prefix from operative name.

    Uses flexible matching that treats:
    - Hyphens, underscores, and spaces as equivalent
    - Plural/singular variations as equivalent (e.g., "Brood Brothers" matches "Brood Brother")

    This handles cases like:
    - Filename: 'void_dancer_troupe' vs header: 'VOID-DANCER TROUPE - LEAD PLAYER'
    - Filename: 'brood_brothers' vs header: 'BROOD BROTHER - COMMANDER'
    - Filename: 'ratlings' vs header: 'RATLING - SNIPER'
    """
    # Look for " - " separator (with spaces) to split team name from operative name
    # We need to find the rightmost " - " that could be the separator
    separator = " - "
    if separator not in header:
        return header

    # Find the last occurrence of " - " separator
    separator_index = header.rfind(separator)
    potential_team_prefix = header[:separator_index]
    suffix = header[separator_index + len(separator):]

    # Normalize both team names for comparison (spaces/hyphens/underscores)
    normalized_team = normalize_for_matching(team).strip().upper()
    normalized_prefix = normalize_for_matching(potential_team_prefix).strip().upper()

    # Also normalize for plurals
    normalized_team_singular = normalize_plural(normalized_team)
    normalized_prefix_singular = normalize_plural(normalized_prefix)

    # If they match (exact or singular form), return just the suffix
    if (normalized_team == normalized_prefix or
        normalized_team_singular == normalized_prefix_singular):
        return suffix

    return header


def process_file(
    file_path: Path, is_team: bool = False, is_tacops: bool = False, exclude: list[str] = None
) -> Any:
    """Process a markdown file and return its structure in YAML-friendly format."""
    headers = extract_headers(file_path)

    if is_team:
        # Categorize team headers, then convert each category to YAML format
        categorized = categorize_team(headers, file_path.stem, exclude)
        return {k: nodes_to_yaml_format(v) for k, v in categorized.items()}
    elif is_tacops:
        # Categorize tacops, then convert each category to YAML format
        categorized = categorize_tacops(headers)
        return {k: nodes_to_yaml_format(v) for k, v in categorized.items()}
    else:
        # Regular file: convert headers to YAML format
        return nodes_to_yaml_format(headers)


def has_markdown_files(dir_path: Path) -> bool:
    """Check if directory contains any .md files recursively."""
    try:
        return any(
            item.suffix == ".md" if item.is_file() else has_markdown_files(item)
            for item in dir_path.iterdir()
        )
    except Exception:
        return False


def should_skip_file(item: Path) -> bool:
    """Check if file should be skipped during processing."""
    return (
        item.name.startswith(".")
        or item.name in ["rules-structure.yml", "teams-structure.yml"]
        or "faq" in item.stem.lower()
    )


def format_key(name: str) -> str:
    """Format filename/dirname as a readable key."""
    return name.replace("_", " ").replace("-", " ").title()


def process_directory(
    dir_path: Path, is_team_dir: bool = False, exclude: list[str] = None
) -> dict[str, Any]:
    """Process directory recursively and return structure."""
    result = {}

    try:
        items = sorted(dir_path.iterdir(), key=lambda x: (x.is_file(), x.name))

        for item in items:
            if should_skip_file(item):
                continue

            if item.is_file() and item.suffix == ".md":
                structure = process_file(
                    item,
                    is_team=is_team_dir,
                    is_tacops=(item.stem.lower() == "tacops"),
                    exclude=exclude,
                )
                result[format_key(item.stem)] = structure

            elif item.is_dir() and has_markdown_files(item):
                subdir = process_directory(item, is_team_dir=(item.name == "team"), exclude=exclude)
                if subdir:
                    result[format_key(item.name)] = subdir

    except Exception as e:
        print(f"Warning: Could not process directory {dir_path}: {e}")

    return result


def generate_structures() -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate both rules and teams structures."""
    print(f"Scanning directory: {EXTRACTED_RULES_DIR}")

    rules = {}
    teams = {}

    try:
        items = sorted(EXTRACTED_RULES_DIR.iterdir(), key=lambda x: (x.is_file(), x.name))

        for item in items:
            if should_skip_file(item):
                continue

            if item.is_file() and item.suffix == ".md":
                # Top-level markdown files: extract headers and convert to YAML format
                headers = extract_headers(item)
                rules[format_key(item.stem)] = nodes_to_yaml_format(headers)

            elif item.is_dir() and has_markdown_files(item):
                if item.name == "team":
                    # Process teams separately with exclusions
                    teams = process_directory(
                        item, is_team_dir=True, exclude=TEAMS_EXCLUDE_CATEGORIES
                    )
                else:
                    # Process other directories for rules
                    structure = process_directory(item)
                    if structure:
                        rules[format_key(item.name)] = structure

    except Exception as e:
        print(f"Error: Could not access {EXTRACTED_RULES_DIR}: {e}")
        return {}, {}

    return rules, teams


def write_yaml(structure: dict[str, Any], output_path: Path) -> None:
    """Write structure to YAML file."""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(
                structure,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
                indent=2,
            )
        print(f"✓ Successfully wrote structure to {output_path}")
    except Exception as e:
        print(f"Error: Could not write to {output_path}: {e}")
        raise


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("Generating Kill Team Rules Structure")
    print("=" * 60)

    if not EXTRACTED_RULES_DIR.exists():
        print(f"Error: Directory not found: {EXTRACTED_RULES_DIR}")
        return 1

    rules, teams = generate_structures()

    if not rules and not teams:
        print("Error: No structure generated")
        return 1

    if rules:
        write_yaml(rules, RULES_OUTPUT_FILE)
        print(f"  Rules sections: {len(rules)}")

    if teams:
        write_yaml(teams, TEAMS_OUTPUT_FILE)
        print(f"  Teams: {len(teams)}")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    exit(main())
