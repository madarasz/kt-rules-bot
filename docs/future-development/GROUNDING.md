# LLM Grounding Strategies to Prevent Hallucinated Rule Quotes

**Status**: Research & Planning (2025-11-17)
**Problem**: LLMs sometimes generate plausible-sounding rule quotes that don't exist in the retrieved RAG context
**Impact**: Undermines trust in bot responses despite explicit prohibitions in system prompt

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Research Findings (2025)](#research-findings-2025)
3. [Proposed Grounding Strategies](#proposed-grounding-strategies)
4. [Implementation Roadmap](#implementation-roadmap)
5. [References](#references)

---

## Current State Analysis

### How Grounding Works Today

#### RAG Context Assembly
Located in [src/services/llm/base.py:321-342](../../src/services/llm/base.py#L321-L342):

```python
def _build_prompt(self, user_query: str, context: list[str]) -> str:
    context_text = "\n\n".join(
        [f"[Context {i + 1}]:\n{chunk}" for i, chunk in enumerate(context)]
    )

    return f"""Context from Kill Team 3rd Edition rules:
{context_text}

User Question: {user_query}

Answer:"""
```

**Observations**:
- Context chunks numbered sequentially (`[Context 1]`, `[Context 2]`, etc.)
- No chunk IDs or attribution metadata included
- No explicit instruction to quote verbatim from context
- LLM free to paraphrase or interpolate between chunks

#### System Prompt Instructions
From [prompts/rule-helper-prompt.md](../../prompts/rule-helper-prompt.md):

```markdown
## Steps to Follow
1. **Always ONLY USE the Kill Team rules received in context** to answer questions.
2. **Never guess or invent rules.** If the answer is not in official sources:
   - State that no official answer can be provided.
```

**Observations**:
- Explicit prohibition against inventing rules
- No specific guidance on quote extraction methodology
- Relies on LLM's inherent understanding of "don't hallucinate"

#### Structured Output Enforcement
All providers use tool calling / structured outputs with schema defined in [src/services/llm/base.py:117-166](../../src/services/llm/base.py#L117-L166):

```python
STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "quotes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote_title": {"type": "string"},
                    "quote_text": {"type": "string"}
                },
                "required": ["quote_title", "quote_text"]
            }
        },
        # ... other fields
    }
}
```

**Observations**:
- Forces JSON structure but doesn't constrain content
- No link between `quote_text` and specific RAG chunks
- Schema compliance ≠ factual grounding

#### Quote Faithfulness Tracking
RAGAS evaluation in [tests/quality/ragas_evaluator.py](../../tests/quality/ragas_evaluator.py) measures:

- **Quote Faithfulness**: Do cited quotes appear in retrieved context?
- **Explanation Faithfulness**: Is the explanation supported by context?
- **Quote Precision/Recall**: Are the right chunks retrieved?

**Current results** (from quality tests):
- Quote faithfulness: ~0.7-0.9 (varies by model)
- Some models hallucinate more than others
- No runtime enforcement—detection happens in testing only

### Why Current Approach Has Limitations

1. **No Attribution Link**: Context chunks lack unique IDs that quotes can reference
2. **Paraphrasing Encouraged**: LLM naturally varies wording, which can introduce errors
3. **Post-Hoc Detection**: Quote faithfulness measured after generation, not enforced during
4. **Prompt Alone Insufficient**: Research shows instructions to "not hallucinate" reduce but don't eliminate the issue

---

## Research Findings (2025)

### State-of-the-Art Grounding Techniques

#### 1. Multi-Layered Grounding (Stanford 2024)
Combining RAG + RLHF + Guardrails achieved **96% reduction in hallucinations** vs. baseline.

**Relevance**: We already have RAG; adding validation guardrails and better prompts could yield significant gains.

#### 2. Agentic RAG
Autonomous reasoning and decision-making in retrieval. LLMs iteratively decide if context is sufficient before generating.

**Relevance**: Our multi-hop retrieval ([src/services/rag/multi_hop_retriever.py](../../src/services/rag/multi_hop_retriever.py)) is an early version of this.

#### 3. Prompt Caching (Anthropic 2025)
Cache RAG context with `cache_control` breakpoints:
- **Cost reduction**: 90% (cached tokens cheaper)
- **Latency reduction**: 85% (faster reads from cache)
- **Grounding benefit**: Cached context gets more stable attention

**Implementation**: Claude Opus 4.1, Sonnet 4.5, Haiku 4.5 support prompt caching.

#### 4. Two-Phase Structured Outputs (OpenAI)
Force LLM to select from provided options using "Lists of Literals" in schema.

**Example**:
```python
# Phase 1: Extract candidate quotes with chunk IDs
quotes_schema = {
    "quotes": {
        "type": "array",
        "items": {
            "chunk_id": {"enum": ["chunk_1", "chunk_2", "chunk_3"]},
            "quote_text": {"type": "string"}
        }
    }
}
```

**Limitation**: Max ~500 chunks due to schema size constraints.

#### 5. Extended Citations API (Claude Beta)
Anthropic's citation API automatically returns paragraph/page references from documents.

**Status**: Beta (2025), requires structured document input.

### Key Insights from Literature

- **Prompt engineering alone**: 30-50% reduction in hallucinations
- **Constrained generation**: 70-90% reduction (but limits flexibility)
- **Post-generation validation**: 100% detection (but doesn't prevent)
- **Hybrid approach**: Combining multiple techniques yields best results

---

## Proposed Grounding Strategies

### Strategy 1: Enhanced Prompt Engineering

**Description**: Add explicit quote extraction protocol to system prompt.

**Changes Required**:
1. Update [prompts/rule-helper-prompt.md](../../prompts/rule-helper-prompt.md) with:
   - "Quote Extraction Protocol" section
   - Instruction: "Quotes must be verbatim copies from context, not paraphrases"
   - Few-shot examples of correct vs. incorrect quote attribution

**Example Addition**:
```markdown
## Quote Extraction Protocol
When citing rules, follow these steps:
1. Locate the exact text in the provided context
2. Copy it verbatim into `quote_text` (word-for-word, including punctuation)
3. Do NOT paraphrase or combine quotes from different sections
4. If a rule is not in context, state "No official answer can be provided"

### Correct Example
Context: "An operative can perform the Shoot action with this weapon while it has a Conceal order."
Quote: "An operative can perform the Shoot action with this weapon while it has a Conceal order."

### Incorrect Example (Paraphrase)
Context: "An operative can perform the Shoot action with this weapon while it has a Conceal order."
Quote: "This weapon allows shooting while concealed." ❌ (Not verbatim)
```

**Complexity**: **Low** (prompt changes only)

**Expected Impact**:
- 30-40% reduction in quote hallucinations (based on research)
- Minimal cost increase (~50-100 tokens to system prompt)

**Trade-offs**:
- ✅ Easy to implement and test
- ✅ Works across all LLM providers
- ❌ Still relies on LLM compliance (no hard enforcement)

**Next Steps**:
1. Draft updated prompt
2. Run quality tests with `--all-models` to measure baseline
3. Deploy updated prompt
4. Re-run quality tests to measure improvement
5. Compare `quote_faithfulness` scores

---

### Strategy 2: Context Chunk Attribution

**Description**: Add unique chunk IDs to context and require quotes to reference them.

**Changes Required**:

1. Update `_build_prompt()` in [src/services/llm/base.py](../../src/services/llm/base.py):
   ```python
   def _build_prompt(self, user_query: str, context: list[str], chunk_ids: list[str]) -> str:
       context_text = "\n\n".join([
           f"[CHUNK_{chunk_ids[i]}]:\n{chunk}"
           for i, chunk in enumerate(context)
       ])

       return f"""Context from Kill Team 3rd Edition rules:
   {context_text}

   User Question: {user_query}

   When quoting rules, reference the chunk ID (e.g., CHUNK_abc123).

   Answer:"""
   ```

2. Update `STRUCTURED_OUTPUT_SCHEMA` to include `chunk_id`:
   ```python
   "quotes": {
       "type": "array",
       "items": {
           "quote_title": {"type": "string"},
           "quote_text": {"type": "string"},
           "chunk_id": {"type": "string"}  # NEW
       }
   }
   ```

3. Add post-generation validator (see Strategy 4)

**Complexity**: **Medium** (schema changes, validation logic)

**Expected Impact**:
- Enables 100% detection of hallucinated quotes (via validation)
- Traceability: Users can see which chunk a quote came from
- May improve LLM grounding (explicit attribution requirement)

**Trade-offs**:
- ✅ Enables validation and traceability
- ✅ Works with existing RAG pipeline
- ❌ Adds ~20-50 tokens per chunk (cost increase)
- ❌ Doesn't prevent hallucination, only detects it

**Next Steps**:
1. Implement chunk ID passing through pipeline
2. Update schema and prompt
3. Implement validator (Strategy 4)
4. Test with quality suite

---

### Strategy 3: Prompt Caching (Claude Only)

**Description**: Use Anthropic's prompt caching to cache RAG context.

**Changes Required**:

Update [src/services/llm/claude.py](../../src/services/llm/claude.py) to add cache breakpoints:

```python
async def generate(self, request: GenerationRequest) -> LLMResponse:
    # Build system prompt with cache control
    system_blocks = [
        {
            "type": "text",
            "text": request.config.system_prompt,
            "cache_control": {"type": "ephemeral"}  # Cache system prompt
        }
    ]

    # Build user message with cached context
    context_text = self._build_prompt("", request.context)  # Context only
    user_content = [
        {
            "type": "text",
            "text": context_text,
            "cache_control": {"type": "ephemeral"}  # Cache context
        },
        {
            "type": "text",
            "text": f"User Question: {request.prompt}\n\nAnswer:"
        }
    ]

    response = await self.client.messages.create(
        model=self.model,
        max_tokens=request.config.max_tokens,
        system=system_blocks,  # Changed from string to blocks
        messages=[{"role": "user", "content": user_content}],
        # ... rest of parameters
    )
```

**Complexity**: **Medium** (Claude-specific implementation)

**Expected Impact**:
- **Cost**: 90% reduction on cached tokens (significant for repeated queries)
- **Latency**: 85% reduction on cache hits
- **Grounding**: Cached context may receive more consistent attention
- Only benefits Claude models

**Trade-offs**:
- ✅ Massive cost/latency savings for popular queries
- ✅ May improve grounding (research suggests cached context is more stable)
- ❌ Claude-only (not portable to other providers)
- ❌ Requires cache warm-up (first query still full cost)

**Cache Strategy**:
- Cache system prompt: Changes rarely (personality updates)
- Cache RAG context: Different per query cluster (e.g., "Conceal order" questions)
- Cache duration: 5 minutes (Anthropic's current limit)

**Next Steps**:
1. Implement cache control in Claude adapter
2. Add cache hit/miss metrics to logging
3. Monitor cost savings via analytics DB
4. Measure impact on `quote_faithfulness` scores

---

### Strategy 4: Post-Generation Quote Validator

**Description**: Validate that each quoted rule actually appears in RAG context before returning response.

**Implementation**:

Create new module [src/services/llm/quote_validator.py](../../src/services/llm/quote_validator.py):

```python
"""Post-generation quote validator for grounding enforcement."""

from dataclasses import dataclass
from difflib import SequenceMatcher

@dataclass
class ValidationResult:
    """Result of quote validation."""
    is_valid: bool
    invalid_quotes: list[dict]  # [{quote_text, chunk_id, reason}]
    validation_score: float  # 0-1, fraction of quotes that are valid

class QuoteValidator:
    """Validates quotes against RAG context."""

    def __init__(self, similarity_threshold: float = 0.85):
        """Initialize validator.

        Args:
            similarity_threshold: Minimum similarity for fuzzy matching (0-1)
        """
        self.similarity_threshold = similarity_threshold

    def validate(
        self,
        quotes: list[dict],  # From LLM response JSON
        context_chunks: list[str]
    ) -> ValidationResult:
        """Validate quotes against context chunks.

        Args:
            quotes: List of {"quote_title": ..., "quote_text": ...} dicts
            context_chunks: Retrieved RAG chunks

        Returns:
            ValidationResult with validity status
        """
        invalid_quotes = []

        for quote in quotes:
            quote_text = quote["quote_text"].strip()

            # Check if quote appears in any chunk (exact or fuzzy match)
            found = False
            for chunk in context_chunks:
                if self._is_quote_in_chunk(quote_text, chunk):
                    found = True
                    break

            if not found:
                invalid_quotes.append({
                    "quote_text": quote_text,
                    "quote_title": quote.get("quote_title", ""),
                    "reason": "Quote not found in any RAG context chunk"
                })

        total_quotes = len(quotes)
        valid_quotes = total_quotes - len(invalid_quotes)
        validation_score = valid_quotes / total_quotes if total_quotes > 0 else 1.0

        return ValidationResult(
            is_valid=(len(invalid_quotes) == 0),
            invalid_quotes=invalid_quotes,
            validation_score=validation_score
        )

    def _is_quote_in_chunk(self, quote: str, chunk: str) -> bool:
        """Check if quote appears in chunk (exact or fuzzy).

        Args:
            quote: Quote text to find
            chunk: Context chunk to search

        Returns:
            True if quote found in chunk
        """
        # Normalize: lowercase, strip extra whitespace
        quote_norm = " ".join(quote.lower().split())
        chunk_norm = " ".join(chunk.lower().split())

        # Exact match (fast path)
        if quote_norm in chunk_norm:
            return True

        # Fuzzy match (allows for minor LLM formatting differences)
        # Use sliding window to find best match
        quote_len = len(quote_norm)
        best_similarity = 0.0

        for i in range(len(chunk_norm) - quote_len + 1):
            window = chunk_norm[i:i + quote_len]
            similarity = SequenceMatcher(None, quote_norm, window).ratio()
            best_similarity = max(best_similarity, similarity)

            if best_similarity >= self.similarity_threshold:
                return True

        return False
```

**Integration Point**:

Update [src/services/discord/orchestrator.py](../../src/services/discord/orchestrator.py) or response handler:

```python
from src.services.llm.quote_validator import QuoteValidator

validator = QuoteValidator(similarity_threshold=0.85)

# After LLM generation
response_json = json.loads(llm_response.answer_text)
validation_result = validator.validate(
    quotes=response_json.get("quotes", []),
    context_chunks=[chunk.text for chunk in rag_context.document_chunks]
)

if not validation_result.is_valid:
    # Log validation failure
    logger.warning(
        "quote_validation_failed",
        invalid_count=len(validation_result.invalid_quotes),
        validation_score=validation_result.validation_score
    )

    # Option 1: Reject response and return error
    return "I encountered an issue validating rule quotes. Please try rephrasing your question."

    # Option 2: Filter out invalid quotes and continue
    response_json["quotes"] = [
        q for q in response_json["quotes"]
        if q not in [inv["quote_text"] for inv in validation_result.invalid_quotes]
    ]
```

**Complexity**: **Medium** (new validator module + integration)

**Expected Impact**:
- **Detection**: 100% of hallucinated quotes caught
- **Prevention**: Depends on integration strategy (reject vs. filter)
- **Quality**: Provides hard guarantee for production use

**Trade-offs**:
- ✅ Hard enforcement of grounding (no hallucinated quotes reach users)
- ✅ Works across all LLM providers
- ✅ Provides quantitative validation metrics
- ❌ Adds ~50-100ms latency (validation overhead)
- ❌ False positives possible (LLM formats quote slightly differently)
- ❌ Doesn't prevent LLM from trying to hallucinate (detection, not prevention)

**Tuning Parameters**:
- `similarity_threshold`: 0.85 = allow minor punctuation/whitespace differences
  - Higher (0.95): Stricter, more false positives
  - Lower (0.75): Lenient, may miss paraphrases

**Next Steps**:
1. Implement validator module
2. Add unit tests with known good/bad quotes
3. Integrate into response pipeline
4. Monitor false positive rate
5. Tune similarity threshold based on production data

---

### Strategy 5: Two-Phase Quote Extraction (Advanced)

**Description**: Decompose answer generation into two LLM calls:
1. **Phase 1**: Extract verbatim quotes from context (with chunk IDs)
2. **Phase 2**: Generate explanation using only pre-extracted quotes

**Implementation**:

```python
async def generate_with_two_phase_quotes(
    self,
    user_query: str,
    context_chunks: list[str]
) -> dict:
    """Two-phase generation for guaranteed grounding.

    Phase 1: Extract quotes
    Phase 2: Generate answer using only extracted quotes
    """

    # === PHASE 1: Quote Extraction ===
    extraction_prompt = f"""Task: Extract verbatim rule quotes relevant to the question.

Context chunks:
{self._format_chunks_with_ids(context_chunks)}

Question: {user_query}

Extract ONLY text that appears verbatim in the context chunks above.
Return a list of quotes with their chunk IDs."""

    extraction_schema = {
        "type": "object",
        "properties": {
            "extracted_quotes": {
                "type": "array",
                "items": {
                    "chunk_id": {"type": "string"},
                    "quote_text": {"type": "string"},
                    "rule_name": {"type": "string"}
                }
            }
        }
    }

    phase1_response = await self.llm.generate(
        prompt=extraction_prompt,
        schema=extraction_schema
    )

    extracted_quotes = phase1_response["extracted_quotes"]

    # === PHASE 2: Answer Generation ===
    answer_prompt = f"""Question: {user_query}

Available quotes (use ONLY these, do not add others):
{self._format_quotes(extracted_quotes)}

Generate a complete answer using only the quotes above."""

    phase2_response = await self.llm.generate(
        prompt=answer_prompt,
        schema=STRUCTURED_OUTPUT_SCHEMA
    )

    return phase2_response
```

**Complexity**: **High** (two LLM calls, orchestration logic)

**Expected Impact**:
- **Grounding**: Near 100% (LLM constrained to pre-extracted quotes)
- **Quality**: May reduce hallucinations to near-zero
- **Latency**: 2x (two LLM calls)
- **Cost**: 2x (two LLM calls)

**Trade-offs**:
- ✅ Maximum grounding (LLM can't invent quotes in phase 2)
- ✅ Explainable pipeline (can debug each phase)
- ✅ Phase 1 results reusable across similar queries
- ❌ 2x cost and latency
- ❌ Complex orchestration logic
- ❌ Risk of quote loss (phase 1 might miss relevant quotes)

**Optimization**:
- Cache phase 1 results for similar queries
- Use faster/cheaper model for phase 1 (e.g., GPT-4o-mini)
- Parallel execution if using different providers

**Next Steps**:
1. Prototype with single test case
2. Measure latency/cost overhead
3. Compare `quote_faithfulness` to single-phase
4. Decide if benefits justify 2x cost

---

### Strategy 6: Constrained Decoding for Quotes (Future)

**Description**: Use constrained generation to force LLM to select quotes from context.

**Approaches**:
1. **OpenAI Structured Outputs with Enums**: Define `quote_text` as enum of all context sentences
2. **Outlines / XGrammar**: Use grammar-based constraints (context-free grammar)
3. **Guidance / LMQL**: Constrain generation with templates

**Example (Conceptual)**:
```python
# Dynamically generate schema with quote options
quote_options = extract_all_sentences(context_chunks)

constrained_schema = {
    "quotes": {
        "type": "array",
        "items": {
            "quote_text": {
                "enum": quote_options  # LLM MUST choose from this list
            }
        }
    }
}
```

**Complexity**: **High** (requires provider support or external library)

**Expected Impact**:
- **Grounding**: 100% (LLM cannot hallucinate quotes)
- **Quality**: Perfect quote attribution
- **Flexibility**: Reduced (LLM can't paraphrase or summarize)

**Trade-offs**:
- ✅ Perfect grounding (impossible to hallucinate quotes)
- ✅ Deterministic quote selection
- ❌ OpenAI enum limit: ~500 options (may not fit all context)
- ❌ Provider-specific (OpenAI supports, others may not)
- ❌ Reduces LLM's natural language flexibility
- ❌ Requires sentence segmentation (can introduce errors)

**Limitations**:
- Context may have 10-50 sentences across 5 chunks = 50-250 enum values
- OpenAI limit: ~500 (may work, but schema gets large)
- If context exceeds limit, need chunking strategy

**Status**:
- **OpenAI**: Supported (structured outputs with enums)
- **Anthropic**: Not directly supported (would need external library)
- **Gemini**: Not directly supported
- **Future**: EBNF support may expand options

**Next Steps** (if pursuing):
1. Research OpenAI enum limits with real context sizes
2. Prototype sentence extraction from chunks
3. Test with quality suite
4. Evaluate flexibility vs. grounding trade-off

---

## Implementation Roadmap

### Phase 1: Quick Wins (Low Effort, High Impact)

**Target**: 30-40% reduction in hallucinations within 1 week

1. **Strategy 1: Enhanced Prompt Engineering** ✅ Implement first
   - Update system prompt with quote extraction protocol
   - Add few-shot examples
   - Run quality tests to measure improvement
   - **Effort**: 2-4 hours
   - **Risk**: Low (easily reversible)

### Phase 2: Validation & Metrics (Medium Effort)

**Target**: 100% detection of hallucinated quotes

2. **Strategy 4: Post-Generation Quote Validator**
   - Implement validator module
   - Integrate into response pipeline
   - Add logging/metrics
   - Decide on error handling (reject vs. filter vs. warn)
   - **Effort**: 1-2 days
   - **Risk**: Low (passive detection initially)

3. **Strategy 2: Context Chunk Attribution** (optional, supports Strategy 4)
   - Add chunk IDs to context formatting
   - Update schema to include `chunk_id` in quotes
   - Enable per-quote traceability
   - **Effort**: 4-6 hours
   - **Risk**: Low (additive change)

### Phase 3: Cost Optimization (Medium Effort, Claude Only)

**Target**: 90% cost reduction on cached queries

4. **Strategy 3: Prompt Caching (Claude)**
   - Implement cache control in Claude adapter
   - Add cache metrics to analytics DB
   - Monitor cost savings
   - **Effort**: 1 day
   - **Risk**: Low (Claude-only, doesn't affect other providers)

### Phase 4: Advanced Grounding (High Effort, Experimental)

**Target**: Near-zero hallucinations (if needed)

5. **Strategy 5: Two-Phase Quote Extraction** (evaluate first)
   - Prototype with single test case
   - Measure cost/latency overhead (2x expected)
   - Compare quality improvement to Phase 1+2
   - **Effort**: 2-3 days
   - **Risk**: Medium (complexity, cost)

6. **Strategy 6: Constrained Decoding** (research only)
   - Investigate provider support
   - Prototype with OpenAI enums
   - Evaluate trade-offs
   - **Effort**: 1 week (research + prototype)
   - **Risk**: High (may not be feasible with context sizes)

### Recommended Start

**Begin with Phase 1 (Strategy 1)**:
- Lowest effort, proven impact
- No architectural changes
- Easily measurable with existing quality tests
- If 30-40% reduction insufficient, proceed to Phase 2

**Evaluation Criteria**:
- Run `python -m src.cli quality-test --all-models --runs 5` before/after each phase
- Track `quote_faithfulness` metric from RAGAS evaluator
- Compare across models (some hallucinate more than others)
- Acceptable threshold: `quote_faithfulness >= 0.95` (≤5% hallucination rate)

---

## References

### Academic Research

1. **Stanford 2024**: Multi-layered grounding (RAG + RLHF + Guardrails) → 96% hallucination reduction
2. **Anthropic 2025**: Prompt caching → 90% cost reduction, 85% latency reduction
3. **OpenAI 2025**: Structured outputs with enums → ~30% citation errors remain even with RAG

### Documentation

- [Anthropic Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [RAGAS Faithfulness Metrics](https://docs.ragas.io/en/stable/concepts/metrics/faithfulness.html)
- [Exploring LLM Citation Generation in 2025](https://medium.com/@prestonblckbrn/exploring-llm-citation-generation-in-2025-4ac7c8980794)

### Codebase

- Current RAG context assembly: [src/services/llm/base.py:321-342](../../src/services/llm/base.py#L321-L342)
- System prompt: [prompts/rule-helper-prompt.md](../../prompts/rule-helper-prompt.md)
- Quote faithfulness tracking: [tests/quality/ragas_evaluator.py](../../tests/quality/ragas_evaluator.py)
- Structured output schema: [src/services/llm/base.py:117-166](../../src/services/llm/base.py#L117-L166)

---

## Appendix: Decision Matrix

| Strategy | Effort | Cost Impact | Latency Impact | Grounding Impact | Provider Support |
|----------|--------|-------------|----------------|------------------|------------------|
| **1. Enhanced Prompts** | Low | +2% (prompt tokens) | None | +30-40% | All |
| **2. Chunk Attribution** | Medium | +5% (chunk IDs) | None | Enables validation | All |
| **3. Prompt Caching** | Medium | -90% (cached) | -85% (cached) | +10-20% (est.) | Claude only |
| **4. Quote Validator** | Medium | None | +50-100ms | 100% detection | All |
| **5. Two-Phase Extraction** | High | +100% (2x calls) | +100% (2x calls) | +60-80% | All |
| **6. Constrained Decoding** | High | None | +10-20% | +90-100% | OpenAI (limited) |

**Recommendation**: Start with **Strategy 1** (prompts), add **Strategy 4** (validator) if needed, optimize with **Strategy 3** (caching) for cost.

---

**Last Updated**: 2025-11-17
**Next Review**: After implementing Phase 1 and measuring results
