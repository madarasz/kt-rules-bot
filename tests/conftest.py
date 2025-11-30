"""Shared pytest fixtures for all tests."""

import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.models.rag_context import DocumentChunk, RAGContext
from src.services.llm.base import LLMProvider, LLMResponse
from src.services.llm.factory import LLMProviderFactory
from src.services.rag.retriever import RAGRetriever


@pytest.fixture
def sample_chunks():
    """Sample document chunks for testing."""
    return [
        DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="Silent\nSilent allows shooting with the weapon while the operative has a Conceal order.",
            header="Silent",
            header_level=2,
            metadata={
                "source": "weapon-rules.md",
                "doc_type": "core-rules",
                "publication_date": "2024-01-01",
                "section": "weapon rules",
            },
            relevance_score=0.9,
            position_in_doc=1,
        ),
        DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="COUNTERACT\nIf all your operatives are expended but your opponent has ready operatives, you can counteract.",
            header="COUNTERACT",
            header_level=2,
            metadata={
                "source": "core-rules.md",
                "doc_type": "core-rules",
                "publication_date": "2024-01-01",
                "section": "phases",
            },
            relevance_score=0.85,
            position_in_doc=2,
        ),
    ]


@pytest.fixture
def sample_rag_context(sample_chunks):
    """Sample RAG context with chunks."""
    return RAGContext.from_retrieval(query_id=uuid4(), chunks=sample_chunks)


@pytest.fixture
def sample_structured_response():
    """Valid structured LLM response JSON."""
    return {
        "smalltalk": False,
        "short_answer": "Yes, with a Silent weapon.",
        "persona_short_answer": "Absolutely.",
        "quotes": [
            {
                "quote_title": "Silent",
                "quote_text": "Silent allows shooting with the weapon while the operative has a Conceal order.",
            }
        ],
        "explanation": "The Silent weapon rule specifically allows shooting while on a Conceal order.",
        "persona_afterword": "Simple rule.",
    }


@pytest.fixture
def mock_llm_response(sample_structured_response):
    """Mock LLM response with structured JSON."""
    return LLMResponse(
        response_id=uuid4(),
        answer_text=json.dumps(sample_structured_response),
        confidence_score=0.88,
        token_count=125,
        latency_ms=1850,
        provider="test",
        model_version="test-model",
        citations_included=True,
        prompt_tokens=100,
        completion_tokens=25,
    )


@pytest.fixture
def mock_llm_provider(mock_llm_response):
    """Mock LLM provider returning structured JSON."""
    provider = AsyncMock(spec=LLMProvider)
    provider.model = "test-model"

    async def mock_generate(_request):
        return mock_llm_response

    provider.generate = AsyncMock(side_effect=mock_generate)
    return provider


@pytest.fixture
def mock_llm_factory(mock_llm_provider):
    """Mock LLM provider factory."""
    factory = Mock(spec=LLMProviderFactory)
    factory.create = Mock(return_value=mock_llm_provider)
    return factory


@pytest.fixture
def mock_rag_retriever(sample_chunks):
    """Mock RAG retriever with sample chunks."""
    retriever = Mock(spec=RAGRetriever)

    def mock_retrieve(_request, query_id):
        rag_context = RAGContext.from_retrieval(query_id, sample_chunks)
        return rag_context, [], {}

    retriever.retrieve = Mock(side_effect=mock_retrieve)
    return retriever


@pytest.fixture
def mock_rag_retriever_multihop(sample_chunks):
    """Mock RAG retriever with multi-hop support."""
    retriever = Mock(spec=RAGRetriever)

    # Create additional chunks for hop 1
    hop_chunks = [
        DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="Additional context from hop 1",
            header="Hop Context",
            header_level=2,
            metadata={"source": "additional.md", "doc_type": "core-rules"},
            relevance_score=0.75,
            position_in_doc=3,
        )
    ]

    # Combine initial and hop chunks
    all_chunks = sample_chunks + hop_chunks
    rag_context = RAGContext.from_retrieval(uuid4(), all_chunks)

    # Create mock hop evaluation
    class MockHopEvaluation:
        def __init__(self):
            self.can_answer = False
            self.reasoning = "Need more context about conceal order"
            self.missing_query = "What is conceal order?"
            self.cost_usd = 0.0001
            self.retrieval_time_s = 0.5
            self.evaluation_time_s = 0.3

    hop_evaluations = [MockHopEvaluation()]

    # Chunk hop map: first 2 chunks from hop 0, third from hop 1
    chunk_hop_map = {
        sample_chunks[0].chunk_id: 0,
        sample_chunks[1].chunk_id: 0,
        hop_chunks[0].chunk_id: 1,
    }

    retriever.retrieve = Mock(return_value=(rag_context, hop_evaluations, chunk_hop_map))
    return retriever
