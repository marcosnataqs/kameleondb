"""Embedding provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    """Result of embedding operation."""

    text: str
    embedding: list[float]
    model: str
    dimensions: int


class EmbeddingProvider(ABC):
    """Interface for embedding providers.

    All providers must implement this interface to be used with KameleonDB's
    semantic search functionality.
    """

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: Text to embed.

        Returns:
            Vector embedding as list of floats.
        """
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts efficiently.

        Args:
            texts: List of texts to embed.

        Returns:
            List of vector embeddings.
        """
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimensions."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier for storage."""
        ...

    def embed_with_metadata(self, text: str) -> EmbeddingResult:
        """Embed text and return with metadata.

        Args:
            text: Text to embed.

        Returns:
            EmbeddingResult with text, embedding, model, and dimensions.
        """
        return EmbeddingResult(
            text=text,
            embedding=self.embed(text),
            model=self.model_name,
            dimensions=self.dimensions,
        )
