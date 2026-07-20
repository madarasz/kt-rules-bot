"""CLI command to list available LLM models grouped by provider.

Prints a table per provider showing input/output token costs (USD per million
tokens) and the reasoning-effort levels each model supports.

Usage:
    python -m src.cli list-models
    python -m src.cli list-models --provider claude
"""

from src.lib.model_name import format_effort_levels, supported_effort_levels
from src.lib.tokens import pricing
from src.services.llm.factory import LLMProviderFactory

# Friendly provider label per adapter class name. Falls back to "<ClassName>"
# minus the "Adapter" suffix for any adapter not listed here.
_PROVIDER_LABELS: dict[str, str] = {
    "ClaudeAdapter": "Claude (Anthropic)",
    "ChatGPTAdapter": "ChatGPT (OpenAI)",
    "GeminiAdapter": "Gemini (Google)",
    "GrokAdapter": "Grok (xAI)",
    "DeepSeekAdapter": "DeepSeek",
    "KimiAdapter": "Kimi (Moonshot)",
    "MistralAdapter": "Mistral",
    "QwenAdapter": "Qwen (Alibaba)",
    "GLMAdapter": "GLM (Z.AI)",
    "MiniMaxAdapter": "MiniMax",
    "DialAdapter": "DIAL",
}


def _provider_label(adapter_class: type) -> str:
    """Human-readable provider name for an adapter class."""
    return _PROVIDER_LABELS.get(adapter_class.__name__, adapter_class.__name__.removesuffix("Adapter"))


def _price_per_million(friendly_name: str, model_id: str, key: str) -> str:
    """Format a per-1M-token price for the `prompt`/`completion` pricing key.

    Pricing is stored per 1K tokens; multiply by 1000. Returns "—" when the
    model has no pricing entry (friendly name tried first, then resolved id).
    """
    entry = pricing.get(friendly_name) or pricing.get(model_id)
    if entry is None or key not in entry:
        return "—"
    return f"${entry[key] * 1000:,.2f}"


def _reasoning_levels(model_id: str) -> str:
    """Comma-separated supported effort levels (canonical order), or "—"."""
    levels = supported_effort_levels(model_id)
    return format_effort_levels(levels, fallback="—")


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a left-aligned, column-padded table to stdout."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    print(fmt(headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt(row))


def list_models(provider_filter: str | None = None) -> None:
    """List LLM models grouped by provider with costs and reasoning levels.

    Args:
        provider_filter: Case-insensitive substring; when given, only providers
            whose label matches are shown.
    """
    headers = ["Model", "Input $/1M", "Output $/1M", "Reasoning levels"]

    # Group registry entries by adapter class, preserving first-seen order.
    groups: dict[type, list[tuple[str, str]]] = {}
    for friendly_name, (adapter_class, model_id, _key_type) in (
        LLMProviderFactory._model_registry.items()
    ):
        groups.setdefault(adapter_class, []).append((friendly_name, model_id))

    needle = provider_filter.lower() if provider_filter else None
    shown = 0

    for adapter_class, models in groups.items():
        label = _provider_label(adapter_class)
        if needle and needle not in label.lower():
            continue

        rows = [
            [
                friendly_name,
                _price_per_million(friendly_name, model_id, "prompt"),
                _price_per_million(friendly_name, model_id, "completion"),
                _reasoning_levels(model_id),
            ]
            for friendly_name, model_id in models
        ]

        print(f"\n{label}")
        print("=" * len(label))
        _print_table(headers, rows)
        shown += 1

    if needle and shown == 0:
        print(f"No providers match '{provider_filter}'.")
    else:
        print("\nCosts are USD per 1,000,000 tokens. '—' = no data / not supported.")
        print("Append a reasoning level to a model with '#', e.g. claude-4.8-opus#high.")
