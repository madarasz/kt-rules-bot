"""Factory for creating service instances.

Centralizes service initialization to reduce code duplication
and improve testability.
"""

from typing import Optional

from src.lib.config import get_config
from src.lib.logging import get_logger
from src.services.llm.factory import LLMProviderFactory
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.retriever import RAGRetriever
from src.services.rag.vector_db import VectorDBService

logger = get_logger(__name__)


class ServiceFactory:
    """Factory for creating commonly-used service instances.

    Follows the Factory Pattern and Dependency Injection principles.
    Reduces code duplication across CLI commands.
    """

    @staticmethod
    def create_vector_db(collection_name: str = "kill_team_rules") -> VectorDBService:
        """Create vector database service.

        Args:
            collection_name: ChromaDB collection name

        Returns:
            Configured VectorDBService instance
        """
        logger.debug(f"Creating VectorDBService with collection: {collection_name}")
        return VectorDBService(collection_name=collection_name)

    @staticmethod
    def create_embedding_service() -> EmbeddingService:
        """Create embedding service.

        Returns:
            Configured EmbeddingService instance
        """
        logger.debug("Creating EmbeddingService")
        return EmbeddingService()

    @staticmethod
    def create_rag_retriever(
        enable_multi_hop: bool = True,
        collection_name: str = "kill_team_rules"
    ) -> RAGRetriever:
        """Create RAG retriever with dependencies.

        Args:
            enable_multi_hop: Whether to enable multi-hop retrieval
            collection_name: Vector DB collection name

        Returns:
            Configured RAGRetriever instance
        """
        logger.debug(f"Creating RAGRetriever (multi_hop={enable_multi_hop})")

        vector_db = ServiceFactory.create_vector_db(collection_name)
        embedding_service = ServiceFactory.create_embedding_service()

        return RAGRetriever(
            vector_db_service=vector_db,
            embedding_service=embedding_service,
            enable_multi_hop=enable_multi_hop,
        )

    @staticmethod
    def create_llm_provider(model: Optional[str] = None):
        """Create LLM provider.

        Args:
            model: Model name (if None, uses default from config)

        Returns:
            LLM provider instance

        Raises:
            ValueError: If model is not supported or API key not configured
        """
        config = get_config()
        model_name = model or config.default_llm_provider

        logger.debug(f"Creating LLM provider: {model_name}")

        provider = LLMProviderFactory.create(model_name)

        if provider is None:
            raise ValueError(
                f"Failed to create LLM provider for {model_name}. "
                "Check that API key is configured in .env file."
            )

        return provider

    @staticmethod
    def validate_services() -> bool:
        """Validate that all required services can be initialized.

        Returns:
            True if all services can be initialized, False otherwise
        """
        try:
            # Test vector DB
            vector_db = ServiceFactory.create_vector_db()

            # Test embedding service
            embedding_service = ServiceFactory.create_embedding_service()

            # Test LLM factory (don't create provider, just check factory)
            config = get_config()
            if not config.default_llm_provider:
                logger.error("No default LLM provider configured")
                return False

            logger.info("All services validated successfully")
            return True

        except Exception as e:
            logger.error(f"Service validation failed: {e}")
            return False
