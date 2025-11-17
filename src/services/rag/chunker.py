"""Markdown chunking service with configurable header splitting.

Splits documents at all header levels from ## up to the specified level.
For example, level 3 chunks at both ## and ### headers.
"""

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from src.lib.constants import MARKDOWN_CHUNK_HEADER_LEVEL
from src.lib.tokens import count_tokens


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
    """Chunks markdown documents at multiple header levels up to a configured maximum."""

    def __init__(self, chunk_level: int | None = None, model: str = "gpt-3.5-turbo"):
        """Initialize chunker.

        Args:
            chunk_level: Maximum header level to chunk at (2-4 for ##-####, default from constants)
                        Chunks at all levels from ## up to and including this level
            model: Model name for token counting
        """
        self.chunk_level = chunk_level if chunk_level is not None else MARKDOWN_CHUNK_HEADER_LEVEL
        self.model = model

        if self.chunk_level < 2 or self.chunk_level > 4:
            raise ValueError("chunk_level must be 2, 3, or 4 (for ##, ###, or #### headers)")

    def chunk(self, content: str) -> list[MarkdownChunk]:
        """Chunk markdown content at the configured header level and above.

        Chunks at all header levels from 2 (##) up to and including the configured level.
        For example, if chunk_level=3, it will chunk at both ## and ### headers.

        Args:
            content: Markdown content

        Returns:
            List of MarkdownChunk objects
        """
        # Strip YAML front matter before processing
        content = self._strip_yaml_frontmatter(content)

        # Create regex pattern for all header levels from 2 up to target level
        header_patterns = [rf"(^{'#' * level} .+$)" for level in range(2, self.chunk_level + 1)]
        combined_pattern = "|".join(header_patterns)

        # Check if content has headers at any of the target levels
        if not re.search(combined_pattern, content, flags=re.MULTILINE):
            # No headers at target levels: return whole document as single chunk
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

        # Split at all target header levels
        return self._split_at_multiple_levels(content)

    def _strip_yaml_frontmatter(self, content: str) -> str:
        """Remove YAML front matter from markdown content.

        Args:
            content: Markdown content that may contain YAML front matter

        Returns:
            Content with YAML front matter removed
        """
        # Check if content starts with YAML front matter delimiter
        if not content.strip().startswith('---'):
            return content

        lines = content.split('\n')

        # Find the closing --- delimiter
        in_frontmatter = False
        content_start_line = 0

        for i, line in enumerate(lines):
            if i == 0 and line.strip() == '---':
                in_frontmatter = True
                continue
            elif in_frontmatter and line.strip() == '---':
                # Found closing delimiter, content starts after this line
                content_start_line = i + 1
                break

        # If we found valid front matter, return content without it
        if content_start_line > 0:
            content_after_frontmatter = '\n'.join(lines[content_start_line:])
            # Strip leading whitespace/empty lines
            return content_after_frontmatter.lstrip()

        # No valid front matter found, return original content
        return content

    def _split_at_multiple_levels(self, content: str) -> list[MarkdownChunk]:
        """Split content at multiple header levels (from ## up to configured level).

        Args:
            content: Markdown content

        Returns:
            List of chunks
        """
        # Find all headers and their positions
        lines = content.split('\n')
        chunks: list[MarkdownChunk] = []
        current_header = ""
        current_header_level = 0
        current_lines = []
        position = 0

        for line in lines:
            # Check if this line is a header at any target level
            header_level = self._get_header_level(line)
            if header_level and 2 <= header_level <= self.chunk_level:
                # Save previous section if exists
                if current_lines:
                    current_text = '\n'.join(current_lines)
                    chunks.append(self._create_chunk_with_level(
                        current_text, current_header, current_header_level, position
                    ))
                    position += 1

                # Start new section
                header_text = line[header_level + 1:].strip()  # Remove "### " prefix
                current_header = header_text
                current_header_level = header_level
                current_lines = [line]
            else:
                # Add line to current section
                current_lines.append(line)

        # Don't forget last section
        if current_lines:
            current_text = '\n'.join(current_lines)
            chunks.append(self._create_chunk_with_level(
                current_text, current_header, current_header_level, position
            ))

        return chunks

    def _get_header_level(self, text: str) -> int:
        """Get the header level of a text line.

        Args:
            text: Text line to check

        Returns:
            Header level (1-6) or 0 if not a header
        """
        if not text.startswith('#'):
            return 0

        # Count consecutive # characters
        level = 0
        for char in text:
            if char == '#':
                level += 1
            elif char == ' ':
                break
            else:
                return 0  # Not a valid header

        return level if level <= 6 else 0

    def _create_chunk_with_level(self, text: str, header: str, header_level: int, position: int) -> MarkdownChunk:
        """Create a chunk from text with specific header level.

        Args:
            text: Chunk text
            header: Section header
            header_level: Actual header level of this chunk
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

    def get_chunk_stats(self, chunks: list[MarkdownChunk]) -> dict:
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
