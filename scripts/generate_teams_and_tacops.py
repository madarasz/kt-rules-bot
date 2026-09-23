#!/usr/bin/env python3
"""Generate docs/teams-and-tacops.md.

Builds a reference document listing:
  - # Teams      : every team name (from extracted-rules/teams-structure.yml)
  - # TacOps     : two-level list of TacOp category -> TacOp names
  - # CritOps    : CritOp names

Sources are the extracted-rules markdown/yaml files. Run from anywhere:

    python scripts/generate_teams_and_tacops.py
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = REPO_ROOT / "extracted-rules"
TEAMS_YAML = RULES_DIR / "teams-structure.yml"
TEAM_DIR = RULES_DIR / "team"
TACOPS_MD = RULES_DIR / "approved-ops-2025" / "tacops.md"
CRITOPS_MD = RULES_DIR / "approved-ops-2025" / "critops.md"
OUTPUT = REPO_ROOT / "docs" / "teams-and-tacops.md"

# "## FLANK - TAC OP - RECON" -> name="FLANK", category="RECON"
TACOP_HEADING = re.compile(r"^##\s+(.+?)\s+-\s+TAC OP\s+-\s+(.+?)\s*$")
# "## **CRIT OP 1: SECURE**" -> name="SECURE"
CRITOP_HEADING = re.compile(r"^##\s+\**\s*CRIT OP\s+\d+\s*:\s*(.+?)\s*\**\s*$")
# Markdown sections pulled from team files by heading suffix:
#   "## NOOSPHERIC NETWORK - Faction Rule" -> "NOOSPHERIC NETWORK"
# Display label -> heading suffix. Operatives come from the yaml file instead.
MD_SECTIONS = {
    "Faction Rules": "Faction Rule",
    "Strategy Ploys": "Strategy Ploy",
    "Firefight Ploys": "Firefight Ploy",
    "Equipment": "Faction Equipment",
}


def _heading_regex(suffix: str) -> re.Pattern[str]:
    return re.compile(rf"^##\s+(.+?)\s+-\s+{re.escape(suffix)}\s*$")


def _entry_names(section: object) -> list[str]:
    """Extract the leading name from each list entry (dict key or plain string).

    Some sections are a single untitled rule stored as a plain string rather
    than a list; return it as one entry.
    """
    if isinstance(section, str):
        return [section]
    names: list[str] = []
    for item in section or []:
        if isinstance(item, dict):
            names.extend(item.keys())
        elif isinstance(item, str):
            names.append(item)
    return names


def _team_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") + ".md"


def _md_section_names(md_text: str, suffix: str) -> list[str]:
    """Names from markdown headings matching `## NAME - <suffix>`."""
    regex = _heading_regex(suffix)
    names: list[str] = []
    for line in md_text.splitlines():
        m = regex.match(line)
        if m:
            names.append(m.group(1).strip())
    return names


def load_teams() -> dict[str, dict[str, list[str]]]:
    """Return {team name: {section: [entry names]}} preserving file order.

    Operatives come from the yaml structure file; faction rules, ploys and
    equipment come from the team markdown headings.
    """
    data = yaml.safe_load(TEAMS_YAML.read_text(encoding="utf-8"))
    teams: dict[str, dict[str, list[str]]] = {}
    for team_name, team in data.items():
        team = team or {}
        md_text = (TEAM_DIR / _team_slug(team_name)).read_text(encoding="utf-8")
        md = {label: _md_section_names(md_text, suffix) for label, suffix in MD_SECTIONS.items()}
        teams[team_name] = {
            "Faction Rules": md["Faction Rules"],
            "Operatives": _entry_names(team.get("Operatives")),
            "Strategy Ploys": md["Strategy Ploys"],
            "Firefight Ploys": md["Firefight Ploys"],
            "Equipment": md["Equipment"],
        }
    return teams


def load_tacops() -> dict[str, list[str]]:
    """Return {category: [tacop names]} preserving first-seen order."""
    categories: dict[str, list[str]] = {}
    for line in TACOPS_MD.read_text(encoding="utf-8").splitlines():
        m = TACOP_HEADING.match(line)
        if m:
            name, category = m.group(1).strip(), m.group(2).strip()
            categories.setdefault(category, []).append(name)
    return categories


def load_critops() -> list[str]:
    names: list[str] = []
    for line in CRITOPS_MD.read_text(encoding="utf-8").splitlines():
        m = CRITOP_HEADING.match(line)
        if m:
            names.append(m.group(1).strip())
    return names


def build_markdown(
    teams: dict[str, dict[str, list[str]]],
    tacops: dict[str, list[str]],
    critops: list[str],
) -> str:
    lines: list[str] = []

    lines.append("# Teams")
    lines.append("")
    for team, sections in teams.items():
        lines.append(f"- {team}")
        for section, entries in sections.items():
            lines.append(f"  - {section}")
            for entry in entries:
                lines.append(f"    - {entry}")
    lines.append("")

    lines.append("# TacOps")
    lines.append("")
    for category, names in tacops.items():
        lines.append(f"- {category}")
        for name in names:
            lines.append(f"  - {name}")
    lines.append("")

    lines.append("# CritOps")
    lines.append("")
    for name in critops:
        lines.append(f"- {name}")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    teams = load_teams()
    tacops = load_tacops()
    critops = load_critops()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build_markdown(teams, tacops, critops), encoding="utf-8")

    operative_count = sum(len(s.get("Operatives", [])) for s in teams.values())
    tacop_count = sum(len(v) for v in tacops.values())
    print(
        f"Wrote {OUTPUT.relative_to(REPO_ROOT)}: "
        f"{len(teams)} teams ({operative_count} operatives), "
        f"{tacop_count} tacops in {len(tacops)} categories, "
        f"{len(critops)} critops"
    )


if __name__ == "__main__":
    main()
