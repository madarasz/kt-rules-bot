"""Analytics recording service for query processing."""

from datetime import UTC, datetime
from uuid import UUID

import discord

from src.lib.constants import RAG_HOP_EVALUATION_MODEL, RAG_MAX_HOPS
from src.lib.database import AnalyticsDatabase
from src.lib.logging import get_logger
from src.models.rag_context import RAGContext
from src.services.llm.base import LLMResponse
from src.services.llm.quote_validator import ValidationResult as QuoteValidationResult
from src.services.llm.validator import ValidationResult

logger = get_logger(__name__)


class AnalyticsRecorder:
    """Records query analytics to database."""

    def __init__(self, analytics_db: AnalyticsDatabase):
        """Initialize recorder with analytics database.

        Args:
            analytics_db: Analytics database instance
        """
        self.analytics_db = analytics_db

    def record_query(
        self,
        query_id: UUID,
        message: discord.Message,
        user_query_text: str,
        llm_response: LLMResponse,
        rag_context: RAGContext,
        validation_result: ValidationResult,
        total_cost: float,
        hop_evaluations: list | None = None,
        chunk_hop_map: dict | None = None,
        quote_validation_result: QuoteValidationResult | None = None,
    ) -> None:
        """Record query and associated data to analytics DB.

        Args:
            query_id: Unique query identifier
            message: Discord message object
            user_query_text: Sanitized user query
            llm_response: LLM response
            rag_context: RAG context with chunks
            validation_result: Validation result
            total_cost: Total cost in USD
            hop_evaluations: Optional hop evaluations
            chunk_hop_map: Optional chunk-to-hop mapping
            quote_validation_result: Optional quote validation result
        """
        if not self.analytics_db.enabled:
            return

        correlation_id = str(query_id)

        try:
            logger.info(
                "Storing query in analytics DB",
                extra={
                    "correlation_id": correlation_id,
                    "chunks_count": len(rag_context.document_chunks),
                },
            )

            # Insert query + response
            self.analytics_db.insert_query(
                {
                    "query_id": str(query_id),
                    "discord_server_id": str(message.guild.id) if message.guild else "DM",
                    "discord_server_name": message.guild.name
                    if message.guild
                    else "Direct Message",
                    "channel_id": str(message.channel.id),
                    "channel_name": message.channel.name
                    if hasattr(message.channel, "name")
                    else "DM",
                    "username": str(message.author.name),
                    "query_text": user_query_text,
                    "response_text": llm_response.answer_text,
                    "llm_model": llm_response.model_version,
                    "confidence_score": llm_response.confidence_score,
                    "rag_score": rag_context.avg_relevance,
                    "validation_passed": validation_result.is_valid,
                    "latency_ms": llm_response.latency_ms,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "multi_hop_enabled": 1 if RAG_MAX_HOPS > 0 else 0,
                    "hops_used": len(hop_evaluations or []),
                    "cost": total_cost,
                    "quote_validation_score": (
                        quote_validation_result.validation_score if quote_validation_result else None
                    ),
                    "quote_total_count": (
                        quote_validation_result.total_quotes if quote_validation_result else 0
                    ),
                    "quote_valid_count": (
                        quote_validation_result.valid_quotes if quote_validation_result else 0
                    ),
                    "quote_invalid_count": (
                        len(quote_validation_result.invalid_quotes)
                        if quote_validation_result
                        else 0
                    ),
                }
            )

            # Insert invalid quotes if any
            if quote_validation_result and quote_validation_result.invalid_quotes:
                self.analytics_db.insert_invalid_quotes(
                    str(query_id), quote_validation_result.invalid_quotes
                )
                logger.info(
                    f"Inserted {len(quote_validation_result.invalid_quotes)} invalid quotes",
                    extra={"correlation_id": correlation_id},
                )

            # Insert hop evaluations if multi-hop was used
            if hop_evaluations:
                evaluations_data = [e.to_dict() for e in hop_evaluations]
                self.analytics_db.insert_hop_evaluations(
                    query_id=str(query_id),
                    evaluations=evaluations_data,
                    evaluation_model=RAG_HOP_EVALUATION_MODEL,
                )
                logger.debug(
                    f"Inserted {len(hop_evaluations)} hop evaluations",
                    extra={"correlation_id": correlation_id},
                )

            # Insert retrieved chunks with hop numbers
            self._insert_chunks(query_id, rag_context, chunk_hop_map or {})

        except Exception as e:
            # Don't crash bot if DB write fails
            logger.error(
                f"Failed to write to analytics DB: {e}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )

    def _insert_chunks(
        self, query_id: UUID, rag_context: RAGContext, chunk_hop_map: dict
    ) -> None:
        """Insert retrieved chunks into analytics DB.

        Args:
            query_id: Query identifier
            rag_context: RAG context with chunks
            chunk_hop_map: Chunk ID to hop number mapping
        """
        chunks_data = [
            {
                "query_id": str(query_id),
                "rank": idx + 1,
                "chunk_header": chunk.header,
                "chunk_text": chunk.text[:500],
                "document_name": chunk.metadata.get("source", "Unknown"),
                "document_type": chunk.metadata.get("doc_type", "core-rules"),
                "vector_similarity": chunk.metadata.get("vector_similarity"),
                "bm25_score": chunk.metadata.get("bm25_score"),
                "rrf_score": chunk.metadata.get("rrf_score"),
                "final_score": chunk.relevance_score,
                "hop_number": chunk_hop_map.get(chunk.chunk_id, 0),
            }
            for idx, chunk in enumerate(rag_context.document_chunks)
        ]

        if chunks_data:
            logger.info(
                f"Inserting {len(chunks_data)} chunks into analytics DB",
                extra={"correlation_id": str(query_id)},
            )
            self.analytics_db.insert_chunks(str(query_id), chunks_data)
            logger.info("Chunks inserted successfully", extra={"correlation_id": str(query_id)})
        else:
            logger.warning(
                "No chunks to insert (rag_context.document_chunks is empty)",
                extra={"correlation_id": str(query_id)},
            )
