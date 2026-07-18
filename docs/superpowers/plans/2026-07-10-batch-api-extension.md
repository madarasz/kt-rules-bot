# Batch API Extension (Kimi, Qwen, Mistral, Gemini, Grok) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the shipped quality-test Batch-API path (Anthropic + OpenAI) to Kimi, Qwen, Mistral, Gemini, and Grok backends, with a per-backend discount table and `expired`-item resubmission.

**Architecture:** Batch knowledge lives in each LLM adapter (`supports_batch` + `build_batch_request` + `parse_batch_result`); the `tests/quality/batch/backends.py` layer owns the submit/poll/fetch envelope per provider. Kimi/Qwen reuse the existing `OpenAICompatBatchBackend` (only base_url/key differ). Mistral, Gemini, and Grok get their own backend classes, all via already-installed SDKs/`httpx` (no new deps). Cost accounting gains a per-backend discount lookup.

**Tech Stack:** Python 3.11+, `openai` SDK (Kimi/Qwen OpenAI-compat batches), `httpx` (Mistral + Grok REST batch), `google-genai` (Gemini batches), pytest with faked clients.

## Global Constraints

- No provider-specific code outside `src/services/llm/` — batch request/parse logic lives in adapter hooks; `backends.py` stays a thin transport envelope. (CLAUDE.md convention)
- No new runtime dependencies. Mistral + Grok batch use `httpx` (already a dep); Gemini uses `google-genai` (already a dep); Kimi/Qwen use `openai` (already a dep). Lazy-import SDK clients inside the backend `client` property, matching the existing `AnthropicBatchBackend`/`OpenAICompatBatchBackend` pattern.
- Import tunables from `src/lib/constants.py`; no hardcoded config in business logic.
- All unit tests use faked network clients (monkeypatched `.client`) — **no live API calls**. Live smoke stays the user's paid step.
- Batch discount default is `0.5`. Kimi (`moonshot`) and Grok (`x`) publish "reduced pricing" without a confirmed percentage — default them to `0.5` with a `# ponytail:` comment flagging the value is an estimate the user must confirm against the pricing page. Reported `batch_savings_usd` for those two is an estimate until confirmed.
- Provider `custom_id` round-trip format is unchanged: `{kind}__{test_id}__{model}__run{n}` via `BatchManifest.make_custom_id`.

---

## File Structure

**Modified:**
- `src/lib/tokens.py` — replace scalar `BATCH_DISCOUNT` with a per-backend dict + lookup; `calculate_llm_cost` gains a `batch_backend: str | None` param.
- `src/services/llm/kimi.py` — add `supports_batch` + two batch hooks (json_object + schema-in-prompt shape).
- `src/services/llm/qwen.py` — same as Kimi (json_object + schema-in-prompt), plus base_url key-prefix switch.
- `src/services/llm/mistral.py` — add batch hooks (OpenAI-compatible json_schema body).
- `src/services/llm/grok.py` — add batch hooks (xAI Responses-API body).
- `src/services/llm/gemini.py` — add batch hooks + expose a reusable numbering/post-process helper for the collect step.
- `tests/quality/batch/backends.py` — wire Kimi/Qwen into `make_backend`/`_API_KEY_TYPE_TO_BACKEND`; add `MistralBatchBackend`, `GeminiBatchBackend`, `GrokBatchBackend`; extend `poll` to report `"expired"`.
- `tests/quality/batch/manifest.py` — add optional `gemini_sentences` per-request field for quote reconstruction; add `expired`-tracking helper.
- `tests/quality/test_runner.py` — collect step: handle `expired` (resubmit) and Gemini post-processing; judge routing already backend-agnostic.
- `tests/quality/CLAUDE.md`, `src/cli/CLAUDE.md`, `docs/batch-api-quality-tests-plan.md` — document expanded coverage.

**Created:**
- `tests/unit/test_batch_discount_per_backend.py`
- `tests/unit/test_batch_hooks_openai_compat.py` (Kimi + Qwen)
- `tests/unit/test_batch_backend_mistral.py`
- `tests/unit/test_batch_backend_gemini.py`
- `tests/unit/test_batch_backend_grok.py`
- `tests/unit/test_batch_expired_resubmit.py`

---

## Task 1: Per-backend discount table in tokens.py

**Files:**
- Modify: `src/lib/tokens.py:121-211`
- Test: `tests/unit/test_batch_discount_per_backend.py`

**Interfaces:**
- Consumes: existing `calculate_llm_cost(prompt_tokens, completion_tokens, model, cache_read_tokens=0, cache_creation_tokens=0, batch=False)`.
- Produces: `BATCH_DISCOUNT: dict[str, float]` (keyed by backend name: `"anthropic"`, `"openai"`, `"mistral"`, `"alibaba"`, `"moonshot"`, `"x"`, `"google"`); `DEFAULT_BATCH_DISCOUNT = 0.5`; `batch_discount_for(backend: str | None) -> float`; `calculate_llm_cost(..., batch=False, batch_backend: str | None = None)` where the discount = `batch_discount_for(batch_backend)` when `batch` is True.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_batch_discount_per_backend.py
from src.lib.tokens import BATCH_DISCOUNT, batch_discount_for, calculate_llm_cost


def test_known_backends_have_discounts():
    for name in ("anthropic", "openai", "mistral", "alibaba", "moonshot", "x", "google"):
        assert 0.0 < BATCH_DISCOUNT[name] <= 1.0


def test_unknown_backend_falls_back_to_default():
    assert batch_discount_for("nope") == 0.5
    assert batch_discount_for(None) == 0.5


def test_batch_backend_selects_discount():
    # gpt-4.1: prompt 0.002, completion 0.008 per 1k. 1000 prompt + 1000 completion.
    live = calculate_llm_cost(1000, 1000, "gpt-4.1")
    batched = calculate_llm_cost(1000, 1000, "gpt-4.1", batch=True, batch_backend="openai")
    assert batched.total_cost == live.total_cost * 0.5
    assert batched.batch_savings == live.total_cost * 0.5


def test_batch_without_backend_uses_default_discount():
    live = calculate_llm_cost(1000, 1000, "gpt-4.1")
    batched = calculate_llm_cost(1000, 1000, "gpt-4.1", batch=True)
    assert batched.total_cost == live.total_cost * 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_discount_per_backend.py -v`
Expected: FAIL — `ImportError: cannot import name 'BATCH_DISCOUNT' ... 'batch_discount_for'` (BATCH_DISCOUNT is currently a float; `batch_discount_for` undefined).

- [ ] **Step 3: Write minimal implementation**

Replace the scalar block at `src/lib/tokens.py:121-124`:

```python
# Batch API discount per backend (fraction off the live, post-cache cost).
# Anthropic, OpenAI, Mistral, Qwen/DashScope, Gemini confirmed 50%.
# ponytail: moonshot (Kimi) and x (Grok) publish "reduced pricing" without a
# confirmed %, defaulted to 0.5 — confirm against their pricing page and correct
# here if different; batch_savings_usd for those two is an estimate until then.
DEFAULT_BATCH_DISCOUNT = 0.5
BATCH_DISCOUNT: dict[str, float] = {
    "anthropic": 0.5,
    "openai": 0.5,
    "mistral": 0.5,
    "alibaba": 0.5,   # Qwen / DashScope
    "google": 0.5,    # Gemini
    "moonshot": 0.5,  # Kimi — estimate, confirm
    "x": 0.5,         # Grok — estimate, confirm
}


def batch_discount_for(backend: str | None) -> float:
    """Return the batch discount fraction for a backend name (default 0.5)."""
    return BATCH_DISCOUNT.get(backend or "", DEFAULT_BATCH_DISCOUNT)
```

Update `calculate_llm_cost` signature (`src/lib/tokens.py:127-134`) to add `batch_backend: str | None = None`, and the batch block (`src/lib/tokens.py:186-197`):

```python
    if batch:
        discount = batch_discount_for(batch_backend)
        factor = 1.0 - discount
        batch_savings = total_cost * discount
        prompt_cost *= factor
        completion_cost *= factor
        cache_read_cost *= factor
        cache_creation_cost *= factor
        total_cost *= factor
    else:
        batch_savings = 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_discount_per_backend.py tests/unit/test_tokens_batch.py -v`
Expected: PASS (both the new file and the existing `test_tokens_batch.py`, since default behavior is unchanged).

- [ ] **Step 5: Thread `batch_backend` through callers**

Find where `calculate_llm_cost(..., batch=...)` is called in the metadata/reporting path and pass the backend name so the correct discount applies:

Run: `grep -rn "calculate_llm_cost" tests/quality src/ | grep -i batch`

At each batch call site (e.g. in `tests/quality/metadata_generator.py` / `test_runner.py` where per-result cost is computed), pass `batch_backend=<the backend name recorded on the manifest request row>`. The manifest request row already carries `"backend"`; use it. If a call site has no backend handy, leave `batch_backend=None` (falls back to 0.5 — unchanged behavior).

- [ ] **Step 6: Run the batch reporting/roundtrip tests**

Run: `source venv/bin/activate && pytest tests/unit/test_report_batch_fields.py tests/unit/test_batch_metadata_roundtrip.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/lib/tokens.py tests/unit/test_batch_discount_per_backend.py tests/quality
git commit -m "feat(batch): per-backend discount table in tokens.py"
```

---

## Task 2: Kimi + Qwen batch hooks (OpenAI-compat, json_object + schema-in-prompt)

**Files:**
- Modify: `src/services/llm/kimi.py`, `src/services/llm/qwen.py`
- Modify: `tests/quality/batch/backends.py:150-166`
- Test: `tests/unit/test_batch_hooks_openai_compat.py`

**Interfaces:**
- Consumes: `GenerationRequest`, `LLMResponse`, `get_pydantic_model` from `src.services.llm.base`; `OpenAICompatBatchBackend(api_key, base_url, name)` from `tests/quality/batch/backends.py`.
- Produces: `KimiAdapter.supports_batch = True`, `KimiAdapter.build_batch_request(self, request, custom_id) -> dict` (shape `{custom_id, method:"POST", url:"/v1/chat/completions", body:{...}}` with `response_format={"type":"json_object"}` and schema appended to the system message), `KimiAdapter.parse_batch_result(cls, raw) -> LLMResponse`. Same three on `QwenAdapter` (provider `"alibaba"`). `make_backend("moonshot")` and `make_backend("alibaba")` return an `OpenAICompatBatchBackend` at the right base_url/key; `_API_KEY_TYPE_TO_BACKEND` maps `"moonshot"->"moonshot"`, `"alibaba"->"alibaba"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_batch_hooks_openai_compat.py
import json

from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.kimi import KimiAdapter
from src.services.llm.qwen import QwenAdapter


def _req():
    return GenerationRequest(
        prompt="Can the Eliminator shoot twice?",
        context=["[chunk] Suspensor System lets it shoot twice."],
        config=GenerationConfig(system_prompt="You are a rules helper.", max_tokens=500, temperature=0.0),
    )


def test_kimi_build_batch_request_is_json_object_with_schema_in_prompt():
    a = KimiAdapter(api_key="k", model="kimi-k2.5")
    line = a.build_batch_request(_req(), "gen__t__kimi-k2.5__run0")
    assert line["custom_id"] == "gen__t__kimi-k2.5__run0"
    assert line["url"] == "/v1/chat/completions"
    body = line["body"]
    assert body["response_format"] == {"type": "json_object"}
    # schema is appended to the system message, not sent as response_format json_schema
    assert "schema" in body["messages"][0]["content"].lower()
    assert body["model"] == "kimi-k2.5"


def test_kimi_parse_batch_result_roundtrips_content():
    answer = json.dumps({"smalltalk": False, "short_answer": "Yes.", "persona_short_answer": "Obviously.",
                         "quotes": [], "explanation": "Suspensor System.", "persona_afterword": "Elementary."})
    raw = {"custom_id": "c", "status_code": 200,
           "body": {"model": "kimi-k2.5", "choices": [{"message": {"content": answer}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}}
    resp = KimiAdapter.parse_batch_result(raw)
    assert resp.provider == "kimi"
    assert resp.prompt_tokens == 10
    assert json.loads(resp.answer_text)["short_answer"] == "Yes."


def test_qwen_build_batch_request_provider_and_schema():
    a = QwenAdapter(api_key="k", model="qwen3-turbo")
    line = a.build_batch_request(_req(), "gen__t__qwen3-turbo__run0")
    assert line["body"]["response_format"] == {"type": "json_object"}
    resp = QwenAdapter.parse_batch_result({
        "custom_id": "c", "status_code": 200,
        "body": {"model": "qwen3-turbo",
                 "choices": [{"message": {"content": '{"smalltalk": false, "short_answer": "Y", "persona_short_answer": "x", "quotes": [], "explanation": "e", "persona_afterword": "a"}'}}],
                 "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}})
    assert resp.provider == "alibaba"
    assert resp.completion_tokens == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_hooks_openai_compat.py -v`
Expected: FAIL — `NotImplementedError: KimiAdapter does not support batch` (base-class hook).

- [ ] **Step 3: Write minimal implementation — Kimi**

Add to `KimiAdapter` (top of the class, mirroring `ChatGPTAdapter`), reusing Kimi's own json_object + schema-in-prompt shape from its `generate()`:

```python
    supports_batch = True

    def build_batch_request(self, request: GenerationRequest, custom_id: str) -> dict:
        """OpenAI-compatible /v1/batches line using Kimi's json_object mode.

        Kimi has thinking mode on by default (incompatible with tool_choice), so
        the live path appends the JSON schema to the system prompt and uses
        response_format={"type":"json_object"}. Batch must match that exactly.
        """
        import json as _json

        from src.services.llm.base import get_pydantic_model

        full_prompt = self._build_prompt(request.prompt, request.context, request.chunk_ids)
        schema = get_pydantic_model(request.config.structured_output_schema).model_json_schema()
        system_with_schema = (
            request.config.system_prompt
            + "\n\nIMPORTANT: You MUST respond with valid JSON matching this exact schema:\n"
            + f"```json\n{_json.dumps(schema, indent=2)}\n```\n"
            + "Do not include any text before or after the JSON object."
        )
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_with_schema},
                {"role": "user", "content": full_prompt},
            ],
            "max_tokens": request.config.max_tokens * 3,  # thinking tokens, matches generate()
            "temperature": request.config.temperature,
            "response_format": {"type": "json_object"},
        }
        return {"custom_id": custom_id, "method": "POST", "url": "/v1/chat/completions", "body": body}

    @classmethod
    def parse_batch_result(cls, raw: dict) -> LLMResponse:
        body = raw.get("body")
        if raw.get("status_code") not in (200, None) or body is None:
            raise RuntimeError(
                f"batch item {raw.get('custom_id')} status {raw.get('status_code')} (no body)"
            )
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        return LLMResponse(
            response_id=uuid4(),
            answer_text=content,
            confidence_score=0.8,
            token_count=usage.get("total_tokens", prompt_tokens + completion_tokens),
            latency_ms=0,
            provider="kimi",
            model_version=body.get("model", ""),
            citations_included=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cached,
            cache_creation_tokens=0,
        )
```

Note: Kimi's live `generate()` sets `provider="kimi"` — confirm the exact string used there and match it (grep `provider=` in `kimi.py`). Kimi multiplies max_tokens for thinking mode in `generate()`; match whatever multiplier the live path uses (check for `* 3`).

- [ ] **Step 4: Write minimal implementation — Qwen**

Add the same three members to `QwenAdapter`, but `provider="alibaba"` (matching its `generate()`), and **no** token multiplier unless `generate()` uses one (Qwen's `generate()` does not multiply — verify). Qwen also switches base_url on `sk-sp-` keys, but that is a backend concern (handled in `make_backend`), not the request body.

```python
    supports_batch = True

    def build_batch_request(self, request: GenerationRequest, custom_id: str) -> dict:
        import json as _json

        from src.services.llm.base import get_pydantic_model

        full_prompt = self._build_prompt(request.prompt, request.context, request.chunk_ids)
        schema = get_pydantic_model(request.config.structured_output_schema).model_json_schema()
        system_with_schema = (
            request.config.system_prompt
            + "\n\nIMPORTANT: You MUST respond with valid JSON matching this exact schema:\n"
            + f"```json\n{_json.dumps(schema, indent=2)}\n```\n"
            + "Do not include any text before or after the JSON object."
        )
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_with_schema},
                {"role": "user", "content": full_prompt},
            ],
            "max_tokens": request.config.max_tokens,
            "temperature": request.config.temperature,
            "response_format": {"type": "json_object"},
        }
        return {"custom_id": custom_id, "method": "POST", "url": "/v1/chat/completions", "body": body}

    @classmethod
    def parse_batch_result(cls, raw: dict) -> LLMResponse:
        body = raw.get("body")
        if raw.get("status_code") not in (200, None) or body is None:
            raise RuntimeError(
                f"batch item {raw.get('custom_id')} status {raw.get('status_code')} (no body)"
            )
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        return LLMResponse(
            response_id=uuid4(),
            answer_text=content,
            confidence_score=0.8,
            token_count=usage.get("total_tokens", prompt_tokens + completion_tokens),
            latency_ms=0,
            provider="alibaba",
            model_version=body.get("model", ""),
            citations_included=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
```

Ensure `uuid4` and `LLMResponse` are imported in both modules (they already import from `base`; add `from uuid import uuid4` if absent — it is present in both).

- [ ] **Step 5: Wire the backends**

In `tests/quality/batch/backends.py`, extend `_API_KEY_TYPE_TO_BACKEND` and `make_backend`:

```python
_API_KEY_TYPE_TO_BACKEND = {
    "anthropic": "anthropic",
    "openai": "openai",
    "moonshot": "moonshot",
    "alibaba": "alibaba",
}
```

```python
def make_backend(name: str) -> BatchBackend | None:
    config = get_config()
    if name == "anthropic":
        return AnthropicBatchBackend(api_key=config.anthropic_api_key)
    if name == "openai":
        return OpenAICompatBatchBackend(
            api_key=config.openai_api_key, base_url="https://api.openai.com/v1", name="openai"
        )
    if name == "moonshot":
        return OpenAICompatBatchBackend(
            api_key=config.moonshot_api_key, base_url="https://api.moonshot.ai/v1", name="moonshot"
        )
    if name == "alibaba":
        key = config.alibaba_api_key or ""
        base_url = (
            "https://coding.dashscope.aliyuncs.com/v1"
            if key.startswith("sk-sp-")
            else "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        return OpenAICompatBatchBackend(api_key=key, base_url=base_url, name="alibaba")
    return None
```

- [ ] **Step 6: Run tests**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_hooks_openai_compat.py tests/unit/test_batch_backends.py tests/unit/test_batch_hooks.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/services/llm/kimi.py src/services/llm/qwen.py tests/quality/batch/backends.py tests/unit/test_batch_hooks_openai_compat.py
git commit -m "feat(batch): Kimi + Qwen batch hooks via OpenAI-compat backend"
```

---

## Task 3: `expired`-item resubmission in the collect state machine

**Files:**
- Modify: `tests/quality/batch/backends.py` (poll returns `"expired"`), `tests/quality/test_runner.py` (collect handles it)
- Test: `tests/unit/test_batch_expired_resubmit.py`

**Interfaces:**
- Consumes: `BatchBackend.poll(batch_id) -> "in_progress" | "ended" | "failed" | "expired"`; `BatchBackend.fetch`.
- Produces: on a generation batch whose `poll` returns `"expired"`, `collect_batch_run` re-submits the still-unfetched requests for that backend (new batch_id, status back to `in_progress`) and stays in `phase="generation_submitted"` instead of erroring. A per-item `errored`/`expired` result already maps to the failure path in `parse_batch_result` (raises) — that is unchanged; this task handles a **whole-batch** `expired` poll status.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_batch_expired_resubmit.py
from tests.quality.batch.backends import OpenAICompatBatchBackend


class _FakeBatches:
    def __init__(self, status):
        self._status = status

    def retrieve(self, _id):
        class R:
            status = self._status
        return R()


class _FakeClient:
    def __init__(self, status):
        self.batches = _FakeBatches(status)


def test_poll_reports_expired_distinctly(monkeypatch):
    b = OpenAICompatBatchBackend(api_key="k", base_url="http://x", name="openai")
    b._client = _FakeClient("expired")
    assert b.poll("batch_1") == "expired"
    b._client = _FakeClient("completed")
    assert b.poll("batch_1") == "ended"
    b._client = _FakeClient("in_progress")
    assert b.poll("batch_1") == "in_progress"
    b._client = _FakeClient("failed")
    assert b.poll("batch_1") == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_expired_resubmit.py -v`
Expected: FAIL — current `OpenAICompatBatchBackend.poll` maps `"expired"` to `"failed"`, so `poll` returns `"failed"` not `"expired"`.

- [ ] **Step 3: Implement — poll distinguishes expired**

In `OpenAICompatBatchBackend.poll` (`tests/quality/batch/backends.py:124-130`):

```python
    def poll(self, batch_id: str) -> str:
        status = self.client.batches.retrieve(batch_id).status
        if status == "completed":
            return "ended"
        if status == "expired":
            return "expired"
        if status in ("failed", "cancelled", "canceled"):
            return "failed"
        return "in_progress"
```

- [ ] **Step 4: Implement — collect resubmits on whole-batch expiry**

In `collect_batch_run`'s generation-phase loop (`tests/quality/test_runner.py` around line 782-808 where it polls each `gen_backends[name]`), add an `expired` branch. Read the surrounding code first; the shape is:

```python
        all_ended = True
        for name, info in manifest.generation.items():
            status = gen_backends[name].poll(info["batch_id"])
            if status == "expired":
                # Re-submit this backend's lines from the manifest and keep waiting.
                lines = self._rebuild_lines_for_backend(manifest, name)
                new_id = gen_backends[name].submit(lines)
                manifest.generation[name] = {"batch_id": new_id, "status": "in_progress"}
                manifest.save()
                print(f"Generation batch {name} expired — resubmitted as {new_id}.")
                all_ended = False
                continue
            if status != "ended":
                all_ended = False
        if not all_ended:
            print("Generation batch(es) not ready — re-run batch-collect later.")
            return manifest.phase
```

Add the helper `_rebuild_lines_for_backend` on the runner: iterate `manifest.requests` rows with `kind == "gen"`, `backend == name`, `custom_id not in manifest.live_done`; rebuild each line via the adapter's `build_batch_request` exactly as `submit_batch_run` did. Factor the per-request line-building from `submit_batch_run` into a shared `_gen_line(manifest_row) -> dict` if it is not already, so submit and resubmit cannot drift. (Read `submit_batch_run` first; reuse its request-object reconstruction — RAG context comes from the cached `context_file`, deterministic.)

- [ ] **Step 5: Run tests**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_expired_resubmit.py tests/unit/test_batch_statemachine.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/quality/batch/backends.py tests/quality/test_runner.py tests/unit/test_batch_expired_resubmit.py
git commit -m "feat(batch): resubmit whole-batch expired generations on collect"
```

---

## Task 4: Mistral batch backend (httpx REST)

**Files:**
- Modify: `tests/quality/batch/backends.py` (add `MistralBatchBackend`), `src/services/llm/mistral.py` (hooks)
- Test: `tests/unit/test_batch_backend_mistral.py`

**Interfaces:**
- Consumes: `httpx` (already a dep), `config.mistral_api_key`.
- Produces: `MistralBatchBackend(api_key)` with `name="mistral"`, `submit(lines) -> job_id` (upload JSONL to `POST /v1/files` purpose=batch → `POST /v1/batch/jobs` with `input_files=[file_id]`, `endpoint="/v1/chat/completions"`, `model=<from first line>`), `poll(job_id)` → `"ended"` on `SUCCESS`, `"expired"` on `TIMEOUT_EXCEEDED`, `"failed"` on `FAILED`/`CANCELLED`, else `"in_progress"`, `fetch(job_id)` downloads `output_file` JSONL → `{custom_id: {custom_id, status_code, body}}`. `MistralAdapter.supports_batch=True` + hooks emitting OpenAI-compatible `{custom_id, body:{model, messages, max_tokens, temperature, response_format json_schema}}` (mirrors its `generate()`); `parse_batch_result` reads `body.choices[0].message.content`, `provider="mistral"`. `_API_KEY_TYPE_TO_BACKEND["mistral"]="mistral"`; `make_backend("mistral")` returns `MistralBatchBackend`.

- [ ] **Step 1: Write the failing test (adapter hooks + backend transport with a fake httpx)**

```python
# tests/unit/test_batch_backend_mistral.py
import json

from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.mistral import MistralAdapter
from tests.quality.batch.backends import MistralBatchBackend


def test_mistral_build_batch_request_json_schema_body():
    a = MistralAdapter(api_key="k", model="mistral-medium-3-5")
    req = GenerationRequest(prompt="q", context=["c"],
                            config=GenerationConfig(system_prompt="s", max_tokens=400, temperature=0.0))
    line = a.build_batch_request(req, "gen__t__mistral-medium-3-5__run0")
    assert line["custom_id"] == "gen__t__mistral-medium-3-5__run0"
    body = line["body"]
    assert body["model"] == "mistral-medium-3-5"
    assert body["response_format"]["type"] == "json_schema"


def test_mistral_parse_batch_result():
    content = json.dumps({"smalltalk": False, "short_answer": "Y", "persona_short_answer": "x",
                         "quotes": [], "explanation": "e", "persona_afterword": "a"})
    raw = {"custom_id": "c", "status_code": 200,
           "body": {"model": "mistral-medium-3-5", "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}}}
    resp = MistralAdapter.parse_batch_result(raw)
    assert resp.provider == "mistral"
    assert resp.prompt_tokens == 4


def test_mistral_backend_poll_status_mapping():
    b = MistralBatchBackend(api_key="k")

    class _Resp:
        def __init__(self, status):
            self._status = status
            self.status_code = 200

        def json(self):
            return {"status": self._status}

        def raise_for_status(self):
            pass

    class _HTTP:
        def __init__(self, status):
            self._status = status

        def get(self, *a, **k):
            return _Resp(self._status)

    b._http = _HTTP("SUCCESS")
    assert b.poll("j") == "ended"
    b._http = _HTTP("TIMEOUT_EXCEEDED")
    assert b.poll("j") == "expired"
    b._http = _HTTP("FAILED")
    assert b.poll("j") == "failed"
    b._http = _HTTP("RUNNING")
    assert b.poll("j") == "in_progress"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_backend_mistral.py -v`
Expected: FAIL — `ImportError: cannot import name 'MistralBatchBackend'` and `NotImplementedError` on the adapter hook.

- [ ] **Step 3: Implement adapter hooks — `src/services/llm/mistral.py`**

Add to `MistralAdapter` (mirror its `generate()` json_schema body; drop `prompt_cache_key` for batch simplicity or keep it — keep it to match live caching):

```python
    supports_batch = True

    def build_batch_request(self, request: GenerationRequest, custom_id: str) -> dict:
        full_prompt = self._build_prompt(request.prompt, request.context, request.chunk_ids)
        model_cls = get_pydantic_model(request.config.structured_output_schema)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.config.system_prompt},
                {"role": "user", "content": full_prompt},
            ],
            "max_tokens": request.config.max_tokens,
            "temperature": request.config.temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": model_cls.__name__,
                    "schema": model_cls.model_json_schema(),
                    "strict": True,
                },
            },
        }
        return {"custom_id": custom_id, "body": body}

    @classmethod
    def parse_batch_result(cls, raw: dict) -> LLMResponse:
        body = raw.get("body")
        if raw.get("status_code") not in (200, None) or body is None:
            raise RuntimeError(
                f"batch item {raw.get('custom_id')} status {raw.get('status_code')} (no body)"
            )
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        return LLMResponse(
            response_id=uuid4(),
            answer_text=content,
            confidence_score=0.8,
            token_count=usage.get("total_tokens", prompt_tokens + completion_tokens),
            latency_ms=0,
            provider="mistral",
            model_version=body.get("model", ""),
            citations_included=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cached,
            cache_creation_tokens=0,
        )
```

- [ ] **Step 4: Implement `MistralBatchBackend` — `tests/quality/batch/backends.py`**

```python
class MistralBatchBackend:
    """Mistral batch: httpx REST against api.mistral.ai (no mistralai SDK dep)."""

    name = "mistral"
    BASE_URL = "https://api.mistral.ai/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._http = None

    @property
    def http(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(
                base_url=self.BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
        return self._http

    def submit(self, lines: list[dict]) -> str:
        import io

        model = lines[0]["body"]["model"]
        buf = io.BytesIO(("\n".join(json.dumps(x) for x in lines)).encode("utf-8"))
        up = self.http.post(
            "/files",
            files={"file": ("batch.jsonl", buf, "application/jsonl")},
            data={"purpose": "batch"},
        )
        up.raise_for_status()
        file_id = up.json()["id"]
        job = self.http.post(
            "/batch/jobs",
            json={"input_files": [file_id], "endpoint": "/v1/chat/completions", "model": model},
        )
        job.raise_for_status()
        job_id = job.json()["id"]
        logger.info(f"Submitted Mistral batch {job_id} ({len(lines)} requests)")
        return job_id

    def poll(self, batch_id: str) -> str:
        r = self.http.get(f"/batch/jobs/{batch_id}")
        r.raise_for_status()
        status = r.json()["status"]
        if status == "SUCCESS":
            return "ended"
        if status == "TIMEOUT_EXCEEDED":
            return "expired"
        if status in ("FAILED", "CANCELLED", "CANCELLATION_REQUESTED"):
            return "failed"
        return "in_progress"

    def fetch(self, batch_id: str) -> dict[str, dict]:
        r = self.http.get(f"/batch/jobs/{batch_id}")
        r.raise_for_status()
        output_file = r.json()["output_file"]
        content = self.http.get(f"/files/{output_file}/content").text
        out: dict[str, dict] = {}
        for raw_line in content.splitlines():
            if not raw_line.strip():
                continue
            line = json.loads(raw_line)
            response = line.get("response") or {}
            out[line["custom_id"]] = {
                "custom_id": line["custom_id"],
                "status_code": response.get("status_code", 200),
                "body": response.get("body"),
            }
        return out
```

Wire it: add `"mistral": "mistral"` to `_API_KEY_TYPE_TO_BACKEND`, and in `make_backend`:

```python
    if name == "mistral":
        return MistralBatchBackend(api_key=config.mistral_api_key)
```

Note: Mistral's output JSONL line shape (`response.body`) should mirror OpenAI's; if the live `output_file` line nests differently, adjust `fetch` when the user runs the paid smoke — the unit test fixes the poll mapping and the adapter round-trip, which is what we can verify offline. Add a `# ponytail:` comment marking `fetch`'s line shape as smoke-confirmable.

- [ ] **Step 5: Run tests**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_backend_mistral.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/llm/mistral.py tests/quality/batch/backends.py tests/unit/test_batch_backend_mistral.py
git commit -m "feat(batch): Mistral batch backend via httpx REST"
```

---

## Task 5: Gemini batch backend + sentence-mapping persistence

**Files:**
- Modify: `tests/quality/batch/backends.py` (add `GeminiBatchBackend`), `src/services/llm/gemini.py` (hooks + reusable numbering helper), `tests/quality/batch/manifest.py` (per-request `gemini_sentences`), `tests/quality/test_runner.py` (submit stores mapping; collect post-processes)
- Test: `tests/unit/test_batch_backend_gemini.py`

**Interfaces:**
- Consumes: `google-genai` (`genai.Client`), the existing `number_sentences_in_chunk` / `post_process_gemini_response` in `gemini.py`, `GeminiAnswer` schema (`get_pydantic_model(..., use_gemini_answer=True)`).
- Produces: `GeminiAdapter.supports_batch=True`; `build_batch_request(self, request, custom_id) -> dict` returning `{custom_id, request:{contents, config}, _gemini_sentences: {chunk_id: [sentences]}}` where `config` carries `response_mime_type="application/json"` + `response_schema` (GeminiAnswer JSON schema) and the numbered prompt is in `contents`; `parse_batch_result(cls, raw) -> LLMResponse` returns the raw `GeminiAnswer` JSON (sentence_numbers, empty quote_text) as `answer_text`, `provider="gemini"`. The collect step reconstructs quote text via `post_process_gemini_response` using the stored mapping. `GeminiBatchBackend(api_key)` name `"google"`: `submit` via `client.batches.create(model, src=[{key, request}...])` (inline), `poll` maps `JOB_STATE_SUCCEEDED`→`ended`, `JOB_STATE_EXPIRED`→`expired`, `JOB_STATE_FAILED`/`CANCELLED`→`failed`, else `in_progress`; `fetch` reads `dest.inlined_responses` → `{key: {custom_id, response}}`. `_API_KEY_TYPE_TO_BACKEND["google"]="google"`.

**Design note (why the extra field):** Gemini's quote extraction numbers sentences at request-build time and reconstructs quote text from returned sentence numbers at parse time. `parse_batch_result` is a stateless classmethod running in a *later* `batch-collect` process, so the mapping must be persisted. Store it per-request in the manifest (`requests[i]["gemini_sentences"]`) at submit and apply `post_process_gemini_response` in collect. This keeps `parse_batch_result` stateless and reuses the proven post-processor.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_batch_backend_gemini.py
import json

from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.gemini import GeminiAdapter
from tests.quality.batch.backends import GeminiBatchBackend


def test_gemini_build_batch_request_has_schema_and_sentence_map():
    a = GeminiAdapter(api_key="k", model="gemini-2.5-flash")
    req = GenerationRequest(
        prompt="Can it move and shoot?",
        context=["The operative can move. It can also shoot."],
        chunk_ids=["chunkidxabc12345"],
        config=GenerationConfig(system_prompt="s", max_tokens=400, temperature=0.0),
    )
    line = a.build_batch_request(req, "gen__t__gemini-2.5-flash__run0")
    assert line["custom_id"] == "gen__t__gemini-2.5-flash__run0"
    cfg = line["request"]["config"]
    assert cfg["response_mime_type"] == "application/json"
    assert "response_schema" in cfg
    # sentence map carried out-of-band for collect-time reconstruction
    assert line["_gemini_sentences"]  # {chunk_id: [sentences]}


def test_gemini_parse_batch_result_returns_geminianswer_json():
    content = json.dumps({"smalltalk": False, "short_answer": "Yes.", "persona_short_answer": "x",
                          "quotes": [{"quote_title": "Move", "sentence_numbers": [1], "quote_text": ""}],
                          "explanation": "e", "persona_afterword": "a"})
    raw = {"custom_id": "c", "response": {
        "candidates": [{"content": {"parts": [{"text": content}]}, "finish_reason": "STOP"}],
        "usage_metadata": {"prompt_token_count": 8, "candidates_token_count": 4, "total_token_count": 12},
        "model_version": "gemini-2.5-flash"}}
    resp = GeminiAdapter.parse_batch_result(raw)
    assert resp.provider == "gemini"
    assert json.loads(resp.answer_text)["quotes"][0]["sentence_numbers"] == [1]


def test_gemini_backend_poll_mapping():
    b = GeminiBatchBackend(api_key="k")

    class _Job:
        def __init__(self, state):
            self.state = type("S", (), {"name": state})()

    class _Batches:
        def __init__(self, state):
            self._state = state

        def get(self, name=None):
            return _Job(self._state)

    class _Client:
        def __init__(self, state):
            self.batches = _Batches(state)

    b._client = _Client("JOB_STATE_SUCCEEDED")
    assert b.poll("n") == "ended"
    b._client = _Client("JOB_STATE_EXPIRED")
    assert b.poll("n") == "expired"
    b._client = _Client("JOB_STATE_FAILED")
    assert b.poll("n") == "failed"
    b._client = _Client("JOB_STATE_RUNNING")
    assert b.poll("n") == "in_progress"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_backend_gemini.py -v`
Expected: FAIL — `ImportError: cannot import name 'GeminiBatchBackend'`, `NotImplementedError` on the hook.

- [ ] **Step 3: Refactor gemini.py — extract the numbering into a reusable helper**

Read `gemini.py:84-112`. Factor the "number sentences across `request.context` / `request.chunk_ids`" block into an instance/static method so both `generate()` and `build_batch_request` use it (DRY):

```python
    @staticmethod
    def _number_context(context, chunk_ids):
        """Return (numbered_chunks, synthetic_chunk_ids, chunk_id_to_sentences)."""
        numbered_chunks, chunk_id_to_sentences, synthetic_chunk_ids = [], {}, []
        for i, chunk in enumerate(context):
            if chunk_ids and i < len(chunk_ids):
                full = chunk_ids[i]
                chunk_id = full[-8:] if len(full) > 8 else full
            else:
                chunk_id = str(i)
            numbered_chunk, sentences = number_sentences_in_chunk(chunk)
            numbered_chunks.append(numbered_chunk)
            chunk_id_to_sentences[chunk_id] = sentences
            synthetic_chunk_ids.append(chunk_id)
        return numbered_chunks, synthetic_chunk_ids, chunk_id_to_sentences
```

Update `generate()` to call `self._number_context(...)` in place of the inline loop (behavior identical — verify existing Gemini unit tests still pass).

- [ ] **Step 4: Add the Gemini batch hooks**

```python
    supports_batch = True

    def build_batch_request(self, request: GenerationRequest, custom_id: str) -> dict:
        from src.services.llm.prompt_builder import build_system_prompt

        numbered, synthetic_ids, sentence_map = self._number_context(
            request.context, request.chunk_ids
        )
        gemini_system_prompt = build_system_prompt("gemini")
        full_prompt = (
            f"{gemini_system_prompt}\n\n"
            f"{self._build_prompt(request.prompt, numbered, synthetic_ids)}"
        )
        model_cls = get_pydantic_model(request.config.structured_output_schema, use_gemini_answer=True)
        max_tokens = request.config.max_tokens * 3 if self.uses_completion_tokens else request.config.max_tokens
        return {
            "custom_id": custom_id,
            "request": {
                "contents": [{"parts": [{"text": full_prompt}], "role": "user"}],
                "config": {
                    "max_output_tokens": max_tokens,
                    "temperature": request.config.temperature,
                    "response_mime_type": "application/json",
                    "response_schema": model_cls.model_json_schema(),
                },
            },
            "_gemini_sentences": sentence_map,
        }

    @classmethod
    def parse_batch_result(cls, raw: dict) -> LLMResponse:
        resp = raw.get("response")
        if resp is None:
            raise RuntimeError(f"batch item {raw.get('custom_id')} has no response")
        candidates = resp.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"batch item {raw.get('custom_id')} returned no candidates")
        text = candidates[0]["content"]["parts"][0]["text"]
        usage = resp.get("usage_metadata", {})
        prompt_tokens = usage.get("prompt_token_count", 0)
        completion_tokens = usage.get("candidates_token_count", 0)
        cached = usage.get("cached_content_token_count", 0) or 0
        return LLMResponse(
            response_id=uuid4(),
            answer_text=text,   # GeminiAnswer JSON w/ sentence_numbers; collect fills quote_text
            confidence_score=0.8,
            token_count=usage.get("total_token_count", prompt_tokens + completion_tokens),
            latency_ms=0,
            provider="gemini",
            model_version=resp.get("model_version", ""),
            citations_included=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cached,
            cache_creation_tokens=0,
        )
```

- [ ] **Step 5: Add `GeminiBatchBackend`**

```python
class GeminiBatchBackend:
    """Gemini batch via google-genai inline requests (no file upload)."""

    name = "google"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None
        self._model = None  # set on submit; needed by create()

    @property
    def client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def submit(self, lines: list[dict]) -> str:
        # lines: [{custom_id, request:{contents, config}, _gemini_sentences}]
        model = lines[0].get("model") or self._model
        src = [{"key": x["custom_id"], "request": x["request"]} for x in lines]
        job = self.client.batches.create(model=model, src=src)
        logger.info(f"Submitted Gemini batch {job.name} ({len(lines)} requests)")
        return job.name

    def poll(self, batch_id: str) -> str:
        state = self.client.batches.get(name=batch_id).state.name
        if state == "JOB_STATE_SUCCEEDED":
            return "ended"
        if state == "JOB_STATE_EXPIRED":
            return "expired"
        if state in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
            return "failed"
        return "in_progress"

    def fetch(self, batch_id: str) -> dict[str, dict]:
        job = self.client.batches.get(name=batch_id)
        out: dict[str, dict] = {}
        for item in job.dest.inlined_responses:
            key = getattr(item, "key", None) or getattr(item, "custom_id", None)
            out[key] = {"custom_id": key, "response": _genai_to_dict(item.response)}
        return out
```

`submit` needs the model name. The batch line's `model` is not in the body (Gemini takes it at `create`). Add `"model": self.model` to the dict returned by `build_batch_request` (top level, alongside `custom_id`), and read `lines[0]["model"]` in `submit`. Add a small `_genai_to_dict(resp)` helper that normalizes the SDK response object into the dict shape `parse_batch_result` expects (candidates/usage_metadata/model_version) — use `resp.model_dump()` if available, else attribute access. Mark `fetch`/`_genai_to_dict` with a `# ponytail:` note that the exact SDK result surface is smoke-confirmable.

Wire: `_API_KEY_TYPE_TO_BACKEND["google"]="google"`; `make_backend("google")` → `GeminiBatchBackend(api_key=config.google_api_key)`.

- [ ] **Step 6: Persist + apply the sentence map (manifest + collect)**

In `tests/quality/batch/manifest.py`, the `requests` rows are free-form dicts; store `gemini_sentences` on the row when building gen requests for Gemini (in `submit_batch_run`). In `collect_batch_run`, after `parse_batch_result` yields a Gemini `LLMResponse`, look up the row's `gemini_sentences` by `custom_id` and call the existing `post_process_gemini_response(answer_dict, sentence_map)` to fill `quote_text`, then re-serialize into `answer_text`. Reuse whatever `generate()` calls; grep `post_process_gemini_response` for its exact signature and apply identically. Guard with `if resp.provider == "gemini" and row.get("gemini_sentences")`.

- [ ] **Step 7: Run tests**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_backend_gemini.py tests/unit/test_llm_adapters.py -k gemini -v`
Expected: PASS (new backend tests + existing Gemini adapter tests unaffected by the `_number_context` refactor).

- [ ] **Step 8: Commit**

```bash
git add src/services/llm/gemini.py tests/quality/batch/backends.py tests/quality/batch/manifest.py tests/quality/test_runner.py tests/unit/test_batch_backend_gemini.py
git commit -m "feat(batch): Gemini batch backend with sentence-map reconstruction"
```

---

## Task 6: Grok batch backend (httpx REST, Responses API) + judge routing

**Files:**
- Modify: `tests/quality/batch/backends.py` (add `GrokBatchBackend`), `src/services/llm/grok.py` (hooks)
- Test: `tests/unit/test_batch_backend_grok.py`

**Interfaces:**
- Consumes: `httpx`, `config.x_api_key`.
- Produces: `GrokAdapter.supports_batch=True` + hooks. `build_batch_request` emits `{custom_id, batch_request_id, batch_request:{responses:{model, input, ...}}}` matching xAI's Responses-API batch shape; `parse_batch_result` reads the Responses output → `LLMResponse` (`provider="grok"`). `GrokBatchBackend(api_key)` name `"x"`: `submit` → `POST /v1/batches` (name) then `POST /v1/batches/{id}/requests` (batch_requests) → returns `batch_id`; `poll` → `GET /v1/batches/{id}` maps `num_pending==0`→`ended` else `in_progress` (`failed` if the batch itself errors); `fetch` → paginated `GET /v1/batches/{id}/results` → `{batch_request_id: {custom_id, response}}`. `_API_KEY_TYPE_TO_BACKEND["x"]="x"`; `make_backend("x")` → `GrokBatchBackend`. Because the judge default (`grok-4-1-fast-reasoning`) is now batchable, `resolve_backend(judge_model)` returns this backend and the existing `_submit_judge_batch` path activates automatically — no judge-routing code change needed, but the judge round now takes two collects.

**Risk note (surface to reviewer):** xAI batch uses the **Responses API** (`input`, not chat `messages`) and a **per-request** success model; the discount is unquantified (defaulted 0.5 in Task 1 with a flag). The request/parse shapes here are built from the REST docs and are **smoke-confirmable only** — unit tests fix the transport/poll logic and the body scaffold, not live fidelity. Mark the body-building and result-parsing with `# ponytail:` smoke-confirm comments.

- [ ] **Step 1: Write the failing test (poll + transport with fake httpx; body scaffold)**

```python
# tests/unit/test_batch_backend_grok.py
from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.grok import GrokAdapter
from tests.quality.batch.backends import GrokBatchBackend


def test_grok_build_batch_request_shape():
    a = GrokAdapter(api_key="k", model="grok-4-1-fast-reasoning")
    req = GenerationRequest(prompt="q", context=["c"],
                            config=GenerationConfig(system_prompt="s", max_tokens=300, temperature=0.0))
    line = a.build_batch_request(req, "judge__t__grok__run0")
    assert line["custom_id"] == "judge__t__grok__run0"
    assert "batch_request" in line
    assert line["batch_request"]["responses"]["model"] == "grok-4-1-fast-reasoning"


def test_grok_backend_poll_pending_zero_is_ended():
    b = GrokBatchBackend(api_key="k")

    class _Resp:
        def __init__(self, pending):
            self._p = pending
            self.status_code = 200

        def json(self):
            return {"state": {"num_pending": self._p, "num_error": 0}}

        def raise_for_status(self):
            pass

    class _HTTP:
        def __init__(self, pending):
            self._p = pending

        def get(self, *a, **k):
            return _Resp(self._p)

    b._http = _HTTP(0)
    assert b.poll("x") == "ended"
    b._http = _HTTP(5)
    assert b.poll("x") == "in_progress"
```

- [ ] **Step 2: Run to verify it fails**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_backend_grok.py -v`
Expected: FAIL — `ImportError: cannot import name 'GrokBatchBackend'`, `NotImplementedError` on the hook.

- [ ] **Step 3: Implement Grok adapter hooks — `src/services/llm/grok.py`**

```python
    supports_batch = True

    def build_batch_request(self, request: GenerationRequest, custom_id: str) -> dict:
        # ponytail: xAI Responses-API batch shape from REST docs; smoke-confirm the
        # exact `input`/`text.format` fields against a live run before trusting output.
        full_prompt = self._build_prompt(request.prompt, request.context, request.chunk_ids)
        model_cls = get_pydantic_model(request.config.structured_output_schema)
        return {
            "custom_id": custom_id,
            "batch_request_id": custom_id,
            "batch_request": {
                "responses": {
                    "model": self.model,
                    "input": [
                        {"role": "system", "content": request.config.system_prompt},
                        {"role": "user", "content": full_prompt},
                    ],
                    "max_output_tokens": request.config.max_tokens,
                    "temperature": request.config.temperature,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": model_cls.__name__,
                            "schema": model_cls.model_json_schema(),
                            "strict": True,
                        }
                    },
                }
            },
        }

    @classmethod
    def parse_batch_result(cls, raw: dict) -> LLMResponse:
        # ponytail: smoke-confirm the Responses output path (output_text vs
        # output[].content[].text) against a live xAI batch result.
        resp = raw.get("response")
        if resp is None:
            raise RuntimeError(f"grok batch item {raw.get('custom_id')} has no response")
        content = resp.get("output_text")
        if content is None:
            # Responses API: output -> [{content:[{type:output_text, text}]}]
            out = resp.get("output") or []
            content = next(
                c["text"] for o in out for c in o.get("content", []) if c.get("type") == "output_text"
            )
        usage = resp.get("usage", {})
        prompt_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        completion_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
        cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0
        return LLMResponse(
            response_id=uuid4(),
            answer_text=content,
            confidence_score=0.8,
            token_count=prompt_tokens + completion_tokens,
            latency_ms=0,
            provider="grok",
            model_version=resp.get("model", ""),
            citations_included=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cached,
            cache_creation_tokens=0,
        )
```

- [ ] **Step 4: Implement `GrokBatchBackend` — `tests/quality/batch/backends.py`**

```python
class GrokBatchBackend:
    """xAI Grok batch via httpx REST (Responses-API batch; no xai_sdk dep)."""

    name = "x"
    BASE_URL = "https://api.x.ai/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._http = None

    @property
    def http(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(
                base_url=self.BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
        return self._http

    def submit(self, lines: list[dict]) -> str:
        created = self.http.post("/batches", json={"name": "quality-test"})
        created.raise_for_status()
        batch_id = created.json()["batch_id"]
        payload = {"batch_requests": [
            {"batch_request_id": x["batch_request_id"], "batch_request": x["batch_request"]}
            for x in lines
        ]}
        added = self.http.post(f"/batches/{batch_id}/requests", json=payload)
        added.raise_for_status()
        logger.info(f"Submitted Grok batch {batch_id} ({len(lines)} requests)")
        return batch_id

    def poll(self, batch_id: str) -> str:
        r = self.http.get(f"/batches/{batch_id}")
        r.raise_for_status()
        state = r.json().get("state", {})
        if state.get("num_pending", 1) == 0:
            return "ended"
        return "in_progress"

    def fetch(self, batch_id: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        token = None
        while True:
            params = {"limit": 100}
            if token:
                params["pagination_token"] = token
            r = self.http.get(f"/batches/{batch_id}/results", params=params)
            r.raise_for_status()
            data = r.json()
            for item in data.get("succeeded", []):
                cid = item["batch_request_id"]
                out[cid] = {"custom_id": cid, "response": item.get("response") or item.get("batch_response")}
            for item in data.get("failed", []):
                cid = item["batch_request_id"]
                out[cid] = {"custom_id": cid, "response": None}
            token = data.get("pagination_token")
            if not token:
                break
        return out
```

Wire: `_API_KEY_TYPE_TO_BACKEND["x"]="x"`; `make_backend("x")` → `GrokBatchBackend(api_key=config.x_api_key)`.

- [ ] **Step 5: Run tests**

Run: `source venv/bin/activate && pytest tests/unit/test_batch_backend_grok.py tests/unit/test_custom_judge_batch.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/llm/grok.py tests/quality/batch/backends.py tests/unit/test_batch_backend_grok.py
git commit -m "feat(batch): Grok batch backend via httpx REST; default judge now batchable"
```

---

## Task 7: Full suite + docs

**Files:**
- Modify: `tests/quality/CLAUDE.md`, `src/cli/CLAUDE.md`, `docs/batch-api-quality-tests-plan.md`

- [ ] **Step 1: Run the whole batch-related suite + lint**

Run:
```bash
source venv/bin/activate && pytest tests/unit -k "batch or token or judge" -v && ruff check src tests
```
Expected: PASS, no lint errors.

- [ ] **Step 2: Update docs**

- `tests/quality/CLAUDE.md` "Batch API workflow" → change coverage line: Anthropic, OpenAI, **Kimi, Qwen, Mistral, Gemini, Grok** batch; only **DeepSeek** falls back to live. Note the default grok judge now batches (two collects), and that Kimi/Grok savings are estimates pending discount confirmation.
- `src/cli/CLAUDE.md` → same coverage note.
- `docs/batch-api-quality-tests-plan.md` → flip the Extension section "❌ NOT IMPLEMENTED" banner; move Kimi/Qwen/Mistral/Gemini/Grok from "Missing/deferred" to done; keep DeepSeek + live-smoke as the only remaining items; note per-backend discount dict shipped.

- [ ] **Step 3: Commit**

```bash
git add tests/quality/CLAUDE.md src/cli/CLAUDE.md docs/batch-api-quality-tests-plan.md
git commit -m "docs(batch): expand coverage to Kimi/Qwen/Mistral/Gemini/Grok"
```

---

## Self-Review

**Spec coverage:** Extension providers Kimi (T2), Qwen (T2), Mistral (T4), Gemini (T5), Grok (T6); per-backend discount dict (T1); expired resubmission (T3); docs (T7). DeepSeek intentionally stays live (no task). Live smoke = user's paid step (out of code scope). ✅
**Placeholder scan:** Two areas explicitly marked smoke-confirmable (Mistral `fetch` line shape, Gemini SDK result surface, Grok Responses I/O) — these are real external-fidelity unknowns, flagged with `# ponytail:` comments and covered offline for transport/poll/scaffold. Not placeholders in the plan-failure sense; each has concrete code + a runnable test.
**Type consistency:** `build_batch_request(self, request, custom_id) -> dict` and `classmethod parse_batch_result(cls, raw) -> LLMResponse` match the base-class hooks and the shipped Claude/ChatGPT adapters. Backend `submit/poll/fetch` match the `BatchBackend` Protocol. `batch_discount_for` / `BATCH_DISCOUNT` used consistently in T1 and referenced by name only there.

## Verification (end of implementation, before code review)

1. `pytest tests/unit -k "batch or token or judge"` — all green.
2. `ruff check src tests` — clean.
3. Faked-network end-to-end: reuse the existing `test_batch_statemachine.py` harness pattern to drive a mixed submit→collect with a Kimi (batch) + DeepSeek (live) model and a Grok judge, asserting a report is produced and `batch_savings_usd` is present. (No live calls.)
4. Live smoke (**user only, costs money**): `--batch-submit --test <t> --model kimi-k2.5 --model gemini-2.5-flash --judge-model grok-4-1-fast-reasoning` then `--batch-collect <dir>` until `phase == done`; confirm report + savings lines.
