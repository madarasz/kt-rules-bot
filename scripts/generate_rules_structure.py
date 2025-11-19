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

from src.lib.constants import RULES_STRUCTURE_PATH, TEAMS_STRUCTURE_PATH

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


def extract_headers(file_path: Path) -> list[str]:
    """Extract all level 2 (##) headers from a markdown file, excluding specified headers."""
    headers = []
    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                if match := re.match(r"^##\s+(.+)$", line.strip()):
                    header = re.sub(r"\*+", "", match.group(1)).strip()
                    # Skip excluded headers
                    if header.upper() not in EXCLUDE_HEADERS:
                        # Apply trimming to remove unwanted prefixes
                        header = trim_leaf_text(header)
                        headers.append(header)
    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")

    return headers


def categorize_tacops(headers: list[str]) -> dict[str, list[str]]:
    """Categorize tactical ops by archetype (RECON, INFILTRATION, etc.)."""
    categories = {"RECON": [], "INFILTRATION": [], "SECURITY": [], "SEEK & DESTROY": []}

    for header in headers:
        if " - TAC OP - " in header.upper():
            tacop_name, _, archetype = header.partition(" - TAC OP - ")
            archetype = archetype.strip().upper()
            if archetype in categories:
                categories[archetype].append(clean_header(tacop_name.strip()))

    return {k: v for k, v in categories.items() if v}


def categorize_team(
    headers: list[str], team_name: str, exclude: list[str] = None
) -> dict[str, Any]:
    """Categorize team headers into faction rules, operatives, ploys, equipment."""
    exclude = exclude or []
    normalized_team = team_name.upper().replace("_", " ")

    categories = {
        "Operative Selection": [],
        "Faction Rules": [],
        "Operatives": [],
        "Strategy Ploys": [],
        "Firefight Ploys": [],
        "Faction Equipment": [],
    }

    for header in headers:
        upper = header.upper()

        # Skip FAQ items
        if upper.startswith(("FAQ", "[FAQ]")):
            continue

        # Categorize based on keywords
        if "OPERATIVE SELECTION" in upper:
            categories["Operative Selection"].append("Operative Selection")
        elif "FACTION RULE" in upper or upper.endswith("- ARCHETYPES"):
            categories["Faction Rules"].append(clean_header(header))
        elif "STRATEGY PLOY" in upper:
            categories["Strategy Ploys"].append(clean_header(header))
        elif "FIREFIGHT PLOY" in upper:
            categories["Firefight Ploys"].append(clean_header(header))
        elif "FACTION EQUIPMENT" in upper:
            categories["Faction Equipment"].append(clean_header(header))
        elif is_operative_header(header, upper, normalized_team):
            operative_name = remove_team_prefix(header, normalized_team)
            categories["Operatives"].append(operative_name)

    # Return only non-empty, non-excluded categories
    return {k: v for k, v in categories.items() if v and k not in exclude}


def is_operative_header(header: str, upper: str, team: str) -> bool:
    """Check if header represents an operative."""
    if " - " not in header:
        return False

    # Must not contain exclusion keywords
    exclusions = ["FACTION RULE", "PLOY", "EQUIPMENT", "SELECTION", "ARCHETYPE"]
    return not any(ex in upper for ex in exclusions)


def remove_team_prefix(header: str, team: str) -> str:
    """Remove 'TEAM_NAME - ' prefix from operative name."""
    pattern = re.compile(r"^" + re.escape(team) + r"\s*-\s*", re.IGNORECASE)
    return pattern.sub("", header)


def process_file(
    file_path: Path, is_team: bool = False, is_tacops: bool = False, exclude: list[str] = None
) -> Any:
    """Process a markdown file and return its structure."""
    headers = extract_headers(file_path)

    if is_team:
        return categorize_team(headers, file_path.stem, exclude)
    elif is_tacops:
        return categorize_tacops(headers)
    else:
        return headers


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
                # Top-level markdown files
                rules[format_key(item.stem)] = extract_headers(item)

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
