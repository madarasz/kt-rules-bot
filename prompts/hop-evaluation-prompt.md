# Instructions

Evaluate whether the provided Kill Team rules context contains all necessary rule definitions to answer the user's question, without assuming pre-defined interactions. Your assessment should focus on identifying whether every operative, ability, and rule *definition* central to the user's question is present.

# Steps to Follow

1. Review the user's question.
2. Identify all operative names, abilities, keywords, and rule definitions required to accurately answer the question. Compile these into a "list of terms."
3. Examine the retrieved rule context for the presence and definition of each term.
4. Determine if you have enough rule definitions from the context to answer the question as written.
5. If insufficient, list which rule definitions or specific terms are missing from the retrieved context.

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

**Example 2 – Missing Context**  
User: "Does Vantage affect Track Enemy TacOp with Seek Light?"  
Context: [Track Enemy TacOp definition]  
Response:
```json
{{
 "can_answer": false,
 "reasoning": "I have Track Enemy TacOp's definition, but missing Vantage terrain and Seek Light weapon definitions.",
 "missing_query": "Vantage terrain, Seek Light weapon"
}}
```

**Example 3 – Partial Context**  
User: "Can Eliminators use Counteract while Concealed?"  
Context: [Counteract Strategic Ploy, Conceal order rules]  
Response:
```json
{{
 "can_answer": false,
 "reasoning": "I have Counteract and Conceal definitions, but missing Eliminator operative definition.",
 "missing_query": "Eliminator operative"
}}
```

# Use Cases

- Reviewing multi-hop retrieval results for Kill Team rules Q&A systems.
- Ensuring all necessary operative, ability, and rule *definitions* are present before answering user questions.

Now review the user question and retrieved context, and respond ONLY in JSON as specified above.