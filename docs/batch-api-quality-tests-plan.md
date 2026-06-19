# Batch API for Quality Tests — Design Plan

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
- **Mixed runs:** models without a batch API (grok, gemini, kimi, deepseek, mistral, etc.) **fall back to live async**, run alongside the batched models, one unified report.

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

**Note:** default judge is `grok-4-1-fast-reasoning` (no batch API) → judge round falls back to live unless the user selects a claude/openai judge.

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
