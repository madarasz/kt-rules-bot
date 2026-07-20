"""Reasoning-effort model-name postfix parsing and validation.

Callers may append a reasoning-effort level to a model name with ``#``, e.g.
``grok-4.3#high`` or ``claude-4.8-opus#low``. This module is the SINGLE source of
truth for:

- the effort vocabulary (``LLM_REASONING_EFFORT_LEVELS``),
- which resolved ``model_id`` supports which levels (``REASONING_EFFORT_SUPPORT``),
- splitting/validating the ``name#effort`` string.

The CLI (``--model`` / ``--judge-model``) validates against this and **terminates**
on an unsupported level; the LLM adapters consult the same matrix and, on a
non-CLI path, **warn + ignore** an unsupported level so a production config typo
never crashes the bot. See src/services/llm/CLAUDE.md for the maintenance note.

Keyed by the resolved ``model_id`` the adapter sees (the 2nd element of the
factory registry tuple), NOT the friendly registry key.
"""

import argparse

# Delimiter between a model name and its reasoning-effort level.
REASONING_EFFORT_DELIMITER = "#"

# Canonical effort vocabulary (superset across providers). A token after ``#``
# must be one of these to be valid *vocabulary*; whether a given model supports
# it is a separate question answered by REASONING_EFFORT_SUPPORT.
LLM_REASONING_EFFORT_LEVELS: tuple[str, ...] = (
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

# ---------------------------------------------------------------------------
# Per-model support matrix (keyed by resolved model_id).
# Only the wired providers (OpenAI, Anthropic, Grok, Gemini) appear. A model_id
# that is absent => the provider has no reasoning-effort knob wired => any
# ``#effort`` on it is rejected by the CLI and warn-ignored at runtime.
#
# Conservative where a provider's exact per-model level set is uncertain; extend
# as providers publish more levels. Intersected with LLM_REASONING_EFFORT_LEVELS
# (so provider-only tokens like Grok/OpenAI ``none`` are intentionally omitted).
# ---------------------------------------------------------------------------

# OpenAI reasoning_effort. gpt-5 family: minimal/low/medium/high; gpt-5.6 adds
# xhigh/max (no minimal); o-series: low/medium/high. Non-reasoning (gpt-4o/4.1)
# and *-chat-latest reject the param and are omitted.
_OPENAI_GPT5 = frozenset({"minimal", "low", "medium", "high"})
_OPENAI_GPT56 = frozenset({"low", "medium", "high", "xhigh", "max"})
_OPENAI_O_SERIES = frozenset({"low", "medium", "high"})

# Anthropic output_config.effort.
_ANTHROPIC_47_48 = frozenset({"low", "medium", "high", "xhigh", "max"})
_ANTHROPIC_46 = frozenset({"low", "medium", "high", "max"})
_ANTHROPIC_45 = frozenset({"low", "medium", "high"})

# Grok reasoning_effort (native none/low/medium/high; canonical intersection).
_GROK = frozenset({"low", "medium", "high"})

# Gemini 3 thinking_level (LOW/HIGH; flash/flash-lite add MINIMAL).
_GEMINI3_PRO = frozenset({"low", "high"})
_GEMINI3_FLASH = frozenset({"minimal", "low", "high"})
# Gemini 2.5 thinking_budget (int) — approximate canonical mapping.
_GEMINI25 = frozenset({"low", "medium", "high"})

REASONING_EFFORT_SUPPORT: dict[str, frozenset[str]] = {
    # --- OpenAI ---
    "gpt-5.6-luna": _OPENAI_GPT56,
    "gpt-5.5": _OPENAI_GPT5,
    "gpt-5.4": _OPENAI_GPT5,
    "gpt-5.4-mini-2026-03-17": _OPENAI_GPT5,
    "gpt-5.4-nano": _OPENAI_GPT5,
    "gpt-5.2": _OPENAI_GPT5,
    "gpt-5.1": _OPENAI_GPT5,
    "gpt-5": _OPENAI_GPT5,
    "gpt-5-mini": _OPENAI_GPT5,
    "gpt-5-nano": _OPENAI_GPT5,
    "o3": _OPENAI_O_SERIES,
    "o3-mini": _OPENAI_O_SERIES,
    "o4-mini": _OPENAI_O_SERIES,
    # --- Anthropic ---
    "claude-opus-4-8": _ANTHROPIC_47_48,
    "claude-opus-4-7": _ANTHROPIC_47_48,
    "claude-opus-4-6": _ANTHROPIC_46,
    "claude-sonnet-4-6": _ANTHROPIC_46,
    "claude-opus-4-5-20251101": _ANTHROPIC_45,
    # --- Grok (reasoning variants only; grok-4-0709 rejects the param) ---
    "grok-4-1-fast-reasoning": _GROK,
    "grok-4-fast-reasoning": _GROK,
    "grok-4.3": _GROK,
    "grok-4.20-0309-reasoning": _GROK,
    "grok-3-mini": _GROK,
    # --- Gemini 3 (thinking_level) ---
    "gemini-3.1-pro-preview": _GEMINI3_PRO,
    "gemini-3-pro-preview": _GEMINI3_PRO,
    "gemini-3-flash-preview": _GEMINI3_FLASH,
    "gemini-3.1-flash-lite": _GEMINI3_FLASH,
    "gemini-3.5-flash": _GEMINI3_FLASH,
    # --- Gemini 2.5 (thinking_budget) ---
    "gemini-2.5-pro": _GEMINI25,
    "gemini-2.5-flash": _GEMINI25,
}


def model_base_name(model: str) -> str:
    """Return the model name with any ``#effort`` postfix stripped (lenient).

    Does not validate the postfix — use at internal registry-lookup sites where
    the string has already passed an entry-point validator.
    """
    return model.split(REASONING_EFFORT_DELIMITER, 1)[0]


def model_slug(model: str) -> str:
    """Return a filename- and URL-safe rendering of a model name.

    The ``#`` delimiter is legal in a filename but is parsed as a fragment
    delimiter in a markdown/URL link, which silently truncates the href. Use
    this wherever a model name becomes a path component or a link target;
    the effort stays visible so runs remain distinguishable.
    """
    return model.replace(REASONING_EFFORT_DELIMITER, "-")


def split_reasoning_effort(model: str) -> tuple[str, str | None]:
    """Split ``'grok-4.3#high'`` -> ``('grok-4.3', 'high')``.

    No delimiter -> ``(model, None)``. Raises ``ValueError`` if the token after
    ``#`` is not valid effort vocabulary (a typo like ``#turbo``). Does NOT check
    whether the model supports the level — that is ``is_effort_supported``.
    """
    if REASONING_EFFORT_DELIMITER not in model:
        return model, None
    base, _, raw = model.partition(REASONING_EFFORT_DELIMITER)
    effort = raw.strip().lower()
    if effort not in LLM_REASONING_EFFORT_LEVELS:
        raise ValueError(
            f"Invalid reasoning-effort level '{raw}' in '{model}'. "
            f"Valid levels: {', '.join(LLM_REASONING_EFFORT_LEVELS)}"
        )
    return base, effort


def format_effort_levels(
    levels: frozenset[str] | None, fallback: str = "none (model has no effort control)"
) -> str:
    """Render effort levels in canonical weakest-to-strongest order.

    Plain ``sorted()`` gives alphabetical order ("high, low, max, medium"),
    which reads as a nonsensical ranking for what is a ranked scale.

    Args:
        levels: Supported effort levels, or None if not supported.
        fallback: String to return when levels is empty.
    """
    if not levels:
        return fallback
    order = {level: i for i, level in enumerate(LLM_REASONING_EFFORT_LEVELS)}
    return ", ".join(sorted(levels, key=lambda lvl: order.get(lvl, len(order))))


def supported_effort_levels(model_id: str) -> frozenset[str] | None:
    """Levels supported by a resolved ``model_id``; ``None`` if the provider has
    no reasoning-effort knob wired for this model."""
    return REASONING_EFFORT_SUPPORT.get(model_id)


def is_effort_supported(model_id: str, effort: str | None) -> bool:
    """True if ``effort`` is a level ``model_id`` accepts. ``None`` effort is
    always "supported" (means: apply nothing / provider default)."""
    if effort is None:
        return True
    levels = REASONING_EFFORT_SUPPORT.get(model_id)
    return levels is not None and effort in levels


def validate_model_arg(arg: str) -> str:
    """argparse ``type=`` for CLI ``--model`` / ``--judge-model``.

    Splits off the effort, resolves the base model to its ``model_id`` via the
    factory registry (lazy import to avoid an import cycle), and raises
    ``argparse.ArgumentTypeError`` if the base is unknown or the effort level is
    unsupported for that model. Returns the original ``arg`` unchanged so the
    postfix flows through to ``LLMProviderFactory.create()``.
    """
    # Lazy import: factory imports this module, so import it at call time only.
    from src.lib.constants import ALL_LLM_PROVIDERS
    from src.services.llm.factory import LLMProviderFactory

    try:
        base, effort = split_reasoning_effort(arg)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc

    # Gate on the curated ALL_LLM_PROVIDERS list, NOT the factory registry. The
    # registry is a superset that includes models deliberately kept out of the
    # literal (e.g. o3, which cannot do structured JSON output); accepting those
    # here would let a paid run start and only fail at response parsing.
    if base not in ALL_LLM_PROVIDERS:
        raise argparse.ArgumentTypeError(
            f"Unknown model '{base}'. Must be one of: {', '.join(sorted(ALL_LLM_PROVIDERS))}"
        )
    registry = LLMProviderFactory._model_registry
    if effort is not None and base in registry:
        model_id = registry[base][1]
        if not is_effort_supported(model_id, effort):
            raise argparse.ArgumentTypeError(
                f"Model '{base}' does not support reasoning effort '{effort}'. "
                f"Supported levels: {format_effort_levels(supported_effort_levels(model_id))}"
            )
    return arg
