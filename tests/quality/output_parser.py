"""Output parser for quality test replay.

Parses saved output files to reconstruct test context for replay without re-running
expensive RAG retrieval and LLM generation operations.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from src.lib.logging import get_logger
from src.services.llm.base import LLMResponse
from tests.quality.metadata_generator import MetadataFormatter, OutputMetadata

logger = get_logger(__name__)


@dataclass
class ParsedOutput:
    """
    Complete parsed output file ready for replay.

    Contains all information needed to skip RAG + LLM phases and proceed directly to evaluation.
    """

    metadata: OutputMetadata
    llm_response: LLMResponse  # Reconstructed from markdown
    query: str  # Original query
    file_path: Path


class ParseError(Exception):
    """Raised when output file cannot be parsed."""

    pass


class OutputParser:
    """
    Parses saved output files to enable test replay.
    """

    @staticmethod
    def parse_output_file(file_path: Path) -> ParsedOutput:
        """
        Parse output file and reconstruct test context.

        Args:
            file_path: Path to output_*.md file

        Returns:
            ParsedOutput with metadata and reconstructed LLM response

        Raises:
            ValueError: If metadata block missing (old output file)
            ParseError: If markdown structure invalid
        """
        content = file_path.read_text()

        # Extract metadata
        metadata = MetadataFormatter.extract_metadata_from_markdown(content)
        if metadata is None:
            raise ValueError(
                f"No metadata block found in {file_path.name}. "
                f"This output file was created before the metadata feature was added. "
                f"Cannot replay without metadata."
            )

        # Extract query
        query = OutputParser._extract_query(content)

        # Reconstruct LLM response
        llm_response = OutputParser._reconstruct_llm_response(content, metadata)

        return ParsedOutput(
            metadata=metadata, llm_response=llm_response, query=query, file_path=file_path
        )

    @staticmethod
    def _extract_query(content: str) -> str:
        """Extract query from # Query section."""
        match = re.search(r"# Query\s*\n(.+?)\n---", content, re.DOTALL)
        if not match:
            raise ParseError("Could not find query section")
        return match.group(1).strip()

    @staticmethod
    def _reconstruct_llm_response(content: str, metadata: OutputMetadata) -> LLMResponse:
        """
        Reconstruct LLMResponse from markdown sections.

        Parses:
        - Short answer (first paragraph after # Response)
        - Quotes (blockquotes with titles)
        - Explanation (## Explanation section)

        Returns LLMResponse with JSON string matching original structure.

        Args:
            content: Full markdown content
            metadata: Parsed metadata with token counts

        Returns:
            LLMResponse object

        Raises:
            ParseError: If required sections cannot be parsed
        """
        # Extract short answer
        short_answer = OutputParser._extract_short_answer(content)

        # Extract quotes
        quotes = OutputParser._extract_quotes(content)

        # Extract explanation
        explanation = OutputParser._extract_explanation(content)

        # Extract persona afterword
        persona_afterword = OutputParser._extract_persona_afterword(content)

        # Reconstruct JSON structure (matching StructuredLLMResponse format)
        # Include required persona fields with default values (they don't affect scoring)
        response_json = {
            "smalltalk": False,  # Default: not smalltalk (rules question)
            "short_answer": short_answer,
            "persona_short_answer": "",  # Default: empty (persona not needed for replay)
            "quotes": quotes,
            "explanation": explanation,
            "persona_afterword": persona_afterword,  # Use extracted value instead of ""
        }

        # Create LLMResponse with metadata tokens
        # Note: LLMResponse uses answer_text field (not response)
        return LLMResponse(
            response_id=__import__("uuid").uuid4(),  # Generate new UUID for replay
            answer_text=json.dumps(response_json),
            confidence_score=1.0,  # Not available from saved output
            token_count=metadata.tokens["total"],
            latency_ms=int(metadata.latency["llm_generation_seconds"] * 1000),
            provider=OutputParser._infer_provider(
                metadata.test_metadata["actual_model_id"]
            ),  # Infer from model ID
            model_version=metadata.test_metadata["actual_model_id"],
            citations_included=len(quotes) > 0,
            prompt_tokens=metadata.tokens["prompt"],
            completion_tokens=metadata.tokens["completion"],
        )

    @staticmethod
    def _extract_short_answer(content: str) -> str:
        """
        Extract short answer paragraph after # Response.

        The short answer is the first paragraph after # Response, before the first quote
        (starts with >) or ## Explanation section.
        """
        # Pattern: # Response\n{answer}\n\n> or \n\n## or ---
        pattern = r"# Response\s*\n(.+?)(?:\n\n>|\n\n##|---)"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            # Try alternative: just extract until end or next section
            pattern_alt = r"# Response\s*\n(.+?)(?:\n##|<!--|$)"
            match = re.search(pattern_alt, content, re.DOTALL)
            if not match:
                logger.warning("Could not extract short answer, using empty string")
                return ""

        answer = match.group(1).strip()

        # Remove any leading/trailing markdown formatting that might have been captured
        # Stop at first quote blockquote if accidentally included
        if "\n>" in answer:
            answer = answer.split("\n>")[0].strip()

        return answer

    @staticmethod
    def _extract_quotes(content: str) -> list[dict]:
        """
        Extract quotes from blockquote format.

        Format:
        > **Quote Title**
        > Quote text line 1
        > Quote text line 2

        Returns list of dicts with: {quote, rule_source, id}
        """
        quotes = []

        # Pattern: > **Title**\n(> text\n)+
        # Updated to handle multi-line quotes properly
        pattern = r"> \*\*(.+?)\*\*\s*\n((?:> .+\n?)+)"

        for match in re.finditer(pattern, content):
            title = match.group(1).strip()
            quote_lines = match.group(2)

            # Remove "> " prefix from each line
            quote_text = "\n".join(
                line[2:] if line.startswith("> ") else line
                for line in quote_lines.split("\n")
                if line.strip()
            )

            quotes.append(
                {
                    "quote_title": title,  # StructuredQuote expects quote_title
                    "quote_text": quote_text.strip(),  # StructuredQuote expects quote_text
                    "chunk_id": OutputParser._generate_quote_id(quote_text),  # StructuredQuote expects chunk_id
                }
            )

        return quotes

    @staticmethod
    def _extract_explanation(content: str) -> str:
        """Extract explanation section after ## Explanation, excluding persona_afterword.

        The persona_afterword is the last paragraph before the --- separator.
        """
        # Pattern: ## Explanation\n{text} until --- or ## or <!-- or end
        pattern = r"## Explanation\s*\n(.+?)(?:\n---|\\n##|<!--|$)"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            logger.warning("Could not extract explanation, using empty string")
            return ""

        full_text = match.group(1).strip()

        # Split into paragraphs (separated by blank lines)
        paragraphs = [p.strip() for p in re.split(r'\n\n+', full_text) if p.strip()]

        # Last paragraph is persona_afterword, rest is explanation
        if len(paragraphs) > 1:
            # Multiple paragraphs: all but last are explanation
            explanation = '\n\n'.join(paragraphs[:-1])
        elif len(paragraphs) == 1:
            # Single paragraph: check if it looks like persona afterword
            if len(paragraphs[0]) < 100 and '**' not in paragraphs[0]:
                # Short, no formatting → likely just persona afterword
                explanation = ""
            else:
                # Long or has formatting → likely just explanation
                explanation = paragraphs[0]
        else:
            explanation = ""

        return explanation

    @staticmethod
    def _extract_persona_afterword(content: str) -> str:
        """Extract persona_afterword from last paragraph of ## Explanation section."""
        # Same pattern as _extract_explanation
        pattern = r"## Explanation\s*\n(.+?)(?:\n---|\\n##|<!--|$)"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return ""

        full_text = match.group(1).strip()

        # Split into paragraphs (separated by blank lines)
        paragraphs = [p.strip() for p in re.split(r'\n\n+', full_text) if p.strip()]

        # Last paragraph is persona_afterword if it looks like one
        if len(paragraphs) > 0:
            last_para = paragraphs[-1]
            # Check if it looks like persona afterword (short, no bold formatting)
            if len(last_para) < 100 and '**' not in last_para:
                return last_para

        return ""

    @staticmethod
    def _generate_quote_id(quote_text: str) -> str:
        """Generate deterministic quote ID from text (last 8 chars of MD5 hash)."""
        return hashlib.md5(quote_text.encode()).hexdigest()[-8:]

    @staticmethod
    def _infer_provider(model_id: str) -> str:
        """
        Infer provider name from model ID.

        Args:
            model_id: Actual model ID (e.g., "claude-sonnet-4-5-20250929")

        Returns:
            Provider name ("claude", "gemini", "chatgpt", etc.)
        """
        model_lower = model_id.lower()

        if "claude" in model_lower:
            return "claude"
        elif "gemini" in model_lower:
            return "gemini"
        elif "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
            return "chatgpt"
        elif "grok" in model_lower:
            return "grok"
        elif "deepseek" in model_lower:
            return "deepseek"
        else:
            logger.warning(f"Could not infer provider from model ID: {model_id}, defaulting to 'unknown'")
            return "unknown"


# Convenience function for batch parsing
def parse_output_directory(output_dir: Path, models: list[str] | None = None) -> list[ParsedOutput]:
    """
    Parse all output_*.md files in a directory.

    Args:
        output_dir: Directory containing output files
        models: Optional list of model names to filter by

    Returns:
        List of ParsedOutput objects

    Note:
        Files that cannot be parsed are logged as warnings and skipped.
    """
    parsed_outputs = []

    for file_path in sorted(output_dir.glob("output_*.md")):
        try:
            parsed = OutputParser.parse_output_file(file_path)

            # Filter by model if specified
            if models and parsed.metadata.test_metadata["model"] not in models:
                logger.debug(f"Skipping {file_path.name} - model filter mismatch")
                continue

            parsed_outputs.append(parsed)

        except (ValueError, ParseError) as e:
            logger.warning(f"Failed to parse {file_path.name}: {e}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error parsing {file_path.name}: {e}", exc_info=True)
            continue

    logger.info(f"Parsed {len(parsed_outputs)} output files from {output_dir}")
    return parsed_outputs
