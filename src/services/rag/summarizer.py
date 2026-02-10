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

    return prompt_file.read_text(encoding="utf-8")


class ChunkSummarizer:
    """Generates one-sentence summaries for rule chunks using LLM."""

    def __init__(self):
        """Initialize the chunk summarizer with LLM provider."""
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

    async def generate_summaries(
        self, chunks: list[MarkdownChunk]
    ) -> tuple[list[MarkdownChunk], int, int, str]:
        """Generate summaries for a batch of chunks from one markdown file.

        Makes a single LLM call to summarize all chunks efficiently.
        Updates the summary field on each chunk in-place.

        Args:
            chunks: List of MarkdownChunk objects to summarize

        Returns:
            Tuple of (chunks, prompt_tokens, completion_tokens, model_name)
            - chunks: Same chunks list with summary field populated
            - prompt_tokens: Number of tokens in the prompt
            - completion_tokens: Number of tokens in the completion
            - model_name: Model used for summary generation

        Raises:
            Exception: If LLM call fails (logged as warning, returns empty summaries)
        """
        if not SUMMARY_ENABLED:
            logger.debug("Summary generation disabled, returning chunks unchanged")
            return (chunks, 0, 0, "")

        if self.provider is None:
            logger.warning("No LLM provider available, returning chunks unchanged")
            return (chunks, 0, 0, "")

        if not chunks:
            logger.debug("No chunks to summarize")
            return (chunks, 0, 0, "")

        try:
            # Build input text with numbered chunks
            chunk_input = self._format_chunks_for_llm(chunks)

            # Build the full prompt
            full_prompt = f"{self.summary_prompt}\n\n{chunk_input}"

            # Configure the generation request
            config = GenerationConfig(
                max_tokens=LLM_DEFAULT_MAX_TOKENS * 3,
                temperature=0.3,
                system_prompt="You are a technical writer creating concise summaries for game rules documentation.",
                structured_output_schema="chunk_summaries",
            )

            request = GenerationRequest(
                prompt=full_prompt,
                context=[],  # No RAG context needed for summarization
                chunk_ids=[],  # Empty list for non-RAG requests
                config=config,
            )

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

            # Parse summaries from structured output
            summaries_dict = {}
            for chunk_summary in summaries_response.summaries:
                summaries_dict[chunk_summary.chunk_number] = chunk_summary.summary

            # Assign summaries to chunks
            for i, chunk in enumerate(chunks, start=1):
                if i in summaries_dict:
                    chunk.summary = summaries_dict[i]
                    logger.debug(f"Chunk {i}: '{chunk.header}' -> '{chunk.summary}'")
                else:
                    chunk.summary = ""
                    logger.warning(f"No summary generated for chunk {i}: '{chunk.header}'")

            logger.info(
                f"Successfully generated {len(summaries_dict)}/{len(chunks)} summaries "
                f"(prompt: {prompt_tokens} tokens, completion: {completion_tokens} tokens, latency: {latency_ms}ms)"
            )
            return (chunks, prompt_tokens, completion_tokens, self.model)

        except Exception as e:
            logger.warning(f"Failed to generate summaries: {e}", exc_info=True)
            # Fallback: set all summaries to empty string
            for chunk in chunks:
                chunk.summary = ""
            return (chunks, 0, 0, "")

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

        return "\n".join(formatted_chunks)
