"""Hybrid search for KameleonDB.

Combines BM25 (keyword) and vector (semantic) search for best-of-both-worlds
search capabilities.

Example:
    >>> from kameleondb import KameleonDB
    >>>
    >>> # Enable embeddings (uses fastembed by default)
    >>> db = KameleonDB("sqlite:///app.db", embeddings=True)
    >>>
    >>> # Create entity with embed_fields
    >>> db.create_entity(
    ...     "Article",
    ...     fields=[
    ...         {"name": "title", "type": "string"},
    ...         {"name": "body", "type": "text"},
    ...     ],
    ...     embed_fields=["title", "body"],
    ... )
    >>>
    >>> # Search
    >>> results = db.search("shipping complaint", limit=10)
"""

from kameleondb.search.engine import IndexStatus, SearchEngine, SearchResult

__all__ = [
    "SearchEngine",
    "SearchResult",
    "IndexStatus",
]
