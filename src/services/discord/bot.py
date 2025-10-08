"""Main bot orchestrator - coordinates all services (Orchestrator Pattern)."""

from datetime import date

import discord

from src.lib.constants import LLM_GENERATION_TIMEOUT
from src.lib.discord_utils import get_random_acknowledgement
from src.lib.logging import get_logger
from src.models.bot_response import BotResponse, Citation
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
    ):
        """Initialize orchestrator with all service dependencies.

        Args:
            rag_retriever: RAG retrieval service
            llm_provider_factory: LLM provider factory (creates provider)
            response_validator: Response validation service
            rate_limiter: Rate limiting service
            context_manager: Conversation context manager
        """
        self.rag = rag_retriever
        self.llm_factory = llm_provider_factory or LLMProviderFactory()
        self.llm = self.llm_factory.create()  # Get configured LLM provider
        self.validator = response_validator or ResponseValidator()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.context_manager = context_manager or ConversationContextManager()

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

            # Step 3: RAG retrieval
            rag_context = self.rag.retrieve(
                RetrieveRequest(
                    query=user_query.sanitized_text,
                    context_key=user_query.conversation_context_id,
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
                },
            )

            # Step 4: LLM generation with retry logic for ContentFilterError
            llm_response = await retry_on_content_filter(
                self.llm.generate,
                GenerationRequest(
                    prompt=user_query.sanitized_text,
                    context=[chunk.text for chunk in rag_context.document_chunks],
                    config=GenerationConfig(timeout_seconds=LLM_GENERATION_TIMEOUT),
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
                    quote=chunk.text[:200],
                    document_type=chunk.metadata.get("document_type", "core-rules"),
                    last_update_date=date.fromisoformat(chunk.metadata.get("last_update_date", "2024-01-15")),
                )
                for chunk in rag_context.document_chunks
            ]

            bot_response = BotResponse.create(
                query_id=user_query.query_id,
                answer_text=llm_response.answer_text,
                citations=citations,
                confidence_score=llm_response.confidence_score,
                rag_score=rag_context.avg_relevance,
                llm_model=llm_response.model_version,
                token_count=llm_response.token_count,
                latency_ms=llm_response.latency_ms,
            )

            # Step 7: Format response
            embeds = formatter.format_response(bot_response, validation_result)

            # Step 8: Send to Discord
            sent_message = await message.channel.send(embeds=embeds)

            # Step 9: Add feedback reaction buttons (👍👎)
            await formatter.add_feedback_reactions(sent_message)

            # Step 10: Update conversation context (message history only)
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
