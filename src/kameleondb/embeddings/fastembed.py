"""FastEmbed provider for local embeddings (no API key required)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kameleondb.embeddings.provider import EmbeddingProvider

if TYPE_CHECKING:
    from fastembed import TextEmbedding


class FastEmbedProvider(EmbeddingProvider):
    """Local embedding provider using fastembed (ONNX).

    Uses BAAI/bge-small-en-v1.5 by default (384 dimensions).
    No API key required - runs entirely locally.

    Example:
        >>> provider = FastEmbedProvider()
        >>> embedding = provider.embed("Hello world")
        >>> len(embedding)
        384
    """

    # Default model - small, fast, good quality
    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

    # Model dimensions mapping
    MODEL_DIMENSIONS = {
        "BAAI/bge-small-en-v1.5": 384,
        "BAAI/bge-base-en-v1.5": 768,
        "sentence-transformers/all-MiniLM-L6-v2": 384,
    }

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Initialize FastEmbed provider.

        Args:
            model: Model name. Defaults to BAAI/bge-small-en-v1.5.
        """
        try:
            from fastembed import TextEmbedding
        except ImportError as e:
            raise ImportError(
                "fastembed is required for local embeddings. "
                "Install it with: pip install kameleondb[embeddings]"
            ) from e

        self._model_name = model
        self._model: TextEmbedding = TextEmbedding(model_name=model)
        self._dimensions = self.MODEL_DIMENSIONS.get(model, 384)

    def embed(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: Text to embed.

        Returns:
            Vector embedding as list of floats.
        """
        # fastembed returns a generator, take first result
        embeddings = list(self._model.embed([text]))
        return embeddings[0].tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts efficiently.

        Args:
            texts: List of texts to embed.

        Returns:
            List of vector embeddings.
        """
        if not texts:
            return []
        embeddings = list(self._model.embed(texts))
        return [emb.tolist() for emb in embeddings]

    @property
    def dimensions(self) -> int:
        """Vector dimensions."""
        return self._dimensions

    @property
    def model_name(self) -> str:
        """Model identifier for storage."""
        return self._model_name
