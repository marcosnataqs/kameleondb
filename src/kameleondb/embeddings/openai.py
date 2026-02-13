"""OpenAI embedding provider."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from kameleondb.embeddings.provider import EmbeddingProvider

if TYPE_CHECKING:
    from openai import OpenAI


class OpenAIProvider(EmbeddingProvider):
    """OpenAI API embedding provider.

    Uses text-embedding-3-small by default with 384 dimensions
    to match the local fastembed model for seamless dev→prod transition.

    Example:
        >>> provider = OpenAIProvider()  # Uses OPENAI_API_KEY env var
        >>> embedding = provider.embed("Hello world")
        >>> len(embedding)
        384
    """

    DEFAULT_MODEL = "text-embedding-3-small"
    DEFAULT_DIMENSIONS = 384  # Match fastembed for dev→prod compatibility

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        dimensions: int = DEFAULT_DIMENSIONS,
        api_key: str | None = None,
    ) -> None:
        """Initialize OpenAI provider.

        Args:
            model: Model name. Defaults to text-embedding-3-small.
            dimensions: Vector dimensions. Defaults to 384.
            api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.
        """
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "openai is required for OpenAI embeddings. "
                "Install it with: pip install kameleondb[embeddings-openai]"
            ) from e

        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self._client: OpenAI = OpenAI(api_key=api_key)
        self._model = model
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: Text to embed.

        Returns:
            Vector embedding as list of floats.
        """
        response = self._client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self._dimensions,
        )
        embedding: list[float] = response.data[0].embedding
        return embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts efficiently.

        Args:
            texts: List of texts to embed.

        Returns:
            List of vector embeddings.
        """
        if not texts:
            return []

        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )
        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    @property
    def dimensions(self) -> int:
        """Vector dimensions."""
        return self._dimensions

    @property
    def model_name(self) -> str:
        """Model identifier for storage."""
        return self._model
