"""Response building service for Discord bot."""

from datetime import date
from uuid import UUID

from src.lib.logging import get_logger
from src.models.bot_response import BotResponse, Citation
from src.models.rag_context import RAGContext
from src.models.structured_response import StructuredLLMResponse
from src.services.llm.base import LLMResponse

logger = get_logger(__name__)


class ResponseBuilder:
    """Builds bot responses from LLM and RAG outputs."""

    @staticmethod
    def build_response(
        query_id: UUID,
        llm_response: LLMResponse,
        rag_context: RAGContext,
        structured_data: StructuredLLMResponse | None = None,
        total_latency_ms: int | None = None,
    ) -> BotResponse:
        """Build bot response from LLM and RAG outputs.

        Args:
            query_id: Query identifier
            llm_response: LLM response
            rag_context: RAG context with chunks
            structured_data: Optional structured response data
            total_latency_ms: Total processing latency (RAG + hops + LLM + validation).
                            If None, uses LLM-only latency from llm_response.

        Returns:
            BotResponse instance
        """
        correlation_id = str(query_id)

        # Build citations from RAG chunks
        citations = ResponseBuilder._build_citations(rag_context)

        # Determine if smalltalk
        smalltalk = ResponseBuilder._detect_smalltalk(
            llm_response, structured_data, correlation_id
        )

        # Clear citations for smalltalk
        if smalltalk:
            citations = []

        # Use total latency if provided, otherwise use LLM-only latency
        latency_ms = total_latency_ms if total_latency_ms is not None else llm_response.latency_ms

        return BotResponse.create(
            query_id=query_id,
            answer_text=llm_response.answer_text,
            citations=citations,
            confidence_score=llm_response.confidence_score,
            rag_score=rag_context.avg_relevance,
            llm_model=llm_response.model_version,
            token_count=llm_response.token_count,
            latency_ms=latency_ms,
            structured_data=structured_data,
        )

    @staticmethod
    def _build_citations(rag_context: RAGContext) -> list[Citation]:
        """Build citations from RAG chunks.

        Args:
            rag_context: RAG context with document chunks

        Returns:
            List of Citation objects
        """
        citations = []
        for chunk in rag_context.document_chunks:
            citation = Citation(
                document_name=chunk.metadata.get("source", "Unknown"),
                section=chunk.header or "General",
                quote=chunk.text,
                document_type=chunk.metadata.get("document_type", "core-rules"),
                last_update_date=date.fromisoformat(
                    chunk.metadata.get("last_update_date", "2024-01-15")
                ),
            )
            citations.append(citation)

        return citations

    @staticmethod
    def _detect_smalltalk(
        llm_response: LLMResponse, structured_data: StructuredLLMResponse | None, correlation_id: str
    ) -> bool:
        """Detect if response is smalltalk.

        Args:
            llm_response: LLM response
            structured_data: Optional structured response data
            correlation_id: Correlation ID for logging

        Returns:
            True if smalltalk detected
        """
        # Check structured data first
        if structured_data and structured_data.smalltalk:
            logger.debug(
                "Detected smalltalk from structured data",
                extra={"correlation_id": correlation_id},
            )
            return True

        # Fallback: detect [SMALLTALK] tag in markdown responses
        if llm_response.answer_text.startswith("[SMALLTALK]"):
            # Strip the tag for display
            llm_response.answer_text = llm_response.answer_text.replace(
                "[SMALLTALK]", ""
            ).strip()
            logger.debug(
                "Detected smalltalk from [SMALLTALK] tag",
                extra={"correlation_id": correlation_id},
            )
            return True

        return False
