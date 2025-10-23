# Context Evaluation for Multi-Hop Retrieval

You are evaluating whether you have sufficient context from Kill Team rules to answer a user's question.

## Your Task

1. Review the user's question
2. Examine the retrieved rule context
3. Determine if you can answer the question with the provided context
4. If not, specify what additional information you need

## User Question
{user_query}

## Retrieved Context
{retrieved_chunks}

## Response Format

Respond ONLY with valid JSON (no markdown, no explanation):

```json
{{
  "can_answer": true,
  "reasoning": "I have the Overwatch rule and valid target definition. Sufficient to answer.",
  "missing_query": null
}}
```

OR

```json
{{
  "can_answer": false,
  "reasoning": "I have the Track Enemy TacOp rule, but missing Vantage terrain interaction and Seek Light weapon rule.",
  "missing_query": "Vantage terrain, Seek Light, determining valid targets"
}}
```

## Field Definitions

- **can_answer** (boolean): true if you have enough context, false if missing information
- **reasoning** (string): Brief explanation (1-2 sentences) of what you have or what's missing
- **missing_query** (string or null):
  - If can_answer=false: A focused retrieval query for the missing rule(s)
  - If can_answer=true: null

## Guidelines for missing_query

- Be specific: "Vantage terrain" not "terrain"
- Focus on rules, not concepts: "Seek Light" not "how Seek Light works"
- Combine related needs: "Vantage and its interaction with Concealed operatives"
- Use official Kill Team terminology
- Keep queries under 100 characters
- Skip the word "rule" 

## Examples

**Example 1 - Sufficient Context**
User: "Can I shoot during Conceal order?"
Context: [Core Rules: Shoot action, Orders: Conceal order restrictions]
Response:
```json
{{
  "can_answer": true,
  "reasoning": "I have the Shoot action definition and Conceal order restrictions. This is sufficient.",
  "missing_query": null
}}
```

**Example 2 - Missing Context**
User: "Does Vantage affect Track Enemy TacOp with Seek Light?"
Context: [Track Enemy TacOp definition]
Response:
```json
{{
  "can_answer": false,
  "reasoning": "I have Track Enemy TacOp, but missing Vantage terrain rule and Seek Light weapon rule needed to determine valid targets.",
  "missing_query": "Vantage terrain, Seek Light"
}}
```

**Example 3 - Partial Context**
User: "Can Eliminators use Counteract while Concealed?"
Context: [Counteract Strategic Ploy, Conceal order rules]
Response:
```json
{{
  "can_answer": false,
  "reasoning": "I have Counteract and Conceal rules, but missing Eliminator-specific rules or exceptions.",
  "missing_query": "Eliminator operative abilities"
}}
```

Now evaluate the provided context and respond with JSON only.
