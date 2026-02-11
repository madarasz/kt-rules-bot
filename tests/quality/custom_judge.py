"""Unified custom LLM judge for quality testing.

Provides domain-specific evaluation for Kill Team rules bot:
- Explanation Faithfulness: Is explanation grounded in quotes?
- Answer Correctness: Does answer match ground truth?

Note: Quote Faithfulness is evaluated separately using fuzzy string matching.
Uses a single LLM call with structured output (Pydantic validation).
"""

import re
from dataclasses import dataclass
from pathlib import Path

from src.lib.constants import (
    CUSTOM_JUDGE_PROMPT_PATH,
    LLM_GENERATION_TIMEOUT,
    QUALITY_TEST_JUDGE_MODEL,
)
from src.lib.logging import get_logger
from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.retry import retry_with_rate_limit_backoff
from tests.quality.test_case_models import GroundTruthAnswer

logger = get_logger(__name__)


def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text.

    Args:
        text: Text potentially containing markdown formatting

    Returns:
        Plain text with markdown formatting removed
    """
    if not text:
        return text

    # Remove code blocks (``` ... ```)
    text = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).replace('```', ''), text)

    # Remove inline code (`...`)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove bold (**text** or __text__)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)

    # Remove italic (*text* or _text_)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)

    # Remove links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Remove headers (# Header)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)

    # Remove blockquotes (> text)
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)

    # Remove horizontal rules (--- or ***)
    text = re.sub(r'^[\*\-_]{3,}\s*$', '', text, flags=re.MULTILINE)

    return text


@dataclass
class CustomJudgeResult:
    """Result from unified custom judge evaluation.

    Note: quote_faithfulness is evaluated separately using fuzzy string matching (not by LLM judge).
    """

    explanation_faithfulness: float  # 0.0-1.0
    answer_correctness: float  # 0.0-1.0 (aggregate)
    feedback: str  # Overall textual evaluation (strengths, problems, suggestions)
    error: str | None = None

    # Detailed per-item breakdowns
    answer_correctness_details: dict[str, float] | None = None  # answer_key -> score

    # Actual token usage from LLM call
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CustomJudge:
    """Unified LLM judge for quality testing (single call with structured output)."""

    def __init__(self, model: str = QUALITY_TEST_JUDGE_MODEL):
        """Initialize custom judge with specified model.

        Args:
            model: LLM model to use for judge evaluation (default: QUALITY_TEST_JUDGE_MODEL)
        """
        self.model = model
        self._provider = None
        self._prompt_template = None

    def _get_provider(self):
        """Lazy-load LLM provider."""
        if self._provider is None:
            self._provider = LLMProviderFactory.create(self.model)
        return self._provider

    def _load_prompt_template(self) -> str:
        """Load prompt template from file.

        Returns:
            Prompt template string with placeholders for formatting

        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        if self._prompt_template is None:
            # Locate prompt file relative to project root
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent
            prompt_file = project_root / CUSTOM_JUDGE_PROMPT_PATH

            if not prompt_file.exists():
                raise FileNotFoundError(
                    f"Custom judge prompt file not found: {prompt_file}\n"
                    f"Expected location: {CUSTOM_JUDGE_PROMPT_PATH}"
                )

            self._prompt_template = prompt_file.read_text(encoding="utf-8")
            logger.debug(f"Loaded custom judge prompt from {CUSTOM_JUDGE_PROMPT_PATH}")

        return self._prompt_template

    # Note: RAG context filtering removed - not needed since quote faithfulness
    # is evaluated separately using fuzzy string matching

    def _calculate_answer_correctness_aggregate(
        self,
        details: dict[str, float],
        ground_truth_answers: list[GroundTruthAnswer],
    ) -> float:
        """Calculate priority-weighted average of per-answer correctness scores.

        Args:
            details: Dict mapping ground_truth_answer.key to correctness score (0.0-1.0)
            ground_truth_answers: List of GroundTruthAnswer objects with keys and priorities

        Returns:
            Weighted average correctness score (0.0-1.0)
        """
        if not details or not ground_truth_answers:
            return 0.0

        # Create case-insensitive mapping from key to GroundTruthAnswer for weight lookup
        answer_by_key = {ans.key.lower(): ans for ans in ground_truth_answers}

        total_weight = 0.0
        weighted_sum = 0.0

        for answer_key, score in details.items():
            # Case-insensitive lookup to handle LLM key variations
            answer_key_lower = answer_key.lower()
            if answer_key_lower in answer_by_key:
                weight = answer_by_key[answer_key_lower].weight
                weighted_sum += score * weight
                total_weight += weight
            else:
                logger.warning(
                    f"Answer key '{answer_key}' from judge not found in ground_truth_answers "
                    f"(case-insensitive). Available keys: {[ans.key for ans in ground_truth_answers]}"
                )

        if total_weight == 0:
            return 0.0

        return weighted_sum / total_weight

    async def evaluate(
        self,
        query: str,
        llm_response_text: str,
        llm_quotes_structured: list[dict],
        ground_truth_answers: list[GroundTruthAnswer],
        ground_truth_contexts: list[str],
    ) -> CustomJudgeResult:
        """Run unified judge evaluation with structured JSON output and per-item scoring.

        Args:
            query: User's question
            llm_response_text: Full LLM response (structured JSON string)
            llm_quotes_structured: List of dicts with chunk_id, quote_title, quote_text
            _rag_context_chunks: Full list of DocumentChunk objects from RAG (unused but kept for interface)
            ground_truth_answers: List of GroundTruthAnswer objects with keys and priorities
            ground_truth_contexts: Rules that should be cited (text only)

        Returns:
            CustomJudgeResult with aggregate scores, detailed breakdowns, and textual feedback

        Raises:
            Exception: If LLM call fails or response parsing fails
        """
        try:
            # Format llm_quotes for display (strip markdown BEFORE formatting to avoid breaking markdown syntax)
            llm_quotes_display = "\n".join(
                f"{i+1}. [{q.get('chunk_id', 'no-id')}] {q.get('quote_title', 'Unknown')}: {strip_markdown(q.get('quote_text', ''))}"
                for i, q in enumerate(llm_quotes_structured)
            ) if llm_quotes_structured else "(none)"

            # Format ground truth answers with keys for judge
            ground_truth_answers_formatted = "\n".join(
                f"Key: '{ans.key}' (priority: {ans.priority})\nText: {ans.text}"
                for ans in ground_truth_answers
            )

            # Strip markdown from LLM response text
            llm_response_text_stripped = strip_markdown(llm_response_text)

            # Format ground truth contexts (strip markdown from each context)
            ground_truth_contexts_formatted = "\n".join(
                f"{i+1}. {strip_markdown(ctx)}" for i, ctx in enumerate(ground_truth_contexts)
            )

            # Load and format prompt template
            template = self._load_prompt_template()
            prompt = template.format(
                query=query,
                ground_truth_answers=ground_truth_answers_formatted,
                ground_truth_contexts=ground_truth_contexts_formatted,
                llm_response_text=llm_response_text_stripped,
                llm_quotes=llm_quotes_display,
            )

            # Configure for structured output
            provider = self._get_provider()
            config = GenerationConfig(
                max_tokens=2048,  # Hardcoded (sufficient for judge evaluation)
                temperature=0,  # Hardcoded (deterministic for consistency)
                system_prompt="You are an expert evaluator for a Kill Team rules bot. Provide structured JSON evaluation with per-item scoring.",
                include_citations=False,
                structured_output_schema="custom_judge",  # Use CustomJudgeResponse Pydantic model
            )

            logger.debug(
                f"Custom judge: Evaluating with {self.model} (query: '{query[:50]}...')"
            )

            # Generate response with retry logic for 429/529 errors
            async def generate_judge_evaluation():
                return await provider.generate(
                    GenerationRequest(prompt=prompt, context=[], chunk_ids=[], config=config)
                )

            response = await retry_with_rate_limit_backoff(
                generate_judge_evaluation,
                timeout_seconds=LLM_GENERATION_TIMEOUT,
            )

            # Debug: Log raw response
            logger.debug(f"Raw LLM response (answer_text, first 1000 chars): {response.answer_text[:1000]}")

            # Parse JSON response (provider handles validation via Pydantic)
            if not response.structured_output:
                raise Exception(
                    f"Custom judge response missing structured_output field. "
                    f"Raw response: {response.answer_text[:500]}"
                )

            result_data = response.structured_output

            # Debug: Log the actual keys in result_data
            logger.debug(f"result_data type: {type(result_data)}")
            if isinstance(result_data, dict):
                logger.debug(f"result_data keys: {list(result_data.keys())}")
                # Check for malformed keys
                for key in result_data:
                    if '\n' in key or '"' in key:
                        logger.error(
                            f"MALFORMED KEY DETECTED: {repr(key)} - "
                            f"contains whitespace or quotes"
                        )
            else:
                logger.debug(f"result_data is not a dict: {type(result_data)}")

            logger.debug(f"result_data content (first 500 chars): {str(result_data)[:500]}")

            # Extract detailed scores from judge response with explicit error handling
            # Note: The LLM returns arrays of {answer_key, score}
            # Convert these to dicts for the backend
            try:
                answer_correctness_list = result_data.get("answer_correctness_details", [])
                # Convert from [{answer_key: "Final Answer", score: 1.0}] to {"Final Answer": 1.0}
                answer_correctness_details = {
                    item["answer_key"]: item["score"] for item in answer_correctness_list
                }
            except (KeyError, AttributeError, TypeError) as e:
                logger.error(
                    f"Failed to convert answer_correctness_details: {e}. "
                    f"Data: {result_data.get('answer_correctness_details', 'N/A')}"
                )
                raise

            # Calculate aggregate (override judge's value with backend calculation)
            answer_correctness_agg = self._calculate_answer_correctness_aggregate(
                answer_correctness_details, ground_truth_answers
            )

            # Extract remaining fields with explicit error handling
            try:
                explanation_faithfulness = result_data["explanation_faithfulness"]
            except KeyError as e:
                logger.error(
                    f"Failed to get explanation_faithfulness: {e}. "
                    f"Available keys: {list(result_data.keys()) if isinstance(result_data, dict) else 'N/A'}"
                )
                raise

            try:
                feedback = result_data["feedback"]
            except KeyError as e:
                logger.error(
                    f"Failed to get feedback: {e}. "
                    f"Available keys: {list(result_data.keys()) if isinstance(result_data, dict) else 'N/A'}"
                )
                raise

            logger.info(
                f"Custom judge evaluation completed: "
                f"explanation_faithfulness={explanation_faithfulness:.2f}, "
                f"answer_correctness={answer_correctness_agg:.2f} (from {len(answer_correctness_details)} answers)"
            )

            return CustomJudgeResult(
                explanation_faithfulness=explanation_faithfulness,
                answer_correctness=answer_correctness_agg,
                feedback=feedback,
                answer_correctness_details=answer_correctness_details,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.token_count,
            )

        except Exception as e:
            logger.error(f"Custom judge evaluation failed: {e}", exc_info=True)
            return CustomJudgeResult(
                explanation_faithfulness=0.0,
                answer_correctness=0.0,
                feedback="",
                error=str(e),
            )
