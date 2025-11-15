# Multi-Hop Retrieval Improvements

**Last updated:** 2025-01-09

Suggested improvements for the multi-hop retrieval system to enhance query answering quality before considering RAPTOR implementation.

---

## Table of Contents

- [Current Implementation Summary](#current-implementation-summary)
- [Recommended Improvements](#recommended-improvements)
  - [1. Increase Max Hops (Quick Win)](#1-increase-max-hops-quick-win)
  - [2. Improve Hop Evaluation Prompt](#2-improve-hop-evaluation-prompt)
  - [3. Add Metadata-Based Filtering](#3-add-metadata-based-filtering)
  - [4. Implement Query Decomposition](#4-implement-query-decomposition)
  - [5. Add Confidence Scoring](#5-add-confidence-scoring)
  - [6. Implement Smart Stopping](#6-implement-smart-stopping)
  - [7. Enable Parallel Hop Retrieval](#7-enable-parallel-hop-retrieval)
  - [8. Add Hop Result Reranking](#8-add-hop-result-reranking)
- [Implementation Priority](#implementation-priority)
- [Testing Strategy](#testing-strategy)

---

## Current Implementation Summary

### What Works Well

✅ **Iterative Context Gathering**: Retrieves additional context when LLM identifies gaps
✅ **LLM-Guided Evaluation**: Uses `gpt-4.1-mini` to assess context sufficiency
✅ **Deduplication**: Prevents duplicate chunks across hops
✅ **Cost Tracking**: Monitors evaluation costs per hop
✅ **Structured Output**: JSON schema ensures consistent evaluation format

### Current Limitations

⚠️ **Max 1 Hop**: `RAG_MAX_HOPS = 1` limits iterative improvement
⚠️ **Generic Prompt**: Evaluation prompt could be more specific to Kill Team rules
⚠️ **No Metadata Filtering**: Doesn't leverage doc_type, source, or other metadata
⚠️ **Sequential Processing**: Hops run one at a time, increasing latency
⚠️ **No Confidence Scoring**: Can't measure certainty of "can_answer" decision
⚠️ **Fixed Stopping**: Only stops when `can_answer = true` or max hops reached

### Current Performance Baseline

**Typical Query (RAG_MAX_HOPS = 1)**:
- Simple query: 2-3s total (initial retrieval + LLM generation)
- 1-hop query: 4-5s total (initial retrieval + hop evaluation + 2nd retrieval + LLM generation)

**Latency Breakdown** (per hop):
- Vector embedding: ~100-200ms
- ChromaDB retrieval: ~200-400ms
- Hybrid fusion (BM25 + RRF): ~100-200ms
- LLM evaluation (gpt-4.1-mini): ~1000-2000ms
- **Total per hop: ~1.5-2.5s**

### Files to Modify

- `src/services/rag/multi_hop_retriever.py` - Main retrieval logic
- `prompts/hop-evaluation-prompt.md` - Evaluation prompt
- `src/lib/constants.py` - Configuration parameters
- `tests/quality/` - Quality tests for multi-hop

---

## Recommended Improvements

### Quick Reference: Latency Impact Summary

| Improvement | Latency Impact | When It Matters |
|-------------|----------------|-----------------|
| **1. Increase Max Hops** | +1.5-2.5s per additional hop | Every multi-hop query |
| **2. Improve Prompt** | No change | - |
| **3. Metadata Filtering** | -50-100ms per hop | Every hop (faster retrieval) |
| **4. Query Decomposition** | +1-2s initial, may reduce hops | Complex queries only |
| **5. Confidence Scoring** | No change | - |
| **6. Smart Stopping** | -1.5-5s (reduces hops) | ~30% of queries |
| **7. Parallel Retrieval** | -50-70% per hop batch | Decomposed queries |
| **8. Result Reranking** | +100-200ms | Every multi-hop query |

**Net Impact** (all improvements combined):
- Best case: +2-3s (smart stopping saves hops)
- Worst case: +5-6s (all 3 hops needed)
- Average: +3-4s (2 hops typical)

---

### 1. Increase Max Hops (Quick Win)

**Effort**: 5 minutes
**Impact**: High
**Cost**: +$0.0001-0.0002 per hop (gpt-4.1-mini evaluation)
**Latency**: +1.5-2.5s per hop (retrieval + evaluation)

#### Current State

```python
# src/lib/constants.py
RAG_MAX_HOPS = 1  # Initial + 1 additional retrieval
```

**Problem**: Many complex queries require more than 2 total retrievals (initial + 1 hop)

#### Proposed Change

```python
# src/lib/constants.py
RAG_MAX_HOPS = 3  # Initial + up to 3 additional retrievals (4 total)
```

#### Rationale

- Complex Kill Team questions often involve 3+ rule sections:
  - Example: "Can concealed Eliminator use Counteract against engaged Pathfinder?"
    - Hop 0: Eliminator operative rules
    - Hop 1: Counteract strategic ploy rules
    - Hop 2: Conceal order restrictions
    - Hop 3: Engage order effects
- Stanford RAPTOR research shows diminishing returns after 3-4 hops
- Cost impact minimal: ~$0.0003 total for 3 hops
- Latency impact: +4.5-7.5s for 3 hops (each hop = retrieval ~500ms + LLM evaluation ~1-2s)

#### Testing

```bash
# Before: Test with RAG_MAX_HOPS = 1
python -m src.cli query "Can concealed Eliminator use Counteract against engaged enemy?" --max-hops 1

# After: Test with RAG_MAX_HOPS = 3
# Edit src/lib/constants.py: RAG_MAX_HOPS = 3
python -m src.cli query "Can concealed Eliminator use Counteract against engaged enemy?" --max-hops 3

# Compare total chunks, relevance, and hop count
```

---

### 2. Improve Hop Evaluation Prompt

**Effort**: 2-3 hours
**Impact**: High
**Cost**: No change (same LLM calls, better quality)
**Latency**: No change

#### Current Issues

The current prompt (`prompts/hop-evaluation-prompt.md`) is good but could be more specific:

1. **Missing Domain Guidance**: Could emphasize Kill Team-specific rule categories
2. **Vague Examples**: Generic examples don't show nuanced scenarios
3. **No Prioritization**: Doesn't guide which gaps are most important
4. **Limited Context About Retrieved Chunks**: Doesn't show metadata (source, doc_type)

#### Proposed Enhancements

**File**: `prompts/hop-evaluation-prompt.md`

##### Enhancement A: Add Kill Team Rule Category Checklist

```markdown
# Kill Team Rule Categories to Check

When evaluating context sufficiency, explicitly check for these Kill Team rule categories:

1. **Operative Definitions**: Datasheets, stat lines, equipment
2. **Abilities & Keywords**: Unique abilities, weapon special rules, keywords (Lethal, Accurate, etc.)
3. **Core Mechanics**: Orders (Conceal/Engage), actions (Move, Shoot, Charge, etc.), phases
4. **Tactical Operations (TacOps)**: Specific TacOp requirements and scoring
5. **Terrain Rules**: Cover, vantage points, traverse, barricades
6. **Faction-Specific Rules**: Team-wide abilities, faction keywords
7. **FAQs & Errata**: Official clarifications that override base rules

For each missing category, identify the specific term/rule name needed.
```

##### Enhancement B: Improved Examples with Metadata

```markdown
**Example 1 – Sufficient Context (Multi-Category)**
User: "Can I shoot during Conceal order?"
Context:
  1. **Core Rules - Orders** (source: kill-team-core-rules.md)
     Conceal order: Operative cannot perform Shoot or Overwatch actions...
  2. **Core Rules - Actions** (source: kill-team-core-rules.md)
     Shoot action: Select ranged weapon and target...

Response:
```json
{
 "can_answer": true,
 "reasoning": "I have Shoot action definition (Core Rules) and Conceal order restrictions (Core Rules). Sufficient to answer definitively.",
 "missing_query": null
}
```

**Example 2 – Missing FAQ/Errata**
User: "Does Blast ignore cover?"
Context:
  1. **Core Rules - Cover** (source: kill-team-core-rules.md)
     Cover provides +1 to save...
  2. **Core Rules - Weapons** (source: kill-team-core-rules.md)
     Blast keyword: When shooting, hit automatically within range...

Response:
```json
{
 "can_answer": false,
 "reasoning": "I have Blast weapon definition and Cover mechanics from Core Rules, but this interaction has an FAQ entry that clarifies special cases. Need official FAQ.",
 "missing_query": "Blast FAQ"
}
```

**Example 3 – Prioritizing Missing Context**
User: "Can Pathfinder Marksman shoot through Vantage terrain?"
Context:
  1. **Team Rules - Pathfinders** (source: pathfinder-team.md)
     Faction ability: Recon...
  2. **Core Rules - Terrain** (source: kill-team-core-rules.md)
     Light terrain: Models can move through...

Response:
```json
{
 "can_answer": false,
 "reasoning": "I have Pathfinder faction rules and basic terrain rules, but missing Vantage terrain definition (critical for shooting interactions) and Marksman operative's specific abilities.",
 "missing_query": "Vantage, Pathfinder Marksman"
}
```
```

##### Enhancement C: Add Progressive Gap Analysis

```markdown
# Progressive Gap Analysis

When evaluating context across multiple hops:

**Hop 1** (after initial retrieval):
- Be CONSERVATIVE: Flag missing context even if you could attempt an answer
- Prioritize getting ALL potentially relevant definitions

**Hop 2+** (after additional retrievals):
- Assess diminishing returns: Are we retrieving genuinely helpful context?
- Consider if question might be unanswerable with current rules (edge case)
- Check for circular reasoning (retrieving same concepts repeatedly)

If by Hop 3 you're still finding gaps, consider:
- Is the question ambiguous or requiring cross-reference of 5+ rules?
- Are we chasing edge cases not explicitly covered in rules?
- Should we answer with available context and note limitations?
```

##### Enhancement D: Metadata-Aware Reasoning

```markdown
# Using Retrieved Chunk Metadata

Each retrieved chunk has metadata:
- `source`: Filename (e.g., "kill-team-core-rules.md", "pathfinder-team.md")
- `doc_type`: Document category ("core-rules", "team-rules", "faq", "ops", "killzone")
- `header`: Section name (e.g., "Movement Phase", "Blast")

In your reasoning, reference these metadata fields:

Good reasoning: "I have Conceal order definition from Core Rules (doc_type: core-rules), but missing Eliminator operative datasheet from Team Rules (doc_type: team-rules)."

Bad reasoning: "I have some rules about Conceal but missing Eliminator info."
```

#### Implementation

**File**: `prompts/hop-evaluation-prompt.md`

```markdown
# Instructions

Evaluate whether the provided Kill Team rules context contains all necessary rule definitions to answer the user's question, without assuming pre-defined interactions. Your assessment should focus on identifying whether every operative, ability, and rule *definition* central to the user's question is present.

# Kill Team Rule Categories

When evaluating context sufficiency, explicitly check for these categories:

1. **Operative Definitions**: Datasheets, stat lines, equipment, weapon profiles
2. **Abilities & Keywords**: Unique abilities, weapon special rules, keywords (Lethal X, Accurate X, Silent, etc.)
3. **Core Mechanics**: Orders (Conceal/Engage), actions (Move, Shoot, Charge, Fight, etc.), phases, activation
4. **Tactical Operations (TacOps)**: Specific TacOp requirements, scoring conditions, restrictions
5. **Terrain Rules**: Cover, vantage points, heavy/light terrain, traverse, barricades
6. **Faction-Specific Rules**: Team-wide abilities, faction keywords, strategic ploys
7. **FAQs & Errata**: Official clarifications that may override base rules

For each missing category, identify the specific term/rule name needed.

# Steps to Follow

1. Review the user's question and identify the primary subject (operative, ability, mechanic, etc.)
2. Determine which Kill Team rule categories are needed to answer fully
3. Check retrieved context for presence of each required category
4. Review metadata (source, doc_type, header) to verify context origin and completeness
5. If insufficient, list which specific terms or rule names are missing

# Progressive Gap Analysis

**Hop 1** (after initial retrieval):
- Be CONSERVATIVE: Flag missing context even if partial answer is possible
- Prioritize getting ALL definitions that might be relevant

**Hop 2+** (after additional retrievals):
- Assess if new retrieval is adding value or redundancy
- Check if gaps are due to ambiguous question or true missing rules
- Consider if edge case is simply not covered in official rules

# User Question
{user_query}

# Retrieved Context
{retrieved_chunks}

# Constraints

- Focus strictly on rule definitions, not pre-existing or assumed interactions
- Only refer to official Kill Team terminology
- Reference metadata in reasoning (e.g., "I have X from Core Rules (doc_type: core-rules)")
- Respond ONLY with valid JSON (no markdown, no explanation outside JSON)
- Reasoning must cite sources (e.g., "I have Counteract definition from Core Rules and Conceal restrictions from Core Rules")
- Each retrieval query should be under 100 characters and focus on specific rules/operatives/abilities
- If sufficient context: set `missing_query` to null
- If missing context: specify exact term names (NO additional words like "rules", "definition", "ability")
- `missing_query` should be comma-separated list of missing terms ONLY

**Bad `missing_query` examples:**
- "Blast weapon minimum range and damage application within blast radius" (too verbose)
- "Is Guard action treated as Shoot action" (phrased as question)
- "Rules about cover" (too generic)

**Good `missing_query` examples:**
- "Blast" (just the keyword/rule name)
- "Guard" (just the action name)
- "Vantage, Pathfinder Marksman" (comma-separated terms)

# Examples

**Example 1 – Sufficient Context (Multi-Category)**
User: "Can I shoot during Conceal order?"
Context:
  1. **Core Rules - Orders** (source: kill-team-core-rules.md, doc_type: core-rules)
     Conceal order: Operative cannot perform Shoot or Overwatch actions...
  2. **Core Rules - Actions** (source: kill-team-core-rules.md, doc_type: core-rules)
     Shoot action: Select ranged weapon and target...

Response:
```json
{
 "can_answer": true,
 "reasoning": "I have Shoot action definition from Core Rules (doc_type: core-rules) and Conceal order restrictions from Core Rules. Sufficient to answer definitively.",
 "missing_query": null
}
```

**Example 2 – Missing Operative Definition**
User: "Can Pathfinder Marksman shoot through Vantage terrain?"
Context:
  1. **Team Rules - Pathfinders** (source: pathfinder-team.md, doc_type: team-rules)
     Faction ability: Recon - Can perform additional actions...
  2. **Core Rules - Terrain** (source: kill-team-core-rules.md, doc_type: core-rules)
     Light terrain: Models can move through...

Response:
```json
{
 "can_answer": false,
 "reasoning": "I have Pathfinder faction rules from Team Rules and basic terrain from Core Rules, but missing Vantage terrain definition (critical for shooting rules) and Pathfinder Marksman operative datasheet.",
 "missing_query": "Vantage, Pathfinder Marksman"
}
```

**Example 3 – Missing FAQ**
User: "Does Blast ignore cover?"
Context:
  1. **Core Rules - Cover** (source: kill-team-core-rules.md, doc_type: core-rules)
     Cover provides +1 save characteristic...
  2. **Core Rules - Weapons** (source: kill-team-core-rules.md, doc_type: core-rules)
     Blast: When shooting, hit automatically within blast radius...

Response:
```json
{
 "can_answer": false,
 "reasoning": "I have Blast keyword from Core Rules and Cover mechanics from Core Rules, but this specific interaction (Blast vs Cover) has an FAQ entry with official clarification.",
 "missing_query": "Blast Cover FAQ"
}
```

**Example 4 – Sufficient After Multiple Hops**
User: "Can concealed Eliminator use Counteract against engaged enemy?"
Context (after 2 hops):
  1. **Team Rules - Eliminator** (source: space-marine-team.md, doc_type: team-rules) [Hop 0]
     Eliminator Sniper operative: Equipment includes bolt sniper rifle...
  2. **Strategic Ploys - Counteract** (source: kill-team-core-rules.md, doc_type: core-rules) [Hop 1]
     Counteract: Use when enemy operative activates within engagement range...
  3. **Orders - Conceal** (source: kill-team-core-rules.md, doc_type: core-rules) [Hop 1]
     Conceal order restrictions: Cannot perform Shoot or Overwatch...
  4. **Orders - Engage** (source: kill-team-core-rules.md, doc_type: core-rules) [Hop 2]
     Engage order: Can perform all actions...

Response:
```json
{
 "can_answer": true,
 "reasoning": "I have Eliminator operative from Team Rules, Counteract ploy from Core Rules, Conceal restrictions from Core Rules, and Engage order mechanics from Core Rules. All necessary definitions present to determine interaction.",
 "missing_query": null
}
```

# Use Cases

- Reviewing multi-hop retrieval results for Kill Team rules Q&A systems
- Ensuring all necessary operative, ability, and rule *definitions* are present before answering
- Identifying specific missing terms to retrieve in next hop

Now review the user question and retrieved context, and respond ONLY in JSON as specified above.
```

#### Testing

```bash
# Test improved prompt with complex query
python -m src.cli query "Can Pathfinder Marksman shoot through Vantage terrain while concealed?" --max-hops 3 --rag-only

# Check logs for:
# - Better reasoning quality (references metadata, categories)
# - More focused missing_query values
# - Progressive gap analysis across hops
```

---

### 3. Add Metadata-Based Filtering

**Effort**: 4-6 hours
**Impact**: Medium-High
**Cost**: No change (improves precision, reduces noise)
**Latency**: -50-100ms per hop (smaller search space in ChromaDB)

#### Current State

Metadata exists but is **not used for filtering** during retrieval:

```python
# Current: No metadata filtering
results = self.vector_db.query(
    query_embeddings=[query_embedding],
    n_results=request.max_chunks,
    # where=None  ← No filtering!
)
```

#### Proposed Change

**Add intelligent metadata filtering based on query analysis**

##### Option A: Simple Keyword-Based Filtering

```python
# src/services/rag/retriever.py

def _infer_doc_type_filter(self, query: str) -> Optional[str]:
    """Infer doc_type filter from query keywords.

    Args:
        query: User query text

    Returns:
        doc_type to filter by, or None for no filter
    """
    query_lower = query.lower()

    # Team-specific queries
    team_names = ["pathfinder", "eliminator", "space marine", "tau", "ork", "aeldari", "tyranid"]
    if any(team in query_lower for team in team_names):
        return "team-rules"

    # TacOp queries
    if "tacop" in query_lower or "tactical operation" in query_lower or "tac op" in query_lower:
        return "ops"

    # FAQ queries
    if "faq" in query_lower or "errata" in query_lower or "clarification" in query_lower:
        return "faq"

    # Killzone terrain queries
    if "killzone" in query_lower or "terrain board" in query_lower:
        return "killzone"

    # Default: no filter (search all)
    return None

def _build_metadata_filter(self, query: str, hop_num: int = 0) -> Optional[Dict[str, Any]]:
    """Build metadata filter for retrieval.

    Args:
        query: User query
        hop_num: Current hop number (0=initial)

    Returns:
        ChromaDB where clause, or None
    """
    doc_type = self._infer_doc_type_filter(query)

    if doc_type:
        logger.debug(f"metadata_filter_applied", doc_type=doc_type, hop=hop_num)
        return {"doc_type": doc_type}

    return None

# In retrieve() method:
def retrieve(self, request: RetrieveRequest, query_id: UUID):
    # ...existing code...

    # Build metadata filter
    where_filter = self._build_metadata_filter(request.query)

    # Query with filter
    results = self.vector_db.query(
        query_embeddings=[query_embedding],
        n_results=request.max_chunks,
        where=where_filter,  # ← Apply filter
    )

    # ...rest of code...
```

##### Option B: LLM-Based Filter Selection (Advanced)

```python
async def _select_doc_type_with_llm(self, query: str) -> List[str]:
    """Use LLM to select relevant doc_types for query.

    Args:
        query: User query

    Returns:
        List of doc_types to search
    """
    prompt = f"""Which Kill Team rule document types are needed for this question?

Question: {query}

Document types:
- core-rules: Core game mechanics (orders, actions, phases, combat)
- team-rules: Faction-specific operatives, abilities, equipment
- faq: Official FAQs and errata
- ops: Tactical operations and missions
- killzone: Terrain and killzone-specific rules

Respond with comma-separated list (or "all" for no filter).
Examples:
- "Can I shoot while concealed?" → "core-rules"
- "Can Pathfinder Marksman use Vantage?" → "team-rules,core-rules"
- "Track Enemy TacOp scoring?" → "ops,core-rules"

Answer (comma-separated doc types or "all"):"""

    # Call fast model (gpt-4.1-mini, ~50 tokens)
    response = await self.evaluation_llm.generate_text(prompt, max_tokens=50)

    if "all" in response.lower():
        return []  # No filter

    return [dt.strip() for dt in response.split(",")]
```

##### Benefits

- **Reduced Noise**: Filter out irrelevant document types
- **Improved Precision**: More focused retrieval
- **Faster Retrieval**: Smaller search space
- **Better Hop Quality**: Subsequent hops can adjust filters based on gaps

##### Drawbacks

- **Risk of Over-Filtering**: Might miss relevant cross-references
- **Keyword Brittleness**: Simple keyword matching may fail on complex queries
- **Added Complexity**: More logic to maintain

##### Testing

```bash
# Test with team-specific query (should filter to team-rules)
python -m src.cli query "Can Pathfinder Marksman move through heavy terrain?" --rag-only

# Check logs for:
# - "metadata_filter_applied" with doc_type=team-rules
# - Retrieved chunks should be from pathfinder-team.md

# Test with core rules query (should filter to core-rules)
python -m src.cli query "Can I charge after performing a Dash action?" --rag-only

# Should filter to doc_type=core-rules
```

---

### 4. Implement Query Decomposition

**Effort**: 1-2 days
**Impact**: High
**Cost**: +$0.0002-0.0005 per query (one LLM call for decomposition)
**Latency**: +1-2s (initial decomposition LLM call, but may reduce total hops needed)

#### Concept

Break complex questions into focused sub-queries for better retrieval precision.

#### Example

**Original**: "Can concealed Eliminator use Counteract against engaged Pathfinder?"

**Decomposed**:
1. "Eliminator operative datasheet and equipment"
2. "Counteract strategic ploy rules"
3. "Conceal order restrictions on abilities"
4. "Engage order effects on targeting"

#### Implementation

**File**: `src/services/rag/query_decomposer.py` (new)

```python
"""Query decomposition for multi-hop retrieval."""

from typing import List
from src.services.llm.factory import LLMProviderFactory
from src.lib.constants import RAG_HOP_EVALUATION_MODEL
from src.lib.logging import get_logger

logger = get_logger(__name__)


class QueryDecomposer:
    """Decomposes complex queries into focused sub-queries."""

    def __init__(self, llm_model: str = RAG_HOP_EVALUATION_MODEL):
        self.llm = LLMProviderFactory.create(llm_model)
        self.prompt_template = self._load_prompt()

    def _load_prompt(self) -> str:
        return """Break down this Kill Team rules question into 2-4 focused sub-queries.

Each sub-query should target a specific rule definition, operative, ability, or mechanic.

Question: {query}

Examples:

Question: "Can concealed Eliminator use Counteract against engaged enemy?"
Sub-queries:
1. Eliminator operative
2. Counteract strategic ploy
3. Conceal order restrictions
4. Engage order targeting rules

Question: "Does Vantage affect Track Enemy TacOp with Seek Light?"
Sub-queries:
1. Vantage terrain rules
2. Track Enemy tactical operation
3. Seek Light weapon special rule

Now decompose the question above into 2-4 focused sub-queries (one per line):"""

    async def decompose(self, query: str) -> List[str]:
        """Decompose complex query into sub-queries.

        Args:
            query: User's complex question

        Returns:
            List of focused sub-queries (2-4 items)
        """
        prompt = self.prompt_template.replace("{query}", query)

        response = await self.llm.generate_text(
            prompt=prompt,
            max_tokens=200,
            temperature=0.0,
        )

        # Parse line-separated sub-queries
        sub_queries = [
            line.strip().lstrip("0123456789.-) ")
            for line in response.strip().split("\n")
            if line.strip()
        ]

        # Limit to 2-4 sub-queries
        sub_queries = sub_queries[:4]

        logger.info(
            "query_decomposed",
            original=query,
            sub_queries=sub_queries,
            count=len(sub_queries),
        )

        return sub_queries
```

**Integration**: `src/services/rag/multi_hop_retriever.py`

```python
class MultiHopRetriever:
    def __init__(self, ..., use_query_decomposition: bool = False):
        self.use_query_decomposition = use_query_decomposition
        if use_query_decomposition:
            from src.services.rag.query_decomposer import QueryDecomposer
            self.query_decomposer = QueryDecomposer()

    async def retrieve_multi_hop(self, query: str, ...):
        # Decompose query if enabled
        if self.use_query_decomposition:
            sub_queries = await self.query_decomposer.decompose(query)

            # Retrieve for each sub-query
            for sub_query in sub_queries:
                sub_context, _, _ = self.base_retriever.retrieve(
                    RetrieveRequest(query=sub_query, ...)
                )
                # Merge unique chunks
                # ...
        else:
            # Standard multi-hop flow
            # ...
```

**Configuration**: `src/lib/constants.py`

```python
# Query decomposition for complex questions
RAG_ENABLE_QUERY_DECOMPOSITION = False  # Set True to enable
RAG_DECOMPOSITION_MODEL = "gpt-4.1-mini"  # Fast model for decomposition
```

#### Benefits

- **Better Precision**: Each sub-query is more focused
- **Comprehensive Coverage**: Ensures all question aspects are searched
- **Explainability**: User can see which sub-queries were used

#### Testing

```bash
# Enable query decomposition
# Edit constants.py: RAG_ENABLE_QUERY_DECOMPOSITION = True

python -m src.cli query "Can concealed Eliminator use Counteract against engaged Pathfinder?" --rag-only

# Check logs for:
# - "query_decomposed" with list of sub-queries
# - Retrieval for each sub-query
# - Merged results
```

---

### 5. Add Confidence Scoring

**Effort**: 3-4 hours
**Impact**: Medium
**Cost**: No change (same LLM calls, just additional field)
**Latency**: No change

#### Concept

Add confidence score to `can_answer` decision to enable smarter stopping.

#### Current Schema

```python
HOP_EVALUATION_SCHEMA = {
    "can_answer": {"type": "boolean"},
    "reasoning": {"type": "string"},
    "missing_query": {"type": "string"},
}
```

#### Proposed Schema

```python
HOP_EVALUATION_SCHEMA = {
    "can_answer": {"type": "boolean"},
    "confidence": {
        "type": "string",
        "enum": ["high", "medium", "low"],
        "description": "Confidence in can_answer decision (high=very certain, medium=somewhat certain, low=uncertain)"
    },
    "reasoning": {"type": "string"},
    "missing_query": {"type": "string"},
}
```

#### Usage

```python
# In multi_hop_retriever.py
if evaluation.can_answer and evaluation.confidence == "high":
    # Stop immediately
    break
elif evaluation.can_answer and evaluation.confidence == "medium":
    # Maybe retrieve one more hop for confirmation
    if hop_num < self.max_hops:
        continue
    else:
        break
elif evaluation.can_answer and evaluation.confidence == "low":
    # Definitely retrieve more context
    continue
```

#### Benefits

- **Smarter Stopping**: Don't stop on uncertain "can_answer=true"
- **Quality Gating**: Can reject low-confidence answers
- **Analytics**: Track confidence distribution

---

### 6. Implement Smart Stopping

**Effort**: 2-3 hours
**Impact**: Medium
**Cost**: Reduces cost (stops earlier when appropriate)
**Latency**: -1.5-5s (reduces unnecessary hops by ~1-3 on average)

#### Concept

Stop hopping early if diminishing returns detected.

#### Implementation

```python
# In multi_hop_retriever.py

def _detect_diminishing_returns(
    self,
    hop_evaluations: List[HopEvaluation],
    new_chunks_per_hop: List[int],
) -> bool:
    """Detect if additional hops are adding value.

    Args:
        hop_evaluations: Evaluations from each hop
        new_chunks_per_hop: Count of new unique chunks per hop

    Returns:
        True if diminishing returns detected
    """
    # Stop if last 2 hops retrieved <2 new chunks each
    if len(new_chunks_per_hop) >= 2:
        if new_chunks_per_hop[-1] <= 1 and new_chunks_per_hop[-2] <= 1:
            logger.info("smart_stop_low_new_chunks", reason="<2 new chunks in last 2 hops")
            return True

    # Stop if reasoning is repetitive (same missing terms)
    if len(hop_evaluations) >= 2:
        last_missing = hop_evaluations[-1].missing_query or ""
        prev_missing = hop_evaluations[-2].missing_query or ""

        if last_missing and prev_missing:
            # Check overlap
            last_terms = set(last_missing.lower().split(","))
            prev_terms = set(prev_missing.lower().split(","))
            overlap = last_terms & prev_terms

            if len(overlap) / len(last_terms) > 0.7:  # 70% overlap
                logger.info("smart_stop_repetitive_gaps", reason="Same missing terms requested")
                return True

    return False

# In retrieve_multi_hop():
new_chunks_per_hop = []

for hop_num in range(1, self.max_hops + 1):
    # ...existing evaluation...

    # Track new chunks
    new_chunks_per_hop.append(len(new_chunks))

    # Check for diminishing returns
    if self._detect_diminishing_returns(hop_evaluations, new_chunks_per_hop):
        logger.info("multi_hop_early_stop", hop=hop_num, reason="diminishing_returns")
        break
```

---

### 7. Enable Parallel Hop Retrieval

**Effort**: 1 day
**Impact**: Medium-High (significant latency reduction)
**Cost**: No change (same retrievals, just parallel)
**Latency**: -50-70% per hop batch (4 sequential sub-queries at 500ms each = 2s → parallel = 500ms)

#### Concept

If query decomposition generates multiple sub-queries, retrieve them in parallel.

#### Implementation

```python
import asyncio

async def retrieve_multi_hop(self, query: str, ...):
    # If using decomposition, retrieve sub-queries in parallel
    if self.use_query_decomposition:
        sub_queries = await self.query_decomposer.decompose(query)

        # Parallel retrieval
        sub_contexts = await asyncio.gather(*[
            self._retrieve_for_subquery(sq, context_key, query_id)
            for sq in sub_queries
        ])

        # Merge all chunks
        for sub_context in sub_contexts:
            # Deduplicate and merge
            # ...
```

#### Benefits

- **Reduced Latency**: Parallel retrieval faster than sequential
- **Better UX**: Faster responses to users

---

### 8. Add Hop Result Reranking

**Effort**: 4-5 hours
**Impact**: Medium-High
**Cost**: No change (reranking is computational, no LLM calls)
**Latency**: +100-200ms (cosine similarity calculations for all chunks)

#### Concept

After accumulating chunks across hops, rerank them by relevance to original query.

#### Implementation

```python
def _rerank_accumulated_chunks(
    self,
    original_query: str,
    chunks: List[DocumentChunk],
) -> List[DocumentChunk]:
    """Rerank accumulated chunks by relevance to original query.

    Args:
        original_query: User's original question
        chunks: All accumulated chunks from hops

    Returns:
        Chunks sorted by relevance to original query
    """
    # Generate embedding for original query
    query_embedding = self.base_retriever.embedding_service.embed_text(original_query)

    # Calculate relevance for each chunk
    for chunk in chunks:
        # Assuming we store embeddings with chunks or can retrieve them
        chunk_embedding = ...  # Get chunk embedding

        # Cosine similarity
        relevance = calculate_cosine_similarity(query_embedding, chunk_embedding)
        chunk.relevance_score = relevance

    # Sort by relevance DESC
    chunks.sort(key=lambda c: c.relevance_score, reverse=True)

    return chunks

# In retrieve_multi_hop():
# After all hops complete
accumulated_chunks = self._rerank_accumulated_chunks(query, accumulated_chunks)
```

---

## Implementation Priority

### Phase 1: Quick Wins (Week 1)

1. **Increase Max Hops** (5 min)
   - Change `RAG_MAX_HOPS = 1` to `3`
   - Test with quality test suite

2. **Improve Hop Evaluation Prompt** (2-3 hours)
   - Implement enhanced prompt with categories, metadata awareness, progressive analysis
   - Test with complex queries

### Phase 2: High-Impact Enhancements (Week 2-3)

3. **Add Metadata-Based Filtering** (4-6 hours)
   - Start with simple keyword-based filtering
   - Test precision improvement

4. **Implement Query Decomposition** (1-2 days)
   - Build QueryDecomposer class
   - Integrate with multi-hop
   - Test coverage improvement

### Phase 3: Advanced Optimizations (Week 4)

5. **Add Confidence Scoring** (3-4 hours)
6. **Implement Smart Stopping** (2-3 hours)
7. **Enable Parallel Retrieval** (1 day)
8. **Add Result Reranking** (4-5 hours)

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/rag/test_multi_hop_improvements.py

def test_metadata_filter_inference():
    """Test that doc_type filter is correctly inferred from query."""
    retriever = RAGRetriever()

    assert retriever._infer_doc_type_filter("Can Pathfinder shoot?") == "team-rules"
    assert retriever._infer_doc_type_filter("Can I charge after Dash?") == "core-rules"
    assert retriever._infer_doc_type_filter("Track Enemy TacOp scoring?") == "ops"

def test_smart_stopping_diminishing_returns():
    """Test that smart stopping detects diminishing returns."""
    retriever = MultiHopRetriever()

    # Last 2 hops retrieved <2 chunks each
    new_chunks = [5, 3, 1, 1]
    assert retriever._detect_diminishing_returns([], new_chunks) is True

    # Still getting new chunks
    new_chunks = [5, 4, 3, 3]
    assert retriever._detect_diminishing_returns([], new_chunks) is False
```

### Quality Tests

```yaml
# tests/quality/multi_hop_improvements_tests.yaml

- id: multi-section-pathfinder-vantage
  query: "Can Pathfinder Marksman shoot through Vantage terrain while concealed?"
  tags: [multi-hop, multi-section, team-rules, core-rules]
  expected_hops: 2-3
  expected_sections:
    - "Pathfinder Marksman operative"
    - "Vantage terrain rules"
    - "Conceal order shooting restrictions"
  expected_metadata_filter: "team-rules,core-rules"
  min_score: 0.85

- id: decomposition-eliminator-counteract
  query: "Can concealed Eliminator use Counteract against engaged enemy?"
  tags: [multi-hop, query-decomposition]
  expected_sub_queries:
    - "Eliminator operative"
    - "Counteract strategic ploy"
    - "Conceal order"
    - "Engage order"
  expected_hops: 2-4
  min_score: 0.85
```

### Integration Tests

```bash
# Test full pipeline with improvements enabled

# Edit constants.py:
# RAG_MAX_HOPS = 3
# RAG_ENABLE_QUERY_DECOMPOSITION = True

python -m src.cli quality-test --test multi-section-pathfinder-vantage
python -m src.cli quality-test --test decomposition-eliminator-counteract

# Compare against baseline (RAG_MAX_HOPS=1, decomposition off)
```

### A/B Comparison

```bash
# Baseline: Current system
RAG_MAX_HOPS=1
python -m src.cli quality-test --all-models > baseline_results.txt

# Improved: Phase 1 + 2
RAG_MAX_HOPS=3
# + Enhanced prompt
# + Metadata filtering
python -m src.cli quality-test --all-models > improved_results.txt

# Compare average scores
python scripts/compare_quality_results.py baseline_results.txt improved_results.txt
```

---

## Expected Outcomes

### Phase 1 (Quick Wins)

- **Hop coverage**: +20-30% queries use 2-3 hops
- **Answer completeness**: +10-15% improvement on multi-section queries
- **Cost**: +$0.0002-0.0003 per query (minimal)
- **Latency**: +4.5-7.5s for 3-hop queries (baseline: 2-3s → 6.5-10.5s total)

### Phase 2 (High-Impact)

- **Retrieval precision**: +15-20% reduction in irrelevant chunks
- **Coverage**: +25% improvement on complex queries
- **Cost**: +$0.0003-0.0005 per query (decomposition)
- **Latency**: +1-2s upfront for decomposition, -0.3-0.5s from metadata filtering (net: +0.5-1.5s)

### Phase 3 (Advanced)

- **Latency**: -20-30% overall (parallel retrieval saves 50-70% per hop batch, smart stopping reduces hops)
- **Efficiency**: -15% average hops (smart stopping)
- **Cost**: Neutral or slightly reduced (fewer unnecessary hops)

### Combined Impact (All Phases)

**Best Case Scenario** (smart stopping kicks in early):
- **Latency**: +2-3s total (vs +7.5s worst case with 3 sequential hops)
- **Quality**: +30-40% improvement on complex queries
- **Cost**: +$0.0003-0.0005 per query

**Worst Case Scenario** (all 3 hops needed, no early stopping):
- **Latency**: +5-6s total (decomposition + 3 hops, but parallel retrieval helps)
- **Quality**: +40-50% improvement on very complex queries
- **Cost**: +$0.0005-0.0008 per query

---

## Decision Point: Multi-Hop vs RAPTOR

After implementing Phase 1 + 2 (2-3 weeks):

**If quality improvement ≥20%**:
- ✅ Multi-hop enhancements successful
- ✅ Defer RAPTOR (not needed)
- ✅ Focus on other features

**If quality improvement <10%**:
- ⚠️ Multi-hop insufficient for complex queries
- ⚠️ Consider RAPTOR implementation
- ⚠️ Analyze which query types still fail

**If quality improvement 10-20%**:
- 🤔 Implement Phase 3 optimizations
- 🤔 Re-evaluate after Phase 3
- 🤔 Consider hybrid: multi-hop + lightweight hierarchical summaries

---

## Next Steps

1. **Immediate**: Increase `RAG_MAX_HOPS` to 3, test with existing quality tests
2. **Week 1**: Improve hop evaluation prompt, measure reasoning quality
3. **Week 2**: Add metadata filtering, test precision improvement
4. **Week 3**: Implement query decomposition, test coverage
5. **Week 4**: Evaluate results, decide on RAPTOR

**Success Criteria**:
- ≥20% improvement in multi-section query accuracy
- ≤$0.0008 cost increase per query
- ≤150% latency increase (baseline 2-3s → target ≤5-7.5s for complex queries)

If criteria met → defer RAPTOR. If not → proceed with RAPTOR implementation plan.

---

## Latency vs Quality Trade-offs

### Acceptable Latency Thresholds

**User Experience Guidelines** (Discord bot context):
- **✅ Excellent**: <3s (instant feel)
- **✅ Good**: 3-5s (acceptable for simple queries)
- **⚠️ Acceptable**: 5-8s (acceptable for complex queries)
- **❌ Slow**: >8s (users may think bot is broken)

**Current System**:
- Simple queries: 2-3s ✅
- 1-hop queries: 4-5s ✅

**With All Improvements**:
- Simple queries: 2-3s ✅ (no change, improvements only affect multi-hop)
- 2-hop queries: 5-6s ⚠️ (acceptable for medium complexity)
- 3-hop queries: 7-9s ⚠️/❌ (pushing limits, but high quality)

### Optimization Strategies by User Tolerance

#### Strategy A: Prioritize Speed (Target <6s)

**Phase 1 Only**:
- Increase max hops to 2 (not 3)
- Skip query decomposition
- Implement smart stopping aggressively
- **Result**: 4-6s typical, 30% quality improvement

#### Strategy B: Balanced (Target <8s)

**Phase 1 + 2 + Smart Stopping**:
- Max hops: 3
- Enhanced prompt
- Metadata filtering
- Smart stopping
- Skip query decomposition (saves 1-2s upfront)
- **Result**: 5-7s typical, 35-40% quality improvement

#### Strategy C: Prioritize Quality (Accept <10s)

**All Phases**:
- Max hops: 3
- All improvements including decomposition and parallel retrieval
- **Result**: 6-9s typical, 40-50% quality improvement

### Recommendation by Use Case

**Discord Bot (Interactive)**:
- Use **Strategy B** (Balanced)
- Users expect <8s for complex questions
- Show typing indicator to manage expectations

**API/Batch Processing**:
- Use **Strategy C** (Quality)
- Latency less critical
- Maximize answer accuracy

**CLI Testing**:
- Use **Strategy C** (Quality)
- Full capabilities for debugging
- Latency irrelevant

### User Communication

**Discord Bot Message**:
```
🔍 Searching Kill Team rules...
[After 3s] 📚 Found initial context, analyzing gaps...
[After 6s] 🎯 Gathering additional rule sections...
[After 8s] ✅ Answer ready!
```

This manages user expectations and makes 7-8s feel acceptable for complex queries.
