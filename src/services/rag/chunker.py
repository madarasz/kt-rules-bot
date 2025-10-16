"""Markdown chunking service with hierarchical header splitting.

Splits documents at all markdown headers (#, ##, ###, ####).
"""

import re
from dataclasses import dataclass
from typing import List
from uuid import UUID, uuid4

from src.lib.tokens import count_tokens, get_embedding_token_limit
from src.lib.constants import EMBEDDING_MODEL


@dataclass
class MarkdownChunk:
    """A chunk of markdown text."""

    chunk_id: UUID
    text: str
    header: str  # Section header path (e.g., "Movement Phase > Declare Actions")
    header_level: int  # 0 for whole doc, 1-4 for #-####
    position: int  # Position in original document
    token_count: int


class MarkdownChunker:
    """Chunks markdown documents at header boundaries (#, ##, ###, ####)."""

    def __init__(self, max_tokens: int | None = None, model: str = "gpt-3.5-turbo"):
        """Initialize chunker.

        Args:
            max_tokens: Maximum tokens per chunk (default: determined by EMBEDDING_MODEL)
            model: Model name for token counting
        """
        self.max_tokens = max_tokens if max_tokens is not None else get_embedding_token_limit(EMBEDDING_MODEL)
        self.model = model

    def chunk(self, content: str) -> List[MarkdownChunk]:
        """Chunk markdown content at all header levels (#, ##, ###, ####).

        Strategy:
        1. Split recursively at each header level (# -> ## -> ### -> ####)
        2. Keep whole document only if no headers AND within token limit
        3. No overlap between chunks (clean semantic boundaries)

        Args:
            content: Markdown content

        Returns:
            List of MarkdownChunk objects
        """
        # Try to find any headers (starting from #)
        has_headers = bool(re.search(r"^#{1,4} ", content, flags=re.MULTILINE))

        if not has_headers:
            # No headers: return whole document if within limit
            total_tokens = count_tokens(content, model=self.model)
            return [
                MarkdownChunk(
                    chunk_id=uuid4(),
                    text=content.strip(),
                    header="",
                    header_level=0,
                    position=0,
                    token_count=total_tokens,
                )
            ]

        # Split at headers recursively, starting at level 1 (#)
        return self._split_at_header_level(content, level=1, parent_header="", base_position=0)

    def _split_at_header_level(
        self, content: str, level: int, parent_header: str, base_position: int
    ) -> List[MarkdownChunk]:
        """Recursively split content at specific header level.

        Args:
            content: Markdown content
            level: Header level to split at (1-4 for #-####)
            parent_header: Parent header path
            base_position: Base position in document

        Returns:
            List of chunks
        """
        if level > 4:
            # No more header levels to split at
            return [self._create_leaf_chunk(content, parent_header, level - 1, base_position)]

        # Create regex pattern for current header level
        header_pattern = rf"(^{'#' * level} .+$)"

        # Check if content has headers at this level
        if not re.search(header_pattern, content, flags=re.MULTILINE):
            # No headers at this level, try next level down
            return self._split_at_header_level(content, level + 1, parent_header, base_position)

        # Split at this header level
        sections = re.split(header_pattern, content, flags=re.MULTILINE)

        chunks: List[MarkdownChunk] = []
        current_header = parent_header
        current_text = ""
        position = 0

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # Check if this is a header line at current level
            if section.startswith('#' * level + ' ') and not section.startswith('#' * (level + 1)):
                # Save previous section if exists
                if current_text:
                    # Recursively split at next header level
                    sub_chunks = self._split_at_header_level(
                        current_text, level + 1, current_header, base_position + position
                    )
                    chunks.extend(sub_chunks)
                    position += 1

                # Start new section
                header_text = section[level + 1:].strip()  # Remove "# " prefix
                current_header = f"{parent_header} > {header_text}" if parent_header else header_text
                current_text = section + "\n"
            else:
                # Add content to current section
                current_text += section + "\n"

        # Don't forget last section
        if current_text:
            sub_chunks = self._split_at_header_level(
                current_text, level + 1, current_header, base_position + position
            )
            chunks.extend(sub_chunks)

        return chunks

    def _create_leaf_chunk(
        self, text: str, header: str, header_level: int, position: int
    ) -> MarkdownChunk:
        """Create a leaf chunk (no more splitting).

        Args:
            text: Chunk text
            header: Section header path
            header_level: Header level
            position: Position in document

        Returns:
            MarkdownChunk
        """
        token_count = count_tokens(text, model=self.model)
        return MarkdownChunk(
            chunk_id=uuid4(),
            text=text.strip(),
            header=header,
            header_level=header_level,
            position=position,
            token_count=token_count,
        )

    def get_chunk_stats(self, chunks: List[MarkdownChunk]) -> dict:
        """Get statistics about chunks.

        Args:
            chunks: List of chunks

        Returns:
            Statistics dictionary
        """
        if not chunks:
            return {"count": 0, "total_tokens": 0, "avg_tokens": 0, "max_tokens": 0}

        token_counts = [chunk.token_count for chunk in chunks]

        return {
            "count": len(chunks),
            "total_tokens": sum(token_counts),
            "avg_tokens": sum(token_counts) / len(token_counts),
            "max_tokens": max(token_counts),
            "min_tokens": min(token_counts),
        }
