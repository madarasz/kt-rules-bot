"""Multi-hop retrieval with LLM-guided context evaluation.

Implements iterative retrieval where an LLM evaluates retrieved context
and requests additional information if needed.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
import json
import asyncio

from src.models.rag_context import RAGContext, DocumentChunk
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.base import GenerationRequest, GenerationConfig
from src.lib.constants import (
    RAG_MAX_HOPS,
    RAG_HOP_CHUNK_LIMIT,
    RAG_HOP_EVALUATION_MODEL,
    RAG_HOP_EVALUATION_TIMEOUT,
    RAG_HOP_EVALUATION_PROMPT_PATH,
)
from src.lib.logging import get_logger

logger = get_logger(__name__)


class HopEvaluation:
    """Result of hop context evaluation."""

    def __init__(
        self,
        can_answer: bool,
        reasoning: str,
        missing_query: Optional[str] = None,
    ):
        self.can_answer = can_answer
        self.reasoning = reasoning
        self.missing_query = missing_query

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "can_answer": self.can_answer,
            "reasoning": self.reasoning,
            "missing_query": self.missing_query,
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

        # Load and cache hop evaluation prompt
        self.evaluation_prompt_template = self._load_prompt_template()

        logger.info(
            "multi_hop_retriever_initialized",
            max_hops=max_hops,
            chunks_per_hop=chunks_per_hop,
            evaluation_model=evaluation_model,
        )

    def _load_prompt_template(self) -> str:
        """Load hop evaluation prompt from file and cache in memory."""
        with open(RAG_HOP_EVALUATION_PROMPT_PATH, "r") as f:
            return f.read()

    async def retrieve_multi_hop(
        self,
        query: str,
        context_key: str,
        query_id: UUID,
    ) -> tuple[RAGContext, List[HopEvaluation], Dict[UUID, int]]:
        """Perform multi-hop retrieval with LLM-guided context evaluation.

        Args:
            query: User's original question
            context_key: Context key for tracking
            query_id: Query UUID

        Returns:
            Tuple of:
            - RAGContext with accumulated chunks
            - List of HopEvaluation objects (one per hop attempted)
            - Dict mapping chunk_id to hop number (0=initial, 1+=hop)
        """
        # Import here to avoid circular dependency
        from src.services.rag.retriever import RetrieveRequest

        accumulated_chunks: List[DocumentChunk] = []
        hop_evaluations: List[HopEvaluation] = []
        chunk_hop_map: Dict[UUID, int] = {}

        # Hop 0: Initial retrieval with original query
        logger.info("multi_hop_started", query=query, max_hops=self.max_hops)

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
                    user_query=query,
                    retrieved_chunks=accumulated_chunks,
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
                        "multi_hop_missing_query_null",
                        hop=hop_num,
                        evaluation=evaluation.reasoning,
                    )
                    break

                hop_request = RetrieveRequest(
                    query=evaluation.missing_query,
                    context_key=context_key,
                    max_chunks=self.chunks_per_hop,
                    use_multi_hop=False,  # Prevent infinite recursion
                )

                hop_context, _, _ = self.base_retriever.retrieve(hop_request, query_id)

                # Deduplicate by chunk_id
                existing_ids = {c.chunk_id for c in accumulated_chunks}
                new_chunks = [
                    c for c in hop_context.document_chunks
                    if c.chunk_id not in existing_ids
                ]

                # Track hop number for new chunks
                for chunk in new_chunks:
                    chunk_hop_map[chunk.chunk_id] = hop_num

                accumulated_chunks.extend(new_chunks)

                logger.info(
                    "multi_hop_retrieval",
                    hop=hop_num,
                    query=evaluation.missing_query,
                    chunks_retrieved=len(hop_context.document_chunks),
                    new_unique_chunks=len(new_chunks),
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
        final_context = RAGContext.from_retrieval(
            query_id=query_id,
            chunks=accumulated_chunks,
        )

        logger.info(
            "multi_hop_finished",
            total_hops=len(hop_evaluations),
            total_chunks=len(accumulated_chunks),
            avg_relevance=final_context.avg_relevance,
        )

        return final_context, hop_evaluations, chunk_hop_map

    async def _evaluate_context(
        self,
        user_query: str,
        retrieved_chunks: List[DocumentChunk],
    ) -> HopEvaluation:
        """Evaluate if retrieved context is sufficient to answer query.

        Args:
            user_query: Original user question
            retrieved_chunks: Currently accumulated chunks

        Returns:
            HopEvaluation with can_answer flag and optional missing_query

        Raises:
            ValueError: If LLM returns invalid JSON
            TimeoutError: If evaluation exceeds timeout
        """
        # Format chunks for prompt
        chunks_text = self._format_chunks_for_prompt(retrieved_chunks)

        # Fill prompt template
        prompt = self.evaluation_prompt_template.format(
            user_query=user_query,
            retrieved_chunks=chunks_text,
        )

        # Call evaluation LLM with hop evaluation schema
        request = GenerationRequest(
            prompt=prompt,
            context=[],
            config=GenerationConfig(
                max_tokens=200,
                temperature=0.0,  # Deterministic
                timeout_seconds=self.evaluation_timeout,
                system_prompt="",  # Empty system prompt for hop evaluation
                structured_output_schema="hop_evaluation",  # Use hop evaluation schema
            ),
        )

        try:
            response = await asyncio.wait_for(
                self.evaluation_llm.generate(request),
                timeout=self.evaluation_timeout,
            )

            # Parse JSON response (already structured by LLM)
            response_text = response.answer_text.strip()
            logger.debug("hop_evaluation_response", response_length=len(response_text))

            # Parse the JSON
            try:
                data = json.loads(response_text)
                logger.debug("hop_evaluation_parsed", keys=list(data.keys()) if isinstance(data, dict) else "not_a_dict")
            except json.JSONDecodeError as e:
                logger.error(
                    "hop_evaluation_json_parse_error",
                    error=str(e),
                    response_preview=response_text[:200],
                )
                raise ValueError(f"Failed to parse hop evaluation JSON: {e}. Response: {response_text[:200]}")

            # Validate required fields
            if "can_answer" not in data or "reasoning" not in data:
                raise ValueError(f"Missing required fields in response: {data}")

            return HopEvaluation(
                can_answer=data["can_answer"],
                reasoning=data["reasoning"],
                missing_query=data.get("missing_query"),
            )

        except json.JSONDecodeError as e:
            logger.error(
                "hop_evaluation_json_parse_failed",
                error=str(e),
                response_text=response.answer_text[:1000],
            )
            raise ValueError(f"Invalid JSON from evaluation LLM: {e}")

        except asyncio.TimeoutError:
            logger.error("hop_evaluation_timeout", timeout=self.evaluation_timeout)
            raise TimeoutError(
                f"Hop evaluation exceeded {self.evaluation_timeout}s timeout"
            )

    def _format_chunks_for_prompt(self, chunks: List[DocumentChunk]) -> str:
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
            header = chunk.header or "Unknown Section"
            text = chunk.text[:300] + "..." if len(chunk.text) > 300 else chunk.text
            formatted_chunks.append(f"{i}. **{header}**\n{text}\n")

        return "\n".join(formatted_chunks)
