"""Batch backends: the submit/poll/fetch envelope for the Batch APIs.

Provider-specific *request building* and *result parsing* live in the LLM
adapters (build_batch_request / parse_batch_result). Backends here only handle
submission, status polling, and result retrieval, normalizing each provider's
result item into the dict shape the matching adapter's parse_batch_result reads.

Base plan: Anthropic + a parameterized OpenAI-compatible backend (OpenAI only,
verified). Everything else returns None from resolve_backend -> live fallback.
"""

import json
from pathlib import Path
from typing import Protocol

from src.lib.config import get_config
from src.lib.logging import get_logger

logger = get_logger(__name__)


class BatchBackend(Protocol):
    """Uniform interface over a provider Batch API."""

    name: str

    def submit(self, lines: list[dict]) -> str:
        """Submit batch lines, return a provider batch_id."""
        ...

    def poll(self, batch_id: str) -> str:
        """Return normalized status: 'in_progress' | 'ended' | 'failed'."""
        ...

    def fetch(self, batch_id: str) -> dict[str, dict]:
        """Return {custom_id: normalized_raw_item} for parse_batch_result."""
        ...


class AnthropicBatchBackend:
    """Anthropic Messages Batches."""

    name = "anthropic"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(
                api_key=self.api_key,
                default_headers={
                    "anthropic-beta": "structured-outputs-2025-11-13"
                },
            )
        return self._client

    def submit(self, lines: list[dict]) -> str:
        # lines are {custom_id, params}; the SDK accepts plain dicts as requests.
        batch = self.client.messages.batches.create(requests=lines)
        logger.info(f"Submitted Anthropic batch {batch.id} ({len(lines)} requests)")
        return batch.id

    def poll(self, batch_id: str) -> str:
        status = self.client.messages.batches.retrieve(batch_id).processing_status
        return "ended" if status == "ended" else "in_progress"

    def fetch(self, batch_id: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for item in self.client.messages.batches.results(batch_id):
            result = item.result
            out[item.custom_id] = {
                "custom_id": item.custom_id,
                "result_type": result.type,
                "message": getattr(result, "message", None),
            }
        return out


class OpenAICompatBatchBackend:
    """OpenAI /v1/batches (JSONL file upload). Parameterized base_url/api_key so
    the same flow can target OpenAI-compatible hosts; base plan wires OpenAI."""

    def __init__(self, api_key: str, base_url: str, name: str):
        self.api_key = api_key
        self.base_url = base_url
        self.name = name
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def submit(self, lines: list[dict]) -> str:
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")
            jsonl_path = Path(f.name)
        try:
            with open(jsonl_path, "rb") as fh:
                uploaded = self.client.files.create(file=fh, purpose="batch")
            batch = self.client.batches.create(
                input_file_id=uploaded.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )
            logger.info(f"Submitted {self.name} batch {batch.id} ({len(lines)} requests)")
            return batch.id
        finally:
            jsonl_path.unlink(missing_ok=True)

    def poll(self, batch_id: str) -> str:
        status = self.client.batches.retrieve(batch_id).status
        if status == "completed":
            return "ended"
        if status == "expired":
            return "expired"
        if status in ("failed", "cancelled", "canceled"):
            return "failed"
        return "in_progress"

    def fetch(self, batch_id: str) -> dict[str, dict]:
        batch = self.client.batches.retrieve(batch_id)
        content = self.client.files.content(batch.output_file_id).text
        out: dict[str, dict] = {}
        for raw_line in content.splitlines():
            if not raw_line.strip():
                continue
            line = json.loads(raw_line)
            response = line.get("response") or {}
            out[line["custom_id"]] = {
                "custom_id": line["custom_id"],
                "status_code": response.get("status_code"),
                "body": response.get("body"),
            }
        return out


# api_key_type (factory registry) -> batch backend name. Only wired backends here.
_API_KEY_TYPE_TO_BACKEND = {
    "anthropic": "anthropic",
    "openai": "openai",
    "moonshot": "moonshot",
    "alibaba": "alibaba",
}


def make_backend(name: str) -> BatchBackend | None:
    """Construct a batch backend by its name (used to rebuild it at collect time)."""
    config = get_config()
    if name == "anthropic":
        return AnthropicBatchBackend(api_key=config.anthropic_api_key)
    if name == "openai":
        return OpenAICompatBatchBackend(
            api_key=config.openai_api_key,
            base_url="https://api.openai.com/v1",
            name="openai",
        )
    if name == "moonshot":
        # Kimi — OpenAI-compatible /v1/batches at the Moonshot base_url.
        return OpenAICompatBatchBackend(
            api_key=config.moonshot_api_key,
            base_url="https://api.moonshot.ai/v1",
            name="moonshot",
        )
    if name == "alibaba":
        # Qwen/DashScope — OpenAI-compatible /v1/batches. sk-sp-* keys use the
        # Coding Plan host (matches QwenAdapter.__init__).
        key = config.alibaba_api_key or ""
        base_url = (
            "https://coding.dashscope.aliyuncs.com/v1"
            if key.startswith("sk-sp-")
            else "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        return OpenAICompatBatchBackend(api_key=key, base_url=base_url, name="alibaba")
    return None


def resolve_backend(model: str) -> BatchBackend | None:
    """Map a friendly model name to a batch backend, or None for live fallback.

    Routing is by the factory registry's (adapter_class, model_id, api_key_type).
    An adapter must set supports_batch = True and have a backend wired here.
    """
    from src.services.llm.factory import LLMProviderFactory

    entry = LLMProviderFactory._model_registry.get(model)
    if entry is None:
        return None
    adapter_class, _model_id, api_key_type = entry
    if not getattr(adapter_class, "supports_batch", False):
        return None
    return make_backend(_API_KEY_TYPE_TO_BACKEND.get(api_key_type))
