## Instructions for Rules Commentary Extraction

You will receive pages from the Kill Team rulebook containing **Rules Commentary** and **Previous Rules Commentary** sections. These sections consist of Question & Answer pairs that clarify ambiguous rules interactions.

## Task
Extract all Q&A pairs from:
- **Rules Commentary** sections
- **Previous Rules Commentary** sections

Ignore all other content including:
- Errata sections
- Terrain type definitions
- Killzone-specific rules
- Any other rule text outside commentary sections

## Critical Extraction Rule
**All text must be transcribed verbatim with absolutely no paraphrasing or rewording.** Extract the questions and answers exactly as they appear in the source material, preserving all wording, terminology, punctuation, and structure.

## Formatting Requirements

**Each Q&A pair must:**
1. Use header 2 (##) and `[FAQ]` prefix for each Q&A pair
2. Start the question with `*Question*:` prefix
3. Start the answer with `*Answer*:` prefix
4. **Bold** the following elements:
   - Faction/unit names (e.g., **CORSAIR VOIDSCARRED**)
   - Ability names (e.g., **Warding Shield**)
   - Game action names (e.g., **Shoot** action, **Guard** action)
   - Keywords (e.g., **Blast**, **Heavy**, **Torrent**)
   - Critical game terms when relevant (e.g., **incapacitated**, **counteract**)

**Example Format:**
```
## [FAQ] *Question*: In the Resolve Attack Dice step of the **Shoot** action, what order are successes resolved in? How does this interact with my rules that reduce or ignore damage from the first attack dice (e.g. **CORSAIR VOIDSCARRED** **Warding Shield**, **HERNKYN YAEGIR** **Tough Survivalists**)?
*Answer*: Successes resolve simultaneously. The defender can select one of the successes being resolved to reduce or ignore (as appropriate to their rule).
```

## Critical Requirements
- **Verbatim extraction only**: Do not paraphrase, condense, or reword any part of questions or answers
- **Zero-tolerance for terminology errors**: Game-specific terms, faction names, ability names, and keywords must be transcribed exactly as they appear
- Preserve all parenthetical examples and rule references
- Maintain the exact wording, punctuation, and structure from the source

## Output Format
- Present all FAQ entries in a single continuous list
- Use clear spacing between FAQ entries
- No headers, tables, or additional commentary needed
- No page references or citations