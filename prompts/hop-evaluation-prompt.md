# Instructions

Evaluate whether the provided Kill Team rules context contains all necessary rule definitions to answer the user's question, without assuming pre-defined interactions. Your assessment should focus on identifying whether every operative, ability, and rule *definition* central to the user's question is present.

# Available Rules Overview

Before identifying missing context, review what rules are available in the database to understand what exists.

## Core Rules Categories
{rule_structure}

## Team Operatives & Faction Rules
{team_structure}

**Usage**: Use this overview to identify precise rule/operative names that exist in the database.

# Gap Detection Strategy

When identifying missing context, follow this process:

1. **Parse the Question**: Identify all nouns (operatives, abilities, terrain, actions, weapon rules)
2. **Check Retrieved Context**: Mark which nouns have definitions present (even if truncated)
3. **Detect Cross-References**: Look for rules REFERENCED BY truncated chunks
4. **Consult Structures Above**: Verify missing nouns exist in the rules/teams structure
5. **Prioritize Gaps**:
   - Critical: Operative datasheets, core action definitions, faction rules
   - Important: Weapon special rules, terrain interactions, order restrictions
   - Secondary: FAQs for edge cases (only if base rules are already present)

**Common Cross-References to Detect**:
- TacOps mention actions → "Operatives can perform X" → need "X" action definition
- Actions mention orders → "cannot perform while Conceal" → need "Conceal order" rules
- Weapons mention terrain → "Seek Light" + "Vantage" question → need both definitions
- Questions about death/incapacitation → look for FAQs about "operative incapacitated", "marker removed"

**Example 1**:
Query: "Can concealed Eliminator use Counteract?"
- ✅ Have: Conceal order restrictions (core-rules)
- ❌ Missing: "Eliminator Sniper" (check teams structure → Angels of Death → Operatives)
- ❌ Missing: "Counteract" (check rules structure → Rules 1 Phases → COUNTERACT)

**Example 2 (Cross-Reference)**:
Query: "What happens when Plant Banner carrier dies?"
Context: PLANT BANNER TacOp (truncated) - text shows "...Operatives can perform..."
- ✅ Have: Plant Banner TacOp header (but truncated)
- ❌ Missing: "Pick Up Marker" (referenced by truncated chunk)
- ❌ Missing: FAQ about marker/carrier death (check for "incapacitated" FAQs)

# Precision in Missing Queries

Use EXACT names from rule_structure and team_structure shown above.

**Good Examples**:
- "Eliminator Sniper" (from Angels of Death operatives)
- "Vantage" (from Rules 4 Killzones terrain types)
- "Counteract" (from Rules 1 Phases)
- "Markerlight, Pathfinder Marksman" (comma-separated, both from Pathfinders)

**Bad Examples**:
- "Eliminator rules" (too vague)
- "Vantage terrain mechanics" (adds unnecessary words)
- "How Counteract works" (phrased as question)
- "information about Pathfinders" (not specific operative name)

# Handling Truncated Chunks

Retrieved chunks are truncated to 300 characters for efficient evaluation. **This is expected behavior.**

## When a Chunk is Truncated (ends with "...")

**DO NOT** request the same rule again (e.g., "Plant Banner" when you already have "PLANT BANNER - TAC OP" header).

**INSTEAD**, extract missing information from what you CAN see:

1. **Look for references to other rules**: "Operatives can perform..." → missing "Pick Up Marker" action
2. **Identify the specific interaction**: "carrier dies" question + "marker" rule → missing "marker carrier incapacitated"
3. **Check if related FAQ exists**: Look for FAQ entries about the interaction

## Examples of Truncation Handling

**BAD** - Requesting the same truncated rule again:
- Context has: "PLANT BANNER - TAC OP - SECURITY ...Operatives can perform... [TRUNCATED]"
- Missing query: "Plant Banner" ❌ (will just retrieve the same chunk)

**GOOD** - Extracting referenced rules from truncated text:
- Context has: "PLANT BANNER - TAC OP - SECURITY ...Operatives can perform... [TRUNCATED]"
- Missing query: "Pick Up Marker" ✅ (retrieves the action referenced in truncated text)

**GOOD** - Identifying interaction-specific rules:
- Question: "What happens when Plant Banner carrier dies?"
- Context has: Plant Banner TacOp (truncated), FAQ about marker death
- Missing query: "Pick Up Marker" ✅ (the action needed to understand carrier mechanics)

## Strategy When Chunk is Truncated

1. **Read the header**: Confirms the rule type is present
2. **Read visible text**: Look for references to other rules (actions, abilities, terms)
3. **Extract referenced terms**: These are what you actually need
4. **Check for FAQs**: May provide the interaction answer without needing full base rule

**Common Cross-References to Detect**:
- TacOps reference actions: "Plant Banner" → "Pick Up Marker", "Place Marker"
- Actions reference states: "Shoot" → "Conceal order", "Engage order"
- Weapons reference terrain: "Seek Light" → "Vantage", "Light terrain"
- Markers reference death: "carrier dies" → "operative incapacitated", "marker placement FAQ"

**When you see "Operatives can perform X action"** → X is what you need, not the parent rule.

**Key Principle**: Truncation means you have the HEADER but not the DETAILS. Request the DETAILS (referenced rules), not the header again.

# Steps to Follow

1. Review the user's question below.
2. Review the available rule/team structures shown above.
3. Identify all operative names, abilities, keywords, and rule definitions required to accurately answer the question. Compile these into a "list of terms."
4. Examine the retrieved context below for the presence and definition of each term.
5. Determine if you have enough rules from the context to answer the question as written.
6. If insufficient, list which rules or specific terms are missing - use EXACT names from the structures above.

# User Question
{user_query}

# Retrieved Context
{retrieved_chunks}

# Constraints

- Focus strictly on rule definitions, not pre-existing or assumed interactions.
- Only refer to official Kill Team terminology and avoid speculation about unstated interactions.
- Respond ONLY with valid JSON (no markdown, no explanation, no added text).
- Reasoning must reference definitions ("I have Counteract definition and Conceal order restrictions," not "I have their interaction").
- Each retrieval query should be under 100 characters and focus on rules/abilities/operatives.
- If sufficient context: set `missing_query` to null.
- If missing context: specify the exact terms names required.
- In `missing_query`, ONLY USE TERM NAMES that are missing. Do not add "rules", "definition", "details", "ability" etc. 

Bad example for `missing_query`: `Blast weapon minimum range and damage application within blast radius`
Good example for `missing_query`: `Blast`

Bad example for `missing_query`: `Is Guard action treated as Shoot action`
Good example for `missing_query`: `Guard`

# Examples

**Example 1 – Sufficient Context**  
User: "Can I shoot during Conceal order?"  
Context: [Core Rules: Shoot action, Orders: Conceal order restrictions]  
Response:
```json
{{
 "can_answer": true,
 "reasoning": "I have definitions for Shoot action and Conceal order; sufficient to answer.",
 "missing_query": null
}}
```

**Example 2 – Truncated Context**
User: "Does Vantage affect Track Enemy TacOp with Seek Light?"
Context:
  1. **TRACK ENEMY - TAC OP - INFILTRATION**
     REVEAL: First time you score VP from this op.
     ADDITIONAL RULES: An enemy operative is being tracked if it's a valid target for a friendly operative within 6" of it. That friendly operative must have... [TRUNCATED]

Response:
```json
{{
 "can_answer": false,
 "reasoning": "Track Enemy TacOp header is present but truncated. The question asks about Vantage terrain and Seek Light weapon rule interactions. These are the missing definitions needed to answer.",
 "missing_query": "Vantage, Seek Light"
}}
```

**Example 3 – Partial Context**  
User: "Can Eliminators use Counteract while Concealed?"  
Context: [Counteract Strategic Ploy, Conceal order rules]  
Response:
```json
{{
 "can_answer": false,
 "reasoning": "I have Counteract and Conceal definitions, but missing Eliminator Sniper operative definition.",
 "missing_query": "Eliminator Sniper"
}}
```

# Use Cases

- Reviewing multi-hop retrieval results for Kill Team rules Q&A systems.
- Ensuring all necessary operative, ability, and rule *definitions* are present before answering user questions.

Now review the user question and retrieved context, and respond ONLY in JSON as specified above.