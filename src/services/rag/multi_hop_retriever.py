"""Multi-hop retrieval with LLM-guided context evaluation.

Implements iterative retrieval where an LLM evaluates retrieved context
and requests additional information if needed.
"""

import asyncio
import json
import time
from dataclasses import replace
from typing import Any
from uuid import UUID

import yaml

from src.lib.constants import (
    LLM_MAX_RETRIES,
    MAX_CHUNK_LENGTH_FOR_EVALUATION,
    RAG_HOP_CHUNK_LIMIT,
    RAG_HOP_EVALUATION_MODEL,
    RAG_HOP_EVALUATION_PROMPT_PATH,
    RAG_HOP_EVALUATION_TIMEOUT,
    RAG_HOP_RATE_LIMIT_DELAY,
    RAG_MAX_HOPS,
    RULES_STRUCTURE_PATH,
    TEAMS_STRUCTURE_PATH,
)
from src.lib.logging import get_logger
from src.models.rag_context import DocumentChunk, RAGContext
from src.models.rag_request import RetrieveRequest
from src.services.llm.base import GenerationConfig, GenerationRequest, RateLimitError
from src.services.llm.factory import LLMProviderFactory
from src.services.rag.hop_cost_calculator import calculate_hop_evaluation_cost
from src.services.rag.team_filtering import TeamFilter

logger = get_logger(__name__)


class HopEvaluation:
    """Result of hop context evaluation."""

    def __init__(
        self,
        can_answer: bool,
        reasoning: str,
        missing_query: str | None = None,
        cost_usd: float = 0.0,
        retrieval_time_s: float = 0.0,
        evaluation_time_s: float = 0.0,
        filled_prompt: str | None = None,
        filtered_teams_count: int = 0,
    ):
        self.can_answer = can_answer
        self.reasoning = reasoning
        self.missing_query = missing_query
        self.cost_usd = cost_usd
        self.retrieval_time_s = retrieval_time_s  # Time for retrieval
        self.evaluation_time_s = evaluation_time_s  # Time for LLM evaluation
        self.filled_prompt = filled_prompt  # Optional: filled prompt for verbose output
        self.filtered_teams_count = filtered_teams_count  # Number of teams after filtering

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "can_answer": self.can_answer,
            "reasoning": self.reasoning,
            "missing_query": self.missing_query,
            "cost_usd": self.cost_usd,
            "retrieval_time_s": self.retrieval_time_s,
            "evaluation_time_s": self.evaluation_time_s,
            "filtered_teams_count": self.filtered_teams_count,
        }


class MultiHopRetriever:
    """Retriever with multi-hop context-aware retrieval."""

    def __init__(
        self,
        base_retriever,  # Type hint omitted to avoid circular import
        max_hops: int = RAG_MAX_HOPS,
        chunks_per_hop: int = RAG_HOP_CHUNK_LIMIT,
        evaluation_model: str = RAG_HOP_EVALUATION_MODEL,
        evaluation_timeout: int = RAG_HOP_EVALUATION_TIMEOUT,
    ):
        """Initialize multi-hop retriever.

        Args:
            base_retriever: Base RAG retriever
            max_hops: Maximum retrieval iterations after initial query
            chunks_per_hop: Maximum chunks to retrieve per hop
            evaluation_model: LLM model for context evaluation
            evaluation_timeout: Timeout for evaluation LLM call (seconds)
        """
        self.base_retriever = base_retriever
        self.max_hops = max_hops
        self.chunks_per_hop = chunks_per_hop
        self.evaluation_timeout = evaluation_timeout

        # Initialize evaluation LLM
        self.evaluation_llm = LLMProviderFactory.create(evaluation_model)

        # Load and cache hop evaluation prompt and structures
        self.evaluation_prompt_template = self._load_prompt_template()
        self.rules_structure_dict = self._load_structure_dict(RULES_STRUCTURE_PATH)
        self.teams_structure_dict = self._load_structure_dict(TEAMS_STRUCTURE_PATH)

        # Initialize team filter for query-specific filtering
        self.team_filter = (
            TeamFilter(self.teams_structure_dict) if self.teams_structure_dict else None
        )

        logger.info(
            "multi_hop_retriever_initialized",
            max_hops=max_hops,
            chunks_per_hop=chunks_per_hop,
            evaluation_model=evaluation_model,
        )

    def _load_prompt_template(self) -> str:
        """Load hop evaluation prompt from file and cache in memory."""
        with open(RAG_HOP_EVALUATION_PROMPT_PATH) as f:
            return f.read()

    def _load_structure_dict(self, file_path: str) -> dict[str, Any]:
        """Load YAML structure file as dictionary.

        Args:
            file_path: Path to YAML structure file

        Returns:
            Structure as dictionary (empty dict if load fails)
        """
        try:
            with open(file_path) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("structure_file_load_failed", file_path=file_path, error=str(e))
            return {}

    async def retrieve_multi_hop(
        self,
        query: str,
        context_key: str,
        query_id: UUID,
        initial_chunks: list[DocumentChunk] | None = None,
        verbose: bool = False,
    ) -> tuple[RAGContext, list[HopEvaluation], dict[UUID, int]]:
        """Perform multi-hop retrieval with LLM-guided context evaluation.

        Args:
            query: User's original question
            context_key: Context key for tracking
            query_id: Query UUID
            initial_chunks: Optional initial chunks from Hop 0 (if already retrieved)
            verbose: If True, capture filled prompts in HopEvaluation objects

        Returns:
            Tuple of:
            - RAGContext with accumulated chunks
            - List of HopEvaluation objects (one per hop attempted)
            - Dict mapping chunk_id to hop number (0=initial, 1+=hop)
        """
        accumulated_chunks: list[DocumentChunk] = []
        hop_evaluations: list[HopEvaluation] = []
        chunk_hop_map: dict[UUID, int] = {}

        logger.info("multi_hop_started", query=query, max_hops=self.max_hops)

        # Hop 0: Use provided initial chunks or retrieve them
        if initial_chunks is not None:
            # Use provided initial chunks (already retrieved in retriever.py)
            accumulated_chunks.extend(initial_chunks)

            # Track hop 0 chunks
            for chunk in initial_chunks:
                chunk_hop_map[chunk.chunk_id] = 0

            logger.info(
                "multi_hop_using_provided_initial_chunks",
                chunks_count=len(initial_chunks),
            )
        else:
            # Perform initial retrieval (fallback for backward compatibility)
            initial_request = RetrieveRequest(
                query=query,
                context_key=context_key,
                max_chunks=self.chunks_per_hop,
                use_multi_hop=False,  # Prevent infinite recursion
            )

            initial_context, _, _ = self.base_retriever.retrieve(initial_request, query_id)
            accumulated_chunks.extend(initial_context.document_chunks)

            # Track hop 0 chunks
            for chunk in initial_context.document_chunks:
                chunk_hop_map[chunk.chunk_id] = 0

            logger.info(
                "multi_hop_initial_retrieval",
                chunks_retrieved=len(initial_context.document_chunks),
                avg_relevance=initial_context.avg_relevance,
            )

        # Iterative hops (1 to max_hops)
        for hop_num in range(1, self.max_hops + 1):
            # Evaluate context: can we answer?
            try:
                evaluation = await self._evaluate_context(
                    user_query=query, retrieved_chunks=accumulated_chunks, verbose=verbose
                )

                hop_evaluations.append(evaluation)

                logger.info(
                    "multi_hop_evaluation",
                    hop=hop_num,
                    can_answer=evaluation.can_answer,
                    reasoning=evaluation.reasoning,
                )

                # If LLM says "ready to answer", stop hopping
                if evaluation.can_answer:
                    logger.info(
                        "multi_hop_complete",
                        total_hops=hop_num - 1,
                        total_chunks=len(accumulated_chunks),
                        reason="sufficient_context",
                    )
                    break

                # Retrieve additional context with focused query
                if not evaluation.missing_query:
                    logger.warning(
                        "multi_hop_missing_query_null", hop=hop_num, evaluation=evaluation.reasoning
                    )
                    break

                # Use header-based lookup with semantic fallback
                retrieval_start = time.time()
                new_chunks = await self._retrieve_for_hop(
                    evaluation.missing_query, context_key, query_id
                )
                evaluation.retrieval_time_s = time.time() - retrieval_start

                # Deduplicate against accumulated chunks
                existing_ids = {c.chunk_id for c in accumulated_chunks}
                new_unique_chunks = [c for c in new_chunks if c.chunk_id not in existing_ids]

                # Track hop number for new chunks
                for chunk in new_unique_chunks:
                    chunk_hop_map[chunk.chunk_id] = hop_num

                accumulated_chunks.extend(new_unique_chunks)

                logger.info(
                    "multi_hop_retrieval",
                    hop=hop_num,
                    query=evaluation.missing_query,
                    chunks_retrieved=len(new_chunks),
                    new_unique_chunks=len(new_unique_chunks),
                    total_chunks=len(accumulated_chunks),
                )

            except Exception as e:
                logger.error(
                    "multi_hop_evaluation_failed",
                    hop=hop_num,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Proceed with what we have
                break

        # If MAX_HOPS reached but can't answer, proceed anyway (Option A)
        if hop_evaluations and not hop_evaluations[-1].can_answer:
            logger.warning(
                "multi_hop_incomplete",
                total_hops=len(hop_evaluations),
                total_chunks=len(accumulated_chunks),
                last_reasoning=hop_evaluations[-1].reasoning,
            )

        # Build final RAGContext from accumulated chunks
        final_context = RAGContext.from_retrieval(query_id=query_id, chunks=accumulated_chunks)

        logger.info(
            "multi_hop_finished",
            total_hops=len(hop_evaluations),
            total_chunks=len(accumulated_chunks),
            avg_relevance=final_context.avg_relevance,
        )

        return final_context, hop_evaluations, chunk_hop_map

    async def _evaluate_context(
        self, user_query: str, retrieved_chunks: list[DocumentChunk], verbose: bool = False
    ) -> HopEvaluation:
        """Evaluate if retrieved context is sufficient to answer query.

        Args:
            user_query: Original user question
            retrieved_chunks: Currently accumulated chunks
            verbose: If True, capture filled prompt in HopEvaluation

        Returns:
            HopEvaluation with can_answer flag and optional missing_query

        Raises:
            ValueError: If LLM returns invalid JSON
            TimeoutError: If evaluation exceeds timeout
            RateLimitError: If rate limit is hit after all retries
        """
        # Format chunks for prompt
        chunks_text = self._format_chunks_for_prompt(retrieved_chunks)

        # Filter teams structure based on query
        filtered_teams = self.teams_structure_dict
        relevant_teams = []
        if self.team_filter:
            relevant_teams = self.team_filter.extract_relevant_teams(user_query)
            filtered_teams = self.team_filter.filter_structure(relevant_teams)

            # Log team filtering results
            logger.info(
                "hop_evaluation_teams_filtered",
                query=user_query,
                relevant_teams=relevant_teams,
                teams_count=len(relevant_teams),
                original_teams_count=len(self.teams_structure_dict),
                reduction_pct=round(
                    (1 - len(filtered_teams) / len(self.teams_structure_dict)) * 100, 1
                )
                if filtered_teams
                else 0,
            )

        # Convert structures to YAML text
        rules_structure_text = yaml.dump(
            self.rules_structure_dict,
            default_flow_style=False,
            allow_unicode=True,
            width=120,
            indent=2,
        )
        teams_structure_text = yaml.dump(
            filtered_teams, default_flow_style=False, allow_unicode=True, width=120, indent=2
        )

        # Fill prompt template with structures
        prompt = self.evaluation_prompt_template.format(
            user_query=user_query,
            retrieved_chunks=chunks_text,
            rule_structure=rules_structure_text,
            team_structure=teams_structure_text,
        )

        # Call evaluation LLM with hop evaluation schema
        request = GenerationRequest(
            prompt=prompt,
            context=[],
            chunk_ids=[],  # Empty list for hop evaluation (no RAG context)
            config=GenerationConfig(
                max_tokens=300,
                temperature=0.0,  # Deterministic
                timeout_seconds=self.evaluation_timeout,
                system_prompt="",  # Empty system prompt for hop evaluation
                structured_output_schema="hop_evaluation",  # Use hop evaluation schema
            ),
        )

        # Retry loop for rate limit errors
        last_error = None
        for attempt in range(LLM_MAX_RETRIES + 1):
            try:
                # Start timer for this attempt (restart on each retry)
                eval_start = time.time()

                response = await asyncio.wait_for(
                    self.evaluation_llm.generate(request), timeout=self.evaluation_timeout
                )

                # Parse JSON response (already structured by LLM)
                response_text = response.answer_text.strip()
                logger.debug("hop_evaluation_response", response_length=len(response_text))

                # Parse the JSON
                try:
                    data = json.loads(response_text)
                    logger.debug(
                        "hop_evaluation_parsed",
                        keys=list(data.keys()) if isinstance(data, dict) else "not_a_dict",
                    )
                except json.JSONDecodeError as e:
                    logger.error(
                        "hop_evaluation_json_parse_error",
                        error=str(e),
                        response_preview=response_text[:200],
                    )
                    raise ValueError(
                        f"Failed to parse hop evaluation JSON: {e}. Response: {response_text[:200]}"
                    ) from e

                # Validate required fields
                if "can_answer" not in data or "reasoning" not in data:
                    raise ValueError(f"Missing required fields in response: {data}")

                # Calculate cost using actual token counts (single source of truth)
                cost_usd = calculate_hop_evaluation_cost(response, RAG_HOP_EVALUATION_MODEL)

                # Calculate evaluation time (only the successful attempt)
                evaluation_time_s = time.time() - eval_start

                return HopEvaluation(
                    can_answer=data["can_answer"],
                    reasoning=data["reasoning"],
                    missing_query=data.get("missing_query"),
                    cost_usd=cost_usd,
                    evaluation_time_s=evaluation_time_s,
                    filled_prompt=prompt if verbose else None,
                    filtered_teams_count=len(relevant_teams),
                )

            except RateLimitError as e:
                last_error = e
                if attempt < LLM_MAX_RETRIES:
                    logger.warning(
                        "hop_evaluation_rate_limit_retry",
                        attempt=attempt + 1,
                        max_retries=LLM_MAX_RETRIES,
                        delay=RAG_HOP_RATE_LIMIT_DELAY,
                        error=str(e),
                    )
                    await asyncio.sleep(RAG_HOP_RATE_LIMIT_DELAY)
                    continue
                else:
                    logger.error(
                        "hop_evaluation_rate_limit_exhausted",
                        attempts=LLM_MAX_RETRIES + 1,
                        error=str(e),
                    )
                    raise

            except json.JSONDecodeError as e:
                logger.error(
                    "hop_evaluation_json_parse_failed",
                    error=str(e),
                    response_text=response.answer_text[:1000],
                )
                raise ValueError(f"Invalid JSON from evaluation LLM: {e}") from e

            except TimeoutError as e:
                logger.error("hop_evaluation_timeout", timeout=self.evaluation_timeout)
                raise TimeoutError(
                    f"Hop evaluation exceeded {self.evaluation_timeout}s timeout"
                ) from e

        # Should never reach here, but just in case
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected error in hop evaluation retry loop")

    def _format_chunks_for_prompt(self, chunks: list[DocumentChunk]) -> str:
        """Format chunks as numbered list for prompt.

        Args:
            chunks: List of DocumentChunk objects

        Returns:
            Formatted string with numbered chunks
        """
        if not chunks:
            return "(No context retrieved yet)"

        formatted_chunks = []
        for i, chunk in enumerate(chunks, 1):
            # Check if truncation is needed
            if len(chunk.text) > MAX_CHUNK_LENGTH_FOR_EVALUATION:
                truncated_text = chunk.text[:MAX_CHUNK_LENGTH_FOR_EVALUATION]
                remaining_text = chunk.text[MAX_CHUNK_LENGTH_FOR_EVALUATION:]

                # Extract header lines (### or ####) from the truncated portion
                # This preserves section structure info even when content is cut off
                missing_headers = []
                for line in remaining_text.split('\n'):
                    stripped = line.strip()
                    if stripped.startswith('####') or stripped.startswith('###'):
                        missing_headers.append(stripped)

                # Build final text with truncation marker and missing headers
                if missing_headers:
                    text = truncated_text + "...\n" + "\n".join(missing_headers)
                else:
                    text = truncated_text + "..."
            else:
                text = chunk.text

            # Get summary from metadata
            summary = chunk.metadata.get("summary", "")

            # Extract first line (header) from text
            header_line = text.split('\n')[0] if text else ""

            if summary:
                # Show header + summary only (concise view for hop evaluation)
                formatted_chunks.append(f"{i}. {header_line}\n{summary}\n")
            else:
                # Fallback to full text if no summary available
                formatted_chunks.append(f"{i}. {text}\n")

        return "\n".join(formatted_chunks)

    def _clean_missing_query(self, missing_query: str) -> list[str]:
        """Parse missing_query into individual titles.

        Handles:
        - Apostrophe-wrapped titles: "'Title A', Title B" → ["Title A", "Title B"]
        - Comma separation: "A, B, C" → ["A", "B", "C"]
        - Whitespace cleanup

        Note: Hyphens are NOT delimiters - "FIREFIGHT PHASE - WHEN A FRIENDLY..."
        is a single title.

        Args:
            missing_query: Raw missing_query from hop evaluation

        Returns:
            List of cleaned individual titles
        """
        # Split by comma first, then strip wrapping quotes per title
        titles = [t.strip().strip("'\"") for t in missing_query.split(',') if t.strip()]

        return titles

    async def _retrieve_for_hop(
        self, missing_query: str, context_key: str, query_id: UUID
    ) -> list[DocumentChunk]:
        """Retrieve chunks for hop using header lookup + semantic fallback.

        For each title in missing_query:
        1. Try fuzzy header match (85% threshold)
        2. If matched, use fuzzy score - 0.01 as relevance
        3. Collect unmatched titles for semantic fallback

        Args:
            missing_query: Comma-separated titles from hop evaluation
            context_key: Context key for tracking
            query_id: Query UUID

        Returns:
            List of retrieved chunks (header-matched first, then semantic)
        """
        # Step 1: Parse into individual titles
        titles = self._clean_missing_query(missing_query)

        header_matched_chunks: list[DocumentChunk] = []
        unmatched_titles: list[str] = []

        # Step 2: Fuzzy header search for each title (85% threshold)
        for title in titles:
            chunk, score = self.base_retriever.retrieve_by_header(title)
            if chunk:
                # Use fuzzy match score - 0.01 as relevance score
                adjusted_score = score - 0.01
                boosted_chunk = replace(chunk, relevance_score=adjusted_score)
                header_matched_chunks.append(boosted_chunk)

                logger.info(
                    "hop_header_match",
                    title=title,
                    matched_header=chunk.header,
                    score=score,
                    adjusted_score=adjusted_score,
                )
            else:
                unmatched_titles.append(title)
                logger.info(
                    "hop_header_no_match",
                    title=title,
                )

        # Step 3: Semantic fallback for unmatched titles
        semantic_chunks: list[DocumentChunk] = []
        if unmatched_titles:
            fallback_query = ", ".join(unmatched_titles)
            hop_request = RetrieveRequest(
                query=fallback_query,
                context_key=context_key,
                max_chunks=self.chunks_per_hop,
                use_multi_hop=False,
            )
            hop_context, _, _ = self.base_retriever.retrieve(hop_request, query_id)
            semantic_chunks = hop_context.document_chunks

            logger.info(
                "hop_semantic_fallback",
                unmatched_titles=unmatched_titles,
                fallback_query=fallback_query,
                chunks_retrieved=len(semantic_chunks),
            )

        # Step 4: Merge and deduplicate (header matches first)
        seen_ids = set()
        final_chunks = []

        for chunk in header_matched_chunks + semantic_chunks:
            if chunk.chunk_id not in seen_ids:
                seen_ids.add(chunk.chunk_id)
                final_chunks.append(chunk)

        logger.info(
            "hop_retrieval_complete",
            header_matched=len(header_matched_chunks),
            semantic_fallback=len(semantic_chunks),
            final_unique=len(final_chunks),
        )

        return final_chunks
