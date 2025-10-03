"""Markdown chunking service with lazy splitting strategy.

Only splits documents when they exceed the embedding model's token limit (8192).
Based on specs/001-we-are-building/research.md Decision 2a.
"""

import re
from dataclasses import dataclass
from typing import List
from uuid import UUID, uuid4

from src.lib.tokens import count_tokens


@dataclass
class MarkdownChunk:
    """A chunk of markdown text."""

    chunk_id: UUID
    text: str
    header: str  # Section header (e.g., "Movement Phase")
    header_level: int  # 0 for whole doc, 2 for ##, 3 for ###
    position: int  # Position in original document
    token_count: int


class MarkdownChunker:
    """Chunks markdown documents using lazy splitting strategy."""

    def __init__(self, max_tokens: int = 8192, model: str = "gpt-3.5-turbo"):
        """Initialize chunker.

        Args:
            max_tokens: Maximum tokens per chunk (default: 8192 for text-embedding-3-small)
            model: Model name for token counting
        """
        self.max_tokens = max_tokens
        self.model = model

    def chunk(self, content: str) -> List[MarkdownChunk]:
        """Chunk markdown content using semantic splitting strategy.

        Strategy:
        1. ALWAYS split at ## headers if document has structured sections
        2. This creates focused semantic chunks even for small documents
        3. If single ## section > max_tokens, split at ### boundaries
        4. Only keep whole document if no ## headers AND ≤ max_tokens
        5. No overlap between chunks

        Args:
            content: Markdown content

        Returns:
            List of MarkdownChunk objects
        """
        # Check if document has ## header structure
        has_h2_headers = bool(re.search(r"^## ", content, flags=re.MULTILINE))

        # ALWAYS split at ## headers if they exist (better semantic granularity)
        if has_h2_headers:
            return self._split_at_headers(content)

        # Count tokens for entire document (no headers found)
        total_tokens = count_tokens(content, model=self.model)

        # Keep whole document only if no structure AND within limit
        if total_tokens <= self.max_tokens:
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

        # Document too large without headers: emergency split at ### or paragraphs
        return self._split_at_headers(content)

    def _split_at_headers(self, content: str) -> List[MarkdownChunk]:
        """Split content at ## header boundaries.

        Args:
            content: Markdown content

        Returns:
            List of chunks
        """
        chunks: List[MarkdownChunk] = []

        # Split at ## headers (H2)
        # Pattern captures the header line and everything until the next ## or end
        sections = re.split(r"(^## .+$)", content, flags=re.MULTILINE)

        current_header = ""
        current_text = ""
        position = 0

        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue

            # Check if this is a header line
            if section.startswith("## "):
                # Save previous section if exists
                if current_text:
                    chunk = self._create_chunk_with_subsplit(
                        current_text, current_header, 2, position
                    )
                    if isinstance(chunk, list):
                        chunks.extend(chunk)
                    else:
                        chunks.append(chunk)
                    position += 1

                # Start new section
                current_header = section[3:].strip()  # Remove "## "
                current_text = section + "\n"
            else:
                # Add content to current section
                current_text += section + "\n"

        # Don't forget last section
        if current_text:
            chunk = self._create_chunk_with_subsplit(
                current_text, current_header, 2, position
            )
            if isinstance(chunk, list):
                chunks.extend(chunk)
            else:
                chunks.append(chunk)

        return chunks

    def _create_chunk_with_subsplit(
        self, text: str, header: str, header_level: int, position: int
    ) -> MarkdownChunk | List[MarkdownChunk]:
        """Create chunk, splitting at ### if necessary.

        Args:
            text: Chunk text
            header: Section header
            header_level: Header level (2 or 3)
            position: Position in document

        Returns:
            Single chunk or list of sub-chunks
        """
        token_count = count_tokens(text, model=self.model)

        # If within limit, return single chunk
        if token_count <= self.max_tokens:
            return MarkdownChunk(
                chunk_id=uuid4(),
                text=text.strip(),
                header=header,
                header_level=header_level,
                position=position,
                token_count=token_count,
            )

        # Section too large: split at ### boundaries
        return self._split_at_subsections(text, header, position)

    def _split_at_subsections(
        self, content: str, parent_header: str, base_position: int
    ) -> List[MarkdownChunk]:
        """Split content at ### header boundaries.

        Args:
            content: Section content
            parent_header: Parent ## header
            base_position: Base position in document

        Returns:
            List of sub-chunks
        """
        chunks: List[MarkdownChunk] = []

        # Split at ### headers (H3)
        subsections = re.split(r"(^### .+$)", content, flags=re.MULTILINE)

        current_subheader = parent_header
        current_text = ""
        sub_position = 0

        for section in subsections:
            section = section.strip()
            if not section:
                continue

            if section.startswith("### "):
                # Save previous subsection if exists
                if current_text:
                    token_count = count_tokens(current_text, model=self.model)
                    chunks.append(
                        MarkdownChunk(
                            chunk_id=uuid4(),
                            text=current_text.strip(),
                            header=current_subheader,
                            header_level=3,
                            position=base_position + sub_position,
                            token_count=token_count,
                        )
                    )
                    sub_position += 1

                # Start new subsection
                current_subheader = f"{parent_header} > {section[4:].strip()}"
                current_text = section + "\n"
            else:
                current_text += section + "\n"

        # Last subsection
        if current_text:
            token_count = count_tokens(current_text, model=self.model)
            chunks.append(
                MarkdownChunk(
                    chunk_id=uuid4(),
                    text=current_text.strip(),
                    header=current_subheader,
                    header_level=3,
                    position=base_position + sub_position,
                    token_count=token_count,
                )
            )

        return chunks

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
