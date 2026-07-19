"""Batch backends: the submit/poll/fetch envelope for the Batch APIs.

Provider-specific *request building* and *result parsing* live in the LLM
adapters (build_batch_request / parse_batch_result). Backends here only handle
submission, status polling, and result retrieval, normalizing each provider's
result item into the dict shape the matching adapter's parse_batch_result reads.

Each provider backend lives in its own module; this file only wires the
registry (api_key_type -> backend) and the routing functions.
"""

from src.lib.config import get_config

from .anthropic import AnthropicBatchBackend
from .gemini import GeminiBatchBackend
from .grok import GrokBatchBackend
from .mistral import MistralBatchBackend
from .openai_compat import OpenAICompatBatchBackend
from .protocol import BatchBackend

__all__ = [
    "BatchBackend",
    "AnthropicBatchBackend",
    "OpenAICompatBatchBackend",
    "MistralBatchBackend",
    "GeminiBatchBackend",
    "GrokBatchBackend",
    "batch_group_key",
    "make_backend",
    "resolve_backend",
]

# api_key_type (factory registry) -> batch backend name. Only wired backends here.
_API_KEY_TYPE_TO_BACKEND = {
    "anthropic": "anthropic",
    "openai": "openai",
    "moonshot": "moonshot",
    "alibaba": "alibaba",
    "mistral": "mistral",
    "google": "google",
    "x": "x",
}


def batch_group_key(backend: BatchBackend, model: str) -> str:
    """Key identifying the single provider batch submission a request joins.

    OpenAI-compatible /v1/batches requires every request in one batch to target
    the same model (else the whole batch is rejected `mismatched_model`), so those
    backends get one group per (backend, model). Providers that accept mixed-model
    batches (Anthropic, Gemini, Grok, Mistral) get one group per backend. The model
    suffix is stripped back off in make_backend(), so the key round-trips.
    """
    if isinstance(backend, OpenAICompatBatchBackend):
        return f"{backend.name}::{model}"
    return backend.name


def make_backend(name: str) -> BatchBackend | None:
    """Construct a batch backend by its name (used to rebuild it at collect time).

    Accepts either a plain backend name or a `name::model` group key (see
    batch_group_key) — the model suffix only partitions submissions and is
    irrelevant to backend construction, so it is stripped here.
    """
    name = name.split("::", 1)[0]
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
    if name == "mistral":
        return MistralBatchBackend(api_key=config.mistral_api_key)
    if name == "google":
        return GeminiBatchBackend(api_key=config.google_api_key)
    if name == "x":
        return GrokBatchBackend(api_key=config.x_api_key)
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
    # A batch-capable provider may still exclude specific models (e.g. OpenAI's
    # *-chat-latest aliases) — those fall back to the live path.
    if not adapter_class.batch_supports_model(_model_id):
        return None
    return make_backend(_API_KEY_TYPE_TO_BACKEND.get(api_key_type))
