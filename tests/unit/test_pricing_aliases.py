"""Pricing table must stay in sync with the factory's model registry.

src/lib/pricing.py cannot import the registry itself (src/lib must not depend on
src/services, and importing the factory would pull in every provider SDK), so the
friendly-name -> model-ID aliases are hand-maintained there. These tests fail if
they drift from LLMProviderFactory._model_registry.
"""

from src.lib.pricing import _PRICING_ALIASES, pricing
from src.services.llm.factory import LLMProviderFactory

_REGISTRY = LLMProviderFactory._model_registry


def test_friendly_name_and_model_id_price_identically():
    """Both spellings of a registered model must hit the same pricing entry.

    Cost calculation is called with `model_version` (the ID the API reports) in the
    served path and with the friendly name when no response is available, so a name
    priced on only one side would silently fall back to the placeholder rate.
    """
    mismatched = {
        friendly: model_id
        for friendly, (_, model_id, _) in _REGISTRY.items()
        if friendly != model_id
        and (friendly in pricing or model_id in pricing)
        and pricing.get(friendly) is not pricing.get(model_id)
    }
    assert not mismatched, (
        "pricing entries differ between friendly name and model ID; "
        f"add to _PRICING_ALIASES in src/lib/pricing.py: {mismatched}"
    )


def test_aliases_match_registry_pairs():
    """Every alias must correspond to a friendly/model-ID pair in the registry."""
    registry_pairs = {
        frozenset((friendly, model_id))
        for friendly, (_, model_id, _) in _REGISTRY.items()
        if friendly != model_id
    }
    stale = [
        f"{alias} -> {target}"
        for alias, target in _PRICING_ALIASES.items()
        if frozenset((alias, target)) not in registry_pairs
    ]
    assert not stale, f"aliases not backed by the factory registry: {stale}"


def test_alias_targets_are_real_entries():
    missing = [target for target in _PRICING_ALIASES.values() if target not in pricing]
    assert not missing, f"alias targets absent from the pricing table: {missing}"
