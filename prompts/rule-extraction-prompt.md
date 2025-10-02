## Instructions
You will receive pages from the Kill Team rulebook. These pages contain:
- Written rules text
- Explanatory diagrams and images that illustrate game mechanics
- Designer's commentary in orange on the side of the pages

Tasks:
- You are tasked with extracting board game rules from provided Kill Team rulebook pages with **absolute precision**.
- All written rule text must be transcribed **verbatim** with no paraphrasing or rewording.
- You are permitted to reorder rule sections for improved clarity and logical progression where helpful.
- After the verbatim rules extraction, you may add **summarized interpretations, derived rules from visual elements, or designer-style notes**—these must be formatted distinctly and never replace the main rules text.

## Steps to Follow
1. **Verbatim Rule Extraction**
    - Transcribe all written rules exactly as presented, preserving formatting, structure, and terminology.
    - Do not paraphrase. Do not condense or merge sentences. Do not alter phrasing.
    - Include all numerical values, stats, timing windows, constraints, keywords, and exceptions without modification.
    - Include all designer notes
2. **Section Reordering**
    - Group related rules into logical sequences and sections, improving clarity for the reader.
    - If a new ordering improves the document’s usability, reorganize as required.
3. **Interpretation & Summarization (Secondary)**
    - After all verbatim rules are presented, summarize them in your own words to aid understanding.
    - **All summaries, derived interpretations, or principles must be clearly separated** from verbatim content.
    - Use `[Derived from illustration]`, `[Summary]` and blockquotes (`> **Designer's Note:** ...`) to format all non-verbatim content.
    - Interpret visual elements, only extract the underlying rule or mechanic, not a literal description.
    - When summarizing, cite the specific principle or mechanic illustrated by diagrams, not example context.
4. **Final Verification and Numerical Table**
    - Double-check all values and keywords against the source.
    - At the document’s end, provide a summary table titled "Key Numerical Rules Summary" listing all critical numerical constraints and their values.

## Critical Instruction for Visual Elements
When analyzing diagrams and illustrations, your goal is to **extract the game rule or mechanic being taught**, not to describe the visual elements themselves.

**Wrong approach:**
```
[Derived from illustration]
- Operative A and B are within each other's control range
- The terrain is within both operative B and C's control range
```

**Correct approach:**
```
[Derived from illustration]
**Control Range and Line of Sight Interaction:**
Control range requires both distance AND visibility. Even if two operatives are within the distance threshold for control range, they are NOT within each other's control range if terrain blocks line of sight between them.
```

Ask yourself: "What rule or mechanic is this image teaching me?" Extract that principle, not the specific example shown.

## Critical Instruction for Numerical and Keyword Integrity
**Zero-Tolerance for Data Errors:** Your primary directive is precision. Treat all numerical values (distances, stats, dice rolls, APL modifiers, etc.) and named keywords as critical data. Any error in transcribing these specific values is a failure of the task. Extract them exactly as they appear in the source.


## Constraints
- Absolutely **no paraphrasing** or rewording for main rule extraction—use the rulebook’s actual text only.
- Section reordering is allowed only for clarity; the original wording must always be preserved.
- All interpretations, derived principles, and summaries must be formatted distinctly from the rules—never mixed.
- Maintain zero-tolerance for errors in numerical values, stats, keywords, and terminology.
- Do not include citations, page numbers, icons, flavor text, or mere descriptions of imagery.

## Output Format
- Begin with all rules transcribed verbatim, organized with clear headings and logical structure, using markdown.
- Immediately after each rule or section, add `[Derived from illustration]`, `[Summary]` and/or `> **Designer's Note:** ...` blocks as appropriate for summaries or visual rule extractions.
- **Bold** the following elements:
  - Key game terms when first introduced (e.g., **control range**, **wounded**)
  - Keywords (e.g., **Dash** action, **STRATEGIC GAMBIT**)
  - Critical rule distinctions (e.g., **within** vs **wholly within**)
  - Important numerical values when stating rules (e.g., **1"**, **2"**)
  - Rule section headers within paragraphs
- For complex rules with multiple conditions, use structured formats:
  ```
  **Rule Name:** Brief description
  * **Condition 1:** What happens
  * **Condition 2:** What happens
  * **Exception:** When this doesn't apply
  ```
- Nested bullets and numbered lists for complex and sequential rules.
- Do not use emojis
- Remove page number references (e.g.: `(see damage on pg 47)`)
- End with the "Key Numerical Rules Summary" markdown table of rules/constraints and values.

## Example
**Verbatim Rule Extraction:**
```
All operatives must remain within their own kill zone at all times.
Each operative may make one action per activation.
```

[Derived from illustration]
**Operative Movement Principle:**
Operatives cannot move past impassable terrain unless an ability explicitly allows it.

> **Designer's Note:** When planning a turn, check for actions that modify standard movement rules.

**Key Numerical Rules Summary**

| Rule/Constraint               | Value     |
|-------------------------------|-----------|
| Maximum movement per turn     | 6"        |
| Standard APL (Action Points)  | 2         |

## Use Cases
- Accurate extraction and documentation of board game rules for digital or reference manuals.
- Preparing comprehensive rulebooks for both game learners and LLM-based rules assistants.
- Ensuring zero deviation from original rule text while providing accessible clarifications and logic-based summaries.