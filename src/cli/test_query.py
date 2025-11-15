"""CLI command to test RAG + LLM locally without Discord.

Usage:
    python -m src.cli.test_query "What actions can I take during movement?"
"""

import argparse
import sys
import json
from datetime import datetime, timezone

from src.lib.config import get_config
from src.lib.constants import (
    LLM_GENERATION_TIMEOUT,
    RAG_MAX_CHUNKS,
    ALL_LLM_PROVIDERS,
    RAG_MAX_HOPS,
)
from src.lib.logging import get_logger
from src.services.llm.factory import LLMProviderFactory
from src.services.llm.validator import ResponseValidator
from src.services.rag.retriever import RAGRetriever, RetrieveRequest
from src.services.rag.vector_db import VectorDBService
from src.services.rag.embeddings import EmbeddingService
from src.services.llm.base import GenerationRequest, GenerationConfig
from src.services.llm.retry import retry_on_content_filter

logger = get_logger(__name__)


def test_query(
    query: str,
    model: str = None,
    max_chunks: int = RAG_MAX_CHUNKS,
    rag_only: bool = False,
    max_hops: int = None,
) -> None:
    """Test RAG + LLM pipeline locally.

    Args:
        query: User question to test
        model: LLM model to use (claude-4.5-sonnet, gemini-2.5-pro, gpt-4o, etc.)
        max_chunks: Maximum chunks to retrieve
        rag_only: If True, stop after RAG retrieval (no LLM call)
        max_hops: Override RAG_MAX_HOPS constant (None = use constant)
    """
    # Override RAG_MAX_HOPS if specified
    if max_hops is not None:
        import src.lib.constants as constants
        constants.RAG_MAX_HOPS = max_hops
        print(f"Overriding RAG_MAX_HOPS to {max_hops}")
        current_max_hops = max_hops
    else:
        current_max_hops = RAG_MAX_HOPS

    config = get_config()

    # Determine model to use
    selected_model = model or config.default_llm_provider
    use_file_search = "-file-search" in selected_model

    print(f"\nQuery: {query}")
    if not rag_only:
        print(f"Model: {selected_model}")
        if use_file_search:
            print(f"Mode: File Search (RAG disabled)")
    else:
        print(f"Mode: RAG-only (no LLM generation)")
    print(f"{'='*60}\n")

    if not use_file_search:
        print(f"Multi-hop: {'enabled' if current_max_hops > 0 else 'disabled'} (max_hops={current_max_hops})")

    # Initialize services (after constant override)
    try:
        # Only initialize RAG services if NOT using file-search model
        if not use_file_search:
            vector_db = VectorDBService(collection_name="kill_team_rules")
            embedding_service = EmbeddingService()
            rag_retriever = RAGRetriever(
                vector_db_service=vector_db,
                embedding_service=embedding_service,
                enable_multi_hop=(current_max_hops > 0),  # Explicitly set based on override
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

    # Step 1: RAG Retrieval (skip for file-search models)
    start_time = datetime.now(timezone.utc)

    if use_file_search:
        # File search mode: create empty RAG context
        print("Step 1: File Search Mode - Skipping RAG")
        print("-" * 60)
        print("Using Gemini File Search tool instead of traditional RAG\n")

        from src.models.rag_context import RAGContext
        from uuid import uuid4, UUID
        rag_context = RAGContext(
            context_id=UUID('00000000-0000-0000-0000-000000000000'),
            query_id=uuid4(),
            document_chunks=[],
            relevance_scores=[],
            total_chunks=0,
            avg_relevance=1.0,  # Not applicable
            meets_threshold=True,
        )
        hop_evaluations = []
        chunk_hop_map = {}
        rag_time = 0.0
    else:
        # Traditional RAG mode
        print("Step 1: RAG Retrieval")
        print("-" * 60)

        try:
            from uuid import uuid4
            query_id = uuid4()

            rag_context, hop_evaluations, chunk_hop_map = rag_retriever.retrieve(
                RetrieveRequest(
                    query=query,
                    context_key="cli:test",
                    max_chunks=max_chunks,
                    use_multi_hop=(current_max_hops > 0),
                    # Use default from RetrieveRequest (0.45)
                ),
                query_id=query_id,
            )

            rag_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            print(f"Retrieved {rag_context.total_chunks} chunks in {rag_time:.2f}s")
            print(f"Average relevance: {rag_context.avg_relevance:.2f}")
            print(f"Meets threshold: {rag_context.meets_threshold}")
            if hop_evaluations:
                print(f"Hops used: {len(hop_evaluations)}")
            print()

            # Display hop information if multi-hop was used
            if hop_evaluations:
                print(f"\n{'='*60}")
                print(f"MULTI-HOP INFORMATION ({len(hop_evaluations)} hops)")
                print(f"{'='*60}")

                for i, hop_eval in enumerate(hop_evaluations, 1):
                    print(f"\n--- Hop {i} ---")
                    print(f"Can Answer: {'✅ Yes' if hop_eval.can_answer else '❌ No'}")
                    print(f"Reasoning: {hop_eval.reasoning}")
                    if hop_eval.missing_query:
                        print(f"Missing Query: \"{hop_eval.missing_query}\"")

                print(f"\n{'='*60}")
                print(f"CHUNKS BY HOP")
                print(f"{'='*60}")

                chunks_by_hop = {}
                for chunk in rag_context.document_chunks:
                    hop_num = chunk_hop_map.get(chunk.chunk_id, 0)
                    if hop_num not in chunks_by_hop:
                        chunks_by_hop[hop_num] = []
                    chunks_by_hop[hop_num].append(chunk)

                for hop_num in sorted(chunks_by_hop.keys()):
                    hop_label = "Initial (Hop 0)" if hop_num == 0 else f"Hop {hop_num}"
                    chunks = chunks_by_hop[hop_num]
                    print(f"\n{hop_label}: {len(chunks)} chunks")
                    for chunk in chunks:
                        print(f"  - {chunk.header} (score: {chunk.relevance_score:.3f})")
                print()

            if rag_context.document_chunks:
                print("All Chunks:")
                for i, chunk in enumerate(rag_context.document_chunks, 1):
                    hop_num = chunk_hop_map.get(chunk.chunk_id, 0) if hop_evaluations else 0
                    hop_label = f" [Hop {hop_num}]" if hop_evaluations else ""
                    print(f"\n{i}. {chunk.header}{hop_label} (relevance: {chunk.relevance_score:.2f})")
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
                    config=GenerationConfig(
                        timeout_seconds=LLM_GENERATION_TIMEOUT
                    ),
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
        try:
            parsed_json = json.loads(llm_response.answer_text)
            print(json.dumps(parsed_json, indent=2))
        except (json.JSONDecodeError, TypeError):
            # Not JSON or can't parse, print as-is
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
        choices=ALL_LLM_PROVIDERS,
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
    parser.add_argument(
        "--max-hops",
        type=int,
        default=None,
        help=f"Override RAG_MAX_HOPS constant (default: {RAG_MAX_HOPS})",
    )

    args = parser.parse_args()

    try:
        test_query(
            args.query,
            model=args.model,
            max_chunks=args.max_chunks,
            rag_only=args.rag_only,
            max_hops=args.max_hops,
        )
    except Exception as e:
        logger.error(f"Test query failed: {e}", exc_info=True)
        print(f"❌ Test query failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
