## Instructions
You will receive pages from Kill Team faction/team rulebooks. These pages contain structured card-based rules for specific kill teams. Your task is to extract these rules with **absolute precision**.

## Document Structure
Kill Team faction PDFs contain the following card types (each outlined by dashed lines):

### 1. Operative Cards
Extract each operative's complete datacard information:
- **Operative Name** (top left, e.g., "Shas'ui Pathfinder")
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

### 2. Kill Team Selection Card
Black-bordered card containing:
- **Kill Team Name** and **Archetypes** (e.g., Infiltration, Recon)
- **Operative Selection Rules:** Exact composition requirements. Operative names should be Title Cased and in **bold** (e.g., **Sorcerer of Tempyrion**)
- **Selection Restrictions:** Which operatives can be taken multiple times
- **Special Definitions:** (e.g., what counts as "pulse weapons")

Rewrite the text to remove footnotes and integrate their referenced information into the main text as much close to the original text as possible. Ensure that the rewritten text is clear and self-contained.

### 3. Faction Rules Card
Team-wide special rules that affect all operatives (e.g., "Markerlights")

### 4. Ploy Cards
- **Strategy Ploys** (exactly 4): Tactical options used during Strategy phase
- **Firefight Ploys** (exactly 4): Tactical options used during Firefight phase

### 5. Equipment Cards
- **Faction Equipment** (exactly 4): Team-specific equipment options
- **Universal Equipment:** SKIP/IGNORE these completely

### Rules Commentaries
**Each Q&A pair must:**
1. Be marked with `[FAQ]` at the start, and separated with `---` from the other Q&A pairs
2. Format the question with `*Question*:` prefix
3. Format the answer with `*Answer*:` prefix


## Extraction Rules
1. ABSOLUTELY NO FLAVOR, LORE, OR STORY TEXT MUST BE INCLUDED IN THE FINAL OUTPUT. Focus solely on the mechanics and rules.
2. **Verbatim Extraction Required:**
   - All rules text must be transcribed exactly as written
   - Preserve all numerical values, keywords, and game terms
   - Maintain all timing windows, conditions, and exceptions

3. **Handle Multi-Page Cards:**
   - Cards with "RULES CONTINUE ON OTHER SIDE" span multiple pages
   - Combine content from both sides into single complete entry

4. **Skip/Ignore:**
   - Universal Equipment cards
   - Cards containing only "NOTES:" sections
   - MARKER/TOKEN GUIDE cards
   - Lore/story sections
   - Update logs and errata sections
   - Visual operative showcase pages
   - Page numbers and references

5. **Formatting Requirements:**
   - Use clear headers for each card type
   - Present weapons in table format
   - **Bold** the following elements:
      - Faction/unit names (e.g., **Corsair Voidscarred**)
      - Ability names (e.g., **Warding Shield**)
      - Game action names (e.g., **Shoot** action, **Guard** action)
      - Keywords (e.g., **Blast**, **Heavy**, **Torrent**)
      - Critical game terms when relevant (e.g., **incapacitated**, **counteract**)
   - Use structured formats for complex multi-condition rules
   - Convert any ALL CAPS phrases to Title Case (capitalize the first letter of each word only). Example: `Corsair Voidscarred` instead of `CORSAIR VOIDSCARRED`

5. **Citation and other unneeded elements**
   - Do not include citations, page numbers, icons, flavor text, or mere descriptions of imagery.

## Output Structure

```markdown
# [Kill Team Name]

## [Kill Team Name] Composition

### Operative Selection
[Exact selection rules from black card]

### Archetypes
- [List archetypes]

# [Kill Team Name] Faction Rules

## [Rule Name]
[Complete rule text]

# [Kill Team Name] Operatives

## [Kill Team Name] - [Operative Name]
**Stats:**    
- APL: [X]
- Move: [X]"
- Save: [X]+
- Wounds: [X]

**Weapons:**
| Type | Name | ATK | HIT | DMG | Weapon Rules |
|------|------|-----|-----|-----|--------------|
| [type] | [name] | [X] | [X]+ | [X/X] | [rules] |

**Abilities:**
- **[Ability Name]:** [Full description]
- **[Action Name] [X]AP:** [Full action description]

**Keywords:** [list keywords]

[Repeat for each operative]

# [Kill Team Name] Strategy Ploys

## [Kill Team Name] - [Ploy Name]
[Complete ploy text]

[Exactly 4 strategy ploys]

# [Kill Team Name] Firefight Ploys

## [Kill Team Name] - [Ploy Name]  
[Complete ploy text]

[Exactly 4 firefight ploys]

# [Kill Team Name] Faction Equipment

## [Kill Team Name] - [Equipment Name]
[Complete equipment text]

[Exactly 4 faction equipment items]
```

## Critical Requirements
- ZERO TOLERANCE for flavor or story text, do not include.
- **Zero tolerance for data errors:** Every stat, keyword, and numerical value must be exact
- **CRITICAL: Use `##` (H2) headers for all major rule sections**
  - Each header should include the team name as prefix
  - Each distinct ploy, operative, equipment, faction rule, or concept must have its own `## [Team name] - Header Name`
  - This structure is essential for document chunking and searchability
  - Examples: `## Canoptek Circle - Obelisk Node Matrix`, `## Canoptek Circle -  Geomancer`, `## Canoptek Circle - Souldrain`
  - Use `###` (H3) for sub-sections within a major element
- **Preserve all weapon rules:** Include every special rule listed in WR column
- **Maintain rule interactions:** Keep all cross-references between abilities
- **Complete extraction:** Every operative and card must be included
- **No citations:** Do not add any citations to your output
- When describing visual rules or demonstrations, extract the underlying mechanic, not the example
- If you are unsure about something or you have observed conflicting rules, let me know