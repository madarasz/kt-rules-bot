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
- Team rules only: consistent bold of game terms, plain keyword lines, bulleted action
  bodies, bracketed AP costs, no footnote markers, no team name in ability headers
"""

import argparse
import re
from dataclasses import dataclass, fields
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


# Weapon rules as they appear in rule text (outside weapon tables), from
# extracted-rules/weapon-rules.md. "Heavy" is deliberately absent: it collides with
# weapon names ("Heavy bolter") and is handled by the terrain rule instead.
WEAPON_RULE_TEXT_PATTERN = re.compile(
    r"(?<!\*)\b("
    r"Accurate \d+|Balanced|Blast \d+[\"\u2033]|Brutal|Ceaseless|"
    # Devastating can carry a leading distance ("2\" Devastating 3"), and rule text
    # sometimes writes the placeholder x instead of a number
    r"(?:\d+|x)[\"\u2033] Devastating (?:\d+|x)|Devastating (?:\d+|x)|Hot|"
    r"Lethal \d\+|Limited \d+|Piercing Crits \d+|Piercing \d+|Punishing|Range \d+[\"\u2033]|"
    r"Relentless|Rending|Saturate|Seek Light|Seek|Severe|Shock|Silent|Stun|"
    r"Torrent \d+[\"\u2033]"
    r")(?![\w\*-])"
)

# Game terms that extraction bolds only inconsistently, as (pattern, replacement) pairs
# applied in order. Terms already bolded are skipped by the `(?<!\*)`/`(?!\*)` guards.
RULE_TEXT_BOLD_RULES = (
    # "counteracted" is deliberately absent - it is never bolded in the rules text
    (re.compile(r"(?<!\*)\b(counteract|counteracting|counteraction)\b(?!\*)"), r"**\1**"),
    (re.compile(r"(?<!\*)\b(incapacitated)\b(?!\*)"), r"**\1**"),
    # "shoot"/"fight" only as the action verb before "against"
    (
        re.compile(
            r"(?<!\*)\b(shoot|fight)\b(?!\*)"
            r"(?= against| or (?:\*\*)?(?:shoot|fight)(?:\*\*)? against)"
        ),
        r"**\1**",
    ),
    (re.compile(r"(?<!\*)\b(Light|Heavy)\b(?!\*)(?= terrain)"), r"**\1**"),
    (re.compile(r"(?<!\*)\b(Vantage|Accessible|Exposed|Ceiling|Insignificant)\b(?!\*)"), r"**\1**"),
    # Both halves of the pair are bolded, however the text arrived
    (
        re.compile(
            r"(?<!\*)(?:\*\*)?\bactivation\b(?:\*\*)?/(?:\*\*)?\bcounteraction\b(?:\*\*)?(?!\*)"
        ),
        "**activation**/**counteraction**",
    ),
    # Outside that pair, "activation" is never bolded
    (re.compile(r"\*\*activation\*\*(?!/\*\*counteraction\*\*)"), "activation"),
)


# Game terms of team rules text, as (pattern, replacement) pairs applied in order to
# body lines only (never headers, tables or keyword lines)
TEAM_TEXT_BOLD_RULES = (
    (re.compile(r"(?<!\*)\b(control range)\b(?!\*)"), r"**\1**"),
    (re.compile(r"(?<!\*)\b(incapacitates|incapacitate)\b(?!\*)"), r"**\1**"),
    # "in cover" bolds only the game term: "**in cover**" -> "in **cover**"
    (re.compile(r"\*\*in cover\*\*"), "in **cover**"),
    # "cover" is bolded, except in the phrase "cover save" which stays plain
    (re.compile(r"\*\*cover\*\* (saves?)\b"), r"cover \1"),
    (re.compile(r"(?<!\*)\b(cover)\b(?!\*)(?! saves?\b)"), r"**\1**"),
)

# A weapon rule name as rule text references it: "Piercing", "Lethal 5+", "Range x",
# "Piercing Crits 1", "Seek Light", "Anti-PSYKER", "Repress"
_WEAPON_RULE_NAME = r"[A-Z][\w'-]*(?: (?:Crits|Light))?(?: (?:\d+\+?\"?|x))?"
# The names in a "the X, Y or Z weapon rule(s)" list, plain or already bold
BARE_WEAPON_RULE_PATTERN = re.compile(
    r"(?<![\w*])(?!(?:The|This|That|Each|Any|All|Its|Their|Other|Same)\b)"
    rf"({_WEAPON_RULE_NAME})(?![\w*+\"])"
    rf"(?=(?:(?:, | or | and )(?:\*\*)?{_WEAPON_RULE_NAME}(?:\*\*)?)* weapon rules?\b)"
)

# Keywords that open a rule sentence and carry the period inside the bold:
# "**SUPPORT.** Select..." (never "**SUPPORT**. Select...")
PERIOD_KEYWORDS = ("SUPPORT", "PSYCHIC", "STRATEGIC GAMBIT")


# Faction rule names that several kill teams share, so the header needs the team name
# to stay unique (e.g. "## ANGELS OF DEATH - ASTARTES - Faction Rule")
SHARED_FACTION_RULES = ("ASTARTES",)


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
    stray_asterisks: int = 0
    heading_case_fixes: int = 0
    keywords_bolded: int = 0
    ploy_references_bolded: int = 0
    weapon_rules_in_text: int = 0
    designer_notes: int = 0
    faction_rules_prefixed: int = 0
    footnote_markers: int = 0
    team_prefixes_removed: int = 0
    team_terms_bolded: int = 0
    keywords_lines_unbolded: int = 0
    keyword_periods: int = 0
    action_bullets: int = 0
    header_blank_lines: int = 0
    ap_costs_bracketed: int = 0

    @property
    def total(self) -> int:
        return sum(getattr(self, field.name) for field in fields(self))

    def __add__(self, other: "CleaningStats") -> "CleaningStats":
        return CleaningStats(
            **{field.name: getattr(self, field.name) + getattr(other, field.name) for field in fields(self)}
        )

    def nonzero(self) -> list[tuple[str, int]]:
        """Return (label, count) for each transformation that changed something."""
        return [
            (field.name.replace("_", " "), getattr(self, field.name))
            for field in fields(self)
            if getattr(self, field.name)
        ]


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
    "wholly within your drop zone" -> "**wholly within** your drop zone"

    Do not re-bold expressions that are already bold.
    """
    # "**wholly within** 5\"" -> "**wholly within 5\"**" (pull the distance inside the bold)
    content, pulled_count = re.subn(
        r'\*\*wholly within\*\* (\d+["″])', r'**wholly within \1**', content
    )

    whole_pattern = re.compile(r'(?<!\*)\bwholly within \d+["″](?!\*)', re.IGNORECASE)
    within_pattern = re.compile(r'(?<!\*)(?<!wholly )\bwithin \d+["″](?!\*)', re.IGNORECASE)

    content, whole_count = whole_pattern.subn(lambda match: f"**{match.group(0)}**", content)
    content, within_count = within_pattern.subn(lambda match: f"**{match.group(0)}**", content)

    # Bare "wholly within" (no distance) is an always-bold game term
    content, bare_count = re.subn(
        r'(?<!\*)\bwholly within\b(?!\*)(?! \d)', "**wholly within**", content
    )

    return content, whole_count + within_count + pulled_count + bare_count


def strip_stray_leading_asterisk(content: str) -> tuple[str, int]:
    """
    Remove a leftover footnote marker at the start of a line.

    Weapon rule footnotes in the PDF read `*Poison: ...`; the extraction sometimes
    keeps the leading `*`, which markdown then renders as an unclosed emphasis.
    Only strip it on the first line of an `###` section (so footnote markers inside
    operative selection lists survive) and only when the line has an odd number of
    single asterisks (so genuine `*italic*` and `**bold**` text is left alone).
    """
    lines = content.split("\n")
    count = 0
    result_lines = []
    prev_nonempty = ""

    for line in lines:
        if (
            prev_nonempty.startswith("### ")
            and line.startswith("*")
            and not line.startswith("**")
            and not line.startswith("* ")
        ):
            singles = len(re.findall(r"(?<!\*)\*(?!\*)", line))
            if singles % 2 == 1:
                line = line[1:]
                count += 1
        if line.strip():
            prev_nonempty = line
        result_lines.append(line)

    return "\n".join(result_lines), count


def normalize_heading_case(content: str) -> tuple[str, int]:
    """
    Uppercase the name part of a heading that is already mostly uppercase.

    Extraction occasionally title-cases part of a name, e.g.
    "### RAVENERS KILL Team - Archetypes" -> "### RAVENERS KILL TEAM - Archetypes".
    Only the text before the first " - " is touched, and only when it is already
    predominantly uppercase, so headings like "## BURROW - Faction Rule" and
    mixed-case ability names are left alone.
    """
    lines = content.split("\n")
    count = 0
    result_lines = []

    for line in lines:
        match = re.match(r"^(#{2,3} )(.+?)( - .*)$", line)
        if match and "[FAQ]" not in line:
            name = match.group(2)
            letters = [c for c in name if c.isalpha()]
            uppercase_ratio = sum(c.isupper() for c in letters) / len(letters) if letters else 0
            if letters and uppercase_ratio >= 0.7 and name != name.upper():
                line = f"{match.group(1)}{name.upper()}{match.group(3)}"
                count += 1
        result_lines.append(line)

    return "\n".join(result_lines), count


def bold_rule_text_keywords(content: str) -> tuple[str, int]:
    """
    Bold game terms in rule text that extraction bolds only inconsistently.

    See `RULE_TEXT_BOLD_RULES` for the terms; the rules are applied in order, so the
    "activation/counteraction" pair is normalised after its halves are bolded, and the
    standalone "activation" is unbolded last.
    """
    count = 0

    for pattern, replacement in RULE_TEXT_BOLD_RULES:
        def substitute(match: re.Match, replacement: str = replacement) -> str:
            nonlocal count
            replaced = match.expand(replacement)
            if replaced != match.group(0):
                count += 1
            return replaced

        content = pattern.sub(substitute, content)

    return content, count


def format_designer_notes(content: str) -> tuple[str, int]:
    """
    Put designer notes in the standard blockquote format.

    "Designer's Note: text" -> "> **Designer's Note:** text"
    """
    pattern = re.compile(
        r"^(?!> )\**(Designer's (?:Note|Commentary)):?\**:?\s*", re.MULTILINE
    )
    return pattern.subn(r"> **\1:** ", content)


def prefix_shared_faction_rules(content: str) -> tuple[str, int]:
    """
    Add the team name to faction rule headers whose name several kill teams share.

    "## ASTARTES - Faction Rule" -> "## ANGELS OF DEATH - ASTARTES - Faction Rule",
    using the team name from the `section` front matter field.
    """
    section = re.search(r"^section: (.+)$", content, re.MULTILINE)
    if not section:
        return content, 0

    team = section.group(1).strip().replace("_", " ").upper()
    count = 0
    for rule in SHARED_FACTION_RULES:
        content, changed = re.subn(
            rf"^## {rule} - Faction Rule$",
            f"## {team} - {rule} - Faction Rule",
            content,
            flags=re.MULTILINE,
        )
        count += changed

    return content, count


def bold_ploy_references(content: str) -> tuple[str, int]:
    """
    Bold references to this document's own ploys in rule text.

    "the Combat Doctrine strategy ploy" -> "the **Combat Doctrine** strategy ploy".
    Only names that have a ploy header in this file are bolded, and designer notes
    (blockquote lines) are left as they are.
    """
    names = re.findall(r"^## (.+?) - (?:Strategy|Firefight) Ploy$", content, re.MULTILINE)
    if not names:
        return content, 0

    count = 0
    lines = content.split("\n")
    for index, line in enumerate(lines):
        if line.startswith(">") or line.startswith("## "):
            continue
        for name in names:
            # Match however the text capitalises the name ("Wrath of Vengeance"), and
            # keep that capitalisation
            pattern = re.compile(
                rf"(?<!\*)\b({re.escape(name)})\b(?!\*)(?= (?:strategy|firefight) ploy)",
                re.IGNORECASE,
            )
            line, changed = pattern.subn(r"**\1**", line)
            count += changed
        lines[index] = line

    return "\n".join(lines), count


def bold_weapon_rules_in_text(content: str) -> tuple[str, int]:
    """
    Bold weapon rule names where they are referenced in rule text.

    Weapon tables keep their own formatting (see `bold_weapon_keywords_in_tables`), and
    headings are left alone. Only team rules files are touched - the core rules explain
    the weapon rules themselves and write their names plain.
    """
    if "document_type: team-rules" not in content:
        return content, 0

    count = 0
    lines = content.split("\n")
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") or stripped.startswith("#") or stripped.startswith("**Keywords:**"):
            continue
        lines[index], changed = WEAPON_RULE_TEXT_PATTERN.subn(r"**\1**", line)
        count += changed

    return "\n".join(lines), count


def is_team_rules(content: str) -> bool:
    """Return whether the content is a team rules file."""
    return "document_type: team-rules" in content


def is_body_line(line: str) -> bool:
    """Return whether a line is rule text (not a header, table, keyword or front matter line)."""
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith(("#", "|", "**Keywords:**", "---")) and not re.match(
        r"^[a-z_]+: ", stripped
    )


def unbold_keywords_line(content: str) -> tuple[str, int]:
    """
    Write the operative keywords line plain.

    "**Keywords:** **BLOODED, CHAOS, THUG**" -> "**Keywords:** BLOODED, CHAOS, THUG"
    """
    if not is_team_rules(content):
        return content, 0

    def substitute(match: re.Match) -> str:
        return f"**Keywords:** {match.group(1).replace('**', '')}"

    return re.subn(r"^\*\*Keywords:\*\* (.*\*\*.*)$", substitute, content, flags=re.MULTILINE)


def fix_keyword_period(content: str) -> tuple[str, int]:
    """
    Put the period inside the bold of rule-opening keywords.

    "**SUPPORT**. Select" -> "**SUPPORT.** Select"
    """
    names = "|".join(PERIOD_KEYWORDS)
    return re.subn(rf"\*\*({names})\*\*\.", r"**\1.**", content)


def bold_team_text_terms(content: str) -> tuple[str, int]:
    """
    Bold game terms in team rules text, see `TEAM_TEXT_BOLD_RULES`.

    Also bolds weapon rule names that rule text references by name only
    ("the Piercing weapon rule" -> "the **Piercing** weapon rule").
    """
    if not is_team_rules(content):
        return content, 0

    count = 0
    lines = content.split("\n")
    for index, line in enumerate(lines):
        if not is_body_line(line):
            continue
        for pattern, replacement in TEAM_TEXT_BOLD_RULES:
            line, changed = pattern.subn(replacement, line)
            count += changed
        line, changed = BARE_WEAPON_RULE_PATTERN.subn(r"**\1**", line)
        count += changed
        lines[index] = line

    return "\n".join(lines), count


def bullet_action_bodies(content: str) -> tuple[str, int]:
    """
    Write every effect and restriction of a unique action as a bullet.

    Applies to the body of `### ... [xAP]` sections. A plain line becomes a top-level
    `- ` bullet. When a plain line that ends in ":" becomes a bullet, the top-level
    bullets that follow it are its sub-items, so they are indented one level.
    """
    if not is_team_rules(content):
        return content, 0

    count = 0
    lines = content.split("\n")
    in_action = False
    nest_items = False
    for index, line in enumerate(lines):
        if line.startswith("#"):
            in_action = bool(re.match(r"^### .*\[\d+AP\]\s*$", line))
            nest_items = False
            continue
        if not in_action or not line.strip():
            continue
        if line.startswith("- "):
            if nest_items:
                lines[index] = f"    {line}"
                count += 1
            continue
        nest_items = False
        if line.startswith((" ", "|", ">", "**Keywords:**")):
            continue
        lines[index] = f"- {line}"
        count += 1
        nest_items = line.rstrip().endswith(":")

    return "\n".join(lines), count


def bracket_ap_cost(content: str) -> tuple[str, int]:
    """Put the AP cost of an action header in brackets: "### X - SPOT 1AP" -> "### X - SPOT [1AP]"."""
    return re.subn(r"^(### .+ )(\d+AP)\s*$", r"\1[\2]", content, flags=re.MULTILINE)


def strip_footnote_markers(content: str) -> tuple[str, int]:
    """
    Remove footnote `*` markers from weapon table cells and `###` header names.

    "| ... | **Shock**, Repress* |" -> "| ... | **Shock**, Repress |"
    "### TRAITOR FLENSER - *Stalk" -> "### TRAITOR FLENSER - Stalk"
    """
    count = 0
    lines = content.split("\n")
    for index, line in enumerate(lines):
        if line.startswith("|") and not re.match(r"^\|[\s\-:|]+\|?$", line):
            line, changed = re.subn(r"(?<=[\w\"+)])\*(?=\s*(?:,|\|))", "", line)
            count += changed
        elif line.startswith("### "):
            line, changed = re.subn(r" - \*(?=\w)(?!.*\*$)", " - ", line)
            count += changed
        lines[index] = line

    return "\n".join(lines), count


def strip_team_prefix_in_h3(content: str) -> tuple[str, int]:
    """
    Remove the kill team name from operative ability headers.

    "### BROOD BROTHERS - MAGUS - Spiritual Leader" -> "### MAGUS - Spiritual Leader".
    Only headers with two more " - " parts after the team name are touched, so
    "### BROOD BROTHERS - Archetypes" stays as it is.
    """
    section = re.search(r"^section: (.+)$", content, re.MULTILINE)
    if not section or not is_team_rules(content):
        return content, 0

    team = section.group(1).strip().replace("_", " ").upper()
    return re.subn(
        rf"^### {re.escape(team)} - (.+ - .+)$", r"### \1", content, flags=re.MULTILINE
    )


def ensure_blank_line_before_headers(content: str) -> tuple[str, int]:
    """Insert a blank line before a `##`/`###` header that directly follows text."""
    return re.subn(r"(?<=\S)\n(#{2,3} )", r"\n\n\1", content)


def find_malformed_tables(content: str) -> list[str]:
    """Return a warning for each table whose rows have a different column count."""
    warnings = []
    table: list[str] = []
    for line in content.split("\n") + [""]:
        if line.startswith("|"):
            table.append(line)
            continue
        if table:
            widths = {row.count("|") for row in table}
            if len(widths) > 1:
                warnings.append(f"table starting '{table[0][:50]}' has rows of {sorted(widths)} pipes")
            table = []
    return warnings


def clean_content(content: str) -> tuple[str, CleaningStats]:
    """Apply all cleaning transformations to file content."""
    stats = CleaningStats()

    # Apply transformations in order
    content, stats.apostrophes = clean_apostrophes(content)
    content, stats.bullets = clean_bullet_points(content)
    content, stats.table_lines = clean_table_formatting(content)
    content, stats.weapon_type_lowercased = normalize_weapon_type_lowercase(content)
    content, stats.footnote_markers = strip_footnote_markers(content)
    content, stats.weapon_keywords_bolded = bold_weapon_keywords_in_tables(content)
    content, stats.empty_cells_normalized = normalize_empty_weapon_cells(content)
    content, stats.ocr_fixes = fix_ocr_errors(content)
    content, stats.within_unbolded = unbold_within(content)
    content, stats.distance_bolded = bold_distance_expressions(content)
    content, stats.stray_asterisks = strip_stray_leading_asterisk(content)
    content, stats.heading_case_fixes = normalize_heading_case(content)
    content, stats.team_prefixes_removed = strip_team_prefix_in_h3(content)
    content, stats.ap_costs_bracketed = bracket_ap_cost(content)
    content, stats.keywords_bolded = bold_rule_text_keywords(content)
    content, stats.team_terms_bolded = bold_team_text_terms(content)
    content, stats.ploy_references_bolded = bold_ploy_references(content)
    content, stats.weapon_rules_in_text = bold_weapon_rules_in_text(content)
    content, stats.keywords_lines_unbolded = unbold_keywords_line(content)
    content, stats.keyword_periods = fix_keyword_period(content)
    content, stats.action_bullets = bullet_action_bodies(content)
    content, stats.designer_notes = format_designer_notes(content)
    content, stats.faction_rules_prefixed = prefix_shared_faction_rules(content)
    content, stats.header_blank_lines = ensure_blank_line_before_headers(content)
    content, stats.trailing_spaces = trim_trailing_whitespace(content)

    return content, stats


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

        content, stats = clean_content(content)

        for warning in find_malformed_tables(content):
            print(f"  WARNING {file_path.name}: {warning}")

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
            details = [f"{count} {label}" for label, count in stats.nonzero()]
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
        for label, count in stats.nonzero():
            print(f"  {label}: {count}")
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
        for label, count in grand_total_stats.nonzero():
            print(f"  {label}: {count}")
    else:
        print("No changes needed - all files are clean!")


if __name__ == "__main__":
    main()
