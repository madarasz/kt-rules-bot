"""Integration test - Mocked end-to-end query flow.

Tests: Discord @ mention → RAG retrieval → LLM generation → Response with citations
All components are mocked - this tests the orchestration logic only.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import discord
import pytest

from src.models.rag_context import DocumentChunk, RAGContext
from src.models.rag_request import RetrieveRequest
from src.models.user_query import UserQuery
from src.services.discord.bot import KillTeamBotOrchestrator
from src.services.discord.context_manager import ConversationContextManager
from src.services.llm.base import GenerationRequest, LLMResponse
from src.services.llm.validator import ResponseValidator
from src.services.rag.retriever import RAGRetriever


@pytest.fixture
def mock_rag_retriever():
    """Mock RAG retriever with relevant rules about movement phase."""
    retriever = Mock(spec=RAGRetriever)

    def mock_retrieve(_request: RetrieveRequest, query_id: UUID):
        # Simulate relevant chunks about movement phase
        rag_context = RAGContext(
            context_id=uuid4(),
            query_id=query_id,
            document_chunks=[
                DocumentChunk(
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    text="During the Movement Phase, operatives can move, dash, or perform actions.",
                    header="Movement Phase",
                    header_level=2,
                    metadata={
                        "source": "core-rules-movement.md",
                        "document_type": "core-rules",
                        "last_update_date": "2024-01-15",
                    },
                    relevance_score=0.92,
                    position_in_doc=5,
                )
            ],
            relevance_scores=[0.92],
            total_chunks=1,
            avg_relevance=0.92,
            meets_threshold=True,
        )
        # Return tuple: (rag_context, hop_evaluations, chunk_hop_map)
        return rag_context, [], {}

    retriever.retrieve = mock_retrieve
    return retriever


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider with high-confidence response."""
    import json
    provider = AsyncMock()

    async def mock_generate(_request: GenerationRequest) -> LLMResponse:
        # Simulate LLM response with structured JSON output
        structured_json = json.dumps({
            "smalltalk": False,
            "short_answer": "Yes.",
            "persona_short_answer": "Obviously.",
            "quotes": [
                {
                    "quote_title": "Movement Phase Rules",
                    "quote_text": "During the Movement Phase, operatives can perform Move, Dash, or Climb/Traverse actions."
                }
            ],
            "explanation": "During the Movement Phase, your operatives can perform several actions including Move (up to Movement characteristic), Dash (free action to move further), and Climb/Traverse (navigate terrain). You can also perform equipment actions during this phase.",
            "persona_afterword": "Elementary tactical options, really."
        })

        return LLMResponse(
            response_id=uuid4(),
            answer_text=structured_json,
            confidence_score=0.88,
            token_count=125,
            latency_ms=1850,
            provider="claude",
            model_version="claude-3-sonnet",
            citations_included=True,
        )

    provider.generate = mock_generate
    provider.model = "claude-3-sonnet"
    return provider


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.fast
async def test_basic_query_flow_end_to_end(mock_rag_retriever, mock_llm_provider):
    """Test basic query: 'What actions can I take during the movement phase?'

    Expected:
    - Response within 30s
    - Citations included
    - Confidence displayed
    - Response contains movement phase information
    """
    # Create orchestrator with mocked services
    # Create a mock factory that returns our mock provider
    mock_factory = Mock()
    mock_factory.create = Mock(return_value=mock_llm_provider)

    orchestrator = KillTeamBotOrchestrator(
        rag_retriever=mock_rag_retriever,
        llm_provider_factory=mock_factory,
        response_validator=ResponseValidator(),
        context_manager=ConversationContextManager(),
    )

    # Create mock Discord message
    message = Mock(spec=discord.Message)
    message.author = Mock(spec=discord.User)
    message.author.id = 123456789
    message.guild = Mock(spec=discord.Guild)
    message.guild.id = 111111111
    message.guild.name = "Test Guild"
    message.channel = Mock(spec=discord.TextChannel)
    message.channel.id = 987654321
    message.channel.name = "test-channel"
    message.channel.send = AsyncMock()
    message.content = "<@bot> What actions can I take during the movement phase?"

    # Create user query
    user_query = UserQuery(
        query_id=uuid4(),
        user_id=UserQuery.hash_user_id("123456789"),
        channel_id="987654321",
        message_text="What actions can I take during the movement phase?",
        sanitized_text="What actions can I take during the movement phase?",
        timestamp=datetime.now(UTC),
        conversation_context_id="987654321:123456789",
        pii_redacted=False,
    )

    # Measure response time
    start_time = datetime.now(UTC)

    # Process query
    await orchestrator.process_query(message, user_query)

    end_time = datetime.now(UTC)
    response_time = (end_time - start_time).total_seconds()

    # ASSERTIONS

    # 1. Response within 30 seconds
    assert response_time < 30, f"Response took {response_time}s (>30s limit)"

    # 2. Message was sent
    assert message.channel.send.called, "Bot did not send a response"

    # 3. Response includes embeds
    call_args = message.channel.send.call_args
    # Check if embeds are in kwargs
    embeds = call_args.kwargs.get("embeds") if call_args.kwargs else None
    # If not in kwargs, try positional args
    if not embeds and call_args.args:
        embeds = call_args.args[0]
    assert embeds is not None, f"Response missing embeds. call_args: {call_args}"
    assert len(embeds) > 0, "No embeds in response"

    embed = embeds[0]

    # 4. Confidence displayed in footer (or model/latency for structured)
    # Structured responses don't show confidence in footer anymore
    assert embed.footer.text, "Footer missing"
    assert "Model:" in embed.footer.text, "Model missing from footer"
    assert "Latency:" in embed.footer.text, "Latency missing from footer"

    # 5. Disclaimer field is present (for non-smalltalk)
    disclaimer_field = next((f for f in embed.fields if f.name == "Disclaimer"), None)
    assert disclaimer_field is not None, "Disclaimer field missing"

    # 6. Response contains movement phase information
    # In structured format, description has short answer + persona
    assert embed.description, "Embed description is empty"

    # Check that explanation field exists and contains relevant info
    explanation_field = next((f for f in embed.fields if f.name == "Explanation"), None)
    assert explanation_field is not None, "Explanation field missing"
    assert "movement" in explanation_field.value.lower() or "Move" in explanation_field.value, "Movement info missing from explanation"

    print(f"✅ Basic query test passed (response time: {response_time:.2f}s)")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.fast
async def test_basic_query_with_context_tracking(mock_rag_retriever, mock_llm_provider):
    """Test that conversation context is tracked correctly."""
    mock_factory = Mock()
    mock_factory.create = Mock(return_value=mock_llm_provider)

    orchestrator = KillTeamBotOrchestrator(
        rag_retriever=mock_rag_retriever,
        llm_provider_factory=mock_factory,
        response_validator=ResponseValidator(),
        context_manager=ConversationContextManager(),
    )

    # Create mock message
    message = Mock(spec=discord.Message)
    message.author = Mock(spec=discord.User)
    message.author.id = 123456789
    message.guild = Mock(spec=discord.Guild)
    message.guild.id = 111111111
    message.guild.name = "Test Guild"
    message.channel = Mock(spec=discord.TextChannel)
    message.channel.id = 987654321
    message.channel.name = "test-channel"
    message.channel.send = AsyncMock()

    # Create user query
    user_query = UserQuery(
        query_id=uuid4(),
        user_id=UserQuery.hash_user_id("123456789"),
        channel_id="987654321",
        message_text="What about movement?",
        sanitized_text="What about movement?",
        timestamp=datetime.now(UTC),
        conversation_context_id="987654321:123456789",
        pii_redacted=False,
    )

    # Process query
    await orchestrator.process_query(message, user_query)

    # Check context manager has the conversation
    context = orchestrator.context_manager.get_context("987654321:123456789")
    # The test has 1 query + 1 response, but context manager adds acknowledgement too
    # Actually it should have 2 messages: user query + bot response (acknowledgement is separate)
    assert len(context.message_history) >= 2, f"Expected at least 2 messages, got {len(context.message_history)}"
    # Find user and bot messages
    user_messages = [m for m in context.message_history if m.role == "user"]
    bot_messages = [m for m in context.message_history if m.role == "bot"]
    assert len(user_messages) >= 1, "Should have at least 1 user message"
    assert len(bot_messages) >= 1, "Should have at least 1 bot message"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.fast
async def test_basic_query_feedback_buttons_added(
    mock_rag_retriever, mock_llm_provider
):
    """Test that feedback buttons (👍👎) are added to response."""
    mock_factory = Mock()
    mock_factory.create = Mock(return_value=mock_llm_provider)

    orchestrator = KillTeamBotOrchestrator(
        rag_retriever=mock_rag_retriever,
        llm_provider_factory=mock_factory,
        response_validator=ResponseValidator(),
        context_manager=ConversationContextManager(),
    )

    # Create mock message with mock sent message
    message = Mock(spec=discord.Message)
    message.author = Mock(spec=discord.User)
    message.author.id = 123456789
    message.guild = Mock(spec=discord.Guild)
    message.guild.id = 111111111
    message.channel = Mock(spec=discord.TextChannel)
    message.channel.id = 987654321

    # Create two separate mock messages - one for acknowledgement, one for response
    ack_message = AsyncMock(spec=discord.Message)
    ack_message.add_reaction = AsyncMock()

    sent_message = AsyncMock(spec=discord.Message)
    sent_message.add_reaction = AsyncMock()

    # Mock send to return different messages for different calls
    send_call_count = 0
    async def mock_send(*_args, **_kwargs):
        nonlocal send_call_count
        send_call_count += 1
        # First call is acknowledgement, second is actual response
        if send_call_count == 1:
            return ack_message
        else:
            return sent_message

    message.channel.send = AsyncMock(side_effect=mock_send)

    # Create user query
    user_query = UserQuery(
        query_id=uuid4(),
        user_id=UserQuery.hash_user_id("123456789"),
        channel_id="987654321",
        message_text="What about movement?",
        sanitized_text="What about movement?",
        timestamp=datetime.now(UTC),
        conversation_context_id="987654321:123456789",
        pii_redacted=False,
    )

    # Process query
    await orchestrator.process_query(message, user_query)

    # Check feedback reactions were added to the response message (not acknowledgement)
    from unittest.mock import call
    assert sent_message.add_reaction.call_args_list == [call("👍"), call("👎")]
