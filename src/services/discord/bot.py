"""Main bot orchestrator - coordinates all services (Orchestrator Pattern)."""

import json
import time

import discord

from src.lib.constants import LLM_GENERATION_TIMEOUT, RAG_MAX_HOPS
from src.lib.database import AnalyticsDatabase
from src.lib.discord_utils import get_random_acknowledgement
from src.lib.logging import get_logger
from src.models.structured_response import StructuredLLMResponse
from src.models.user_query import UserQuery
from src.services.discord import formatter
from src.services.discord.analytics_recorder import AnalyticsRecorder
from src.services.discord.context_manager import ConversationContextManager
from src.services.discord.error_message_builder import ErrorMessageBuilder
from src.services.discord.llm_provider_manager import LLMProviderManager
from src.services.discord.query_cost_calculator import QueryCostCalculator
from src.services.discord.response_builder import ResponseBuilder
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.quote_validator import QuoteValidator
from src.services.llm.rate_limiter import RateLimiter
from src.services.llm.retry import retry_on_content_filter
from src.services.llm.validator import ResponseValidator
from src.services.orchestrator import QueryOrchestrator
from src.services.rag.retriever import RAGRetriever

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
        feedback_logger=None,
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

        # Try to create default LLM provider for rate limiting
        try:
            self.llm = self.llm_factory.create()
        except KeyError:
            logger.warning(
                "No global LLM API key found in .env, will use per-server keys only. "
                "Rate limiting may not work correctly without a default provider."
            )
            self.llm = None

        self.validator = response_validator or ResponseValidator()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.context_manager = context_manager or ConversationContextManager()
        self.feedback_logger = feedback_logger

        # Initialize helper services
        self.analytics_db = analytics_db or AnalyticsDatabase.from_config()
        self.analytics_recorder = AnalyticsRecorder(self.analytics_db)
        self.llm_provider_manager = LLMProviderManager(self.llm_factory)
        self.quote_validator = QuoteValidator()
        self.cost_calculator = QueryCostCalculator()
        self.response_builder = ResponseBuilder()

        # Initialize shared orchestrator for RAG + LLM flow
        self.orchestrator = QueryOrchestrator(
            rag_retriever=rag_retriever,
            llm_factory=self.llm_factory,
            enable_quote_validation=True
        )

    async def process_query(self, message: discord.Message, user_query: UserQuery) -> None:
        """Process user query through full orchestration flow.

        Flow: rate limit → acknowledgement → RAG → LLM → validate → format → send → feedback

        Args:
            message: Discord message object
            user_query: Parsed user query
        """
        correlation_id = str(user_query.query_id)
        guild_id = str(message.guild.id) if message.guild else None

        logger.info(
            "Processing query",
            extra={
                "correlation_id": correlation_id,
                "query": user_query.sanitized_text[:100],
                "guild_id": guild_id,
            },
        )

        try:
            # Step 1: Create LLM provider for this guild
            llm, error_message = self.llm_provider_manager.create_provider(
                guild_id, correlation_id
            )
            if error_message:
                await message.channel.send(error_message)
                return

            # Step 2: Rate limiting check
            if not await self._check_rate_limit(message, user_query, llm.model):
                return

            # Step 3: Send acknowledgement
            await message.channel.send(get_random_acknowledgement())

            # Start timing for total latency (after acknowledgement)
            start_time = time.time()

            # Step 4: RAG retrieval
            rag_context, hop_evaluations, chunk_hop_map, embedding_cost, retrieval_latency_ms = await self._perform_rag_retrieval(user_query)

            # Step 5: LLM generation
            llm_response, chunk_ids = await self._perform_llm_generation(
                user_query, rag_context, llm
            )

            # Step 6: Parse and validate structured response
            structured_data = self._parse_structured_response(llm_response, correlation_id)

            # Step 7: Validate quotes against RAG context
            quote_validation_result = self._validate_quotes(
                structured_data, rag_context, chunk_ids, correlation_id
            )

            # Step 8: Validate response quality
            validation_result = self.validator.validate(llm_response, rag_context)
            if not validation_result.is_valid:
                self._log_validation_failure(validation_result, llm_response, rag_context, correlation_id)

            # Calculate total latency (end timing before Discord send)
            total_latency_ms = int((time.time() - start_time) * 1000)

            # Step 9: Build bot response
            bot_response = self.response_builder.build_response(
                user_query.query_id, llm_response, rag_context, structured_data, total_latency_ms
            )

            # Step 10: Send response to Discord
            await self._send_response(message, bot_response, validation_result, user_query)

            # Step 11: Calculate and log costs and latency breakdowns
            costs = self.cost_calculator.calculate_total_cost(
                user_query.sanitized_text, llm_response, hop_evaluations
            )
            latency_breakdown = QueryCostCalculator.calculate_latency_breakdown(
                retrieval_latency_ms, hop_evaluations, llm_response.latency_ms
            )
            self._log_costs(costs, correlation_id)

            # Step 12: Record analytics
            self.analytics_recorder.record_query(
                user_query.query_id,
                message,
                user_query.sanitized_text,
                llm_response,
                rag_context,
                validation_result,
                costs,
                latency_breakdown,
                hop_evaluations,
                chunk_hop_map,
                quote_validation_result,
            )

            # Step 13: Update conversation context
            self._update_conversation_context(user_query, llm_response)

            logger.info(
                "Query processed successfully",
                extra={
                    "correlation_id": correlation_id,
                    "confidence": llm_response.confidence_score,
                    "rag_score": rag_context.avg_relevance,
                    "latency_ms": total_latency_ms,
                    "llm_latency_ms": llm_response.latency_ms,
                },
            )

        except Exception as e:
            await self._handle_error(message, e, correlation_id)

    async def _check_rate_limit(
        self, message: discord.Message, user_query: UserQuery, model: str
    ) -> bool:
        """Check rate limit for user query.

        Returns:
            True if allowed, False if rate limited
        """
        is_allowed, retry_after = self.rate_limiter.check_rate_limit(
            provider=model, user_id=user_query.user_id
        )

        if not is_allowed:
            await message.channel.send(
                f"⏳ Rate limit reached. Please retry in {retry_after:.0f}s."
            )
            logger.warning(
                "Rate limit hit",
                extra={"correlation_id": str(user_query.query_id), "retry_after": retry_after},
            )
            return False

        return True

    async def _perform_rag_retrieval(self, user_query: UserQuery) -> tuple:
        """Perform RAG retrieval with optional multi-hop.

        Uses shared orchestrator for consistent RAG behavior.

        Returns:
            Tuple of (rag_context, hop_evaluations, chunk_hop_map, embedding_cost, retrieval_latency_ms)
        """
        rag_context, hop_evaluations, chunk_hop_map, embedding_cost, retrieval_latency_ms = await self.orchestrator.retrieve_rag(
            query=user_query.sanitized_text,
            query_id=user_query.query_id,
            context_key=user_query.conversation_context_id,
            use_multi_hop=(RAG_MAX_HOPS > 0),
        )

        return rag_context, hop_evaluations, chunk_hop_map, embedding_cost, retrieval_latency_ms

    async def _perform_llm_generation(self, user_query: UserQuery, rag_context, llm_provider) -> tuple:
        """Perform LLM generation with retry logic.

        Uses shared orchestrator with Discord-specific retry wrapper.

        Args:
            user_query: User query object
            rag_context: Pre-retrieved RAG context
            llm_provider: LLM provider instance (guild-specific)

        Returns:
            Tuple of (llm_response, chunk_ids)
        """
        # Wrap orchestrator call with Discord-specific retry logic
        async def generate_with_retry():
            return await self.orchestrator.generate_with_context(
                query=user_query.sanitized_text,
                query_id=user_query.query_id,
                model=llm_provider.model,
                rag_context=rag_context,
                llm_provider=llm_provider,
                generation_timeout=LLM_GENERATION_TIMEOUT,
            )

        llm_response, chunk_ids = await retry_on_content_filter(
            generate_with_retry,
            timeout_seconds=LLM_GENERATION_TIMEOUT,
        )

        return llm_response, chunk_ids

    def _parse_structured_response(self, llm_response, correlation_id: str):
        """Parse and validate structured JSON response.

        Returns:
            StructuredLLMResponse instance

        Raises:
            ValueError: If JSON is invalid
        """
        try:
            structured_data = StructuredLLMResponse.from_json(llm_response.answer_text)
            structured_data.validate()
            logger.debug(
                "Parsed structured LLM response",
                extra={
                    "correlation_id": correlation_id,
                    "quotes_count": len(structured_data.quotes),
                    "smalltalk": structured_data.smalltalk,
                },
            )
            return structured_data

        except (ValueError, json.JSONDecodeError) as e:
            logger.error(
                f"LLM returned invalid JSON (provider: {llm_response.model_version}): {e}",
                extra={
                    "correlation_id": correlation_id,
                    "response_preview": llm_response.answer_text[:200],
                },
            )
            raise ValueError(
                f"LLM provider {llm_response.model_version} returned invalid JSON. "
                "All providers must return structured JSON output."
            ) from e

    def _validate_quotes(self, structured_data, rag_context, chunk_ids, correlation_id: str):
        """Validate quotes against RAG context.

        Returns:
            QuoteValidationResult or None
        """
        if not structured_data or structured_data.smalltalk or not structured_data.quotes:
            return None

        quote_validation_result = self.quote_validator.validate(
            quotes=[
                {
                    "quote_title": q.quote_title,
                    "quote_text": q.quote_text,
                    "chunk_id": getattr(q, "chunk_id", ""),
                }
                for q in structured_data.quotes
            ],
            context_chunks=[chunk.text for chunk in rag_context.document_chunks],
            chunk_ids=chunk_ids,
        )

        logger.info(
            "Quote validation complete",
            extra={
                "correlation_id": correlation_id,
                "validation_score": quote_validation_result.validation_score,
                "valid_quotes": quote_validation_result.valid_quotes,
                "invalid_quotes": len(quote_validation_result.invalid_quotes),
            },
        )

        # Log invalid quotes
        if not quote_validation_result.is_valid:
            for invalid_quote in quote_validation_result.invalid_quotes:
                logger.warning(
                    "Invalid quote detected",
                    extra={
                        "correlation_id": correlation_id,
                        "quote_title": invalid_quote.get("quote_title", ""),
                        "quote_preview": invalid_quote.get("quote_text", "")[:100],
                        "reason": invalid_quote.get("reason", ""),
                    },
                )

        return quote_validation_result

    def _log_validation_failure(self, validation_result, llm_response, rag_context, correlation_id: str):
        """Log validation failure."""
        logger.warning(
            f"Validation failed: {validation_result.reason}",
            extra={
                "correlation_id": correlation_id,
                "llm_confidence": llm_response.confidence_score,
                "rag_score": rag_context.avg_relevance,
            },
        )

    async def _send_response(self, message, bot_response, validation_result, user_query):
        """Format and send response to Discord."""
        # Detect smalltalk
        smalltalk = (
            bot_response.structured_data.smalltalk
            if bot_response.structured_data
            else False
        )

        # Format response
        embeds = formatter.format_response(bot_response, validation_result, smalltalk=smalltalk)

        # Create feedback buttons
        feedback_view = None
        if self.feedback_logger:
            feedback_view = formatter.create_feedback_view(
                feedback_logger=self.feedback_logger,
                query_id=str(user_query.query_id),
                response_id=str(bot_response.response_id),
            )

        # Send to Discord
        await message.channel.send(embeds=embeds, view=feedback_view)

    def _log_costs(self, costs: dict, correlation_id: str):
        """Log cost breakdown."""
        logger.info(
            "Query cost breakdown",
            extra={
                "correlation_id": correlation_id,
                "initial_embedding_cost": f"${costs['initial_embedding_cost']:.6f}",
                "hop_embedding_cost": f"${costs['hop_embedding_cost']:.6f}",
                "hop_evaluation_cost": f"${costs['hop_evaluation_cost']:.6f}",
                "main_llm_cost": f"${costs['main_llm_cost']:.6f}",
                "total_cost": f"${costs['total_cost']:.6f}",
            },
        )

    def _update_conversation_context(self, user_query: UserQuery, llm_response):
        """Update conversation context with user query and bot response."""
        self.context_manager.add_message(
            user_query.conversation_context_id, role="user", text=user_query.sanitized_text
        )
        self.context_manager.add_message(
            user_query.conversation_context_id, role="bot", text=llm_response.answer_text
        )

    async def _handle_error(self, message, error: Exception, correlation_id: str):
        """Handle error and send user-friendly message."""
        error_message = ErrorMessageBuilder.build_error_message(error)

        logger.error(
            f"Error processing query: {error}",
            extra={
                "correlation_id": correlation_id,
                "error_type": type(error).__name__,
                "user_message": error_message,
            },
            exc_info=True,
        )

        await message.channel.send(error_message)
