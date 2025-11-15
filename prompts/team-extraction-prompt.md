## Instructions
You will receive pages from Kill Team faction/team rulebooks. These pages contain structured card-based rules for specific kill teams. Your task is to extract these rules with **absolute precision**.

## Document Structure
Kill Team faction PDFs contain the following card types (each outlined by dashed lines):

### 1. Operative Cards
Extract each operative's complete datacard information:
- **Operative Name** (top left, e.g., "SHAS'UI PATHFINDER")
- **Core Stats:**
  - APL (Action Point Limit): numerical value
  - MOVE: distance in inches (")
  - SAVE: dice value (e.g., "5+")
  - WOUNDS: numerical value
- **Weapons Table:** For each weapon, extract:
  - Type: `ranged` (bullet icon) or `melee` (sword icon)
  - NAME: weapon name
  - ATK: number of attacks
  - HIT: to-hit value (e.g., "4+")
  - DMG: normal/critical damage (e.g., "4/5")
  - WR (Weapon Rules): all special rules (e.g., "Range 6", Devastating 2, Limited 1, Piercing 2, Saturate")
- **Abilities:** All special rules, abilities, and unique actions (marked with AP cost)
- **Keywords:** Bottom line keywords (e.g., "PATHFINDER, T'AU EMPIRE, LEADER, SHAS'UI")

#### Abilities
All special rules, abilities, and unique actions (marked with AP cost) as heading 3: 
```
### [OPERATIVE NAME] - [Ability Name]
```

### 2. Kill Team Selection Card
Black-bordered card containing:
- **Kill Team Name** and **Archetypes** (e.g., INFILTRATION, RECON)
- **Operative Selection Rules:** Exact composition requirements with weapon options
- **Selection Restrictions:** Which operatives can be taken multiple times
- **Special Definitions:** (e.g., what counts as "pulse weapons")

Rewrite the text to remove footnotes and integrate their referenced information into the main text as much close to the original text as possible. Ensure that the rewritten text is clear and self-contained.

### 3. Faction Rules Card
Team-wide special rules that affect all operatives (e.g., "MARKERLIGHTS"). Put each new faction rule into a new header 2 section. Use header 3 sections if there are multiple variants of a single faction rule.

### 4. Ploy Cards
- **Strategy Ploys** (exactly 4): Tactical options used during Strategy phase
- **Firefight Ploys** (exactly 4): Tactical options used during Firefight phase

### 5. Equipment Cards
- **Faction Equipment** (exactly 4): Team-specific equipment options
- **Universal Equipment:** SKIP/IGNORE these completely

### Rules Commentaries
**Each Q&A pair must:**
1. Use header 2 (##) and `[FAQ]` prefix for each Q&A pair
2. Format the question with `*Question*:` prefix
3. Format the answer with `*Answer*:` prefix
4. **Bold** the following elements:
   - Faction/unit names (e.g., **CORSAIR VOIDSCARRED**)
   - Ability names (e.g., **Warding Shield**)
   - Game action names (e.g., **Shoot** action, **Guard** action)
   - Keywords (e.g., **Blast 2"**, **Heavy** terrain, **Torrent**)
   - Critical game terms when relevant (e.g., **incapacitated**, **counteract**)

## Extraction Rules
1. **Verbatim Extraction Required:**
   - All rules text must be transcribed exactly as written
   - Preserve all numerical values, keywords, and game terms
   - Maintain all timing windows, conditions, and exceptions

2. **Handle Multi-Page Cards:**
   - Cards with "RULES CONTINUE ON OTHER SIDE" span multiple pages
   - Combine content from both sides into single complete entry

3. **Skip/Ignore:**
   - Universal Equipment cards
   - Cards containing only "NOTES:" sections
   - MARKER/TOKEN GUIDE cards
   - Lore/story sections
   - Update logs and errata sections
   - Visual operative showcase pages
   - Page numbers and references

4. **Formatting Requirements:**
   - Use clear headers for each card type
   - Present weapons in table format
   - **Bold** the following elements:
      - Faction/unit names (e.g., **CORSAIR VOIDSCARRED**)
      - Ability names (e.g., **Warding Shield**)
      - Game action names (e.g., **Shoot** action, **Guard** action)
      - Keywords (e.g., **Blast**, **Heavy** terrain, **Torrent**)
      - Critical game terms when relevant (e.g., **incapacitated**, **counteract**, **visible**, **wholly within x"**, **control range**, **in cover**)
   - Use structured formats for complex multi-condition rules

5. **Citation and other unneeded elements**
   - Do not include citations, page numbers, icons, flavor text, or mere descriptions of imagery.

## Output Structure

```markdown
## [KILL TEAM NAME] - Operative Selection
[Exact selection rules from black card]

### [KILL TEAM NAME] - Archetypes
- [List archetypes]

## [Faction Rule Name] - Faction Rule
### [Faction Rule Name] - [Faction Rule Variant]
[Complete rule text]

## [KILL TEAM NAME] - [OPERATIVE NAME]
**Stats:**    
- APL: [X]
- Move [X]"
- Save [X]+
- Wounds [X]

**Weapons:**
| Type | Name | ATK | HIT | DMG | Weapon Rules |
|------|------|-----|-----|-----|--------------|
| [type] | [name] | [X] | [X]+ | [X/X] | [rules] |

**Keywords:** [list keywords]

### [OPERATIVE NAME] - [Ability Name]
[Full ability description]

### [OPERATIVE NAME] - [Action Name] [X]AP
[Full action description]

[Repeat for each operative]

## [Strategy Ploy Name] - Strategy Ploy
[Complete ploy text]

[Exactly 4 strategy ploys]

## [Firefight Ploy Name] - Firefight Ploy
[Complete ploy text]

[Exactly 4 firefight ploys]

## [Equipment Name] - Faction Equipment
[Complete equipment text]

[Exactly 4 faction equipment items]
```

## Critical Requirements
- ZERO TOLERANCE for flavor or story text, do not include such.
- **Zero tolerance for data errors:** Every stat, keyword, and numerical value must be exact
- **CRITICAL: Use `##` (H2) headers for all major rule sections**
  - Each header should include the team name as prefix
  - Each distinct ploy, operative, equipment, faction rule, or concept must have its own `## [Team name] - Header Name`
  - This structure is essential for document chunking and searchability
  - Examples: `## OBELISK NODE MATRIX`, `## CANOPTEK CIRCLE - GEOMANCER`, `## SOULDRAIN - Strategy Ploy`
  - Use `###` (H3) for sub-sections within a major element
- No empty header sections. If it's empty, skip it.
- **Preserve all weapon rules:** Include every special rule listed in WR column
- **Maintain rule interactions:** Keep all cross-references between abilities
- **Complete extraction:** Every operative and card must be included
- **NO CITATIONS:** Do not add any citations to your output
- When describing visual rules or demonstrations, extract the underlying mechanic, not the example
- If you are unsure about something or you have observed conflicting rules, let me know