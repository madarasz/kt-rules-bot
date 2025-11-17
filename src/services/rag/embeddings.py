"""Embedding service for generating vector embeddings.

Uses OpenAI text-embedding-3-small for document embedding.
Based on specs/001-we-are-building/contracts/rag-pipeline.md
"""

import openai
from openai import OpenAI

from src.lib.config import get_config
from src.lib.constants import EMBEDDING_MODEL
from src.lib.logging import get_logger
from src.lib.tokens import get_embedding_dimensions, get_embedding_token_limit

logger = get_logger(__name__)


class EmbeddingService:
    """Service for generating embeddings using OpenAI API."""

    def __init__(self, model: str = EMBEDDING_MODEL):
        """Initialize embedding service.

        Args:
            model: Embedding model name (default: text-embedding-3-small)
        """
        self.model = model
        self.dimensions = get_embedding_dimensions(model)  # Model dimensions
        self.max_tokens = get_embedding_token_limit(model)  # Model token limit

        # Initialize OpenAI client
        config = get_config()
        if not config.openai_api_key:
            raise ValueError("OpenAI API key is required for embedding service")

        self.client = OpenAI(api_key=config.openai_api_key)

        logger.info(
            "embedding_service_initialized",
            model=self.model,
            dimensions=self.dimensions,
            max_tokens=self.max_tokens,
        )

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector

        Raises:
            ValueError: If text is empty
            openai.OpenAIError: If API call fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            response = self.client.embeddings.create(model=self.model, input=text)

            embedding = response.data[0].embedding

            logger.debug(
                "embedding_generated", text_length=len(text), embedding_dimensions=len(embedding)
            )

            return embedding

        except openai.OpenAIError as e:
            logger.error("embedding_generation_failed", error=str(e), model=self.model)
            raise

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in a batch.

        More efficient than calling embed_text() multiple times.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            ValueError: If texts list is empty
            openai.OpenAIError: If API call fails
        """
        if not texts:
            raise ValueError("Texts list cannot be empty")

        # Filter out empty texts
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            raise ValueError("All texts are empty")

        try:
            response = self.client.embeddings.create(model=self.model, input=valid_texts)

            embeddings = [item.embedding for item in response.data]

            logger.info("batch_embeddings_generated", count=len(embeddings), model=self.model)

            return embeddings

        except openai.OpenAIError as e:
            logger.error(
                "batch_embedding_failed", error=str(e), model=self.model, text_count=len(texts)
            )
            raise

    def get_model_info(self) -> dict[str, object]:
        """Get information about the embedding model.

        Returns:
            Model information dictionary
        """
        return {
            "model": self.model,
            "dimensions": self.dimensions,
            "max_tokens": self.max_tokens,
            "provider": "openai",
        }
