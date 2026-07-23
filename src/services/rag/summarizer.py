"""Chunk summarization service for RAG pipeline.

Generates concise one-sentence summaries for rule chunks using LLM.
Used during ingestion to enhance retrieval quality.
"""

import time
from pathlib import Path

from src.lib.constants import (
    CHUNK_SUMMARY_PROMPT_PATH,
    LLM_DEFAULT_MAX_TOKENS,
    SUMMARY_ENABLED,
    SUMMARY_LLM_MODEL,
)
from src.lib.logging import get_logger
from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.schemas import ChunkSummaries
from src.services.rag.chunker import MarkdownChunk

logger = get_logger(__name__)


def load_summary_prompt() -> str:
    """Load summary generation prompt from file.

    Returns:
        Prompt text for summary generation

    Raises:
        FileNotFoundError: If prompt file not found
    """

    # Locate prompt file relative to project root
    # Assuming this file is at src/services/rag/summarizer.py
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    prompt_file = project_root / CHUNK_SUMMARY_PROMPT_PATH

    if not prompt_file.exists():
        raise FileNotFoundError(
            f"Summary prompt file not found: {prompt_file}\n"
            f"Expected location: {CHUNK_SUMMARY_PROMPT_PATH}"
        )

    from src.services.llm.prompt_builder import strip_cache_markers

    return strip_cache_markers(prompt_file.read_text(encoding="utf-8"))


def summaries_complete(chunks: list[MarkdownChunk]) -> bool:
    """True when every chunk carries a non-empty summary.

    The single test for "may this file be recorded as cleanly ingested?", shared by
    the live path (ingestor.py) and the batch path (summarizer_batch.py). Token
    counts are not a substitute: a truncated or partially-numbered LLM response
    bills tokens while `apply_summaries` blanks the chunks it did not cover, and
    under incremental ingestion a file recorded clean is never revisited.
    """
    return bool(chunks) and all(chunk.summary for chunk in chunks)


class ChunkSummarizer:
    """Generates one-sentence summaries for rule chunks using LLM."""

    def __init__(self):
        """Initialize the chunk summarizer with LLM provider."""
        # Set before any early return: build_request() is public and is called by
        # the batch path, which does not go through generate_summaries()' guards.
        # A half-initialized instance must fail as "disabled", not AttributeError.
        self.summary_prompt = ""
        self.model = SUMMARY_LLM_MODEL

        if not SUMMARY_ENABLED:
            logger.info("Summary generation is disabled (SUMMARY_ENABLED=False)")
            self.provider = None
            return

        # Use LLMProviderFactory to get the appropriate provider
        self.provider = LLMProviderFactory.create(SUMMARY_LLM_MODEL)
        if self.provider is None:
            logger.error(f"Failed to create LLM provider for model: {SUMMARY_LLM_MODEL}")
            return

        self.summary_prompt = load_summary_prompt()
        self.model = SUMMARY_LLM_MODEL
        logger.info(f"Initialized ChunkSummarizer with model: {SUMMARY_LLM_MODEL}")

    def build_request(self, chunks: list[MarkdownChunk]) -> GenerationRequest:
        """Build the summarization request for one file's chunks.

        Shared by the live path below and the Batch API path
        (src/services/rag/summarizer_batch.py), so both send byte-identical
        prompts and the summaries they produce are interchangeable.
        """
        chunk_input = self._format_chunks_for_llm(chunks)

        # For Claude: split into cache-control blocks (static instructions cached,
        # dynamic data not). For all other providers: plain string.
        from src.services.llm.claude import ClaudeAdapter
        from src.services.llm.prompt_builder import CACHE_BREAK_MARKER, split_user_prompt_for_cache

        if isinstance(self.provider, ClaudeAdapter):
            full_prompt = split_user_prompt_for_cache(
                f"{self.summary_prompt}{CACHE_BREAK_MARKER}\n\n{chunk_input}"
            )
        else:
            full_prompt = f"{self.summary_prompt}\n\n{chunk_input}"

        config = GenerationConfig(
            max_tokens=LLM_DEFAULT_MAX_TOKENS * 3,
            temperature=0.3,
            system_prompt=(
                "You are a technical writer creating concise summaries for game rules "
                "documentation."
            ),
            structured_output_schema="chunk_summaries",
        )

        return GenerationRequest(
            prompt=full_prompt,
            context=[],  # No RAG context needed for summarization
            chunk_ids=[],  # Empty list for non-RAG requests
            config=config,
        )

    @staticmethod
    def apply_summaries(chunks: list[MarkdownChunk], summaries_response: ChunkSummaries) -> int:
        """Copy structured summaries onto chunks in place; returns how many matched.

        Chunk numbers are 1-based and follow `_format_chunks_for_llm` ordering.

        The count is of chunks that actually received a non-empty summary — not of
        entries the model returned. A truncated response covering chunks 1-3 of 22,
        or one numbering chunks that do not exist, must not read as a full success:
        callers compare this against `len(chunks)` to decide whether the file may be
        recorded as cleanly ingested.
        """
        summaries_dict = {cs.chunk_number: cs.summary for cs in summaries_response.summaries}
        matched = 0
        for i, chunk in enumerate(chunks, start=1):
            summary = summaries_dict.get(i, "")
            if summary:
                chunk.summary = summary
                matched += 1
                logger.debug(f"Chunk {i}: '{chunk.header}' -> '{chunk.summary}'")
            else:
                chunk.summary = ""
                logger.warning(f"No summary generated for chunk {i}: '{chunk.header}'")
        return matched

    async def generate_summaries(
        self, chunks: list[MarkdownChunk]
    ) -> tuple[list[MarkdownChunk], int, int, int, int, str]:
        """Generate summaries for a batch of chunks from one markdown file.

        Makes a single LLM call to summarize all chunks efficiently.
        Updates the summary field on each chunk in-place.

        Args:
            chunks: List of MarkdownChunk objects to summarize

        Returns:
            Tuple of (chunks, prompt_tokens, completion_tokens,
                      cache_read_tokens, cache_creation_tokens, model_name)
            - chunks: Same chunks list with summary field populated
            - prompt_tokens: Number of tokens in the prompt
            - completion_tokens: Number of tokens in the completion
            - cache_read_tokens: Prompt tokens served from cache (discounted)
            - cache_creation_tokens: Tokens written to cache (Anthropic only)
            - model_name: Model used for summary generation

        Raises:
            Exception: If LLM call fails (logged as warning, returns empty summaries)
        """
        if not SUMMARY_ENABLED:
            logger.debug("Summary generation disabled, returning chunks unchanged")
            return (chunks, 0, 0, 0, 0, "")

        if self.provider is None:
            logger.warning("No LLM provider available, returning chunks unchanged")
            return (chunks, 0, 0, 0, 0, "")

        if not chunks:
            logger.debug("No chunks to summarize")
            return (chunks, 0, 0, 0, 0, "")

        try:
            request = self.build_request(chunks)

            # Make LLM call with structured output
            logger.info(f"Generating summaries for {len(chunks)} chunks...")
            start_time = time.time()

            response = await self.provider.generate(request)

            latency_ms = int((time.time() - start_time) * 1000)

            # Parse structured response
            # The response can be in structured_output (dict) or answer_text (JSON string)
            if response.structured_output:
                summaries_data = response.structured_output
            else:
                import json
                summaries_data = json.loads(response.answer_text)

            # Validate with Pydantic model
            summaries_response = ChunkSummaries.model_validate(summaries_data)

            prompt_tokens = response.prompt_tokens
            completion_tokens = response.completion_tokens
            cache_read_tokens = response.cache_read_tokens
            cache_creation_tokens = response.cache_creation_tokens

            matched = self.apply_summaries(chunks, summaries_response)

            logger.info(
                f"Successfully generated {matched}/{len(chunks)} summaries "
                f"(prompt: {prompt_tokens} tokens, completion: {completion_tokens} tokens, "
                f"cache_read: {cache_read_tokens} tokens, latency: {latency_ms}ms)"
            )
            return (
                chunks,
                prompt_tokens,
                completion_tokens,
                cache_read_tokens,
                cache_creation_tokens,
                response.model_version or self.model,  # served model (alias may redirect)
            )

        except Exception as e:
            logger.warning(f"Failed to generate summaries: {e}", exc_info=True)
            # Fallback: set all summaries to empty string
            for chunk in chunks:
                chunk.summary = ""
            return (chunks, 0, 0, 0, 0, "")

    def _format_chunks_for_llm(self, chunks: list[MarkdownChunk]) -> str:
        """Format chunks as numbered input for LLM.

        Args:
            chunks: List of chunks to format

        Returns:
            Formatted input string
        """
        formatted_chunks = []
        for i, chunk in enumerate(chunks, start=1):
            formatted_chunks.append(
                f"Chunk {i}:\n"
                f"Header: {chunk.header}\n"
                f"Text: {chunk.text}\n"
            )

        if not formatted_chunks:
            return ""

        # Wrap in an XML tag so the dynamically injected (uncached) rule data is
        # clearly delimited from the static XML-structured prompt above the cache break.
        body = "\n".join(formatted_chunks)
        return f"<rules_chunks>\n{body}\n</rules_chunks>"
