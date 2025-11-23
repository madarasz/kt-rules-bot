# Claude Haiku 4.5 Structured Output Fallback Implementation Plan

**Status**: Planning
**Priority**: Medium
**Complexity**: Moderate
**Estimated Effort**: 1-2 hours (145 lines of code)
**Last Updated**: 2025-11-23

---

## Problem Statement

Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) does not support the new Pydantic structured outputs API (`beta.messages.parse` with `output_format`), resulting in the error:

```
BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error',
'message': "'claude-haiku-4-5-20251001' does not support output_format."}}
```

Claude Sonnet 4.5 and Opus 4.1 support structured outputs, but Haiku requires a fallback to the older "tool use" API approach.

---

## Executive Summary

**Complexity**: MODERATE
**Risk Level**: LOW
**Total Changes**: ~145 lines across 3 files

The solution requires:
- Model detection logic (Simple)
- Dual API path implementation (Moderate)
- Response parsing differences (Moderate)
- Testing requirements (Moderate)

The fallback reuses the battle-tested "tool use" API that was used until commit `ce8d119`, making this a low-risk change.

---

## Model Support Matrix

| Model | Model ID | Structured Outputs | Tool Use |
|-------|----------|-------------------|----------|
| **Claude 4.5 Sonnet** | `claude-sonnet-4-5-20250929` | ✅ Supported | ✅ Supported |
| **Claude 4.1 Opus** | `claude-opus-4-1-20250805` | ✅ Supported | ✅ Supported |
| **Claude 4.5 Haiku** | `claude-haiku-4-5-20251001` | ❌ NOT Supported | ✅ Supported |

**Source**: Anthropic API error message and phased rollout of structured outputs feature. Haiku models typically receive new features after flagship models.

---

## Current Implementation (Structured Outputs Only)

**File**: `src/services/llm/claude.py` (lines 84-106)

```python
# Current implementation - only works with Sonnet/Opus
response = await asyncio.wait_for(
    self.client.beta.messages.parse(
        model=self.model,
        max_tokens=request.config.max_tokens,
        temperature=request.config.temperature,
        system=request.config.system_prompt,
        messages=[{"role": "user", "content": full_prompt}],
        betas=["structured-outputs-2025-11-13"],
        output_format=pydantic_model,  # ← Haiku doesn't support this
    ),
    timeout=request.config.timeout_seconds,
)

# Extract structured output from parsed response
parsed_output = response.parsed_output
answer_text = parsed_output.model_dump_json()
```

---

## Old Format (Tool Use - Pre-Pydantic Migration)

**Found in**: Git commit `ce8d119` (before Pydantic migration)

```python
# Old implementation - works with ALL Claude models
response = await asyncio.wait_for(
    self.client.messages.create(
        model=self.model,
        max_tokens=request.config.max_tokens,
        temperature=request.config.temperature,
        system=request.config.system_prompt,
        messages=[{"role": "user", "content": full_prompt}],
        tools=[{
            "name": "format_kill_team_answer",
            "description": "Format Kill Team rules answer with quotes and explanation",
            "input_schema": STRUCTURED_OUTPUT_SCHEMA  # JSON schema dict
        }],
        tool_choice={
            "type": "tool",
            "name": "format_kill_team_answer"
        }
    ),
    timeout=request.config.timeout_seconds,
)

# Extract JSON from tool use block
tool_use_block = None
for block in response.content:
    if hasattr(block, 'type') and block.type == 'tool_use':
        tool_use_block = block
        break

if not tool_use_block:
    raise Exception("Expected tool_use block but none returned")

tool_input = tool_use_block.input  # Dict with structured data
answer_text = json.dumps(tool_input)  # Convert to JSON string
```

**Key Differences**:

| Aspect | Structured Outputs | Tool Use |
|--------|-------------------|----------|
| API Method | `beta.messages.parse()` | `messages.create()` |
| Schema Format | Pydantic model | JSON dict |
| Schema Location | `output_format` parameter | `tools[0].input_schema` |
| Response Structure | `response.parsed_output` (Pydantic) | `response.content[0].input` (dict) |
| Beta Header | Required (`structured-outputs-2025-11-13`) | Not required |

---

## Implementation Plan

### 1. Add Model Capability Constants

**File**: `src/lib/constants.py`
**Location**: After line 61 (PDF extraction providers section)

```python
# Claude models that support structured outputs (beta.messages.parse)
# Models not in this list use tool use fallback
CLAUDE_MODELS_WITH_STRUCTURED_OUTPUTS = [
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-1-20250805",
    # claude-haiku-4-5-20251001 not yet supported
]
```

**Lines Added**: ~5

---

### 2. Update Claude Adapter with Dual API Path

**File**: `src/services/llm/claude.py`

#### 2a. Add Import (line ~8)

```python
import json  # Add for tool use response serialization
```

#### 2b. Import Constants (line ~20)

```python
from src.lib.constants import CLAUDE_MODELS_WITH_STRUCTURED_OUTPUTS
```

#### 2c. Import JSON Schemas (line ~27)

```python
from src.services.llm.base import (
    STRUCTURED_OUTPUT_SCHEMA,      # Add this
    HOP_EVALUATION_SCHEMA,          # Add this
    # ... existing imports ...
)
```

#### 2d. Replace API Call Section (lines 75-106)

```python
# Select schema based on configuration
schema_type = request.config.structured_output_schema

if schema_type == "hop_evaluation":
    pydantic_model = HopEvaluation
    json_schema = HOP_EVALUATION_SCHEMA
    tool_name = "evaluate_context_sufficiency"
    tool_description = "Evaluate if retrieved context is sufficient to answer the question"
else:  # "default"
    pydantic_model = Answer
    json_schema = STRUCTURED_OUTPUT_SCHEMA
    tool_name = "format_kill_team_answer"
    tool_description = "Format Kill Team rules answer with quotes and explanation"

# Check if model supports structured outputs
supports_structured_outputs = self.model in CLAUDE_MODELS_WITH_STRUCTURED_OUTPUTS

if supports_structured_outputs:
    # NEW API: Use Pydantic structured output with beta.messages.parse()
    logger.debug(f"Using structured outputs API for {self.model}")
    response = await asyncio.wait_for(
        self.client.beta.messages.parse(
            model=self.model,
            max_tokens=request.config.max_tokens,
            temperature=request.config.temperature,
            system=request.config.system_prompt,
            messages=[{"role": "user", "content": full_prompt}],
            betas=["structured-outputs-2025-11-13"],
            output_format=pydantic_model,
        ),
        timeout=request.config.timeout_seconds,
    )

    # Extract structured output from parsed response
    parsed_output = response.parsed_output
    answer_text = parsed_output.model_dump_json()

else:
    # FALLBACK: Use tool use for models without structured outputs support
    logger.debug(f"Using tool use fallback for {self.model}")
    response = await asyncio.wait_for(
        self.client.messages.create(
            model=self.model,
            max_tokens=request.config.max_tokens,
            temperature=request.config.temperature,
            system=request.config.system_prompt,
            messages=[{"role": "user", "content": full_prompt}],
            tools=[{
                "name": tool_name,
                "description": tool_description,
                "input_schema": json_schema
            }],
            tool_choice={
                "type": "tool",
                "name": tool_name
            }
        ),
        timeout=request.config.timeout_seconds,
    )

    # Extract JSON from tool use block
    tool_use_block = None
    for block in response.content:
        if hasattr(block, 'type') and block.type == 'tool_use':
            tool_use_block = block
            break

    if not tool_use_block:
        raise Exception("Expected tool_use block but none returned")

    tool_input = tool_use_block.input
    answer_text = json.dumps(tool_input)

# Common response processing continues here (lines 107+)
latency_ms = int((time.time() - start_time) * 1000)

# Validate it's not empty
if not answer_text or not answer_text.strip():
    raise Exception("Claude returned empty JSON")

# ... rest of method unchanged ...
```

**Lines Changed**: ~60

---

### 3. Verify Schema Definitions Exist

**File**: `src/services/llm/base.py`
**Location**: Lines 126-200

**Status**: ✅ No changes needed

The JSON schema dictionaries (`STRUCTURED_OUTPUT_SCHEMA` and `HOP_EVALUATION_SCHEMA`) already exist in the codebase from the pre-Pydantic implementation. These are ready to use for the tool use fallback.

---

### 4. Add Unit Tests

**File**: `tests/unit/test_llm_adapters.py`

```python
class TestClaudeAdapter:
    # ... existing tests ...

    @pytest.mark.asyncio
    async def test_haiku_uses_tool_use_fallback(self):
        """Test Haiku model uses tool use fallback (not structured outputs)."""
        adapter = ClaudeAdapter(api_key="test-key", model="claude-haiku-4-5-20251001")

        # Mock messages.create (tool use API)
        adapter.client.messages.create = AsyncMock(
            return_value=Mock(
                content=[
                    Mock(
                        type='tool_use',
                        input={
                            'smalltalk': False,
                            'short_answer': 'Yes.',
                            'persona_short_answer': 'Obviously.',
                            'quotes': [],
                            'explanation': 'Test explanation',
                            'persona_afterword': 'Elementary.'
                        }
                    )
                ],
                usage=Mock(input_tokens=100, output_tokens=50)
            )
        )

        request = GenerationRequest(
            prompt="Test query",
            context=["Test context"],
            config=GenerationConfig()
        )

        response = await adapter.generate(request)

        # Verify tool use API was called (not beta.messages.parse)
        adapter.client.messages.create.assert_called_once()
        assert response.answer_text
        assert response.provider == "claude"

    @pytest.mark.asyncio
    async def test_sonnet_uses_structured_outputs(self):
        """Test Sonnet model uses structured outputs API."""
        adapter = ClaudeAdapter(api_key="test-key", model="claude-sonnet-4-5-20250929")

        # Mock beta.messages.parse (structured outputs API)
        mock_parsed = Mock()
        mock_parsed.model_dump_json.return_value = json.dumps({
            'smalltalk': False,
            'short_answer': 'Yes.',
            'persona_short_answer': 'Obviously.',
            'quotes': [],
            'explanation': 'Test explanation',
            'persona_afterword': 'Elementary.'
        })

        adapter.client.beta.messages.parse = AsyncMock(
            return_value=Mock(
                parsed_output=mock_parsed,
                usage=Mock(input_tokens=100, output_tokens=50)
            )
        )

        request = GenerationRequest(
            prompt="Test query",
            context=["Test context"],
            config=GenerationConfig()
        )

        response = await adapter.generate(request)

        # Verify structured outputs API was called
        adapter.client.beta.messages.parse.assert_called_once()
        assert response.answer_text
        assert response.provider == "claude"

    @pytest.mark.asyncio
    async def test_opus_uses_structured_outputs(self):
        """Test Opus model uses structured outputs API."""
        adapter = ClaudeAdapter(api_key="test-key", model="claude-opus-4-1-20250805")

        # Mock beta.messages.parse (structured outputs API)
        mock_parsed = Mock()
        mock_parsed.model_dump_json.return_value = json.dumps({
            'smalltalk': False,
            'short_answer': 'Yes.',
            'persona_short_answer': 'Obviously.',
            'quotes': [],
            'explanation': 'Test explanation',
            'persona_afterword': 'Elementary.'
        })

        adapter.client.beta.messages.parse = AsyncMock(
            return_value=Mock(
                parsed_output=mock_parsed,
                usage=Mock(input_tokens=100, output_tokens=50)
            )
        )

        request = GenerationRequest(
            prompt="Test query",
            context=["Test context"],
            config=GenerationConfig()
        )

        response = await adapter.generate(request)

        # Verify structured outputs API was called
        adapter.client.beta.messages.parse.assert_called_once()
        assert response.answer_text
        assert response.provider == "claude"
```

**Lines Added**: ~80

---

### 5. Integration Testing

**CLI quality tests**:

```bash
# Test Haiku with actual API (uses fallback)
python -m src.cli quality-test --model claude-4.5-haiku --test eliminator-concealed-counteract

# Test Sonnet with actual API (uses structured outputs)
python -m src.cli quality-test --model claude-4.5-sonnet --test eliminator-concealed-counteract

# Test Opus with actual API (uses structured outputs)
python -m src.cli quality-test --model claude-4.1-opus --test eliminator-concealed-counteract
```

**Expected Outcome**: All three models should pass quality tests with correct JSON responses.

---

## Files Affected

| File | Lines Changed | Type | Description |
|------|--------------|------|-------------|
| `src/services/llm/claude.py` | ~60 lines | **MAJOR** | Add model detection, dual API paths, fallback response parsing |
| `src/lib/constants.py` | ~5 lines | **MINOR** | Add `CLAUDE_MODELS_WITH_STRUCTURED_OUTPUTS` constant |
| `tests/unit/test_llm_adapters.py` | ~80 lines | **MINOR** | Add unit tests for Haiku fallback and Sonnet/Opus structured outputs |
| **Total** | **~145 lines** | | |

---

## Risk Assessment

### Low Risk Factors

✅ **Battle-tested code**: Old API (tool use) was used until commit `c01d0fb`
✅ **Purely additive**: Doesn't break existing Sonnet/Opus functionality
✅ **Schemas exist**: JSON schema definitions already in codebase
✅ **Identical output**: Both APIs return JSON strings with same structure

### Medium Risk Factors

⚠️ **Dual maintenance**: Need to maintain two code paths
⚠️ **Schema sync**: Pydantic and JSON dict schemas must stay aligned
⚠️ **Version tracking**: Need to monitor when Haiku gains support

### Mitigation Strategies

- Centralize model support list in `constants.py` (single source of truth)
- Add debug logging to show which API path is used
- Document fallback behavior in code comments
- Monitor Anthropic release notes for Haiku structured outputs support

---

## Future Considerations

### When Haiku Gains Structured Outputs Support

Update `src/lib/constants.py`:

```python
CLAUDE_MODELS_WITH_STRUCTURED_OUTPUTS = [
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-1-20250805",
    "claude-haiku-4-5-20251001",  # ← Add when supported
]
```

**No other code changes needed** - automatic migration to new API.

### Eventually Remove Fallback Code

Once all supported Claude models use structured outputs:
- Remove tool use code path entirely
- Simplifies `claude.py` significantly (~30 lines removed)
- Single maintenance path

---

## Alternative Approaches (Not Recommended)

### Alternative 1: Remove Haiku from Supported Models
❌ Reduces functionality
❌ Users lose cheaper/faster Haiku option

### Alternative 2: Keep Only Tool Use for All Models
❌ Loses benefits of new structured outputs API (better reliability)
❌ Doesn't leverage latest Anthropic features

### Alternative 3: Separate Adapter Classes
❌ Increases code duplication
❌ Harder to maintain

**Recommended**: Dual API path with model detection (as outlined above)

---

## Documentation Updates

**File**: `src/services/llm/CLAUDE.md`
**Section**: "Claude Adapter" (line ~36)

**Addition**:
```markdown
#### Model-Specific API Usage

Claude Haiku 4.5 does not yet support Pydantic structured outputs. The adapter
automatically detects model capabilities and uses the appropriate API:

- **Sonnet 4.5, Opus 4.1**: `beta.messages.parse()` with Pydantic schemas
- **Haiku 4.5**: `messages.create()` with tool use (JSON schema fallback)

Both approaches return identical JSON output formats.
```

---

## Implementation Checklist

- [ ] Update `src/lib/constants.py` with model support list
- [ ] Add model detection logic to `src/services/llm/claude.py`
- [ ] Implement dual API path (structured outputs vs tool use)
- [ ] Add response parsing for both paths
- [ ] Add debug logging for API path selection
- [ ] Write unit tests for Haiku fallback
- [ ] Write unit tests for Sonnet/Opus structured outputs
- [ ] Run unit tests: `pytest tests/unit/test_llm_adapters.py`
- [ ] Run integration test with Haiku: `python -m src.cli quality-test --model claude-4.5-haiku`
- [ ] Run integration test with Sonnet: `python -m src.cli quality-test --model claude-4.5-sonnet`
- [ ] Run integration test with Opus: `python -m src.cli quality-test --model claude-4.1-opus`
- [ ] Update `src/services/llm/CLAUDE.md` documentation
- [ ] Monitor Anthropic release notes for Haiku support announcement

---

## References

- **Error Source**: User query with Haiku model failing with 400 error
- **Old Implementation**: Git commit `ce8d119` (pre-Pydantic migration)
- **Anthropic API Docs**: https://docs.anthropic.com/
- **Related Docs**: `docs/STRUCTURED-OUTPUT-IMPLEMENTATION.md`, `docs/TROUBLESHOOTING-PYDANTIC-MIGRATION.md`
