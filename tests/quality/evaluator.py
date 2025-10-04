"""Evaluator for quality test requirements.

Evaluates both "contains" and "llm" type requirements.
"""

import asyncio
import re
from typing import List

from tests.quality.models import (
    TestRequirement,
    RequirementResult,
)
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.base import GenerationRequest, GenerationConfig
from src.lib.logging import get_logger

logger = get_logger(__name__)


class RequirementEvaluator:
    """Evaluates test requirements against responses."""

    def __init__(self, judge_model: str = "gemini-2.5-flash"):
        """Initialize evaluator.

        Args:
            judge_model: LLM model to use for "llm" type requirements
        """
        self.judge_model = judge_model
        self._judge_provider = None

    def _get_judge_provider(self):
        """Lazy-load judge provider."""
        if self._judge_provider is None:
            self._judge_provider = LLMProviderFactory.create(self.judge_model)
        return self._judge_provider

    async def evaluate_all(
        self, requirements: List[TestRequirement], response: str
    ) -> List[RequirementResult]:
        """Evaluate all requirements against a response.

        Args:
            requirements: List of test requirements
            response: Response text to evaluate

        Returns:
            List of requirement results
        """
        results = []

        for req in requirements:
            if req.type == "contains":
                result = self._evaluate_contains(req, response)
            elif req.type == "llm":
                result = await self._evaluate_llm(req, response)
            else:
                logger.error(f"Unknown requirement type: {req.type}")
                result = RequirementResult(
                    requirement=req,
                    passed=False,
                    points_earned=0,
                    details=f"Unknown requirement type: {req.type}",
                )

            results.append(result)

        return results

    def _evaluate_contains(
        self, requirement: TestRequirement, response: str
    ) -> RequirementResult:
        """Evaluate a 'contains' requirement.

        Args:
            requirement: Requirement to evaluate
            response: Response text

        Returns:
            RequirementResult
        """
        # Strip markdown formatting from response for comparison
        clean_response = self._strip_markdown(response)
        clean_requirement = requirement.description.strip()

        # Normalize: lowercase and collapse whitespace
        clean_response = self._normalize_text(clean_response)
        clean_requirement = self._normalize_text(clean_requirement)

        # Substring match
        passed = clean_requirement in clean_response

        return RequirementResult(
            requirement=requirement,
            passed=passed,
            points_earned=requirement.points if passed else 0,
            details=f"Text {'found' if passed else 'not found'} in response",
        )

    async def _evaluate_llm(
        self, requirement: TestRequirement, response: str
    ) -> RequirementResult:
        """Evaluate an 'llm' requirement using LLM judge.

        Args:
            requirement: Requirement to evaluate
            response: Response text

        Returns:
            RequirementResult
        """
        judge_provider = self._get_judge_provider()

        # Truncate response if too long (keep first 1500 chars to avoid token limits)
        truncated_response = response[:1500]
        if len(response) > 1500:
            truncated_response += "\n...(truncated)"

        # Build prompt for LLM judge
        judge_prompt = f"""You are evaluating whether a statement is true about a given response.

Statement to verify: "{requirement.description}"

Response to evaluate:
---
{truncated_response}
---

Is the statement true about the response? Answer with just "YES" or "NO" followed by a brief explanation."""

        try:
            llm_response = await judge_provider.generate(
                GenerationRequest(
                    prompt=judge_prompt,
                    context=[],  # No RAG context needed for judging
                    config=GenerationConfig(
                        max_tokens=200,  # Increased from 100 to avoid MAX_TOKENS
                        temperature=0.0,
                        system_prompt="You are a precise evaluator. Answer only YES or NO without any additional text or explanation.",
                        include_citations=False,
                        timeout_seconds=30,
                    ),
                )
            )

            answer = llm_response.answer_text.strip().upper()
            passed = answer.startswith("YES")

            return RequirementResult(
                requirement=requirement,
                passed=passed,
                points_earned=requirement.points if passed else 0,
                details=llm_response.answer_text[:200],  # Truncate if too long
            )

        except Exception as e:
            logger.error(f"LLM judge evaluation failed: {e}", exc_info=True)
            return RequirementResult(
                requirement=requirement,
                passed=False,
                points_earned=0,
                details=f"Evaluation failed: {str(e)}",
            )

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for comparison.

        Args:
            text: Text to normalize

        Returns:
            Normalized text (lowercase, collapsed whitespace)
        """
        # Convert to lowercase
        text = text.lower()

        # Collapse multiple whitespace characters into single space
        text = re.sub(r'\s+', ' ', text)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Strip common markdown formatting from text.

        Args:
            text: Text with markdown

        Returns:
            Text with markdown stripped
        """
        # Remove bold/italic markers
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)

        # Remove code blocks
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`(.+?)`", r"\1", text)

        # Remove links but keep text
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)

        # Remove headers
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

        return text
