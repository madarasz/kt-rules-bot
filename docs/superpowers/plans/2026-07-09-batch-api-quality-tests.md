# Batch API for Quality Tests — Implementation Plan (Base scope)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in, resumable **batch** path to `quality-test` that submits generation (and, when the judge model supports it, judge) LLM calls through the Anthropic and OpenAI Batch APIs at 50% token cost, reusing the existing prompt-building, output format, judge, and reporting code.

**Architecture:** A two-phase state machine driven by a `batch_state.json` manifest in the results dir. `batch-submit` builds the same `GenerationRequest`s the live path builds, then either submits them to a batch backend (batchable models) or runs them live now (non-batch models). `batch-collect` is single-pass and hand-re-runnable: one status check, advance the phase at most one step, exit. Batch knowledge lives in each LLM adapter via three hooks (`supports_batch`, `build_batch_request`, `parse_batch_result`); `backends.py` owns only the submit/poll/fetch envelope. Judging reuses the existing replay-over-saved-outputs flow.

**Tech Stack:** Python 3.11+, `anthropic` 0.74.1 (`client.messages.batches`), `openai` 2.8.1 (`client.batches` + `client.files`), existing ChromaDB/RAG cache, pytest.

**Source spec:** [docs/batch-api-quality-tests-plan.md](../../batch-api-quality-tests-plan.md). Scope confirmed with user: **Base plan** — Anthropic backend + one parameterized OpenAI-compatible backend. Gemini, Mistral, Grok, DeepSeek stay on the live-async fallback path in this pass.

## Global Constraints

- Python **3.11+**, full type hints, `dataclass` for new data holders (matches repo).
- Import tunables from [src/lib/constants.py](../../../src/lib/constants.py); never hardcode config values.
- **No provider-specific code outside `src/services/llm/`** — batch request building / result parsing lives in the adapters, not in `tests/quality/batch/`.
- **No new dependencies** — `anthropic` and `openai` SDKs are already installed and already expose batch APIs.
- Hash user IDs with SHA-256 where user data is involved (N/A for quality tests, but keep the rule).
- TDD: failing unit test first, minimal code, green, commit. `ruff check .` clean before each commit.
- `python -m src.cli quality-test` live runs **cost money** — never run the full matrix to validate. Unit tests use fakes; exactly one tiny live smoke at the end (Task 13), run by the user.

## Scope decisions locked in (deltas from the source spec)

1. **No separate `request_builder.py` / `result_parser.py` modules.** That logic is the adapter hooks `build_batch_request` (Task 3/4) and `parse_batch_result`. `tests/quality/batch/` holds only `manifest.py` and `backends.py`. Rationale: the spec itself says "keep batch knowledge inside each adapter"; two extra modules would duplicate the split.
2. **Claude batch uses the tool-use JSON path, not `output_config.format`.** The Claude adapter already has a proven `tools` + `tool_choice` fallback that returns schema-shaped JSON ([claude.py:168-207](../../../src/services/llm/claude.py)); batch supports the identical `MessageCreateParamsNonStreaming` params. `parse_batch_result` reads the `tool_use` block exactly like that fallback. Avoids the `output_config` beta. `# ponytail: tool-use JSON in batch; switch to output_config.format only if a model drops tool support.`
3. **OpenAI-compat backend is parameterized (`base_url`, `api_key`) so it *can* serve OpenAI / Kimi / Qwen**, but only **OpenAI** (`ChatGPTAdapter`) sets `supports_batch = True` and is verified in this pass. `KimiAdapter` / `QwenAdapter` keep `supports_batch = False` with a one-line comment — their structured-output mode differs (json_object vs json_schema) and their batch discount is unconfirmed; wiring them is a later, verify-first follow-up. This honors the "OpenAI-compat covers all three" structure without shipping an unverified 50% savings claim.
4. **Judge round batches only when the judge model is batchable.** Default judge is `grok-4-1-fast-reasoning` (not a base-plan backend) → judge always runs live via the existing replay path, so a single `batch-collect` finishes the run. If `--judge-model gpt-4.1-mini` is passed, the judge round is batched (exercised by the Task 13 smoke).

## File map

**New:**
- `tests/quality/batch/__init__.py`
- `tests/quality/batch/manifest.py` — `BatchManifest` dataclass + `load`/`save`.
- `tests/quality/batch/backends.py` — `BatchBackend` protocol, `AnthropicBatchBackend`, `OpenAICompatBatchBackend`, `resolve_backend(model)`.
- `tests/unit/test_tokens_batch.py`, `tests/unit/test_batch_hooks.py`, `tests/unit/test_batch_manifest.py`, `tests/unit/test_batch_backends.py`, `tests/unit/test_batch_metadata_roundtrip.py`.

**Modified:**
- `src/lib/tokens.py` — batch discount path + `batch_savings` field.
- `src/services/llm/base.py` — three batch hooks on `LLMProvider`.
- `src/services/llm/claude.py`, `src/services/llm/chatgpt.py` — implement the hooks.
- `tests/quality/reporting/report_models.py` — `batch_savings_usd` / `judge_batch_savings_usd`.
- `tests/quality/reporting/report_generator.py` — "Batch savings" report line.
- `tests/quality/metadata_generator.py` + `tests/quality/output_parser.py` — persist & read back the batch flag + savings.
- `tests/quality/test_runner.py` — `submit_batch_run` / `collect_batch_run`; factor judge core shared with `replay_tests_from_outputs`.
- `src/cli/quality_test.py`, `src/cli/__main__.py` — `--batch-submit` / `--batch-collect` flags.
- `tests/quality/CLAUDE.md`, `src/cli/CLAUDE.md` — document the workflow.

---

### Task 1: Batch discount in the cost model

**Files:**
- Modify: `src/lib/tokens.py` (`LLMCostBreakdown` ~17-34, `calculate_llm_cost` ~120-187)
- Test: `tests/unit/test_tokens_batch.py`

**Interfaces:**
- Produces: `calculate_llm_cost(..., batch: bool = False) -> LLMCostBreakdown`; `LLMCostBreakdown` gains `batch_savings: float`. `BATCH_DISCOUNT: dict[str, float]` keyed by cache_mode-ish backend name, default `0.5`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_tokens_batch.py
from src.lib.tokens import calculate_llm_cost

def test_batch_halves_prompt_and_completion_cost_after_cache():
    live = calculate_llm_cost(1000, 500, "gpt-4.1")
    batched = calculate_llm_cost(1000, 500, "gpt-4.1", batch=True)
    assert batched.total_cost == live.total_cost * 0.5
    # batch_savings = what the same tokens cost live (after cache) minus batched cost
    assert abs(batched.batch_savings - (live.total_cost - batched.total_cost)) < 1e-9
    assert live.batch_savings == 0.0

def test_batch_stacks_on_anthropic_cache():
    # cache read tokens are separate for anthropic; batch discount applies on top
    batched = calculate_llm_cost(1000, 500, "claude-4.6-sonnet",
                                 cache_read_tokens=800, batch=True)
    live = calculate_llm_cost(1000, 500, "claude-4.6-sonnet", cache_read_tokens=800)
    assert abs(batched.total_cost - live.total_cost * 0.5) < 1e-9
```

- [ ] **Step 2: Run it, verify it fails** — `pytest tests/unit/test_tokens_batch.py -v` → FAIL (`batch` kwarg / `batch_savings` missing).

- [ ] **Step 3: Implement.** Add `batch_savings: float` to `LLMCostBreakdown`. In `calculate_llm_cost`, add `batch: bool = False`. Compute the breakdown exactly as today into a local `live_total`, `live_prompt_cost`, etc. Then:

```python
    BATCH_DISCOUNT = 0.5  # both Anthropic and OpenAI batch = 50%; per-backend override later
    if batch:
        factor = 1.0 - BATCH_DISCOUNT
        batch_savings = total_cost * BATCH_DISCOUNT
        prompt_cost *= factor
        completion_cost *= factor
        cache_read_cost *= factor
        cache_creation_cost *= factor
        total_cost *= factor
    else:
        batch_savings = 0.0
```

Add `batch_savings=batch_savings` to the returned `LLMCostBreakdown(...)`. Keep `cache_savings` computed on the pre-discount (live) numbers so the two savings never double-count — leave the existing `cache_savings` math untouched (it already runs before the batch block).

- [ ] **Step 4: Green** — `pytest tests/unit/test_tokens_batch.py -v` → PASS. `ruff check src/lib/tokens.py`.

- [ ] **Step 5: Commit** — `git add src/lib/tokens.py tests/unit/test_tokens_batch.py && git commit -m "feat(tokens): add 50% batch discount path with batch_savings"`

---

### Task 2: Batch hooks on the LLM base class

**Files:**
- Modify: `src/services/llm/base.py` (`LLMProvider`, ~402-435)
- Test: `tests/unit/test_batch_hooks.py`

**Interfaces:**
- Produces on `LLMProvider`: class attr `supports_batch: bool = False`; `build_batch_request(self, request: GenerationRequest, custom_id: str) -> dict` (default `raise NotImplementedError`); `@classmethod parse_batch_result(cls, raw: dict) -> LLMResponse` (default `raise NotImplementedError`). `raw` is the backend-normalized `{"custom_id", "status", "message"/"body", "usage"...}` — see Task 6 for the exact shape each backend returns.

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_batch_hooks.py
from src.services.llm.gemini import GeminiAdapter
from src.services.llm.claude import ClaudeAdapter
from src.services.llm.chatgpt import ChatGPTAdapter

def test_non_batch_adapter_defaults_false():
    assert GeminiAdapter.supports_batch is False  # class attr, no instance needed

def test_batchable_adapters_opt_in():
    assert ClaudeAdapter.supports_batch is True
    assert ChatGPTAdapter.supports_batch is True
```

- [ ] **Step 2: Verify fail** — `pytest tests/unit/test_batch_hooks.py -v` → FAIL (attr missing / False). *(The `True` asserts stay red until Tasks 3–4; that's expected — run only `test_non_batch_adapter_defaults_false` green here.)*

- [ ] **Step 3: Implement** in `base.py`:

```python
    supports_batch: bool = False

    def build_batch_request(self, request: "GenerationRequest", custom_id: str) -> dict:
        """Return a backend-ready batch line for this request. Override in batch adapters."""
        raise NotImplementedError(f"{type(self).__name__} does not support batch")

    @classmethod
    def parse_batch_result(cls, raw: dict) -> "LLMResponse":
        """Convert a normalized batch result item into an LLMResponse. Override in batch adapters."""
        raise NotImplementedError(f"{cls.__name__} does not support batch")
```

- [ ] **Step 4: Green** — `pytest tests/unit/test_batch_hooks.py::test_non_batch_adapter_defaults_false -v` → PASS.

- [ ] **Step 5: Commit** — `git add src/services/llm/base.py tests/unit/test_batch_hooks.py && git commit -m "feat(llm): add batch hooks to LLMProvider base"`

---

### Task 3: Claude batch hooks

**Files:**
- Modify: `src/services/llm/claude.py` (add hooks near `generate`, reuse `_get_system`, `get_schema_info`)
- Test: `tests/unit/test_batch_hooks.py` (extend)

**Interfaces:**
- Produces: `ClaudeAdapter.supports_batch = True`; `build_batch_request(request, custom_id)` → `{"custom_id": custom_id, "params": {...MessageCreateParamsNonStreaming...}}`; `parse_batch_result(raw)` → `LLMResponse`.
- Consumes (Task 6): backend passes each Anthropic result item normalized to `{"custom_id", "result_type": "succeeded|errored|expired|canceled", "message": <anthropic Message or dict>}`.

- [ ] **Step 1: Failing test** (round-trips a fake succeeded item):

```python
# add to tests/unit/test_batch_hooks.py
import json
from types import SimpleNamespace
from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.claude import ClaudeAdapter

def _fake_claude_msg():
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use",
                                 input={"smalltalk": False, "short_answer": "Yes.",
                                        "persona_short_answer": "", "quotes": [],
                                        "explanation": "x", "persona_afterword": ""})],
        usage=SimpleNamespace(input_tokens=100, output_tokens=20,
                              cache_read_input_tokens=80, cache_creation_input_tokens=0),
    )

def test_claude_build_batch_request_has_tool_and_custom_id():
    a = ClaudeAdapter(api_key="x", model="claude-sonnet-4-5-20250929")
    req = GenerationRequest(prompt="q", context=["c"], config=GenerationConfig(), chunk_ids=None)
    line = a.build_batch_request(req, custom_id="gen__t__m__run1")
    assert line["custom_id"] == "gen__t__m__run1"
    p = line["params"]
    assert p["model"] == "claude-sonnet-4-5-20250929"
    assert p["tool_choice"]["name"] == p["tools"][0]["name"]
    assert p["messages"][0]["role"] == "user"

def test_claude_parse_batch_result_roundtrips():
    raw = {"custom_id": "gen__t__m__run1", "result_type": "succeeded", "message": _fake_claude_msg()}
    resp = ClaudeAdapter.parse_batch_result(raw)
    assert json.loads(resp.answer_text)["short_answer"] == "Yes."
    assert resp.prompt_tokens == 100 and resp.completion_tokens == 20
    assert resp.cache_read_tokens == 80
    assert resp.provider == "claude"
```

- [ ] **Step 2: Verify fail** — `pytest tests/unit/test_batch_hooks.py -k claude -v` → FAIL.

- [ ] **Step 3: Implement** in `ClaudeAdapter`:

```python
    supports_batch = True

    def build_batch_request(self, request: GenerationRequest, custom_id: str) -> dict:
        full_prompt = request.prompt if isinstance(request.prompt, list) else \
            self._build_prompt(request.prompt, request.context, request.chunk_ids)
        system = _get_system(request.config.system_prompt, request.config.use_cache)
        info = get_schema_info(request.config.structured_output_schema)
        params: dict = {
            "model": self.model,
            "max_tokens": request.config.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": full_prompt}],
            "tools": [{"name": info.tool_name, "description": info.tool_description,
                       "input_schema": info.json_schema}],
            "tool_choice": {"type": "tool", "name": info.tool_name},
        }
        if self.model not in CLAUDE_MODELS_WITHOUT_TEMPERATURE:
            params["temperature"] = request.config.temperature
        return {"custom_id": custom_id, "params": params}

    @classmethod
    def parse_batch_result(cls, raw: dict) -> LLMResponse:
        from uuid import uuid4
        if raw.get("result_type") != "succeeded":
            raise RuntimeError(f"batch item {raw.get('custom_id')} {raw.get('result_type')}")
        msg = raw["message"]
        tool_block = next(b for b in msg.content if getattr(b, "type", None) == "tool_use")
        answer_text = json.dumps(tool_block.input)
        u = msg.usage
        pt, ct = u.input_tokens, u.output_tokens
        return LLMResponse(
            response_id=uuid4(), answer_text=answer_text, confidence_score=0.8,
            token_count=pt + ct, latency_ms=0, provider="claude",
            model_version=getattr(msg, "model", None) or "",  # backend fills model if absent
            citations_included=True, prompt_tokens=pt, completion_tokens=ct,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            structured_output=tool_block.input,
        )
```

Note: `model_version` may be empty from the raw message; the backend (Task 6) sets it from the request mapping if the SDK object omits it. `parse_batch_result` raising on non-succeeded is caught by `collect_batch_run` (Task 10) and mapped to the existing error-result path.

- [ ] **Step 4: Green** — `pytest tests/unit/test_batch_hooks.py -k claude -v` → PASS. `ruff check src/services/llm/claude.py`.

- [ ] **Step 5: Commit** — `git add src/services/llm/claude.py tests/unit/test_batch_hooks.py && git commit -m "feat(claude): batch request/result hooks via tool-use JSON"`

---

### Task 4: OpenAI batch hooks

**Files:**
- Modify: `src/services/llm/chatgpt.py`
- Test: `tests/unit/test_batch_hooks.py` (extend)

**Interfaces:**
- Produces: `ChatGPTAdapter.supports_batch = True`; `build_batch_request(request, custom_id)` → `{"custom_id", "method": "POST", "url": "/v1/chat/completions", "body": {...}}`; `parse_batch_result(raw)` → `LLMResponse`.
- Consumes (Task 6): each OpenAI output line normalized to `{"custom_id", "status_code", "body": <chat.completion dict>}`.

- [ ] **Step 1: Failing test**

```python
# add to tests/unit/test_batch_hooks.py
from src.services.llm.chatgpt import ChatGPTAdapter

def test_openai_build_batch_request_json_schema():
    a = ChatGPTAdapter(api_key="x", model="gpt-4.1")
    req = GenerationRequest(prompt="q", context=["c"], config=GenerationConfig(), chunk_ids=None)
    line = a.build_batch_request(req, custom_id="gen__t__gpt-4.1__run1")
    assert line["url"] == "/v1/chat/completions"
    b = line["body"]
    assert b["model"] == "gpt-4.1"
    assert b["response_format"]["type"] == "json_schema"
    assert "max_tokens" in b  # non-reasoning model

def test_openai_parse_batch_result_roundtrips():
    body = {"choices": [{"message": {"content":
              '{"smalltalk": false, "short_answer": "Yes.", "persona_short_answer": "",'
              ' "quotes": [], "explanation": "x", "persona_afterword": ""}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                      "prompt_tokens_details": {"cached_tokens": 80}},
            "model": "gpt-4.1-2025"}
    raw = {"custom_id": "gen__t__gpt-4.1__run1", "status_code": 200, "body": body}
    resp = ChatGPTAdapter.parse_batch_result(raw)
    assert resp.prompt_tokens == 100 and resp.cache_read_tokens == 80
    assert resp.model_version == "gpt-4.1-2025"
    assert resp.structured_output["short_answer"] == "Yes."
```

- [ ] **Step 2: Verify fail** — `pytest tests/unit/test_batch_hooks.py -k openai -v` → FAIL.

- [ ] **Step 3: Implement** in `ChatGPTAdapter` (mirror `generate`, but emit a JSONL body with `response_format` json_schema built from the Pydantic model rather than calling `.parse`):

```python
    supports_batch = True

    def build_batch_request(self, request: GenerationRequest, custom_id: str) -> dict:
        full_prompt = self._build_prompt(request.prompt, request.context, request.chunk_ids)
        model_cls = get_pydantic_model(request.config.structured_output_schema)
        schema = model_cls.model_json_schema()
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.config.system_prompt},
                {"role": "user", "content": full_prompt},
            ],
            "response_format": {"type": "json_schema", "json_schema":
                {"name": model_cls.__name__, "schema": schema, "strict": True}},
        }
        if self.uses_completion_tokens:
            body["max_completion_tokens"] = request.config.max_tokens * 3
        else:
            body["max_tokens"] = request.config.max_tokens
        if self.supports_temperature:
            body["temperature"] = request.config.temperature
        return {"custom_id": custom_id, "method": "POST",
                "url": "/v1/chat/completions", "body": body}

    @classmethod
    def parse_batch_result(cls, raw: dict) -> LLMResponse:
        import json as _json
        from uuid import uuid4
        if raw.get("status_code") not in (200, None):
            raise RuntimeError(f"batch item {raw.get('custom_id')} status {raw.get('status_code')}")
        body = raw["body"]
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        pt = usage.get("prompt_tokens", 0)
        ct = usage.get("completion_tokens", 0)
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        return LLMResponse(
            response_id=uuid4(), answer_text=content, confidence_score=0.8,
            token_count=usage.get("total_tokens", pt + ct), latency_ms=0, provider="chatgpt",
            model_version=body.get("model", ""), citations_included=True,
            prompt_tokens=pt, completion_tokens=ct, cache_read_tokens=cached,
            cache_creation_tokens=0, structured_output=_json.loads(content),
        )
```

`# ponytail: response_format json_schema replicates what beta.chat.completions.parse builds; strict=True keeps the same validation.`

- [ ] **Step 4: Green** — `pytest tests/unit/test_batch_hooks.py -v` → all PASS (incl. Task 2's `test_batchable_adapters_opt_in`). `ruff check src/services/llm/chatgpt.py`.

- [ ] **Step 5: Commit** — `git add src/services/llm/chatgpt.py tests/unit/test_batch_hooks.py && git commit -m "feat(chatgpt): batch request/result hooks via json_schema body"`

---

### Task 5: Batch manifest

**Files:**
- Create: `tests/quality/batch/__init__.py`, `tests/quality/batch/manifest.py`
- Test: `tests/unit/test_batch_manifest.py`

**Interfaces:**
- Produces: `BatchManifest` dataclass with `phase: str` (`"generation_submitted" | "judge_submitted" | "scoring" | "done"`), `created_at: str`, `models: list[str]`, `judge_model: str`, `runs: int`, `test_ids: list[str]`, `report_dir: str`, `generation: dict[str, dict]` (backend → `{batch_id, status}`), `judge: dict[str, dict]`, `requests: list[dict]` (each `{custom_id, test_id, model, run_num, kind, backend, batchable}`), `live_done: list[str]`. `custom_id` format: `f"{kind}__{test_id}__{model}__run{run_num}"`. Classmethods `load(report_dir: Path) -> BatchManifest`, method `save(self) -> None` (writes `batch_state.json` under `report_dir`). Static `parse_custom_id(cid) -> tuple[str,str,str,int]`.

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_batch_manifest.py
from pathlib import Path
from tests.quality.batch.manifest import BatchManifest

def test_save_load_roundtrip(tmp_path: Path):
    m = BatchManifest(phase="generation_submitted", created_at="t", models=["claude-4.6-sonnet"],
                      judge_model="grok-4-1-fast-reasoning", runs=1, test_ids=["t1"],
                      report_dir=str(tmp_path), generation={"anthropic": {"batch_id": "b1", "status": "in_progress"}},
                      judge={}, requests=[{"custom_id": "gen__t1__claude-4.6-sonnet__run1",
                      "test_id": "t1", "model": "claude-4.6-sonnet", "run_num": 1,
                      "kind": "gen", "backend": "anthropic", "batchable": True}], live_done=[])
    m.save()
    assert (tmp_path / "batch_state.json").exists()
    loaded = BatchManifest.load(tmp_path)
    assert loaded.phase == "generation_submitted"
    assert loaded.generation["anthropic"]["batch_id"] == "b1"

def test_parse_custom_id():
    assert BatchManifest.parse_custom_id("judge__t1__gpt-4.1__run3") == ("judge", "t1", "gpt-4.1", 3)
```

- [ ] **Step 2: Verify fail** — `pytest tests/unit/test_batch_manifest.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement** `manifest.py` with `@dataclass`, `asdict`/`json.dump` in `save`, `json.load` + `BatchManifest(**data)` in `load`, and `parse_custom_id` splitting on `"__"` (rsplit run token, strip `run` prefix → int). `__init__.py` empty.

- [ ] **Step 4: Green** — `pytest tests/unit/test_batch_manifest.py -v` → PASS.

- [ ] **Step 5: Commit** — `git add tests/quality/batch/ tests/unit/test_batch_manifest.py && git commit -m "feat(batch): BatchManifest state file"`

---

### Task 6: Batch backends (submit/poll/fetch envelope)

**Files:**
- Create: `tests/quality/batch/backends.py`
- Test: `tests/unit/test_batch_backends.py`

**Interfaces:**
- Produces:
  - `class BatchBackend(Protocol)`: `name: str`; `submit(lines: list[dict]) -> str` (returns batch_id); `poll(batch_id: str) -> str` (normalized status: `"in_progress" | "ended" | "failed"`); `fetch(batch_id: str) -> dict[str, dict]` (custom_id → normalized raw item, shape consumed by the adapters' `parse_batch_result`).
  - `AnthropicBatchBackend(api_key)` — `submit` calls `client.messages.batches.create(requests=[Request(custom_id=..., params=...)])`; `poll` maps `processing_status`→`ended`/`in_progress`; `fetch` iterates `client.messages.batches.results(id)` → `{custom_id, result_type, message}`.
  - `OpenAICompatBatchBackend(api_key, base_url, name)` — `submit` writes the lines as JSONL via `client.files.create(purpose="batch")` then `client.batches.create(input_file_id=..., endpoint="/v1/chat/completions", completion_window="24h")`; `poll` maps `status`→`ended`(`completed`)/`in_progress`/`failed`; `fetch` downloads `output_file_id` JSONL → `{custom_id, status_code, body}`.
  - `resolve_backend(model: str) -> BatchBackend | None` — maps a friendly model name to a backend via `LLMProviderFactory._model_registry[model]` `(adapter_class, model_id, api_key_type)`: `api_key_type == "anthropic"` → `AnthropicBatchBackend`; `"openai"` → `OpenAICompatBatchBackend(base_url="https://api.openai.com/v1", name="openai")`. Any other type, **or** an adapter whose `supports_batch` is False → return `None` (caller runs live). API keys resolved from `get_config()` (same fields the factory uses).

- [ ] **Step 1: Failing test** (fakes the SDK clients; no network):

```python
# tests/unit/test_batch_backends.py
from tests.quality.batch.backends import resolve_backend

def test_resolve_backend_routing():
    assert resolve_backend("claude-4.6-sonnet").name == "anthropic"
    assert resolve_backend("gpt-4.1").name == "openai"
    assert resolve_backend("grok-4-1-fast-reasoning") is None   # not batchable in base plan
    assert resolve_backend("gemini-2.5-flash") is None          # supports_batch False

def test_anthropic_poll_maps_status(monkeypatch):
    from tests.quality.batch import backends
    b = backends.AnthropicBatchBackend(api_key="x")
    class _FakeBatch:  processing_status = "ended"
    monkeypatch.setattr(b, "_client", type("C", (), {"messages": type("M", (), {"batches":
        type("B", (), {"retrieve": staticmethod(lambda i: _FakeBatch())})()})()})())
    assert b.poll("bid") == "ended"
```

- [ ] **Step 2: Verify fail** — `pytest tests/unit/test_batch_backends.py -v` → FAIL.

- [ ] **Step 3: Implement** `backends.py`. Lazy-create SDK clients (`_client` property). `AnthropicBatchBackend.submit` builds `from anthropic.types.messages.batch_create_params import Request` items (verify exact import path against installed 0.74.1 with `python -c "import anthropic.types.messages as m; print(dir(m))"`; fall back to plain dicts `{"custom_id":..., "params":...}` which the SDK also accepts). `fetch` sets `message.model`-derived `model_version` when present. `OpenAICompatBatchBackend` writes JSONL to a temp file in the scratchpad/`report_dir`, uploads, creates batch, and on `fetch` reads each JSONL line into `{custom_id, status_code: line["response"]["status_code"], body: line["response"]["body"]}`. `resolve_backend` imports `LLMProviderFactory._model_registry` and the adapter classes' `supports_batch`.

- [ ] **Step 4: Green** — `pytest tests/unit/test_batch_backends.py -v` → PASS. `ruff check tests/quality/batch/backends.py`.

- [ ] **Step 5: Commit** — `git add tests/quality/batch/backends.py tests/unit/test_batch_backends.py && git commit -m "feat(batch): Anthropic + OpenAI-compat batch backends with model routing"`

---

### Task 7: Report-model + report savings fields

**Files:**
- Modify: `tests/quality/reporting/report_models.py` (`IndividualTestResult` ~54, `ModelSummary`)
- Modify: `tests/quality/reporting/report_generator.py` (cost-breakdown header)
- Test: `tests/unit/test_batch_hooks.py` or a small new `tests/unit/test_report_batch_fields.py`

**Interfaces:**
- Produces: `IndividualTestResult.batch_savings_usd: float = 0.0`, `.judge_batch_savings_usd: float = 0.0`; `ModelSummary.avg_batch_savings` property; report gains a "Batch savings" line + combined total.

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_report_batch_fields.py
from tests.quality.reporting.report_models import IndividualTestResult, ModelSummary

def test_batch_savings_defaults_and_aggregate():
    r = IndividualTestResult(test_id="t", query="q", model="m", score=80, max_score=100,
        passed=True, tokens=10, cost_usd=0.01, output_char_count=1,
        generation_time_seconds=1.0, output_filename="f", batch_savings_usd=0.02)
    assert r.batch_savings_usd == 0.02 and r.judge_batch_savings_usd == 0.0
    assert ModelSummary("m", [r]).avg_batch_savings == 0.02
```

- [ ] **Step 2: Verify fail** — `pytest tests/unit/test_report_batch_fields.py -v` → FAIL.

- [ ] **Step 3: Implement.** Add the two fields next to `cache_savings_usd`/`judge_cache_savings_usd`. Add `avg_batch_savings` mirroring `avg_cache_savings_pct`'s pattern (mean of `r.batch_savings_usd`). In `report_generator.py`, find where the cache-savings line is emitted in the cost header and add a sibling "Batch savings: $X (N% of gross)" line plus a "Total savings (cache + batch): $Y". Grep: `grep -n "cache_savings\|Cache savings\|avg_cache_savings" tests/quality/reporting/report_generator.py`.

- [ ] **Step 4: Green** — `pytest tests/unit/test_report_batch_fields.py -v` → PASS.

- [ ] **Step 5: Commit** — `git add tests/quality/reporting/ tests/unit/test_report_batch_fields.py && git commit -m "feat(reporting): batch-savings fields + report line"`

---

### Task 8: Persist & read back batch metadata

**Files:**
- Modify: `tests/quality/metadata_generator.py` (writer + `extract_deterministic_metrics_from_metadata` / `OutputMetadata`)
- Modify: `tests/quality/output_parser.py` (surface batch fields)
- Modify: `tests/quality/test_runner.py` (`_save_output` signature: add `batch: bool = False`, `batch_savings_usd: float = 0.0`)
- Test: `tests/unit/test_batch_metadata_roundtrip.py`

**Interfaces:**
- Produces: output `*.md` metadata JSON gains `"batch": bool` and `"batch_savings_usd": float`; `OutputMetadata` exposes them; `_evaluate_parsed_output` (Task 10) reads them onto the result.

- [ ] **Step 1: Failing test** — write a minimal output via `_save_output(..., batch=True, batch_savings_usd=0.03, ragas_metrics=RagasMetrics(), llm_response=<fake>, ...)`, then `OutputParser.parse_output_file` and assert `parsed.metadata` carries `batch is True` and `batch_savings_usd == 0.03`. (Reuse the empty-`RagasMetrics()` no-eval path so metadata is written.)

- [ ] **Step 2: Verify fail** → FAIL.

- [ ] **Step 3: Implement.** In `metadata_generator.py`: read `grep -n "def generate_metadata\|class OutputMetadata\|response_json\|tokens\|costs" tests/quality/metadata_generator.py` and add `batch` + `batch_savings_usd` to the emitted JSON (in the costs block) and to `OutputMetadata`. Thread the two new params through `_save_output` → `MetadataGenerator.generate_metadata`. In `output_parser.py`, no reconstruction change needed beyond exposing the fields on `metadata` (they ride in `OutputMetadata`).

- [ ] **Step 4: Green** → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(quality): persist batch flag + savings in output metadata"`

---

### Task 9: Factor the judge core (shared by replay and batch)

**Files:**
- Modify: `tests/quality/test_runner.py` — extract from `replay_tests_from_outputs` a reusable `async def _judge_parsed_outputs(self, parsed_outputs, test_cases_map, report_dir) -> list[IndividualTestResult]`; have `replay_tests_from_outputs` call it. Extract the CustomJudge request-assembly/parse into `CustomJudge.build_batch_request(...) -> GenerationRequest` and `CustomJudge.parse_result(response: LLMResponse, ground_truth_answers) -> CustomJudgeResult` (from `custom_judge.py:263-393`) so the judge batch round can reuse them.
- Test: `tests/unit/` — a focused test that `_judge_parsed_outputs` over one saved output (with a stubbed `CustomJudge.evaluate`) returns one `IndividualTestResult` written into `report_dir`.

**Interfaces:**
- Consumes: `parse_output_directory` (existing), `CustomJudge` (existing).
- Produces: `_judge_parsed_outputs(...)`, `CustomJudge.build_batch_request(...)`, `CustomJudge.parse_result(...)`. `_evaluate_parsed_output` now also copies `batch`/`batch_savings_usd` from `parsed_output.metadata` onto the returned `IndividualTestResult` (`.batch_savings_usd`).

- [ ] **Step 1: Failing test** — stub `CustomJudge.evaluate` (monkeypatch to return a fixed `CustomJudgeResult`), point `_judge_parsed_outputs` at a dir with one hand-written `output_*.md`, assert one result and that `result.batch_savings_usd` reflects metadata.

- [ ] **Step 2: Verify fail** → FAIL.

- [ ] **Step 3: Implement** the extraction. Keep `replay_tests_from_outputs`'s external behavior identical (it still creates its own REPLAYS dir and delegates the eval loop to `_judge_parsed_outputs`). `CustomJudge.build_batch_request` returns the `GenerationRequest(prompt=<split-or-stripped>, context=[], chunk_ids=[], config=<custom_judge config>)` exactly as `evaluate` builds today; `parse_result` runs lines 319-393's extraction against a passed-in `LLMResponse`.

- [ ] **Step 4: Green** → PASS. Also run existing replay coverage: `pytest tests/ -k replay -v`.

- [ ] **Step 5: Commit** — `git commit -am "refactor(quality): factor judge core for reuse by batch + replay"`

---

### Task 10: State machine — submit_batch_run + collect_batch_run

**Files:**
- Modify: `tests/quality/test_runner.py`
- Test: `tests/unit/test_batch_statemachine.py` (fakes backends via monkeypatch; no network)

**Interfaces:**
- Produces:
  - `async def submit_batch_run(self, report_dir, test_id, models, runs, judge_model, force_rag) -> BatchManifest` — retrieves cached RAG per test (existing `run_tests_in_parallel` RAG path), builds a gen `GenerationRequest` per `test×model×run`, splits models by `resolve_backend(model) is not None`; batchable → `adapter.build_batch_request(req, custom_id)` grouped per backend, `backend.submit(lines)` → store `batch_id`; non-batch → run existing `run_test(...)` live now and record `custom_id` in `live_done`. Writes `batch_state.json` (`phase="generation_submitted"`). Returns manifest.
  - `async def collect_batch_run(self, report_dir) -> str` — loads manifest, does the single-pass advance described below, saves manifest, returns the new `phase`.

**Single-pass `collect_batch_run` logic:**
```
phase generation_submitted:
    for each gen backend: status = backend.poll(batch_id); store it
    if any status == "in_progress": print status; return "generation_submitted"   # re-run later
    for each gen backend: items = backend.fetch(batch_id)
        for custom_id,item: resp = adapter.parse_batch_result(item)  (on RuntimeError → error result)
          write output_*.md via _save_output(no-eval style, batch=True,
                batch_savings_usd = calculate_llm_cost(..., batch=True).batch_savings)
    parsed = parse_output_directory(report_dir)
    if resolve_backend(judge_model) is not None:
        build judge requests (CustomJudge.build_batch_request per parsed output),
        backend.submit → judge[backend]={batch_id}; phase="judge_submitted"
    else:
        results = _judge_parsed_outputs(parsed, ..., report_dir)   # live judge (default grok)
        _finalize_report(results, report_dir); phase="done"
    return phase

phase judge_submitted:
    status = judge_backend.poll(batch_id)
    if in_progress: print; return "judge_submitted"
    fetch judge items; phase="scoring"  (fall through)

phase scoring:
    parsed = parse_output_directory(report_dir)
    results = [_evaluate_from_batch_judge(po, judge_item) ...]   # CustomJudge.parse_result
    _finalize_report(results, report_dir); phase="done"
    return "done"

phase done: print "already complete"; return "done"
```
`_finalize_report` = build `QualityReport` + `aggregate_results` + `ReportGenerator(...).generate_all_reports()` into `report_dir` (lift the shared tail out of `quality_test.py`).

- [ ] **Step 1: Failing test** — monkeypatch `resolve_backend` to return a fake backend whose `poll` returns `"ended"` and `fetch` returns one synthetic claude item; run `submit_batch_run` then `collect_batch_run` with a `grok` judge stubbed live; assert `phase == "done"`, `report.md` exists, and the single result carries `batch_savings_usd > 0`. Second test: `poll` returns `"in_progress"` → `collect_batch_run` returns `"generation_submitted"` and writes no report (resumability).

- [ ] **Step 2: Verify fail** → FAIL.

- [ ] **Step 3: Implement.** Reuse `run_tests_in_parallel`'s RAG-context retrieval for the gen requests (extract a `_build_generation_requests(...)` helper if cleaner). Map error items through the existing `_create_error_result`. Keep everything idempotent off `manifest.phase`.

- [ ] **Step 4: Green** — `pytest tests/unit/test_batch_statemachine.py -v` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(quality): batch submit/collect state machine"`

---

### Task 11: CLI wiring

**Files:**
- Modify: `src/cli/__main__.py` (`quality-test` subparser ~139-185; dispatch ~347)
- Modify: `src/cli/quality_test.py` (`quality_test(...)` — add `batch_submit: bool`, `batch_collect: str | None`)
- Test: `tests/unit/test_cli_commands.py` (extend — arg parsing only)

**Interfaces:**
- Produces: mutually-exclusive `--batch-submit` (flag) and `--batch-collect <results_dir>` on `quality-test`. `--batch-submit` reuses `--test/--model/--all-models/--runs/--judge-model/--force-rag`, calls `runner.submit_batch_run(...)`, prints batch IDs + the exact `python -m src.cli quality-test --batch-collect <dir>` command, exits. `--batch-collect` calls `runner.collect_batch_run(dir)` once, prints `phase` + per-batch status, exits.

- [ ] **Step 1: Failing test** — assert the parser accepts `["quality-test","--batch-submit","--test","t","--model","claude-4.6-sonnet"]` and rejects `--batch-submit --batch-collect x` (mutually exclusive → SystemExit).

- [ ] **Step 2: Verify fail** → FAIL.

- [ ] **Step 3: Implement.** Add an argparse mutually-exclusive group. In `quality_test.py`, branch at the top: if `batch_collect` → run collect + print, return; if `batch_submit` → confirm (respect `skip_confirm`), setup `report_dir`, `asyncio.run(runner.submit_batch_run(...))`, print IDs + collect command, return. Otherwise the existing live/replay flow. Route both new args in `__main__.py` dispatch.

- [ ] **Step 4: Green** — `pytest tests/unit/test_cli_commands.py -v` → PASS. `python -m src.cli quality-test --help` shows the flags.

- [ ] **Step 5: Commit** — `git commit -am "feat(cli): --batch-submit / --batch-collect for quality-test"`

---

### Task 12: Documentation

**Files:**
- Modify: `tests/quality/CLAUDE.md` (add a "Batch API workflow" section: submit → collect-until-done, savings reporting, resumability, base-plan backend coverage + which models fall back to live).
- Modify: `src/cli/CLAUDE.md` (document the two flags under `quality-test`).

- [ ] **Step 1:** Write the sections (commands from Task 13, the phase model, and the "grok judge runs live / batchable judge batches" note).
- [ ] **Step 2:** `git commit -am "docs: batch quality-test workflow"`

---

### Task 13: Live smoke verification (costs money — user runs once)

**Not automated. The user runs these; an agent must not run the full matrix.**

- [ ] **13a — single batched model, live judge (default grok):**
```bash
python -m src.cli quality-test --batch-submit --test eliminator-concealed-counteract \
  --model claude-4.6-sonnet --skip-confirm
# note the printed results dir + collect command, then:
python -m src.cli quality-test --batch-collect tests/quality/results/<timestamp>
# re-run the collect line until it prints phase == done
```
Confirm: `report.md` generated; a **"Batch savings"** line ≈ 50% of token cost sits next to the existing cache-savings line with a combined total; `output_*.md` match the live format; `batch_state.json` shows `phase: done`.

- [ ] **13b — batched judge path:** same as 13a but `--judge-model gpt-4.1-mini` → expect a `judge` batch in the manifest and **two** collects to reach `done` (gen batch, then judge batch).

- [ ] **13c — resumability:** run a `--batch-collect` immediately after submit (before the batch ends) → it prints status and exits, writes no report; re-running after `done` prints "already complete" and does not re-submit or re-score.

- [ ] **13d — mixed run:** `--batch-submit --test <t> --model claude-4.6-sonnet --model grok-4-1-fast-reasoning` → grok runs live at submit, claude via batch; one collect → single `report.md` with both models.

- [ ] **Full regression:** `pytest tests/unit/ tests/contract/ -q && ruff check .` → all green.

---

## Self-review notes

- **Spec coverage:** cost model (T1), base hooks (T2), Claude/OpenAI hooks (T3/T4), manifest (T5), backends+routing (T6), report savings (T7), metadata round-trip (T8), judge-core reuse (T9), state machine (T10), CLI (T11), docs (T12), verification (T13). Gemini/Mistral/Kimi/Qwen/Grok/DeepSeek batch = **out of base scope** (live fallback) — spec's Extension section deferred by the user's scope choice.
- **Deliberate simplifications** (all flagged in "Scope decisions"): no `request_builder.py`/`result_parser.py` modules; Claude tool-use JSON instead of `output_config.format`; Kimi/Qwen `supports_batch=False` pending discount verification; judge batches only when the judge model is batchable.
- **Type consistency:** `custom_id` format identical across T5/T6/T10; `parse_batch_result` raises on non-success and T10 catches → `_create_error_result`; `batch_savings_usd` flows T1→T7→T8→T10.
- **Open verify-at-execution:** exact Anthropic `Request` import path for `messages.batches.create` on SDK 0.74.1 (T6 Step 3 gives the fallback: plain dicts).
