"""Uniform interface over a provider Batch API."""

from typing import Protocol


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
