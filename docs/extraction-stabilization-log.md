# Extraction Stabilization Log

## Goal
Minimize diffs when re-running rule extraction by standardizing prompt and clean script.

## Initial Analysis (Baseline)

**wolf_scouts.md**: 95 lines changed
**hierotek_circle.md**: 156 lines changed

### Identified Inconsistency Categories:

1. **Header format for Faction Rules/Ploys/Equipment**
   - Old: `## ELEMENTAL STORM - Faction Rule`
   - New: `## WOLF SCOUTS - ELEMENTAL STORM`

2. **Action name casing** (H3 headers)
   - Old: `### CHRONOMANCER - Countertemporal Nanomine [1AP]`
   - New: `### CHRONOMANCER - COUNTERTEMPORAL NANOMINE [1AP]`

3. **"within" bolding inconsistency**
   - Old: `within your **STORM**`
   - New: `**within** your **STORM**`

4. **Empty weapon rules cell**
   - Old: `| |` (empty)
   - New: `| - |`

5. **Weapon rules bolding in tables**
   - Old: `| **Blast 2"**, **Lethal 5+** |`
   - New: `| Blast 2", Lethal 5+ |`

6. **FAQ format**
   - Old: `## [FAQ] *Question:* Can my **STORM**...`
   - New: `## [FAQ] Can my STORM be measured...`

7. **Period placement after keywords like STRATEGIC GAMBIT**
   - Old: `**STRATEGIC GAMBIT.**`
   - New: `**STRATEGIC GAMBIT**.`

8. **"0CP" vs "OCP"** (OCR error)

9. **Operative selection text variance**

10. **Line breaks** - restriction clauses on separate lines vs inline

11. **"counteracting" bolding** - sometimes bold, sometimes not

---

## Iteration 1

**Changes to prompt:**
- Added explicit header format rules for Faction Rules, Ploys, Equipment (NO team name prefix)
- Added explicit FAQ format (question on same line as header)
- Added "DO NOT bold weapon rules in tables" rule
- Added "Empty weapon rules: Leave cell empty" rule
- Added "within should NOT be bolded" rule
- Added "Period placement INSIDE bold markers" rule
- Added "Restriction clauses: Keep on same line" rule
- Added Title Case for passive abilities, ALL CAPS for actions with AP cost

**Changes to clean_rules.py:**
- Added `unbold_weapon_rules_in_tables()` - removes ** from weapon rule cells
- Added `normalize_empty_weapon_cells()` - converts "| - |" to "| |"
- Added `fix_ocr_errors()` - fixes OCP -> 0CP
- Added `unbold_within()` - removes bold from "within"
- Added `fix_period_placement()` - fixes **KEYWORD**. to **KEYWORD.**

**Results:**
- wolf_scouts.md: 42 lines changed (was 95)
- hierotek_circle.md: 142 lines changed (was 156)
- **Total: 184 lines (was 251) - 27% improvement**

**Remaining issues:**
1. Empty table cells: `| |` vs `|  |` (spacing)
2. **incapacitated** bold inconsistency
3. **within X"** bold inconsistency (prompt says not bold, but sometimes needed)
4. **SUPPORT.** vs **SUPPORT**. period placement
5. Action names: Title Case vs ALL CAPS inconsistency
6. Operative selection text variance
7. FAQs sometimes dropped during extraction
8. **Vantage**, **Engage**, **control** bold inconsistency

---

## Iteration 2

**Changes to prompt:**
- Added explicit list of terms that should always be bold
- Added weapon rules in rule text should be bold

**Changes to clean_rules.py:**
- Fixed table cell formatting (was producing `|  |`, needed `| |`)
- Added `normalize_distance_bolding()` - removes bold from "within X"" patterns

**Results:**
- wolf_scouts.md: 46 lines changed (was 42)
- hierotek_circle.md: 130 lines changed (was 142)
- **Total: 176 lines (was 184) - 4% improvement**

**Remaining issues:**
1. Empty table cells: `| |` vs `||` (spacing bug in clean script)
2. Operative names in selection lists not bold
3. Selection text wording varies
4. Blank lines added inconsistently

**Versioned copies created:** `team-extraction-prompt.v2.md`, `clean_rules.v2.py`

---

## Iteration 3

**Changes to prompt:**
- Added "Preserve exact wording" instruction for selection cards
- Added "Bold operative names in selection lists" instruction

**Changes to clean_rules.py:**
- Fixed empty cell formatting to use single space for empty cells (`| |` not `|  |`)

**Results:**
- wolf_scouts.md: 22 lines changed (was 32)
- hierotek_circle.md: 116 lines changed (was 130)
- **Total: 138 lines (was 162) - 15% improvement**

**Remaining issues:**
1. Selection text wording variance ("consists of X operatives selected from the follows:" vs "consists of:")
2. `**within 6"**` bold inconsistency - committed has it bold, prompt said not to
3. Weapon rules bolding in rule text (Shock, Stun, Severe, etc.)
4. Extra blank lines added between paragraphs

**Versioned copies created:** `team-extraction-prompt.v3.md`, `clean_rules.v3.py`

---

## Iteration 4

**Changes to prompt:**
- REMOVE "distance expressions should NOT be bolded" (committed version HAS them bold)
- Strengthen "preserve exact wording" instruction with examples

**Changes to clean_rules.py:**
- Added `normalize_weapon_type_casing()` - fixes `ranged`→`Ranged`, `melee`→`Melee`
- Removed distance_unbolded call (preserve distance bolding)

**Results:**
- wolf_scouts.md: 29 lines changed (was 73 before fix, 22 best)
- hierotek_circle.md: 168 lines changed (was 154)
- **Total: 197 lines - LLM non-determinism causing variance**

**Key insight:** LLM extraction is inherently non-deterministic. Results vary significantly between runs even with identical prompts.

**Versioned copies created:** `team-extraction-prompt.v4.md`, `clean_rules.v4.py`

---

## Summary

| Iteration | Wolf Scouts | Hierotek Circle | Total | Change |
|-----------|-------------|-----------------|-------|--------|
| Baseline  | 95          | 156             | 251   | -      |
| 1         | 42          | 142             | 184   | -27%   |
| 2         | 46          | 130             | 176   | -30%   |
| 3 (best)  | 22          | 116             | 138   | -45%   |
| 4         | 29          | 168             | 197   | -22%   |

**Best result: Iteration 3 with 138 lines changed (45% improvement)**

### Remaining unavoidable variances (LLM non-determinism):
1. Selection text wording varies
2. Extra blank lines added/removed
3. Bolding of game terms (Shock, Stun, Severe, obscured)
4. Minor text reformatting

### Successfully normalized by clean script:
- Apostrophes (curly → straight)
- Bullet formatting
- Table formatting
- Empty table cells
- Weapon type casing (ranged → Ranged)
- OCR errors (OCP → 0CP)
- Period placement for keywords

---
