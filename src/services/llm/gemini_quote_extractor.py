"""Gemini quote extraction via sentence numbering.

Pre-processes chunks by numbering sentences, then extracts verbatim quotes
using sentence numbers returned by Gemini (avoids RECITATION errors).

Split strategy:
- Newlines (\n) end sentences (handles subheaders, bullets, tables)
- Sentence endings (. ? !) also end sentences within lines
"""

import re
from typing import Any

from src.lib.logging import get_logger

logger = get_logger(__name__)


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using newlines and punctuation.

    Rules:
    1. Newlines (\n) end sentences (handles subheaders, bullets, tables)
    2. Sentence endings (. ? !) followed by space also end sentences
    3. Empty sentences are filtered out
    4. Leading/trailing whitespace is stripped from each sentence

    Args:
        text: Text to split

    Returns:
        List of sentence strings (non-empty, stripped)

    Example:
        >>> split_into_sentences("Line 1\nLine 2. Next sentence.")
        ['Line 1', 'Line 2.', 'Next sentence.']
    """
    # Step 1: Split on newlines first
    lines = text.split("\n")

    sentences = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Step 2: Split each line on sentence endings (. ? ! followed by space)
        # Use regex to split but keep the punctuation with the sentence
        parts = re.split(r"([.?!])\s+", line)

        # Reconstruct sentences with their ending punctuation
        current_sentence = ""
        for i, part in enumerate(parts):
            if part in [".", "?", "!"]:
                # This is punctuation, add it to current sentence
                current_sentence += part
                sentences.append(current_sentence.strip())
                current_sentence = ""
            elif i > 0 and parts[i - 1] in [".", "?", "!"]:
                # Previous part was punctuation, this is start of new sentence
                current_sentence = part
            else:
                # Continue building current sentence
                current_sentence += part

        # Add any remaining sentence (line that didn't end with . ? !)
        if current_sentence.strip():
            sentences.append(current_sentence.strip())

    return [s for s in sentences if s]  # Filter empty strings


def number_sentences_in_chunk(chunk: str) -> tuple[str, list[str]]:
    """Add [S1], [S2], ... markers to sentences in chunk.

    Args:
        chunk: Original chunk text

    Returns:
        Tuple of (numbered_chunk, sentence_list):
        - numbered_chunk: Chunk with [S1], [S2] markers inserted
        - sentence_list: List of original sentences (for extraction)

    Example:
        >>> chunk = "Line 1\nLine 2"
        >>> numbered, sentences = number_sentences_in_chunk(chunk)
        >>> numbered
        '[S1] Line 1\n[S2] Line 2'
        >>> sentences
        ['Line 1', 'Line 2']
    """
    sentences = split_into_sentences(chunk)

    if not sentences:
        # Edge case: empty chunk
        logger.warning("Chunk has no sentences after splitting")
        return chunk, []

    # Build numbered chunk by inserting [SN] before each sentence
    numbered_parts = []
    for i, sentence in enumerate(sentences, start=1):
        numbered_parts.append(f"[S{i}] {sentence}")

    numbered_chunk = "\n".join(numbered_parts)

    return numbered_chunk, sentences


def extract_verbatim_quote(
    sentences: list[str], sentence_numbers: list[int], quote_title: str = ""
) -> str:
    """Extract verbatim quote text using sentence numbers.

    Args:
        sentences: List of sentences from the chunk (1-indexed)
        sentence_numbers: Which sentences to extract (1-indexed, e.g., [1, 3])
        quote_title: Rule title (for logging only)

    Returns:
        Verbatim quote text (concatenated sentences, separated by space)

    Example:
        >>> sentences = ["First sentence.", "Second sentence.", "Third."]
        >>> extract_verbatim_quote(sentences, [1, 3])
        'First sentence. Third.'
    """
    if not sentence_numbers:
        logger.debug(
            f"No sentence numbers provided for quote '{quote_title}', returning empty quote"
        )
        return ""

    extracted = []
    for num in sentence_numbers:
        # Convert to 0-indexed
        idx = num - 1

        # Validate index
        if idx < 0 or idx >= len(sentences):
            logger.warning(
                f"Invalid sentence number {num} for quote '{quote_title}' "
                f"(chunk has {len(sentences)} sentences). Skipping."
            )
            continue

        extracted.append(sentences[idx])

    # Join sentences with space
    return " ".join(extracted)


def post_process_gemini_response(
    response_json: dict[str, Any],
    _original_chunks: list[str],
    _chunk_ids: list[str] | None,
    chunk_id_to_sentences: dict[str, list[str]],
) -> dict[str, Any]:
    """Replace empty quote_text fields with verbatim quotes using sentence_numbers.

    Args:
        response_json: Gemini's JSON response with sentence_numbers
        _original_chunks: Original unnumbered chunks (unused, kept for interface compatibility)
        chunk_ids: Optional list of chunk IDs (UUIDs)
        chunk_id_to_sentences: Mapping of chunk_id (last 8 chars) -> sentence list

    Returns:
        Modified JSON with populated quote_text fields

    Example:
        >>> response = {
        ...     "quotes": [{
        ...         "quote_title": "Rule",
        ...         "quote_text": "",
        ...         "sentence_numbers": [1, 2],
        ...         "chunk_id": "abc12345"
        ...     }]
        ... }
        >>> chunk_id_to_sentences = {"abc12345": ["First.", "Second."]}
        >>> result = post_process_gemini_response(response, [], None, chunk_id_to_sentences)
        >>> result["quotes"][0]["quote_text"]
        'First. Second.'
    """
    quotes = response_json.get("quotes", [])

    logger.info(
        f"Post-processing {len(quotes)} quotes. Available chunk IDs: {list(chunk_id_to_sentences.keys())}"
    )

    for quote in quotes:
        quote_text = quote.get("quote_text", "").strip()
        sentence_numbers = quote.get("sentence_numbers", [])
        chunk_id = quote.get("chunk_id", "")
        quote_title = quote.get("quote_title", "")

        # Skip if quote_text is already populated
        if quote_text:
            logger.debug(
                f"Quote '{quote_title}' already has quote_text, skipping extraction"
            )
            continue

        # Skip if no sentence_numbers provided
        if not sentence_numbers:
            logger.debug(
                f"Quote '{quote_title}' has no sentence_numbers, leaving quote_text empty"
            )
            continue

        # Get sentences for this chunk
        sentences = chunk_id_to_sentences.get(chunk_id, [])

        if not sentences:
            logger.warning(
                f"No sentences found for chunk_id '{chunk_id}' (quote: '{quote_title}'). "
                f"Available chunk IDs: {list(chunk_id_to_sentences.keys())}. "
                "Cannot extract quote."
            )
            continue

        logger.info(
            f"Looking up chunk_id '{chunk_id}' for quote '{quote_title}': found {len(sentences)} sentences"
        )

        # Extract verbatim quote
        verbatim_quote = extract_verbatim_quote(sentences, sentence_numbers, quote_title)

        # Update quote_text
        quote["quote_text"] = verbatim_quote

        logger.info(
            f"Extracted verbatim quote for '{quote_title}'",
            extra={
                "chunk_id": chunk_id,
                "sentence_numbers": sentence_numbers,
                "quote_length": len(verbatim_quote),
            },
        )

    return response_json
