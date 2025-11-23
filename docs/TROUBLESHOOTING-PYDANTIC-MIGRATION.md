# Troubleshooting: Pydantic Migration Errors

**Last updated**: 2025-11-23

## Symptoms

After pulling commit `47cb01e` (Pydantic migration), you're still seeing API errors:

### Gemini Error
```
400 INVALID_ARGUMENT. Unknown name "responseMimeType" at 'generation_config': Cannot find field.
Unknown name "responseSchema" at 'generation_config': Cannot find field.
```

### Claude Error
```
Unexpected value(s) `structured-outputs-2025-09-17` for the `anthropic-beta` header
```

## Root Cause

These errors indicate **stale Python bytecode** (.pyc files) is being loaded instead of the updated source code.

## Solution

### Step 1: Clear Python Cache

```bash
# Remove all __pycache__ directories
find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null

# Remove all .pyc files
find . -name '*.pyc' -delete

# If using pytest cache
rm -rf .pytest_cache/
```

### Step 2: Reinstall Dependencies

```bash
# Force reinstall to ensure latest SDK versions
pip install -r requirements.txt --upgrade --force-reinstall

# Verify SDK versions
python3 -c "import anthropic; print(f'anthropic: {anthropic.__version__}')"
python3 -c "import openai; print(f'openai: {openai.__version__}')"
```

**Expected versions**:
- `anthropic >= 0.74.1`
- `openai >= 2.8.1`

### Step 3: Verify Implementation

Run the diagnostic script:

```bash
python scripts/verify_implementation.py
```

**Expected output**:
```
=== SDK Versions ===
anthropic: 0.74.1 (required: >=0.74.1)
openai: 2.8.1 (required: >=2.8.1)
google-genai: installed

=== Schemas ===
✅ HopEvaluation.missing_query: Nullable (CORRECT)
✅ schemas.py exists at: /home/user/kt-rules-bot/src/services/llm/schemas.py

=== Claude Adapter ===
✅ Claude: Using correct beta header (2025-11-13)
✅ Claude: Using beta.messages.parse

=== Gemini Adapter ===
✅ Gemini: Passing Pydantic model directly (CORRECT)
✅ Gemini: Using types.GenerateContentConfig
```

### Step 4: Run Tests

```bash
# Unit tests
pytest tests/unit/test_llm_adapters.py -v

# Quality tests (single model to verify)
python -m src.cli quality-test --model claude-4.5-sonnet --test eliminator-concealed-counteract
```

## What Changed

### Gemini (Fixed in 47cb01e)

**Before** (WRONG - causes API error):
```python
generation_config = types.GenerateContentConfig(
    response_schema=pydantic_model.model_json_schema(),  # ❌ JSON dict
)
```

**After** (CORRECT):
```python
generation_config = types.GenerateContentConfig(
    max_output_tokens=max_tokens,
    temperature=request.config.temperature,
    response_mime_type="application/json",
    response_schema=pydantic_model,  # ✅ Pass Pydantic model directly
)
```

**File**: `src/services/llm/gemini.py:143-148`

### Claude (Fixed in c01d0fb)

**Before** (WRONG - old beta header):
```python
"anthropic-beta": "pdfs-2024-09-25,files-api-2025-04-14,structured-outputs-2025-09-17"
```

**After** (CORRECT):
```python
"anthropic-beta": "pdfs-2024-09-25,files-api-2025-04-14,structured-outputs-2025-11-13"
```

**File**: `src/services/llm/claude.py:48`

## Docker/Container Environments

If running in Docker or a containerized environment:

```bash
# Rebuild container with --no-cache
docker-compose down
docker-compose build --no-cache
docker-compose up

# Or if using Docker directly
docker build --no-cache -t kt-rules-bot .
docker run kt-rules-bot
```

## Virtual Environment

If using a virtual environment:

```bash
# Deactivate and reactivate
deactivate
source venv/bin/activate  # or source .venv/bin/activate

# Or recreate the virtual environment
rm -rf venv/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Still Seeing Errors?

### 1. Verify File Contents

Manually check the files contain the correct code:

```bash
# Check Gemini
grep -A 5 "response_schema=" src/services/llm/gemini.py | grep -v "model_json_schema()"

# Should show:
#     response_schema=pydantic_model,  # Pass Pydantic model directly

# Check Claude
grep "structured-outputs" src/services/llm/claude.py

# Should show:
#     "anthropic-beta": "pdfs-2024-09-25,files-api-2025-04-14,structured-outputs-2025-11-13"
```

### 2. Check Import Paths

Ensure Python is loading from the correct location:

```python
import sys
from src.services.llm.gemini import GeminiAdapter

# Print where module is loaded from
print(sys.modules['src.services.llm.gemini'].__file__)
# Expected: /home/user/kt-rules-bot/src/services/llm/gemini.py
```

### 3. Enable Debug Logging

```bash
# Run with debug logging
export LOG_LEVEL=DEBUG
python -m src.cli quality-test --model gemini-2.5-pro --test eliminator-concealed-counteract
```

### 4. API Key Issues

Verify API keys are valid and have correct permissions:

```bash
# Test Claude API key
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: structured-outputs-2025-11-13" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello"}]
  }'

# Test Gemini API key
curl "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-pro:generateContent?key=$GOOGLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{"parts": [{"text": "Hello"}]}]
  }'
```

## Quick Reference: Commits

- `c01d0fb` - Initial Pydantic implementation (all providers)
- `740bcf2` - Fix HopEvaluation.missing_query to allow None
- `84764ca` - Fix Claude adapter unit tests
- `8b933f2` - Fix API compatibility for Gemini and DeepSeek (first attempt)
- `47cb01e` - **Fix Gemini API parameter (pass Pydantic model directly)** ⭐

## Need Help?

If errors persist after following all steps:

1. Check the git log to confirm you have commit `47cb01e` or later:
   ```bash
   git log --oneline -5
   ```

2. Create a minimal reproduction case:
   ```python
   from src.services.llm.gemini import GeminiAdapter
   from src.services.llm.base import GenerationRequest, GenerationConfig

   adapter = GeminiAdapter(api_key="your-key", model="gemini-2.5-pro")
   request = GenerationRequest(
       prompt="Test query",
       context=["Test context"],
       config=GenerationConfig()
   )

   # This should work without API errors
   response = await adapter.generate(request)
   ```

3. Check for conflicting installations:
   ```bash
   pip list | grep -E "anthropic|openai|google"
   ```

## Success Criteria

After following these steps, you should see:

✅ **Unit tests pass**:
```bash
$ pytest tests/unit/test_llm_adapters.py
===================== test session starts ======================
...
tests/unit/test_llm_adapters.py::TestClaudeAdapter::test_generate_rate_limit PASSED
tests/unit/test_llm_adapters.py::TestClaudeAdapter::test_generate_auth_error PASSED
...
```

✅ **Quality tests pass** (no API errors):
```bash
$ python -m src.cli quality-test --model claude-4.5-sonnet --test eliminator-concealed-counteract
Running test: eliminator-concealed-counteract
Provider: claude-4.5-sonnet
✓ Test passed
```

✅ **No cache warnings**:
```bash
$ python scripts/verify_implementation.py
============================================================
Pydantic Implementation Verification
============================================================

=== SDK Versions ===
anthropic: 0.74.1 (required: >=0.74.1)
openai: 2.8.1 (required: >=2.8.1)
...
✅ All checks passed
```

---

**Document Status**: Complete
**Last Updated**: 2025-11-23
