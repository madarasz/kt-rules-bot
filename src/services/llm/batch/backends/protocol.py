"""Uniform interface over a provider Batch API."""

from typing import Protocol


class BatchBackend(Protocol):
    """Uniform interface over a provider Batch API."""

    name: str

    def submit(self, lines: list[dict], label: str = "quality-test") -> str:
        """Submit batch lines, return a provider batch_id.

        `label` names the submission for the provider's console where the API has
        a field for it (currently only xAI). Backends whose API has no such field
        accept it and ignore it, so callers can always pass one.
        """
        ...

    def poll(self, batch_id: str) -> str:
        """Return normalized status: 'in_progress' | 'ended' | 'failed'."""
        ...

    def fetch(self, batch_id: str) -> dict[str, dict]:
        """Return {custom_id: normalized_raw_item} for parse_batch_result."""
        ...
