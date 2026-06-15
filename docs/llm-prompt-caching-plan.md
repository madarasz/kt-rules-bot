# LLM Prompt Caching Plan

Tracks the design and remaining work for Anthropic prompt caching across all prompt types.

## Current State

### What works

`<!--CACHE_BREAK-->` markers in prompt files drive Anthropic cache-control blocks for the **main system prompt** (`base-prompt-template.md`).

Flow:
1. Marker placed in prompt file at the desired cache boundary
2. `build_system_prompt()` strips the marker → clean string for non-Claude providers
3. `build_claude_system_blocks()` splits on the marker → `list[dict]` with `cache_control: ephemeral` on the stable block(s)
4. `claude.py._get_system()` detects the default prompt and substitutes the blocks; custom prompts (e.g. summarizer) pass through as plain strings

### Prompts with markers and their status

| Prompt file | Used by | Default model | Marker strips? | Cache active? |
|---|---|---|---|---|
| `base-prompt-template.md` | Main query flow | Claude | ✅ via `build_system_prompt()` | ✅ (system prompt blocks) |
| `chunk-summary-prompt.md` | `summarizer.py` | Grok | ✅ via `strip_cache_markers()` | ❌ user-msg, not system |
| `hop-evaluation-prompt-with-rule-reference.md` | `multi_hop_retriever.py` | GPT | ✅ via `strip_cache_markers()` | ❌ user-msg, not system |
| `quality-test-custom-judge.md` | `custom_judge.py` | Grok | ✅ via `strip_cache_markers()` | ❌ user-msg, not system |
| `team-extraction-prompt.md` | `download_team.py` | Gemini | ✅ via `strip_cache_markers()` | ❌ extraction path |

---

## Remaining Work: User-Message Caching

Three prompts (summarizer, hop evaluator, custom judge) are large and mostly static. They are passed as user-message content, not as system prompts. Anthropic supports `cache_control` on user message content blocks the same way as system prompt blocks.

### Why it matters

- `hop-evaluation-prompt-with-rule-reference.md`: ~4000 tokens of static instructions + core rules structure (stable per session). Called once per hop, per query. At high query volume this is significant.
- `quality-test-custom-judge.md`: ~3000 tokens of static rubric + examples. Called for every test case × every run.
- `chunk-summary-prompt.md`: ~1500 tokens of static instructions. Called once per ingested file.

### Design

#### 1. `GenerationRequest.prompt` as content blocks

Currently `prompt: str`. For Claude, change to `str | list[dict]`.

```python
@dataclass
class GenerationRequest:
    prompt: str | list[dict]  # str for all providers; list[dict] for Claude with cache blocks
    ...
```

#### 2. Helper: `split_user_prompt_for_cache(text: str) -> str | list[dict]`

Add to `prompt_builder.py`:

```python
def split_user_prompt_for_cache(text: str) -> str | list[dict]:
    """Split user message on CACHE_BREAK_MARKER into cacheable content blocks.

    Returns plain str if no marker (non-Claude path or no caching needed).
    Returns list[dict] with cache_control on stable blocks if marker found.
    """
    if CACHE_BREAK_MARKER not in text:
        return text
    parts = text.split(CACHE_BREAK_MARKER)
    blocks: list[dict] = []
    for i, part in enumerate(parts):
        stripped = part.strip()
        if not stripped:
            continue
        block: dict = {"type": "text", "text": stripped}
        if i < len(parts) - 1:
            block["cache_control"] = {"type": "ephemeral"}
        blocks.append(block)
    return blocks or text
```

#### 3. `claude.py.generate()`: handle list prompt

In the `messages` parameter of both API call sites:

```python
# Current
messages=[{"role": "user", "content": full_prompt}]

# New
user_content = full_prompt if isinstance(full_prompt, str) else full_prompt
messages=[{"role": "user", "content": user_content}]
```

The Anthropic SDK accepts `content` as either `str` or `list[ContentBlock]`.

#### 4. Callers: opt in per-prompt

Each caller that wants Claude caching calls `split_user_prompt_for_cache()` before building `GenerationRequest`:

**`summarizer.py`**:
```python
# After: full_prompt = f"{self.summary_prompt}\n\n{chunk_input}"
# The summary_prompt already has the marker stripped. For Claude, we want to
# cache the static instructions and NOT cache the per-file chunk input.
# So: rebuild with marker intact when provider is Claude, then split.
```

This requires the loaders to optionally keep markers rather than always stripping them.

#### 5. Provider-aware loading

Two options:

**Option A — Two loader variants** (simpler):
```python
load_summary_prompt()         # strips markers (non-Claude)
load_summary_prompt_raw()     # keeps markers (Claude)
```
Caller checks `isinstance(provider, ClaudeAdapter)` and picks the right loader.

**Option B — Unified: always strip in loader, reassemble with marker at call site** (cleaner):
Move the static/dynamic split to the caller, not the file:
```python
# In summarizer
static_part = self.summary_prompt  # already stripped
dynamic_part = chunk_input
if isinstance(self.provider, ClaudeAdapter):
    from src.services.llm.prompt_builder import CACHE_BREAK_MARKER
    full_prompt = f"{static_part}{CACHE_BREAK_MARKER}\n\n{dynamic_part}"
    full_prompt = split_user_prompt_for_cache(full_prompt)
else:
    full_prompt = f"{static_part}\n\n{dynamic_part}"
```

**Recommendation**: Option B. No raw-loading variants needed; the marker in the file just documents where the split point is. The caller reassembles explicitly.

---

## Hop Evaluator Special Case

`hop-evaluation-prompt-with-rule-reference.md` has a complex structure:

```
[static instructions]           ← always the same
[core rules structure]          ← {rule_structure}: stable per session, changes on re-ingest
<!--CACHE_BREAK-->
[team rules]                    ← {team_structure}: filtered per query (dynamic)
[user question]                 ← {user_query}: dynamic
[retrieved context]             ← {retrieved_chunks}: dynamic
```

The `{rule_structure}` (core rules YAML, ~1000 tokens) is stable within a session. For caching to work on the block before the marker, the text must be **identical** across calls. This holds as long as no re-ingest happens between calls — which is true in production (the DB is loaded once at bot startup).

Cache benefit here is high: the instructions + core rules block is ~3000 tokens, called on every hop. At 5 hops/query × 100 queries/day = 500 cache reads/day on the large block.

The current marker placement (between core rules and team rules) is **correct** for this structure.

---

## Implementation Order

1. **Done**: `strip_cache_markers()` called in all 4 loaders — markers no longer leak to LLMs.
2. **Done**: `quality-test-custom-judge.md` marker moved after the static rubric (before `# Important Notes`).
3. **Next** (when Claude usage expands to these paths):
   - Add `split_user_prompt_for_cache()` to `prompt_builder.py`
   - Update `claude.py.generate()` to accept `list[dict]` content
   - Update each caller (summarizer, hop evaluator, custom judge) with Option B reassembly

Priority order for step 3:
1. Hop evaluator — highest call volume, largest stable block
2. Custom judge — run during every quality test
3. Summarizer — one-time per ingestion, lower priority

---

## Notes

- Anthropic cache TTL is 5 minutes (ephemeral). Cache hits require requests within that window with identical content.
- Cache creation costs 25% more than normal input tokens; cache reads cost 10% of normal input tokens.
- Break-even: cache read pays off after ~3 reads of the same block within 5 min. Hop evaluator easily hits this at any real query volume.
- The `beta.messages.parse()` path (structured outputs) used by `claude.py` supports `cache_control` on both system and user content blocks.
