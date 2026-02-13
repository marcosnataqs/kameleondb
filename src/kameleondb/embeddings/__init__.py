"""Embedding providers for semantic search.

This module provides embedding providers for KameleonDB's hybrid search.
By default, uses FastEmbed (local, no API key required).

Example:
    >>> from kameleondb.embeddings import FastEmbedProvider, OpenAIProvider
    >>>
    >>> # Local embeddings (default)
    >>> provider = FastEmbedProvider()
    >>> embedding = provider.embed("Hello world")
    >>>
    >>> # OpenAI embeddings
    >>> provider = OpenAIProvider(api_key="sk-...")
    >>> embedding = provider.embed("Hello world")
"""

from kameleondb.embeddings.provider import EmbeddingProvider, EmbeddingResult

__all__ = [
    "EmbeddingProvider",
    "EmbeddingResult",
    "get_provider",
]


def get_provider(
    provider: str | EmbeddingProvider = "fastembed",
    **kwargs: object,
) -> EmbeddingProvider:
    """Get an embedding provider by name or return the provider if already instantiated.

    Args:
        provider: Provider name ("fastembed", "openai") or EmbeddingProvider instance.
        **kwargs: Additional arguments passed to the provider constructor.

    Returns:
        EmbeddingProvider instance.

    Raises:
        ValueError: If provider name is unknown.
        ImportError: If required dependencies are not installed.

    Example:
        >>> provider = get_provider("fastembed")
        >>> provider = get_provider("openai", api_key="sk-...")
        >>> provider = get_provider(MyCustomProvider())
    """
    if isinstance(provider, EmbeddingProvider):
        return provider

    if provider == "fastembed":
        from kameleondb.embeddings.fastembed import FastEmbedProvider

        return FastEmbedProvider(**kwargs)  # type: ignore[arg-type]
    elif provider == "openai":
        from kameleondb.embeddings.openai import OpenAIProvider

        return OpenAIProvider(**kwargs)  # type: ignore[arg-type]
    else:
        raise ValueError(
            f"Unknown embedding provider: {provider}. Available: 'fastembed', 'openai'"
        )
