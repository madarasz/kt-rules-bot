"""Chunk summarization service for RAG pipeline.

Generates concise one-sentence summaries for rule chunks using LLM.
Used during ingestion to enhance retrieval quality.
"""

import time
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field

from src.lib.config import get_config
from src.lib.constants import (
    CHUNK_SUMMARY_PROMPT_PATH,
    LLM_DEFAULT_MAX_TOKENS,
    SUMMARY_ENABLED,
    SUMMARY_LLM_MODEL,
)
from src.lib.logging import get_logger
from src.services.rag.chunker import MarkdownChunk

logger = get_logger(__name__)


class ChunkSummary(BaseModel):
    """Single chunk summary."""

    chunk_number: int = Field(description="Chunk number (1-indexed)")
    summary: str = Field(description="One-sentence summary of the chunk")


class ChunkSummaries(BaseModel):
    """Batch of chunk summaries."""

    summaries: list[ChunkSummary] = Field(description="List of chunk summaries")


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
        """Initialize the chunk summarizer with OpenAI client."""
        if not SUMMARY_ENABLED:
            logger.info("Summary generation is disabled (SUMMARY_ENABLED=False)")
            return

        config = get_config()
        self.client = OpenAI(api_key=config.openai_api_key)
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

        if not chunks:
            logger.debug("No chunks to summarize")
            return (chunks, 0, 0, "")

        try:
            # Build input text with numbered chunks
            chunk_input = self._format_chunks_for_llm(chunks)

            # Make OpenAI call with structured output
            logger.info(f"Generating summaries for {len(chunks)} chunks...")
            start_time = time.time()

            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a technical writer creating concise summaries for game rules documentation.",
                    },
                    {"role": "user", "content": f"{self.summary_prompt}\n\n{chunk_input}"},
                ],
                response_format=ChunkSummaries,
                temperature=0.3,
                max_tokens=LLM_DEFAULT_MAX_TOKENS * 2,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract structured response
            summaries_response = completion.choices[0].message.parsed
            prompt_tokens = completion.usage.prompt_tokens
            completion_tokens = completion.usage.completion_tokens

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
