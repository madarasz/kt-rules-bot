"""CLI command to test RAG + LLM locally without Discord.

Usage:
    python -m src.cli.test_query "What actions can I take during movement?"
"""

import argparse
import sys
from datetime import datetime, timezone

from src.lib.config import get_config
from src.lib.constants import LLM_GENERATION_TIMEOUT, RAG_MAX_CHUNKS
from src.lib.logging import get_logger
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.validator import ResponseValidator
from src.services.rag.retriever import RAGRetriever, RetrieveRequest
from src.services.rag.vector_db import VectorDBService
from src.services.rag.embeddings import EmbeddingService
from src.services.llm.base import GenerationRequest, GenerationConfig
from src.services.llm.retry import retry_on_content_filter

logger = get_logger(__name__)


def test_query(query: str, model: str = None, max_chunks: int = RAG_MAX_CHUNKS, rag_only: bool = False) -> None:
    """Test RAG + LLM pipeline locally.

    Args:
        query: User question to test
        model: LLM model to use (claude-sonnet, gemini-2.5-pro, gpt-4o, etc.)
        max_chunks: Maximum chunks to retrieve
        rag_only: If True, stop after RAG retrieval (no LLM call)
    """
    config = get_config()
    print(f"\nQuery: {query}")
    if not rag_only:
        print(f"Model: {model or config.default_llm_provider}")
    else:
        print(f"Mode: RAG-only (no LLM generation)")
    print(f"{'='*60}\n")

    # Initialize services
    try:
        vector_db = VectorDBService(collection_name="kill_team_rules")
        embedding_service = EmbeddingService()
        rag_retriever = RAGRetriever(
            vector_db_service=vector_db,
            embedding_service=embedding_service,
        )

        # Only initialize LLM services if not rag_only
        if not rag_only:
            llm_factory = LLMProviderFactory()
            llm_provider = llm_factory.create(model)
            validator = ResponseValidator(
                llm_confidence_threshold=0.7,
                rag_score_threshold=0.45,  # Match retrieval threshold
            )

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        print(f"❌ Error initializing services: {e}")
        sys.exit(1)

    # Step 1: RAG Retrieval
    print("Step 1: RAG Retrieval")
    print("-" * 60)

    start_time = datetime.now(timezone.utc)

    try:
        from uuid import uuid4
        query_id = uuid4()

        rag_context = rag_retriever.retrieve(
            RetrieveRequest(
                query=query,
                context_key="cli:test",
                max_chunks=max_chunks,
                # Use default from RetrieveRequest (0.45)
            ),
            query_id=query_id,
        )

        rag_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        print(f"Retrieved {rag_context.total_chunks} chunks in {rag_time:.2f}s")
        print(f"Average relevance: {rag_context.avg_relevance:.2f}")
        print(f"Meets threshold: {rag_context.meets_threshold}")
        print()

        if rag_context.document_chunks:
            print("Chunks:")
            for i, chunk in enumerate(rag_context.document_chunks, 1):
                print(f"\n{i}. {chunk.header} (relevance: {chunk.relevance_score:.2f})")
                #print(f"   Source: {chunk.metadata.get('source', 'unknown')}")
                print(f"   Text: {chunk.text[:200]}...")

    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}", exc_info=True)
        print(f"❌ RAG retrieval failed: {e}")
        sys.exit(1)

    # If rag_only mode, stop here
    if rag_only:
        print(f"\n{'='*60}")
        print(f"RAG retrieval completed in {rag_time:.2f}s")
        print(f"{'='*60}\n")
        return

    # Step 2: LLM Generation
    print(f"\n{'='*60}")
    print("Step 2: LLM Generation")
    print("-" * 60)

    llm_start = datetime.now(timezone.utc)

    try:
        import asyncio

        # Wrap LLM generation with retry logic for ContentFilterError
        llm_response = asyncio.run(
            retry_on_content_filter(
                llm_provider.generate,
                GenerationRequest(
                    prompt=query,
                    context=[chunk.text for chunk in rag_context.document_chunks],
                    config=GenerationConfig(timeout_seconds=LLM_GENERATION_TIMEOUT),
                ),
                timeout_seconds=LLM_GENERATION_TIMEOUT
            )
        )

        llm_time = (datetime.now(timezone.utc) - llm_start).total_seconds()

        print(f"Generated response in {llm_time:.2f}s")
        print(f"Confidence: {llm_response.confidence_score:.2f}")
        print(f"Tokens: {llm_response.token_count}")
        print(f"Provider: {llm_response.provider}")
        print()

        print("Answer:")
        print("-" * 60)
        print(llm_response.answer_text)

    except Exception as e:
        logger.error(f"LLM generation failed: {e}", exc_info=True)
        print(f"❌ LLM generation failed: {e}")
        sys.exit(1)

    # Step 3: Validation
    print(f"\n{'='*60}")
    print("Step 3: Validation")
    print("-" * 60)

    try:
        validation_result = validator.validate(llm_response, rag_context)

        print(f"Valid: {validation_result.is_valid}")
        print(f"LLM Confidence: {validation_result.llm_confidence:.2f}")
        print(f"RAG Score: {validation_result.rag_score:.2f}")
        print(f"Reason: {validation_result.reason}")

    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        print(f"❌ Validation failed: {e}")
        sys.exit(1)

    # Summary
    total_time = (datetime.now(timezone.utc) - start_time).total_seconds()
    print(f"\n{'='*60}")
    print(f"Total time: {total_time:.2f}s")
    print(f"  RAG: {rag_time:.2f}s")
    print(f"  LLM: {llm_time:.2f}s")
    print(f"{'='*60}\n")


def main():
    """Main entry point for test_query CLI."""
    parser = argparse.ArgumentParser(
        description="Test RAG + LLM pipeline locally without Discord"
    )
    parser.add_argument("query", help="Question to ask")
    parser.add_argument(
        "--model",
        "-m",
        choices=[
            "claude-sonnet",
            "claude-opus",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gpt-5",
            "gpt-5-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4o",
        ],
        help="LLM model to use (default: from config)",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=RAG_MAX_CHUNKS,
        help=f"Maximum chunks to retrieve (default: {RAG_MAX_CHUNKS})",
    )
    parser.add_argument(
        "--rag-only",
        action="store_true",
        help="Stop after RAG retrieval, do not call LLM",
    )

    args = parser.parse_args()

    try:
        test_query(args.query, model=args.model, max_chunks=args.max_chunks, rag_only=args.rag_only)
    except Exception as e:
        logger.error(f"Test query failed: {e}", exc_info=True)
        print(f"❌ Test query failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
