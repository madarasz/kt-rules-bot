"""Main bot orchestrator - coordinates all services (Orchestrator Pattern)."""

from datetime import date
import json

import discord

from src.lib.constants import (
    LLM_GENERATION_TIMEOUT,
    RAG_MAX_HOPS,
    RAG_HOP_EVALUATION_MODEL,
)
from src.lib.database import AnalyticsDatabase
from src.lib.discord_utils import get_random_acknowledgement
from src.lib.logging import get_logger
from src.models.bot_response import BotResponse, Citation
from src.models.structured_response import StructuredLLMResponse
from src.models.user_query import UserQuery
from src.services.discord import formatter
from src.services.discord.context_manager import ConversationContextManager
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.rate_limiter import RateLimiter
from src.services.llm.validator import ResponseValidator
from src.services.rag.retriever import RAGRetriever, RetrieveRequest
from src.services.llm.base import GenerationRequest, GenerationConfig
from src.services.llm.retry import retry_on_content_filter

logger = get_logger(__name__)


class KillTeamBotOrchestrator:
    """Orchestrator Pattern - coordinates all services for query processing."""

    def __init__(
        self,
        rag_retriever: RAGRetriever,
        llm_provider_factory: LLMProviderFactory = None,
        response_validator: ResponseValidator = None,
        rate_limiter: RateLimiter = None,
        context_manager: ConversationContextManager = None,
        analytics_db: AnalyticsDatabase = None,
        feedback_logger = None,
    ):
        """Initialize orchestrator with all service dependencies.

        Args:
            rag_retriever: RAG retrieval service
            llm_provider_factory: LLM provider factory (creates provider)
            response_validator: Response validation service
            rate_limiter: Rate limiting service
            context_manager: Conversation context manager
            analytics_db: Analytics database (optional, disabled by default)
            feedback_logger: Feedback logger for reaction tracking
        """
        self.rag = rag_retriever
        self.llm_factory = llm_provider_factory or LLMProviderFactory()
        self.llm = self.llm_factory.create()  # Get configured LLM provider
        self.validator = response_validator or ResponseValidator()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.context_manager = context_manager or ConversationContextManager()
        self.analytics_db = analytics_db or AnalyticsDatabase.from_config()
        self.feedback_logger = feedback_logger

    async def process_query(
        self,
        message: discord.Message,
        user_query: UserQuery,
    ) -> None:
        """Process user query through full orchestration flow.

        Flow: rate limit → acknowledgement → RAG → LLM → validate → format → send → feedback buttons

        Args:
            message: Discord message object
            user_query: Parsed user query
        """
        correlation_id = str(user_query.query_id)
        logger.info(
            "Processing query",
            extra={
                "correlation_id": correlation_id,
                "query": user_query.sanitized_text[:100],  # Truncate for logs
            },
        )

        try:
            # Step 1: Rate limiting check
            is_allowed, retry_after = self.rate_limiter.check_rate_limit(
                provider=self.llm.model,
                user_id=user_query.user_id,
            )

            if not is_allowed:
                await message.channel.send(
                    f"⏳ Rate limit reached. Please retry in {retry_after:.0f}s."
                )
                logger.warning(
                    "Rate limit hit",
                    extra={"correlation_id": correlation_id, "retry_after": retry_after},
                )
                return

            # Step 2: Send acknowledgement/please-wait message
            acknowledgement = get_random_acknowledgement()
            await message.channel.send(acknowledgement)

            # Step 3: RAG retrieval (with optional multi-hop)
            rag_context, hop_evaluations, chunk_hop_map = self.rag.retrieve(
                RetrieveRequest(
                    query=user_query.sanitized_text,
                    context_key=user_query.conversation_context_id,
                    use_multi_hop=(RAG_MAX_HOPS > 0),
                    # Uses RAG_MAX_CHUNKS and RAG_MIN_RELEVANCE from constants
                ),
                query_id=user_query.query_id,
            )

            logger.debug(
                "RAG retrieval complete",
                extra={
                    "correlation_id": correlation_id,
                    "chunks_retrieved": rag_context.total_chunks,
                    "avg_relevance": rag_context.avg_relevance,
                    "hops_used": len(hop_evaluations),
                },
            )

            # Step 4: LLM generation with retry logic for ContentFilterError
            llm_response = await retry_on_content_filter(
                self.llm.generate,
                GenerationRequest(
                    prompt=user_query.sanitized_text,
                    context=[chunk.text for chunk in rag_context.document_chunks],
                    config=GenerationConfig(
                        timeout_seconds=LLM_GENERATION_TIMEOUT
                    ),
                ),
                timeout_seconds=LLM_GENERATION_TIMEOUT
            )

            logger.debug(
                "LLM generation complete",
                extra={
                    "correlation_id": correlation_id,
                    "confidence": llm_response.confidence_score,
                    "token_count": llm_response.token_count,
                },
            )

            # Parse structured JSON response (mandatory - no fallback)
            try:
                structured_data = StructuredLLMResponse.from_json(llm_response.answer_text)
                structured_data.validate()
                logger.debug(
                    "Parsed structured LLM response",
                    extra={
                        "correlation_id": correlation_id,
                        "quotes_count": len(structured_data.quotes),
                        "smalltalk": structured_data.smalltalk,
                    }
                )
            except (ValueError, json.JSONDecodeError) as e:
                logger.error(
                    f"LLM returned invalid JSON (provider: {llm_response.model_version}): {e}",
                    extra={
                        "correlation_id": correlation_id,
                        "response_preview": llm_response.answer_text[:200]
                    }
                )
                raise ValueError(
                    f"LLM provider {llm_response.model_version} returned invalid JSON. "
                    "All providers must return structured JSON output."
                )

            # Step 5: Validation (FR-013: combined LLM + RAG validation)
            validation_result = self.validator.validate(llm_response, rag_context)

            if not validation_result.is_valid:
                # Send fallback message
                fallback_msg = formatter.format_fallback_message(validation_result.reason)
                #await message.channel.send(fallback_msg)

                logger.warning(
                    f"Validation failed: {validation_result.reason}",
                    extra={
                        "correlation_id": correlation_id,
                        "llm_confidence": llm_response.confidence_score,
                        "rag_score": rag_context.avg_relevance,
                    },
                )
                #return

            # Step 6: Convert LLMResponse + RAGContext to BotResponse
            citations = [
                Citation(
                    document_name=chunk.metadata.get("source", "Unknown"),
                    section=chunk.header or "General",
                    quote=chunk.text,
                    document_type=chunk.metadata.get("document_type", "core-rules"),
                    last_update_date=date.fromisoformat(chunk.metadata.get("last_update_date", "2024-01-15")),
                )
                for chunk in rag_context.document_chunks
            ]

            # Determine if smalltalk
            smalltalk = False
            if structured_data and structured_data.smalltalk:
                # Use smalltalk flag from structured JSON
                smalltalk = True
                citations = []
                logger.debug(
                    "Detected smalltalk from structured data",
                    extra={"correlation_id": correlation_id}
                )
            elif llm_response.answer_text.startswith("[SMALLTALK]"):
                # Fallback: detect [SMALLTALK] tag in markdown responses
                llm_response.answer_text = llm_response.answer_text.replace("[SMALLTALK]", "").strip()
                citations = []
                smalltalk = True
                logger.debug(
                    "Detected smalltalk from [SMALLTALK] tag",
                    extra={"correlation_id": correlation_id}
                )

            bot_response = BotResponse.create(
                query_id=user_query.query_id,
                answer_text=llm_response.answer_text,
                citations=citations,
                confidence_score=llm_response.confidence_score,
                rag_score=rag_context.avg_relevance,
                llm_model=llm_response.model_version,
                token_count=llm_response.token_count,
                latency_ms=llm_response.latency_ms,
                structured_data=structured_data,
            )

            # Step 7: Format response
            embeds = formatter.format_response(bot_response, validation_result, smalltalk=smalltalk)

            # Step 8: Send to Discord
            sent_message = await message.channel.send(embeds=embeds)

            # Step 9: Register response for feedback tracking
            if self.feedback_logger:
                self.feedback_logger.register_response(
                    str(user_query.query_id),
                    str(bot_response.response_id)
                )

            # Step 9b: Add feedback reaction buttons (👍👎)
            await formatter.add_feedback_reactions(sent_message)

            # Step 10: Store in analytics DB (if enabled)
            if self.analytics_db.enabled:
                try:
                    from datetime import datetime, timezone

                    logger.info(
                        "Storing query in analytics DB",
                        extra={"correlation_id": correlation_id, "chunks_count": len(rag_context.document_chunks)}
                    )

                    # Insert query + response
                    self.analytics_db.insert_query({
                        "query_id": str(user_query.query_id),
                        "discord_server_id": str(message.guild.id) if message.guild else "DM",
                        "discord_server_name": message.guild.name if message.guild else "Direct Message",
                        "channel_id": str(message.channel.id),
                        "channel_name": message.channel.name if hasattr(message.channel, 'name') else "DM",
                        "username": str(message.author.name),
                        "query_text": user_query.sanitized_text,
                        "response_text": llm_response.answer_text,
                        "llm_model": llm_response.model_version,
                        "confidence_score": llm_response.confidence_score,
                        "rag_score": rag_context.avg_relevance,
                        "validation_passed": validation_result.is_valid,
                        "latency_ms": llm_response.latency_ms,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "multi_hop_enabled": 1 if RAG_MAX_HOPS > 0 else 0,
                        "hops_used": len(hop_evaluations),
                    })

                    # Insert hop evaluations if multi-hop was used
                    if hop_evaluations:
                        evaluations_data = [e.to_dict() for e in hop_evaluations]
                        self.analytics_db.insert_hop_evaluations(
                            query_id=str(user_query.query_id),
                            evaluations=evaluations_data,
                            evaluation_model=RAG_HOP_EVALUATION_MODEL,
                        )
                        logger.debug(
                            f"Inserted {len(hop_evaluations)} hop evaluations",
                            extra={"correlation_id": correlation_id}
                        )

                    # Insert retrieved chunks with hop numbers
                    chunks_data = [
                        {
                            "query_id": str(user_query.query_id),
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
                            extra={"correlation_id": correlation_id}
                        )
                        self.analytics_db.insert_chunks(str(user_query.query_id), chunks_data)
                        logger.info(
                            "Chunks inserted successfully",
                            extra={"correlation_id": correlation_id}
                        )
                    else:
                        logger.warning(
                            "No chunks to insert (rag_context.document_chunks is empty)",
                            extra={"correlation_id": correlation_id}
                        )

                except Exception as e:
                    # Don't crash bot if DB write fails
                    logger.error(
                        f"Failed to write to analytics DB: {e}",
                        extra={"correlation_id": correlation_id},
                        exc_info=True
                    )

            # Step 11: Update conversation context (message history only)
            self.context_manager.add_message(
                user_query.conversation_context_id,
                role="user",
                text=user_query.sanitized_text,
            )
            self.context_manager.add_message(
                user_query.conversation_context_id,
                role="bot",
                text=llm_response.answer_text,
            )

            logger.info(
                "Query processed successfully",
                extra={
                    "correlation_id": correlation_id,
                    "confidence": llm_response.confidence_score,
                    "rag_score": rag_context.avg_relevance,
                    "latency_ms": llm_response.latency_ms,
                    "validation_passed": True,
                },
            )

        except Exception as e:
            logger.error(
                f"Error processing query: {e}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            await message.channel.send(
                "❌ An error occurred while processing your request. "
                "Please try again in a moment."
            )
