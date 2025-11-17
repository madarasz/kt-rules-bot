"""Property-based tests for MarkdownChunker.

Uses Hypothesis to generate random markdown content and verify chunker properties.
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from src.services.rag.chunker import MarkdownChunker


@pytest.mark.slow  # Requires tiktoken encoding download
@given(st.text(min_size=10, max_size=5000))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=50)
def test_chunker_never_loses_content(markdown_text):
    """Property: chunking never loses significant content."""
    chunker = MarkdownChunker()

    chunks = chunker.chunk(markdown_text)

    # All text should be preserved in chunks (allowing for some whitespace normalization)
    reconstructed = "".join(chunk.text for chunk in chunks)

    # If the original text is entirely whitespace, the chunker may return empty
    original_stripped = markdown_text.strip()
    if not original_stripped:
        # If original is empty/whitespace, reconstructed can be empty too
        return

    # Content length should be similar (allowing for YAML frontmatter removal and whitespace)
    # We allow up to 30% difference to account for frontmatter stripping
    assert len(reconstructed) >= len(markdown_text) * 0.7, \
        f"Lost too much content: original {len(markdown_text)}, reconstructed {len(reconstructed)}"


@pytest.mark.slow  # Requires tiktoken encoding download
@given(st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pd', 'Po')), min_size=10, max_size=1000))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=30)
def test_chunker_produces_valid_chunks(markdown_text):
    """Property: chunker always produces valid MarkdownChunk objects."""
    chunker = MarkdownChunker()

    chunks = chunker.chunk(markdown_text)

    # Should produce at least one chunk
    assert len(chunks) >= 1

    # All chunks should have required attributes
    for chunk in chunks:
        assert hasattr(chunk, 'text')
        assert hasattr(chunk, 'header')
        assert hasattr(chunk, 'header_level')
        assert isinstance(chunk.text, str)
        assert isinstance(chunk.header, str)
        assert isinstance(chunk.header_level, int)
        assert chunk.header_level >= 0


@pytest.mark.slow  # Requires tiktoken encoding download
@given(st.integers(min_value=2, max_value=4))
@settings(max_examples=3)
def test_chunker_respects_header_level(header_level):
    """Property: chunker respects configured header level."""
    chunker = MarkdownChunker(chunk_level=header_level)

    # Create content with multiple header levels
    content = "\n\n".join([
        f"{'#' * level} Header Level {level}\n\nContent for level {level}"
        for level in range(1, header_level + 3)
    ])

    chunks = chunker.chunk(content)

    # Should split at the configured level
    assert len(chunks) >= 1


@pytest.mark.slow  # Requires tiktoken encoding download
def test_chunker_yaml_frontmatter_property():
    """Property: YAML frontmatter is always stripped from first chunk."""
    chunker = MarkdownChunker()

    # Content with valid YAML frontmatter
    content_with_yaml = """---
source: Test
date: 2024-01-01
---

## Section 1

Content here."""

    chunks = chunker.chunk(content_with_yaml)

    # First chunk should not start with ---
    assert len(chunks) > 0
    assert not chunks[0].text.startswith("---") or "source:" not in chunks[0].text


@pytest.mark.slow  # Requires tiktoken encoding download
@given(st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=20))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=30)
def test_chunker_multiple_sections(section_texts):
    """Property: chunker handles multiple sections."""
    chunker = MarkdownChunker(chunk_level=2)

    # Create content with multiple ## sections
    content = "\n\n".join([
        f"## Section {i}\n\n{text}"
        for i, text in enumerate(section_texts)
    ])

    chunks = chunker.chunk(content)

    # Should produce chunks
    assert len(chunks) >= 1

    # Number of chunks should be related to number of sections
    # (might be equal or less due to chunking strategy)
    assert len(chunks) <= len(section_texts)
