"""Unified custom LLM judge for quality testing.

Provides domain-specific evaluation for Kill Team rules bot:
- Quote Faithfulness: Are quotes verbatim from RAG contexts?
- Explanation Faithfulness: Is explanation grounded in quotes?
- Answer Correctness: Does answer match ground truth?

Uses a single LLM call with structured output (Pydantic validation).
"""

from dataclasses import dataclass
from pathlib import Path

from src.lib.constants import QUALITY_TEST_JUDGE_MODEL, CUSTOM_JUDGE_PROMPT_PATH
from src.lib.logging import get_logger
from src.services.llm.base import GenerationConfig, GenerationRequest
from src.services.llm.factory import LLMProviderFactory

logger = get_logger(__name__)


@dataclass
class CustomJudgeResult:
    """Result from unified custom judge evaluation."""

    quote_faithfulness: float  # 0.0-1.0
    explanation_faithfulness: float  # 0.0-1.0
    answer_correctness: float  # 0.0-1.0
    feedback: str  # Overall textual evaluation (strengths, problems, suggestions)
    error: str | None = None

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

    async def evaluate(
        self,
        query: str,
        llm_response_text: str,
        llm_quotes: list[str],
        rag_contexts: list[str],
        ground_truth_answers: list[str],
        ground_truth_contexts: list[str],
    ) -> CustomJudgeResult:
        """Run unified judge evaluation with structured JSON output.

        Args:
            query: User's question
            llm_response_text: Full LLM response (structured JSON string or formatted text)
            llm_quotes: List of quotes extracted from LLM response
            rag_contexts: Retrieved RAG context chunks available to the LLM
            ground_truth_answers: Expected answer statements
            ground_truth_contexts: Rules that should be cited

        Returns:
            CustomJudgeResult with three metric scores (0.0-1.0) and textual feedback

        Raises:
            Exception: If LLM call fails or response parsing fails
        """
        try:
            # Load and format prompt template
            template = self._load_prompt_template()
            prompt = template.format(
                query=query,
                ground_truth_answers="\n".join(
                    f"{i+1}. {ans}" for i, ans in enumerate(ground_truth_answers)
                ),
                ground_truth_contexts="\n".join(
                    f"{i+1}. {ctx}" for i, ctx in enumerate(ground_truth_contexts)
                ),
                rag_contexts="\n".join(
                    f"{i+1}. {ctx}" for i, ctx in enumerate(rag_contexts)
                ),
                llm_response_text=llm_response_text,
                llm_quotes="\n".join(f"{i+1}. {q}" for i, q in enumerate(llm_quotes))
                if llm_quotes
                else "(none)",
            )

            # Configure for structured output
            provider = self._get_provider()
            config = GenerationConfig(
                max_tokens=2048,  # Hardcoded (sufficient for judge evaluation)
                temperature=0,  # Hardcoded (deterministic for consistency)
                system_prompt="You are an expert evaluator for a Kill Team rules bot. Provide structured JSON evaluation.",
                include_citations=False,
                structured_output_schema="custom_judge",  # Use CustomJudgeResponse Pydantic model
            )

            logger.debug(
                f"Custom judge: Evaluating with {self.model} (query: '{query[:50]}...')"
            )

            # Generate response
            response = await provider.generate(
                GenerationRequest(prompt=prompt, context=[], config=config)
            )

            # Parse JSON response (provider handles validation via Pydantic)
            if not response.structured_output:
                raise Exception(
                    f"Custom judge response missing structured_output field. "
                    f"Raw response: {response.answer_text[:500]}"
                )

            result_data = response.structured_output

            logger.info(
                f"Custom judge evaluation completed: "
                f"quote_faithfulness={result_data['quote_faithfulness']:.2f}, "
                f"explanation_faithfulness={result_data['explanation_faithfulness']:.2f}, "
                f"answer_correctness={result_data['answer_correctness']:.2f}"
            )

            return CustomJudgeResult(
                quote_faithfulness=result_data["quote_faithfulness"],
                explanation_faithfulness=result_data["explanation_faithfulness"],
                answer_correctness=result_data["answer_correctness"],
                feedback=result_data["feedback"],
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.token_count,
            )

        except Exception as e:
            logger.error(f"Custom judge evaluation failed: {e}", exc_info=True)
            return CustomJudgeResult(
                quote_faithfulness=0.0,
                explanation_faithfulness=0.0,
                answer_correctness=0.0,
                feedback="",
                error=str(e),
            )
