# Batch API for Quality Tests — Design Plan

## Implementation status (2026-07-09)

**Base scope SHIPPED** on branch `feat/batch-api-quality-tests` (impl plan: [docs/superpowers/plans/2026-07-09-batch-api-quality-tests.md](superpowers/plans/2026-07-09-batch-api-quality-tests.md)). Anthropic + OpenAI batch backends, everything else live fallback.

**✅ Done (base scope):**
- `src/lib/tokens.py` — `calculate_llm_cost(..., batch=True)` + `batch_savings`; batch discount **stacks on top of cache** accounting (both computed independently).
- `src/services/llm/base.py` — `supports_batch` + `build_batch_request` + `parse_batch_result` hooks.
- `src/services/llm/claude.py`, `chatgpt.py` — hooks implemented; `supports_batch = True`.
- `tests/quality/batch/manifest.py` — `BatchManifest` (state file).
- `tests/quality/batch/backends.py` — `AnthropicBatchBackend`, `OpenAICompatBatchBackend`, `resolve_backend`/`make_backend`.
- `tests/quality/reporting/` — `batch_savings_usd`/`judge_batch_savings_usd` fields, `avg_batch_savings`, report + console "Batch net savings" line + combined total.
- `tests/quality/metadata_generator.py` + `output_parser.py` — persist/read back `batch`, `batch_savings_usd`, **and `cache_savings_usd`** per output.
- `tests/quality/test_runner.py` — `submit_batch_run` / `collect_batch_run` state machine; judge core factored (`build_judge_request`/`parse_result`/`_judge_parsed_outputs`) and shared with `replay_tests_from_outputs`.
- `src/cli/quality_test.py` + `__main__.py` — `--batch-submit` / `--batch-collect` (mutually exclusive).
- Docs: `tests/quality/CLAUDE.md`, `src/cli/CLAUDE.md`, `CLI_USAGE.md`.
- Verified: unit suite green + faked-network end-to-end `batch-collect` (real parse→save→report), report shows **both** cache + batch savings.

**🟡 Intentional divergences from this plan** (see impl plan "Scope decisions"):
- No separate `request_builder.py` / `result_parser.py` — that logic lives in the adapter hooks (keeps provider code inside `src/services/llm/`).
- Claude batch uses the **tool-use JSON** path, not `output_config.format` (reuses the proven fallback).
- `OpenAIBatchBackend` shipped as the parameterized `OpenAICompatBatchBackend` (base_url/api_key) — OpenAI wired + verified.
- Batch discount is a global `0.5` (both shipped backends are 50%), **not** yet a per-backend dict.

**✅ Extension SHIPPED (2026-07-10)** on branch `feat/batch-api-extension`
(impl plan: [docs/superpowers/plans/2026-07-10-batch-api-extension.md](superpowers/plans/2026-07-10-batch-api-extension.md)):
- **Kimi & Qwen** — `supports_batch = True`; reuse the OpenAI-compat backend at the Moonshot / DashScope base_url (json_object + schema-in-prompt, matching each adapter's `generate()`).
- **Mistral** — `MistralBatchBackend` via httpx REST (`/v1/batch/jobs` + file upload); OpenAI-compatible json_schema body. No `mistralai` dep.
- **Gemini** — `GeminiBatchBackend` via `google-genai` inline batches; sentence map persisted per-request in the manifest so verbatim quote extraction survives into `batch-collect`.
- **Grok** — `GrokBatchBackend` via httpx REST (Responses-API batch shape). The default judge (`grok-4-1-fast-reasoning`) is now batchable → judge round batches (two collects). No `xai_sdk` dep.
- **Per-backend discount dict** in `tokens.py` (`BATCH_DISCOUNT` keyed by backend; `batch_discount_for`); `calculate_llm_cost(..., batch_backend=...)`.
- **`expired` whole-batch resubmission** on `batch-collect` (deterministic rebuild from persisted RAG context).

**❌ Still missing / by design:**
- DeepSeek batch — stays live-async (no native batch API on `api.deepseek.com`; as designed).
- **Live smoke** (Verification §2/§3 — costs money): to be run by the user. Mistral/Grok result-line shapes and the Gemini inline-result surface are `# ponytail:`-flagged as smoke-confirmable.
- **Discount confirmation:** Kimi (`moonshot`) and Grok (`x`) default to 50% in `BATCH_DISCOUNT` but publish only "reduced pricing" — confirm the real % and correct the dict; their `batch_savings_usd` is an estimate until then.

## Context

Quality tests (`python -m src.cli quality-test`) make **two LLM calls per result**:
1. **Generation** — `orchestrator.generate_with_context()`, once per `test × model × run` ([test_runner.py:255](../tests/quality/test_runner.py)).
2. **Judge** — `CustomJudge.evaluate()`, once per generated result ([custom_judge.py:299](../tests/quality/custom_judge.py)).

Today both run live/async with a concurrency semaphore (`QUALITY_TEST_MAX_CONCURRENT_LLM_REQUESTS`) and exponential-backoff retry. RAG is already pre-cached (`context_file` JSON), so RAG is not on the hot path. For large matrices (`--all-models --runs 10`), this hits rate limits, is slow, and pays full token price.

**Anthropic and OpenAI both offer a Batch API at 50% token cost** with ≤24h turnaround. This plan adds an opt-in batch path for quality tests to cut cost ~50% on eligible models and eliminate rate-limit thrash, while reusing the existing prompt-building, output format, judge, and reporting code.

### Decisions (confirmed with user)
- **Scope:** batch **both** generation and judge, as **two sequential batch rounds** (gen batch finishes → judge batch submitted).
- **CLI UX:** **split commands** — `batch-submit` returns batch IDs and exits; `batch-collect <dir>` is **single-pass** (checks batch status once, advances if ready, else prints "not ready, re-run later" and exits — **no internal polling/backoff**). The user re-runs `batch-collect` manually until the final report is produced. Resumable via persisted state. Fits CI / multi-hour waits.
- **Cost tracking:** **batch savings** (50% discount on batched calls) must be tracked and reported **alongside the existing cache savings** — both surfaced per-result and in the aggregate report.
- **Mixed runs:** models without a batch API **fall back to live async**, run alongside the batched models, one unified report. Per research (see [Extension](#extension-batch-support-for-gemini-mistral-kimi-qwen-deepseek)), the only provider here with **no** native batch API is **DeepSeek** (on `api.deepseek.com`); Gemini, Mistral, Kimi, Qwen — and even Grok — all support batch. So the batchable set is much larger than this plan originally assumed.

## Batch API mechanics (reference)

| | Anthropic | OpenAI |
|---|---|---|
| Submit | `client.messages.batches.create(requests=[Request(custom_id, params=MessageCreateParamsNonStreaming(...))])` | upload JSONL via `client.files.create(purpose="batch")` → `client.batches.create(input_file_id, endpoint="/v1/chat/completions", completion_window="24h")` |
| Poll | `batches.retrieve(id).processing_status` → `"ended"` | `batches.retrieve(id).status` → `"completed"` |
| Results | `batches.results(id)` → iterator of `{custom_id, result.type, result.message}` | download `output_file_id` JSONL → lines `{custom_id, response.body}` |
| Structured output | `params.output_config={"format":{"type":"json_schema","schema":...}}` (cannot use `beta.messages.parse()` in batch) | line `body.response_format={"type":"json_schema","json_schema":...}` |
| Caching | `cache_control` blocks supported in batch params | `prompt_caching` automatic |
| Discount | 50% | 50% |
| Eligible models here | `claude-*` (`ClaudeAdapter`) | `gpt-*`, `o3*` (`ChatGPTAdapter`) |

**Note:** default judge is `grok-4-1-fast-reasoning`. This plan originally assumed Grok has no batch API and the judge round always falls back to live — **that assumption is wrong**: xAI does offer a batch API (own SDK shape, see [Extension](#extension-batch-support-for-gemini-mistral-kimi-qwen-deepseek)). The judge round can still run live for simplicity, but batching the default judge is now possible.

## Architecture — two-phase state machine

The batch run is driven by a manifest (`batch_state.json`) in the results dir. `batch-collect` is **idempotent, single-pass, and re-runnable by hand**: one invocation does **one status check** and advances the `phase` at most one step, then exits. It never polls or sleeps internally. Because judging needs generation output, the normal happy path is **submit once, then collect ~2 times**:

- **collect #1** — generation batch ended → write outputs, submit judge batch (or run judge live if judge model isn't batchable).
- **collect #2** — judge batch ended → compute metrics + report.
- If a batch isn't ready yet, that collect simply reports status and exits; re-run later. (With a non-batch judge like the default grok, judging runs live inside collect #1, so a single collect finishes the run.)

```
batch-submit
  └─ RAG (cached) → build generation GenerationRequests (reuse live path)
     ├─ batch-eligible models → submit generation batch per backend
     └─ non-batch models     → run live async now, write output_*.md
     write batch_state.json (phase = "generation_submitted")

batch-collect  (single pass per invocation; user re-runs until phase == "done")
  phase generation_submitted:
     check gen batch status ONCE
       not ended → print status, exit (re-run later)
       ended     → retrieve gen results → write output_*.md for batched models
                   build judge requests for ALL results (batched + live)
                     judge model batchable     → submit judge batch (phase = judge_submitted)
                     judge model not batchable → run judge live now → score → report (phase = done)
  phase judge_submitted:
     check judge batch status ONCE
       not ended → print status, exit (re-run later)
       ended     → retrieve judge results (phase = scoring, fall through)
  phase scoring:
     parse outputs + judge results → compute metrics → IndividualTestResults
     → aggregate → ReportGenerator (phase = done)
```

The judge step intentionally mirrors the existing `replay_tests_from_outputs()` flow ([test_runner.py:589](../tests/quality/test_runner.py)) — once generation outputs exist as `output_*.md`, judging is a replay over saved outputs, just sourced from a batch instead of live calls.

## Key reuse points (do NOT reinvent)

- **Prompt building:** generation requests built exactly as the live path (`generate_with_context` → provider's request assembly, RAG context, cache markers); judge requests via `CustomJudge`'s existing template fill + `split_user_prompt_for_cache` / `strip_cache_markers` ([custom_judge.py:263](../tests/quality/custom_judge.py)).
- **Output format:** batched generations write the same `output_{test_id}_{model}_{run}.md` files; everything downstream is identical.
- **Parsing back:** `output_parser.parse_output_directory()` already reconstructs results from `output_*.md`.
- **Judge replay:** extend `replay_tests_from_outputs()` to accept a batch-sourced judge instead of live.
- **Reporting:** `QualityReport` + `aggregate_results()` + `ReportGenerator` unchanged.
- **Cost model:** `calculate_llm_cost()` in [src/lib/tokens.py](../src/lib/tokens.py) — add a batch discount path.

## New components

New module `tests/quality/batch/`:

- **`manifest.py`** — `BatchManifest` dataclass + `load`/`save` (JSON in results dir). Fields: `phase`, `created_at`, `models`, `judge_model`, `runs`, `test_ids`, `report_dir`, `generation: {backend: {batch_id, status}}`, `judge: {backend: {batch_id, status}}`, `requests: [{custom_id, test_id, model, run_num, kind: "gen"|"judge", backend, batchable}]`, `live_done: [custom_id...]`. `custom_id` encodes `{kind}__{test_id}__{model}__run{n}` for round-trip mapping.
- **`backends.py`** — thin wrapper per batch backend exposing a uniform interface: `submit(items) -> batch_id`, `poll(batch_id) -> status`, `fetch(batch_id) -> {custom_id: LLMResponse}`. Two impls: `AnthropicBatchBackend`, `OpenAIBatchBackend`. Map a friendly model name → backend via the existing `LLMProviderFactory._model_registry` adapter class.
- **`request_builder.py`** — convert a `GenerationRequest` (`prompt`, `context`, `config`) into a batch line: Anthropic `MessageCreateParamsNonStreaming` (with `output_config.format` for structured schema + `cache_control` blocks) and OpenAI JSONL body (`response_format`, messages). Must replicate the structured-output + caching logic currently in [claude.py](../src/services/llm/claude.py) / [chatgpt.py](../src/services/llm/chatgpt.py) but in **non-parse** batch form.
- **`result_parser.py`** — convert a raw batch result item into the existing `LLMResponse` (answer_text, prompt/completion/cache tokens, model_version, `structured_output`) so callers can't tell it came from a batch. Handle per-item `errored`/`expired` → set the error path identical to live failures ([test_runner.py:302-326](../tests/quality/test_runner.py)).

## Changes to existing files

- **`src/services/llm/base.py`** — add to `LLMProvider`: `supports_batch: bool = False` and two optional hooks `build_batch_request(self, request: GenerationRequest) -> dict` and `classmethod parse_batch_result(raw) -> LLMResponse`. Keeps batch knowledge inside each adapter (respects "no provider-specific code outside `src/services/llm/`").
- **`src/services/llm/claude.py`, `chatgpt.py`** — implement the three batch hooks; set `supports_batch = True`. Reuse their existing schema/cache helpers.
- **`src/lib/tokens.py`** — `calculate_llm_cost(..., batch: bool = False)`. When `batch`, apply the 50% discount **on top of** cache accounting and add a `batch_savings` field to `LLMCostBreakdown` (sibling of the existing `cache_savings`). `batch_savings` = (what the same tokens would cost live, after cache) − (batched cost). Both savings are computed and stored independently so neither double-counts the other.
- **`tests/quality/reporting/report_models.py` + `report_generator.py`** — `IndividualTestResult` already carries `cache_savings_usd` / `judge_cache_savings_usd`; add `batch_savings_usd` / `judge_batch_savings_usd`. `ModelSummary` aggregates them; the cost-breakdown header in `report.md` gains a "Batch savings" line next to the existing cache-savings line, plus a combined total-savings figure.
- **`tests/quality/test_runner.py`** — add `submit_batch_run(...)` and `collect_batch_run(report_dir)` orchestrating the state machine; refactor `run_test`'s gen-failure handling and judge invocation so both the live and batch paths share them. Extend `replay_tests_from_outputs` (or factor its judge core) to accept batch-sourced judge responses.
- **`src/cli/quality_test.py` + `src/cli/__main__.py`** — add mutually-exclusive flags `--batch-submit` and `--batch-collect <results_dir>` to the `quality-test` subcommand. `--batch-submit` reuses existing `--test/--model/--all-models/--runs/--judge-model/--force-rag` args and prints the IDs + the exact `batch-collect` command to run. `--batch-collect` loads the manifest and advances the state machine, printing current `phase` and per-batch status each invocation.
- **Docs:** update [tests/quality/CLAUDE.md](../tests/quality/CLAUDE.md) and [src/cli/CLAUDE.md](../src/cli/CLAUDE.md) with the batch workflow.

## Results-dir / logging integration

Reuse the existing `tests/quality/results/{timestamp}/` convention. The batch run adds exactly one new artifact, `batch_state.json`; all other files (`output_*.md`, `prompt.md`, `report.md`, `report.json`, charts) are written by the **existing** code at the same paths. Because outputs are written incrementally as batches complete, a partially-collected run is inspectable. The per-result metadata JSON in `output_*.md` gains `"batch": true/false` and `"batch_savings_usd"` (alongside the existing cache-savings fields) so both savings types are attributable per result and re-derivable by `output_parser.py` on collect.

## Fallback & edge handling

- **Non-batch generation models:** run live in `batch-submit` (small N typically), outputs written immediately; their `custom_id`s land in `live_done`.
- **Non-batch judge model (default grok):** judge runs live in `batch-collect` scoring step — no judge batch submitted.
- **Per-item batch errors** (`errored`/`expired`/`canceled`): mapped to the existing error result path; surfaced in the report like any live failure. `expired` items can be re-submitted on a subsequent `batch-collect` (optional enhancement).
- **Mixed cache+batch cost:** Anthropic batch + cache stack; cost calc must apply the 50% batch discount on top of cache accounting.

## Verification

1. **Unit:** `request_builder` produces valid Anthropic/OpenAI batch params for a known `GenerationRequest` (structured schema + cache blocks present); `result_parser` round-trips a sample batch result item into an `LLMResponse` equal to the live shape. Add to `tests/unit/`.
2. **Tiny live smoke (costs money — run once, single test):**
   ```bash
   python -m src.cli quality-test --batch-submit --test eliminator-concealed-counteract --model claude-4.6-sonnet --judge-model gpt-4.1-mini
   # prints batch IDs + collect command
   python -m src.cli quality-test --batch-collect tests/quality/results/<timestamp>
   # single pass: prints status and exits if not ready; re-run by hand until phase == done
   ```
   Confirm: `report.md` generated; `output_*.md` match the live format; report shows a **"Batch savings"** line ≈ 50% of token cost **plus** the existing cache-savings line, with a combined total. Cross-check against an equivalent live run.
3. **Mixed run:** `--batch-submit --test <t> --model claude-4.6-sonnet --model grok-4-1-fast-reasoning` → grok runs live at submit, claude via batch; single report contains both.
4. **Resumability:** re-running `batch-collect` when a batch is not yet ended is a no-op that just prints status; re-running after `done` does not duplicate submissions or re-score. Manifest `phase` is the single source of truth.

## Risks / open considerations

- **Latency:** worst case ~48h (two 24h rounds). Acceptable for cost-sensitive batch CI; not for interactive iteration (keep the existing live path as default).
- **Structured outputs in batch:** Claude batch cannot use `beta.messages.parse()`; must hand-build `output_config.format` and parse the returned JSON. Validate the schema matches `StructuredLLMResponse` / `CustomJudgeResponse`.
- **Per-key API config:** batch backends must resolve the same API keys the factory uses (global `.env`; per-guild not relevant for quality tests).
- **Token-count fidelity:** ensure batch result usage fields (incl. cache read/creation) are read so cost + savings stay accurate.

---

## Extension: batch support for Gemini, Mistral, Kimi, Qwen, DeepSeek

> **✅ IMPLEMENTED (2026-07-10)** — Kimi, Qwen, Mistral, Gemini, and Grok now batch. Only **DeepSeek** remains on the live-async fallback. See [Implementation status](#implementation-status-2026-07-09). The notes below are the design reference the implementation followed.

Research (July 2026) into each provider's batch offering. The headline: batch coverage is far wider than the base plan assumed. Instead of two batch backends (Anthropic, OpenAI) with everything else live, there are **three backend families** and only **one** provider (DeepSeek) that genuinely has no batch path.

### Provider matrix

| Provider | Adapter (this repo) | Native batch? | API shape | custom-id field | Poll → done state | Structured output in batch | Cache in batch | Discount |
|---|---|---|---|---|---|---|---|---|
| Anthropic | `ClaudeAdapter` | Yes | `messages.batches` | `custom_id` | `processing_status == "ended"` | `output_config.format` | `cache_control` | 50% |
| OpenAI | `ChatGPTAdapter` | Yes | `/v1/batches` (JSONL files) | `custom_id` | `status == "completed"` | `response_format` json_schema | automatic | 50% |
| **Gemini** | `GeminiAdapter` | Yes | own SDK `client.batches.create` | `key` (JSONL) / list order (inline) | `state.name == "JOB_STATE_SUCCEEDED"` | `response_mime_type`+`response_schema` | `cached_content` | 50% |
| **Mistral** | (new `MistralAdapter`) | Yes | own SDK `client.batch.jobs` | `custom_id` | `status == "SUCCESS"` | `response_format` in body | n/a | 50% |
| **Kimi/Moonshot** | `KimiAdapter` | Yes | **OpenAI-compatible `/v1/batches`** | `custom_id` | `status == "completed"` | `response_format` json_schema | automatic | unconfirmed¹ |
| **Qwen/DashScope** | (new `QwenAdapter`) | Yes | **OpenAI-compatible `/v1/batches`** (compatible-mode base_url) | `custom_id` | `status == "completed"`² | `response_format` json_schema | automatic | 50% |
| **DeepSeek** | `DeepSeekAdapter` | **No** (on `api.deepseek.com`) | — 3rd-party only (SiliconCloud/Together/Novita) | — | — | — | — | n/a → **live fallback** |
| Grok/xAI | `GrokAdapter` | Yes | own SDK `client.batch.create`/`.add` | `custom_id` → `batch_request_id` | `status == "succeeded"` (per-item) | `response_format` json_schema | n/a | reduced¹ |

¹ Kimi and Grok docs state "reduced pricing" but don't publish the exact percentage — **verify against their pricing pages before trusting savings numbers**. Make the discount rate **per-backend configurable** rather than hardcoding `0.5` (see tokens.py change below).
² DashScope status flow: `validating → in_progress → finalizing → completed`.

### Three backend families (the lazy structural win)

The base plan's `backends.py` had two impls. This extension groups the additions so we write **three** new backends, not five:

1. **`OpenAICompatBatchBackend(base_url, api_key_env)`** — one parameterized class covering **OpenAI, Kimi, and Qwen**. All three use the identical `/v1/batches` flow: `files.create(purpose="batch")` → `batches.create(input_file_id, endpoint="/v1/chat/completions", completion_window="24h")` → poll `.status == "completed"` → download `output_file_id` JSONL. Only base_url + api-key env var differ. Point the stock `openai` SDK at each base_url:
   - OpenAI: `https://api.openai.com/v1`
   - Kimi: `https://api.moonshot.ai/v1` (`MOONSHOT_API_KEY`, models `kimi-k2.5`/`kimi-k2.6`)
   - Qwen: `https://dashscope.aliyuncs.com/compatible-mode/v1` (intl: `…ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`)
   This collapses the base plan's separate `OpenAIBatchBackend` into the parameterized one — net simpler.
2. **`GeminiBatchBackend`** — `google-genai` SDK. Distinct request/result shapes (see below).
3. **`MistralBatchBackend`** — `mistralai` SDK. `client.batch.jobs.create(input_files=[...], endpoint="/v1/chat/completions", model=...)`, inline `requests=[...]` allowed <10k, poll `client.batch.jobs.get(job_id).status`, download `job.output_file`.

Grok's batch (own `client.batch.create/.add` shape) would be a 4th native backend — **defer it**; keeping Grok (incl. the default judge) on the live path is the simplest correct option and the base plan already handles live judge. Add `GrokBatchBackend` only if judge-batch savings prove worth it.

DeepSeek: **no code** — stays on the existing live-async fallback path. (Batch would require routing to a 3rd-party host with a different key/base_url — out of scope.)

### Per-provider mechanics (implementation notes)

**Gemini** — most divergent, needs the most bespoke code in `request_builder`/`result_parser`:
- Submit: `client.batches.create(model=..., src=...)`. `src` = inline list of request dicts (<20 MB) **or** an uploaded JSONL file name (`client.files.upload(..., config=UploadFileConfig(mime_type='jsonl'))`).
- JSONL line shape is **not** OpenAI's: `{"key": "<custom_id>", "request": {"contents": [...], "config": {...}}}`.
- Structured output: `config.response_mime_type='application/json'` + `config.response_schema=<schema>` (not the `response_format`/`json_schema` wrapper). Validate the schema round-trips `CustomJudgeResponse` / `StructuredLLMResponse`.
- Poll: `client.batches.get(name).state.name` → `JOB_STATE_SUCCEEDED` / `JOB_STATE_RUNNING` / `JOB_STATE_PENDING` / `JOB_STATE_FAILED` / `JOB_STATE_EXPIRED` (48 h) / `JOB_STATE_CANCELLED`.
- Results: inline → `batch_job.dest.inlined_responses`; file → `batch_job.dest.file_name` then `client.files.download`. Each line a `GenerateContentResponse` or an error object. Reuse `GeminiAdapter`'s existing response→`LLMResponse` mapping.

**Mistral**:
- Upload: `client.files.upload(purpose="batch")`, JSONL lines `{"custom_id": "0", "body": {model, messages, max_tokens, response_format, …}}`.
- Poll states: `QUEUED / RUNNING / SUCCESS / FAILED / TIMEOUT_EXCEEDED / CANCELLATION_REQUESTED / CANCELLED`. Failed items land in a separate error file (`job.error_file`).
- Structured output via `body.response_format` (json_schema). Up to 1M requests/batch.

**Kimi/Moonshot & Qwen/DashScope** — the OpenAI-compatible pair:
- JSONL line is OpenAI-identical: `{"custom_id", "method": "POST", "url": "/v1/chat/completions", "body": {...}}`. Same `request_builder` output as OpenAI, same `result_parser`. This is why `OpenAICompatBatchBackend` handles all three with no shape-specific branches.
- Qwen caveat: results/limits are regional (50k req / 500 MB / 6 MB per line); embeddings use `text-embedding-v4`. Judge/gen only need `/v1/chat/completions`.

### Deltas to the base plan's "New components" / "Changes to existing files"

- **`backends.py`** — implement `OpenAICompatBatchBackend` (parameterized, replaces the base plan's `OpenAIBatchBackend`), `GeminiBatchBackend`, `MistralBatchBackend`. Map model→backend via `LLMProviderFactory._model_registry` adapter class (Kimi/Qwen adapters resolve to the OpenAI-compat backend with their base_url/key).
- **`request_builder.py` / `result_parser.py`** — add a Gemini variant (`key`+`request` envelope, `response_schema`, `dest.*` results) and a Mistral variant. Kimi/Qwen reuse the OpenAI path verbatim.
- **`src/services/llm/base.py` hooks** — implement `supports_batch` + `build_batch_request` + `parse_batch_result` in `GeminiAdapter`, `KimiAdapter`, and new `MistralAdapter`/`QwenAdapter`. `DeepSeekAdapter` leaves `supports_batch = False`.
- **`src/lib/tokens.py`** — make the batch discount **per-backend** (dict/lookup), default `0.5`, so Kimi/Grok can be corrected once their real rate is confirmed without a code change. Don't hardcode `0.5` globally.
- **Deps** — `mistralai` and `google-genai` SDKs (google-genai may already be present via `GeminiAdapter`; Kimi/Qwen need only the existing `openai` SDK, no new dep). Add `mistralai` to `requirements.txt` only if a `MistralAdapter` doesn't already pull it.
- **Config** — batch backends resolve keys from global `.env` (`MOONSHOT_API_KEY`, `DASHSCOPE_API_KEY`/`x_api_key` equivalents, `MISTRAL_API_KEY`, `GOOGLE_API_KEY`), same as the factory.

### Verification additions

- Unit: `request_builder` emits a valid **Gemini** `{key, request}` line with `response_schema`, and a valid **Mistral** `{custom_id, body}` line; `result_parser` round-trips one sample `GenerateContentResponse` and one Mistral output line into an `LLMResponse` equal to the live shape.
- Smoke (costs money, run once each): a `--batch-submit` with `--model gemini-2.5-flash`, and one with `--model kimi-k2.5` (exercises the OpenAI-compat path against a non-OpenAI base_url). Confirm `report.md` shows a Batch-savings line and outputs match live format.
- Discount audit: for Kimi and Grok, cross-check the reported `batch_savings_usd` against their published pricing before relying on the number; adjust the per-backend rate in tokens.py if not 50%.

### Sources

- [Gemini Batch API](https://ai.google.dev/gemini-api/docs/batch-api) · [batch-api.md.txt](https://ai.google.dev/gemini-api/docs/batch-api.md.txt)
- [Mistral Batch Processing](https://docs.mistral.ai/studio-api/batch-processing) · [Batch endpoints](https://docs.mistral.ai/api/endpoint/batch)
- [Kimi Batch API guide](https://platform.kimi.ai/docs/guide/use-batch-api) · [Migrating from OpenAI to Kimi](https://platform.moonshot.ai/docs/guide/migrating-from-openai-to-kimi)
- [DashScope/Qwen OpenAI-compatible batch](https://www.alibabacloud.com/help/en/model-studio/batch-interfaces-compatible-with-openai)
- [DeepSeek API docs](https://api-docs.deepseek.com/) (no native batch) · [SiliconCloud batch for DeepSeek](https://news.aibase.com/news/16228)
- [xAI Batch API](https://docs.x.ai/developers/advanced-api-usage/batch-api)
