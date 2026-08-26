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

**Footnote-derived abilities:** Weapon rules marked with `*` in a weapon table (e.g. `Crush*`) are explained in a footnote below the table (e.g. `*Crush: Whenever you strike...`). Extract each such footnote as its own `###` section for that operative, and:
- Place these footnote sections FIRST, before the operative's other abilities and actions
- Strip the leading `*` marker - the section body must start with the rule text itself, never with `*`

**CRITICAL: Preserve exact wording** from the PDF as much as possible:
- Transcribe the card's sentences as printed. NEVER add clarifying words, and never invent a lead-in sentence (such as a total operative count) that is not printed on the card
- Keep weapon options as INDENTED SUB-BULLETS under the operative they belong to - never flatten them into a prose sentence:
```
- **INTERCESSOR GUNNER** with auxiliary grenade launcher and one of the following options:
    - Auto bolt rifle; fists
    - Bolt rifle; fists
```
- **Bold operative names** in selection lists (e.g., `**PACK LEADER**`, `**FANGBEARER**`)

**Composition wording:** always use this exact template, with digits for the counts, whatever wording the card itself uses:
```
Your kill team consists of 1 **ANGEL OF DEATH** operative selected from the following list:
...
And 5 **ANGEL OF DEATH** operatives selected from the following list:
```

**Composition format:** The card lists composition as `↘` entries under `OPERATIVES`. Turn those entries into ONE lead-in sentence followed by a single, FLAT bullet list of the selectable operatives - never a nested list. For `↘ 1 RAVENER PRIME operative` and `↘ 4 RAVENER operatives selected from the following list: FELLTALON, ...` write:
```
Your kill team consists of 1 **RAVENER PRIME** operative and 4 **RAVENER** operatives selected from the following list:
- **FELLTALON**
```

### 3. Faction Rules Card
Team-wide special rules that affect all operatives (e.g., "MARKERLIGHTS"). Put each new faction rule into a new header 2 section. Use header 3 sections if there are multiple variants of a single faction rule, and repeat the rule name in each variant header:
```
## CHAPTER TACTICS - Faction Rule
### CHAPTER TACTICS - 1. AGGRESSIVE
### CHAPTER TACTICS - 2. DUELLER
```

Output the faction rules in the order they are printed, reading the card top to bottom then left to right. The first faction rule printed must be the first `##` faction rule section in your output - never reorder them.

**CRITICAL Header Format for Faction Rules:**
```
## [RULE NAME] - Faction Rule
```
Example: `## ELEMENTAL STORM - Faction Rule`, NOT `## WOLF SCOUTS - ELEMENTAL STORM`

**Exception - shared faction rules:** a rule named after a keyword that several kill teams share (currently `ASTARTES`) DOES take the team name, so the header stays unique:
```
## ANGELS OF DEATH - ASTARTES - Faction Rule
```
This applies only to the bare keyword; names that already contain it (`VETERAN ASTARTES`, `HUNTING ASTARTES`) stay as they are.

**Designer's Notes** are kept, as a blockquote on their own paragraph:
```
> **Designer's Note:** text of the designer's note
```

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
- Bold every named rule referenced in the question or answer - abilities, faction rules, ploys, equipment and tac ops (e.g. `the **Subterranean Ambush** rule`, `the **Implant** tac op`)
- The question goes on the SAME LINE as the header after `*Question:*`
- Bold game terms like **STORM**, **WOLF SCOUT**, etc. in both question and answer
- Do NOT repeat the question on a separate line

## Extraction Rules
1. **Verbatim Extraction Required:**
   - All rules text must be transcribed exactly as written - do not paraphrase, expand, or add explanatory words of your own (if the card says "you can interrupt to use this rule", do not write "you can interrupt that operative's activation to use this rule")
   - Never invent list items: a bulleted rule list must contain exactly the bullets printed on the card, in the printed order (do not add a "middle" case such as `Equal, nothing happens.` that the card does not print)
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
   - **Keep bulleted rule text bulleted:** if the card presents effects as a bulleted list, keep every effect as its own bullet in ONE block - never merge them into a paragraph, and never separate them with blank lines
   - **"within" should NOT be bolded** - only bold the target (e.g., `within your **STORM**`, `within **control range**`)
   - **Distance expressions should NOT be bolded** (e.g., `within 6"` not `**within 6"**`)
   - **Period placement:** Place periods INSIDE bold markers for special keywords (e.g., `**STRATEGIC GAMBIT.**` not `**STRATEGIC GAMBIT**.`)
   - **Restriction clauses:** Keep in the same block as the main rule text, never as a separate paragraph. When an action has an effect and a separate restriction sentence, write them as two bullets of one list:
```
### ELIMINATOR SNIPER - OPTICS [1AP]
- Until the start of this operative's next activation, whenever it's shooting, enemy operatives cannot be **obscured**.
- This operative cannot perform this action while within **control range** of an enemy operative.
```
   - **Bold tac op names** in rule text (e.g. `(e.g. **Surveillance**)`)
   - **Bold both halves of "activation/counteraction"** (`**activation**/**counteraction**`). On its own, "activation" is NOT bolded
   - **Always bold these terms:** **incapacitated**, **counteract**, **visible**, **obscured**, **control range**, **cover** (but NOT in the phrase "cover save", which stays plain), **STORM** (team-specific), **REANIMATED** (team-specific), **Conceal**, **Engage**
   - **Weapon rules in rule text** (outside tables) should be bold: **Severe**, **Saturate**, **Lethal**, **Rending**, **Piercing**, **Blast**, **Shock**, **Stun**, etc.

5. **Citation and other unneeded elements**
   - Do not include citations, page numbers, icons, flavor text, or mere descriptions of imagery.

6. **Flavor text - ALWAYS DELETE:**
   Nearly every faction rule, ploy, equipment and operative card opens with one or two sentences of lore that sit between the card title and the actual rule. That text is flavor text. Delete it.
   A sentence is flavor text if it does NOT contain a game instruction (no action, no dice, no distance, no token, no "you can", no "whenever/each time").
   Recognise it by: narrative present tense about the faction ("Raveners dig extensive tunnel networks..."), adjectives about how fearsome/skilled they are, or anything a reader could remove without changing how the rule is played.
   The body of every section must START with the first sentence that carries a game instruction.
   Example - PDF card reads:
   ```
   BURROW
   Raveners will emerge from their tunnels to strike at unsuspecting victims, then disappear again before their foe can properly react.
   When setting up a RAVENER kill team before the battle, ...
   ```
   Correct output:
   ```
   ## BURROW - Faction Rule
   When setting up a **RAVENER** kill team before the battle, ...
   ```

## Output Structure Example

```markdown
## [KILL TEAM NAME] - Operative Selection
[Exact selection rules from black card]

### [KILL TEAM NAME] - Archetypes
- [one bullet per archetype, never several on one line]

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
  - **Operatives:** `## [KILL TEAM NAME] - [OPERATIVE NAME]` (team name prefix, with any trailing "KILL TEAM" dropped: `## RAVENERS - RAVENER PRIME`, NOT `## RAVENERS KILL TEAM - RAVENER PRIME`)
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
- **NO ADDED WORDS:** Never expand a sentence with your own clarification. If the card says "you can interrupt to use this rule", write exactly that - not "you can interrupt that enemy operative's activation/counteraction to use this rule"
- **NO CITATIONS:** Do not add any citations to your output
- When describing visual rules or demonstrations, extract the underlying mechanic, not the example
- If you are unsure about something or you have observed conflicting rules, let me know
<!--CACHE_BREAK-->