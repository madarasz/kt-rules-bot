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
All special rules, abilities, and unique actions as heading 3:

**Passive abilities** use Title Case:
```
### [OPERATIVE NAME] - [Ability Name in Title Case]
```
Example: `### WOLF SCOUT FROSTEYE - Storm-veiled Execution`

**Actions with AP cost** use ALL CAPS for the action name:
```
### [OPERATIVE NAME] - [ACTION NAME IN ALL CAPS] [X]AP
```
Example: `### WOLF SCOUT FANGBEARER - HEALING BALMS [1AP]`

### 2. Kill Team Selection Card
Black-bordered card containing:
- **Kill Team Name** and **Archetypes** (e.g., INFILTRATION, RECON)
- **Operative Selection Rules:** Exact composition requirements with weapon options
- **Selection Restrictions:** Which operatives can be taken multiple times
- **Special Definitions:** (e.g., what counts as "pulse weapons")

Rewrite the text to remove footnotes and integrate their referenced information into the main text as much close to the original text as possible. Ensure that the rewritten text is clear and self-contained.

**CRITICAL: Preserve exact wording** from the PDF as much as possible. For example:
- If PDF says "Your kill team consists of 6 operatives selected from the follows:" - use exactly that text
- **Bold operative names** in selection lists (e.g., `**PACK LEADER**`, `**FANGBEARER**`)

### 3. Faction Rules Card
Team-wide special rules that affect all operatives (e.g., "MARKERLIGHTS"). Put each new faction rule into a new header 2 section. Use header 3 sections if there are multiple variants of a single faction rule.

**CRITICAL Header Format for Faction Rules:**
```
## [RULE NAME] - Faction Rule
```
Example: `## ELEMENTAL STORM - Faction Rule`, NOT `## WOLF SCOUTS - ELEMENTAL STORM`

### 4. Ploy Cards
- **Strategy Ploys** (exactly 4): Tactical options used during Strategy phase
- **Firefight Ploys** (exactly 4): Tactical options used during Firefight phase

**CRITICAL Header Format for Ploys:**
```
## [PLOY NAME] - Strategy Ploy
## [PLOY NAME] - Firefight Ploy
```
Example: `## CLOAKED BY THE STORM - Strategy Ploy`, NOT `## WOLF SCOUTS - CLOAKED BY THE STORM - Strategy Ploy`

### 5. Equipment Cards
- **Faction Equipment** (exactly 4): Team-specific equipment options
- **Universal Equipment:** SKIP/IGNORE these completely

**CRITICAL Header Format for Equipment:**
```
## [EQUIPMENT NAME] - Faction Equipment
```
Example: `## FROST WEAPONS - Faction Equipment`, NOT `## WOLF SCOUTS - FROST WEAPONS - Faction Equipment`

### Rules Commentaries
**Each Q&A pair must use this EXACT format:**
```
## [FAQ] *Question:* [Full question text with **bold** game terms]
*Answer:* [Full answer text]
```
Example:
```
## [FAQ] *Question:* Can my **STORM** be measured through Wall Terrain in Close Quarters?
*Answer:* No.
```
- The question goes on the SAME LINE as the header after `*Question:*`
- Bold game terms like **STORM**, **WOLF SCOUT**, etc. in both question and answer
- Do NOT repeat the question on a separate line

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
      - Keywords in rule text (e.g., **Blast**, **Heavy** terrain, **Torrent**)
      - Critical game terms when relevant (e.g., **incapacitated**, **counteract**, **visible**, **wholly within x"**, **control range**, **in cover**)
   - **DO NOT bold** weapon rules inside weapon tables - write them as plain text (e.g., `Piercing 1, Lethal 5+` not `**Piercing 1**, **Lethal 5+**`)
   - **Empty weapon rules:** Leave the cell empty (e.g., `| |`) - do NOT use `-` or `—`
   - Use structured formats for complex multi-condition rules
   - **"within" should NOT be bolded** - only bold the target (e.g., `within your **STORM**`, `within **control range**`)
   - **Distance expressions should NOT be bolded** (e.g., `within 6"` not `**within 6"**`)
   - **Period placement:** Place periods INSIDE bold markers for special keywords (e.g., `**STRATEGIC GAMBIT.**` not `**STRATEGIC GAMBIT**.`)
   - **Restriction clauses:** Keep on same line/paragraph as the main rule text, do NOT put on separate line
   - **Always bold these terms:** **incapacitated**, **counteract**, **visible**, **obscured**, **control range**, **cover**, **STORM** (team-specific), **REANIMATED** (team-specific), **Conceal**, **Engage**
   - **Weapon rules in rule text** (outside tables) should be bold: **Severe**, **Saturate**, **Lethal**, **Rending**, **Piercing**, **Blast**, **Shock**, **Stun**, etc.

5. **Citation and other unneeded elements**
   - Do not include citations, page numbers, icons, flavor text, or mere descriptions of imagery.

## Output Structure Example

```markdown
## [KILL TEAM NAME] - Operative Selection
[Exact selection rules from black card]

### [KILL TEAM NAME] - Archetypes
- [List archetypes]

## [FACTION RULE NAME] - Faction Rule
### [FACTION RULE NAME] - [Faction Rule Variant]
[Complete rule text]

## [KILL TEAM NAME] - [OPERATIVE NAME]
**Stats:**    
- APL: [X]
- Move [X]"
- Save [X]+
- Wounds [X]

**Weapons:**
| Type | Name | ATK | HIT | DMG | Weapon Rules |
|---|---|---|---|---|---|
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
  - **Operatives:** `## [KILL TEAM NAME] - [OPERATIVE NAME]` (team name prefix)
  - **Faction Rules:** `## [RULE NAME] - Faction Rule` (NO team name prefix)
  - **Strategy Ploys:** `## [PLOY NAME] - Strategy Ploy` (NO team name prefix)
  - **Firefight Ploys:** `## [PLOY NAME] - Firefight Ploy` (NO team name prefix)
  - **Equipment:** `## [EQUIPMENT NAME] - Faction Equipment` (NO team name prefix)
  - This structure is essential for document chunking and searchability
  - Use `###` (H3) for sub-sections within a major element (abilities, actions)
- The distinction between **within** and **wholly within** is very important, do not mix these up
- No empty header sections. If it's empty, skip it.
- **Preserve all weapon rules:** Include every special rule listed in WR column
- **Maintain rule interactions:** Keep all cross-references between abilities
- **Complete extraction:** Every operative and card must be included
- **NO CITATIONS:** Do not add any citations to your output
- When describing visual rules or demonstrations, extract the underlying mechanic, not the example
- If you are unsure about something or you have observed conflicting rules, let me know