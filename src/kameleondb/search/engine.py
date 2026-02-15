"""Hybrid search engine for KameleonDB.

Combines BM25 (keyword) and vector (semantic) search using Reciprocal Rank Fusion.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from kameleondb.embeddings.provider import EmbeddingProvider


@dataclass
class SearchResult:
    """Result from hybrid search."""

    entity: str
    id: str
    score: float
    data: dict[str, Any]
    matched_text: str


@dataclass
class IndexStatus:
    """Status of search index for an entity."""

    entity: str
    indexed: int
    pending: int
    last_updated: datetime | None


class SearchEngine:
    """Hybrid search engine combining BM25 and vector search.

    Uses Reciprocal Rank Fusion (RRF) to combine results from both
    keyword (BM25) and semantic (vector) search.
    """

    # RRF constant (standard value used by Elasticsearch, etc.)
    RRF_K = 60

    def __init__(
        self,
        engine: Engine,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        """Initialize search engine.

        Args:
            engine: SQLAlchemy engine
            embedding_provider: Provider for generating embeddings.
                If None, vector search is disabled (BM25 only).
        """
        self._engine = engine
        self._provider = embedding_provider
        self._is_postgresql = engine.dialect.name == "postgresql"

        # Initialize search tables
        self._ensure_search_tables()

    def _ensure_search_tables(self) -> None:
        """Create search tables if they don't exist."""
        with Session(self._engine) as session:
            if self._is_postgresql:
                self._create_postgresql_tables(session)
            else:
                self._create_sqlite_tables(session)
            session.commit()

    def _create_postgresql_tables(self, session: Session) -> None:
        """Create PostgreSQL search tables with pgvector and tsvector."""
        # Check if pgvector extension exists
        has_pgvector = False
        try:
            session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            has_pgvector = True
        except Exception:
            pass  # pgvector not available, will use BM25 only

        dimensions = self._provider.dimensions if self._provider else 384

        # Main search table
        session.execute(
            text(f"""
            CREATE TABLE IF NOT EXISTS kdb_search (
                id VARCHAR(36) PRIMARY KEY,
                entity_name VARCHAR(255) NOT NULL,
                record_id VARCHAR(36) NOT NULL,
                content TEXT NOT NULL,
                {"embedding vector(" + str(dimensions) + ")," if has_pgvector else ""}
                model VARCHAR(100),
                dimensions INTEGER,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE,
                UNIQUE(entity_name, record_id)
            )
        """)
        )

        # Indexes
        session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_kdb_search_entity ON kdb_search(entity_name)")
        )
        session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_kdb_search_record ON kdb_search(record_id)")
        )

        # tsvector for FTS (generated column)
        try:
            session.execute(
                text("""
                ALTER TABLE kdb_search
                ADD COLUMN IF NOT EXISTS tsv tsvector
                GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
            """)
            )
            session.execute(
                text("CREATE INDEX IF NOT EXISTS ix_kdb_search_fts ON kdb_search USING gin(tsv)")
            )
        except Exception:
            pass  # Already exists or not supported

        # Vector index (HNSW for fast approximate search)
        if has_pgvector:
            with contextlib.suppress(Exception):
                session.execute(
                    text("""
                    CREATE INDEX IF NOT EXISTS ix_kdb_search_vector
                    ON kdb_search USING hnsw (embedding vector_cosine_ops)
                """)
                )

    def _create_sqlite_tables(self, session: Session) -> None:
        """Create SQLite search tables with FTS5 and sqlite-vec."""
        # Main search table (for metadata)
        session.execute(
            text("""
            CREATE TABLE IF NOT EXISTS kdb_search (
                id TEXT PRIMARY KEY,
                entity_name TEXT NOT NULL,
                record_id TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                model TEXT,
                dimensions INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT,
                UNIQUE(entity_name, record_id)
            )
        """)
        )

        # Indexes
        session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_kdb_search_entity ON kdb_search(entity_name)")
        )
        session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_kdb_search_record ON kdb_search(record_id)")
        )

        # FTS5 virtual table for BM25 search
        with contextlib.suppress(Exception):
            session.execute(
                text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS kdb_search_fts USING fts5(
                    id UNINDEXED,
                    entity_name,
                    record_id UNINDEXED,
                    content,
                    tokenize='porter unicode61'
                )
            """)
            )

    def index_record(
        self,
        entity_name: str,
        record_id: str,
        content: str,
    ) -> None:
        """Index a single record for search.

        Args:
            entity_name: Entity name
            record_id: Record ID
            content: Text content to index (pre-formatted from embed_fields)
        """
        # Generate embedding if provider is available
        embedding = None
        model = None
        dimensions = None

        if self._provider:
            embedding = self._provider.embed(content)
            model = self._provider.model_name
            dimensions = self._provider.dimensions

        with Session(self._engine) as session:
            if self._is_postgresql:
                self._index_postgresql(
                    session, entity_name, record_id, content, embedding, model, dimensions
                )
            else:
                self._index_sqlite(
                    session, entity_name, record_id, content, embedding, model, dimensions
                )
            session.commit()

    def _index_postgresql(
        self,
        session: Session,
        entity_name: str,
        record_id: str,
        content: str,
        embedding: list[float] | None,
        model: str | None,
        dimensions: int | None,
    ) -> None:
        """Index record in PostgreSQL."""
        from uuid import uuid4

        # Upsert into kdb_search
        if embedding:
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
            session.execute(
                text("""
                INSERT INTO kdb_search (id, entity_name, record_id, content, embedding, model, dimensions)
                VALUES (:id, :entity_name, :record_id, :content, :embedding::vector, :model, :dimensions)
                ON CONFLICT (entity_name, record_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    model = EXCLUDED.model,
                    dimensions = EXCLUDED.dimensions,
                    updated_at = NOW()
            """),
                {
                    "id": str(uuid4()),
                    "entity_name": entity_name,
                    "record_id": record_id,
                    "content": content,
                    "embedding": embedding_str,
                    "model": model,
                    "dimensions": dimensions,
                },
            )
        else:
            session.execute(
                text("""
                INSERT INTO kdb_search (id, entity_name, record_id, content, model, dimensions)
                VALUES (:id, :entity_name, :record_id, :content, :model, :dimensions)
                ON CONFLICT (entity_name, record_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    updated_at = NOW()
            """),
                {
                    "id": str(uuid4()),
                    "entity_name": entity_name,
                    "record_id": record_id,
                    "content": content,
                    "model": model,
                    "dimensions": dimensions,
                },
            )

    def _index_sqlite(
        self,
        session: Session,
        entity_name: str,
        record_id: str,
        content: str,
        embedding: list[float] | None,
        model: str | None,
        dimensions: int | None,
    ) -> None:
        """Index record in SQLite."""
        import json
        from uuid import uuid4

        search_id = str(uuid4())
        embedding_blob = json.dumps(embedding) if embedding else None

        # Check if exists
        existing = session.execute(
            text("SELECT id FROM kdb_search WHERE entity_name = :entity AND record_id = :record"),
            {"entity": entity_name, "record": record_id},
        ).fetchone()

        if existing:
            # Update
            session.execute(
                text("""
                UPDATE kdb_search SET
                    content = :content,
                    embedding = :embedding,
                    model = :model,
                    dimensions = :dimensions,
                    updated_at = datetime('now')
                WHERE entity_name = :entity_name AND record_id = :record_id
            """),
                {
                    "content": content,
                    "embedding": embedding_blob,
                    "model": model,
                    "dimensions": dimensions,
                    "entity_name": entity_name,
                    "record_id": record_id,
                },
            )
            # Update FTS
            session.execute(
                text(
                    "DELETE FROM kdb_search_fts WHERE entity_name = :entity AND record_id = :record"
                ),
                {"entity": entity_name, "record": record_id},
            )
        else:
            # Insert
            session.execute(
                text("""
                INSERT INTO kdb_search (id, entity_name, record_id, content, embedding, model, dimensions)
                VALUES (:id, :entity_name, :record_id, :content, :embedding, :model, :dimensions)
            """),
                {
                    "id": search_id,
                    "entity_name": entity_name,
                    "record_id": record_id,
                    "content": content,
                    "embedding": embedding_blob,
                    "model": model,
                    "dimensions": dimensions,
                },
            )

        # Insert into FTS
        session.execute(
            text("""
            INSERT INTO kdb_search_fts (id, entity_name, record_id, content)
            VALUES (:id, :entity_name, :record_id, :content)
        """),
            {
                "id": existing[0] if existing else search_id,
                "entity_name": entity_name,
                "record_id": record_id,
                "content": content,
            },
        )

    def delete_record(self, entity_name: str, record_id: str) -> None:
        """Remove a record from the search index.

        Args:
            entity_name: Entity name
            record_id: Record ID
        """
        with Session(self._engine) as session:
            session.execute(
                text("DELETE FROM kdb_search WHERE entity_name = :entity AND record_id = :record"),
                {"entity": entity_name, "record": record_id},
            )
            if not self._is_postgresql:
                session.execute(
                    text(
                        "DELETE FROM kdb_search_fts WHERE entity_name = :entity AND record_id = :record"
                    ),
                    {"entity": entity_name, "record": record_id},
                )
            session.commit()

    def search(
        self,
        query: str,
        entity: str | None = None,
        entities: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Perform hybrid search with optional structured filters.

        Combines BM25 (keyword) and vector (semantic) search using RRF.

        Args:
            query: Search query text
            entity: Single entity to search (optional)
            entities: List of entities to search (optional)
            limit: Maximum results to return
            min_score: Minimum score threshold
            where: Structured filters to apply (e.g., {"status": "open", "priority": "high"})

        Returns:
            List of SearchResult objects sorted by relevance
        """
        # Fetch more results if filtering, to ensure we have enough after filter
        fetch_limit = limit * 4 if where else limit * 2

        # Get BM25 results
        bm25_results = self._bm25_search(query, entity, entities, fetch_limit)

        # Get vector results (if provider available)
        vector_results: list[tuple[str, str, str, float]] = []
        if self._provider:
            vector_results = self._vector_search(query, entity, entities, fetch_limit)

        # Combine with RRF
        results = self._reciprocal_rank_fusion(bm25_results, vector_results, fetch_limit, min_score)

        # Apply structured filters if provided
        if where:
            results = self._apply_where_filters(results, where)

        # Apply final limit
        return results[:limit]

    def _apply_where_filters(
        self,
        results: list[SearchResult],
        where: dict[str, Any],
    ) -> list[SearchResult]:
        """Apply structured filters to search results.

        Filters results where data fields match the where conditions.
        Supports exact match only (no operators yet).

        Args:
            results: Search results to filter
            where: Dict of field -> value conditions (AND logic)

        Returns:
            Filtered results
        """
        filtered = []
        for result in results:
            data = result.data
            # Parse data if it's a JSON string
            if isinstance(data, str):
                import json

                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    continue

            # Check all conditions (AND logic)
            match = True
            for field, expected in where.items():
                if field not in data or data[field] != expected:
                    match = False
                    break

            if match:
                filtered.append(result)

        return filtered

    def _bm25_search(
        self,
        query: str,
        entity: str | None,
        entities: list[str] | None,
        limit: int,
    ) -> list[tuple[str, str, str, float]]:
        """BM25 keyword search.

        Returns:
            List of (record_id, entity_name, content, score) tuples
        """
        with Session(self._engine) as session:
            if self._is_postgresql:
                return self._bm25_postgresql(session, query, entity, entities, limit)
            else:
                return self._bm25_sqlite(session, query, entity, entities, limit)

    def _bm25_postgresql(
        self,
        session: Session,
        query: str,
        entity: str | None,
        entities: list[str] | None,
        limit: int,
    ) -> list[tuple[str, str, str, float]]:
        """PostgreSQL BM25 search using tsvector."""
        where_clause = ""
        params: dict[str, Any] = {"query": query, "limit": limit}

        if entity:
            where_clause = "AND entity_name = :entity"
            params["entity"] = entity
        elif entities:
            placeholders = ", ".join(f":e{i}" for i in range(len(entities)))
            where_clause = f"AND entity_name IN ({placeholders})"
            for i, e in enumerate(entities):
                params[f"e{i}"] = e

        result = session.execute(
            text(f"""
            SELECT record_id, entity_name, content, ts_rank(tsv, query) AS score
            FROM kdb_search, plainto_tsquery('english', :query) query
            WHERE tsv @@ query {where_clause}
            ORDER BY score DESC
            LIMIT :limit
        """),
            params,
        )
        return [(row[0], row[1], row[2], float(row[3])) for row in result.fetchall()]

    def _bm25_sqlite(
        self,
        session: Session,
        query: str,
        entity: str | None,
        entities: list[str] | None,
        limit: int,
    ) -> list[tuple[str, str, str, float]]:
        """SQLite BM25 search using FTS5."""
        where_clause = ""
        params: dict[str, Any] = {"query": query, "limit": limit}

        if entity:
            where_clause = "AND entity_name = :entity"
            params["entity"] = entity
        elif entities:
            placeholders = ", ".join(f":e{i}" for i in range(len(entities)))
            where_clause = f"AND entity_name IN ({placeholders})"
            for i, e in enumerate(entities):
                params[f"e{i}"] = e

        result = session.execute(
            text(f"""
            SELECT record_id, entity_name, content, bm25(kdb_search_fts) AS score
            FROM kdb_search_fts
            WHERE kdb_search_fts MATCH :query {where_clause}
            ORDER BY score
            LIMIT :limit
        """),
            params,
        )
        # SQLite bm25() returns negative values (lower is better), convert to positive
        return [(row[0], row[1], row[2], -float(row[3])) for row in result.fetchall()]

    def _vector_search(
        self,
        query: str,
        entity: str | None,
        entities: list[str] | None,
        limit: int,
    ) -> list[tuple[str, str, str, float]]:
        """Vector similarity search.

        Returns:
            List of (record_id, entity_name, content, score) tuples
        """
        if not self._provider:
            return []

        query_embedding = self._provider.embed(query)

        with Session(self._engine) as session:
            if self._is_postgresql:
                return self._vector_postgresql(session, query_embedding, entity, entities, limit)
            else:
                return self._vector_sqlite(session, query_embedding, entity, entities, limit)

    def _vector_postgresql(
        self,
        session: Session,
        query_embedding: list[float],
        entity: str | None,
        entities: list[str] | None,
        limit: int,
    ) -> list[tuple[str, str, str, float]]:
        """PostgreSQL vector search using pgvector."""
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        where_clause = "WHERE embedding IS NOT NULL"
        params: dict[str, Any] = {"embedding": embedding_str, "limit": limit}

        if entity:
            where_clause += " AND entity_name = :entity"
            params["entity"] = entity
        elif entities:
            placeholders = ", ".join(f":e{i}" for i in range(len(entities)))
            where_clause += f" AND entity_name IN ({placeholders})"
            for i, e in enumerate(entities):
                params[f"e{i}"] = e

        result = session.execute(
            text(f"""
            SELECT record_id, entity_name, content, 1 - (embedding <=> :embedding::vector) AS score
            FROM kdb_search
            {where_clause}
            ORDER BY embedding <=> :embedding::vector
            LIMIT :limit
        """),
            params,
        )
        return [(row[0], row[1], row[2], float(row[3])) for row in result.fetchall()]

    def _vector_sqlite(
        self,
        session: Session,
        query_embedding: list[float],
        entity: str | None,
        entities: list[str] | None,
        limit: int,
    ) -> list[tuple[str, str, str, float]]:
        """SQLite vector search.

        Note: For full sqlite-vec support, this would use the vec0 virtual table.
        For now, falls back to loading embeddings and computing in Python.
        """
        import json

        # Build query
        where_clause = "WHERE embedding IS NOT NULL"
        params: dict[str, Any] = {"limit": limit * 10}  # Fetch more for filtering

        if entity:
            where_clause += " AND entity_name = :entity"
            params["entity"] = entity
        elif entities:
            placeholders = ", ".join(f":e{i}" for i in range(len(entities)))
            where_clause += f" AND entity_name IN ({placeholders})"
            for i, e in enumerate(entities):
                params[f"e{i}"] = e

        result = session.execute(
            text(f"""
            SELECT record_id, entity_name, content, embedding
            FROM kdb_search
            {where_clause}
            LIMIT :limit
        """),
            params,
        )

        # Compute cosine similarity in Python
        results = []
        for row in result.fetchall():
            stored_embedding = json.loads(row[3]) if row[3] else None
            if stored_embedding:
                score = self._cosine_similarity(query_embedding, stored_embedding)
                results.append((row[0], row[1], row[2], score))

        # Sort by score descending
        results.sort(key=lambda x: -x[3])
        return results[:limit]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = sum(x * y for x, y in zip(a, b, strict=True))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        similarity: float = dot_product / (norm_a * norm_b)
        return similarity

    def _reciprocal_rank_fusion(
        self,
        bm25_results: list[tuple[str, str, str, float]],
        vector_results: list[tuple[str, str, str, float]],
        limit: int,
        min_score: float,
    ) -> list[SearchResult]:
        """Combine results using Reciprocal Rank Fusion.

        RRF formula: score = sum(1 / (k + rank)) for each result list

        Args:
            bm25_results: (record_id, entity_name, content, score) from BM25
            vector_results: (record_id, entity_name, content, score) from vector
            limit: Max results
            min_score: Minimum score threshold

        Returns:
            Combined and ranked SearchResult list
        """
        scores: dict[str, float] = {}
        record_info: dict[str, tuple[str, str]] = {}  # record_id -> (entity_name, content)

        # Add BM25 scores
        for rank, (record_id, entity_name, content, _) in enumerate(bm25_results):
            scores[record_id] = scores.get(record_id, 0) + 1 / (self.RRF_K + rank + 1)
            record_info[record_id] = (entity_name, content)

        # Add vector scores
        for rank, (record_id, entity_name, content, _) in enumerate(vector_results):
            scores[record_id] = scores.get(record_id, 0) + 1 / (self.RRF_K + rank + 1)
            record_info[record_id] = (entity_name, content)

        # Sort by combined score
        ranked = sorted(scores.items(), key=lambda x: -x[1])

        # Build results (need to fetch full record data)
        results = []
        for record_id, score in ranked[:limit]:
            if score < min_score:
                continue

            entity_name, content = record_info[record_id]

            # Fetch full record
            data = self._get_record_data(record_id, entity_name)

            results.append(
                SearchResult(
                    entity=entity_name,
                    id=record_id,
                    score=score,
                    data=data,
                    matched_text=content,
                )
            )

        return results

    def _get_record_data(self, record_id: str, _entity_name: str) -> dict[str, Any]:
        """Fetch full record data by ID.

        This is a simplified implementation - the actual integration
        should use the Entity class for proper storage mode handling.

        Args:
            record_id: Record ID to fetch
            _entity_name: Entity name (unused, kept for future storage mode handling)
        """
        try:
            with Session(self._engine) as session:
                # Try shared storage first
                result = session.execute(
                    text("""
                    SELECT data FROM kdb_records
                    WHERE id = :id AND is_deleted = false
                """),
                    {"id": record_id},
                )
                row = result.fetchone()
                if row and row[0]:
                    data = row[0]
                    if isinstance(data, str):
                        return json.loads(data)
                    return data
        except Exception:
            # Table may not exist when SearchEngine is used standalone
            pass

        # Record not found in shared storage
        return {}

    def get_status(self, entity: str | None = None) -> list[IndexStatus]:
        """Get indexing status.

        Args:
            entity: Optional entity name to filter

        Returns:
            List of IndexStatus for each entity
        """
        with Session(self._engine) as session:
            if entity:
                where_clause = "WHERE entity_name = :entity"
                params = {"entity": entity}
            else:
                where_clause = ""
                params = {}

            result = session.execute(
                text(f"""
                SELECT entity_name, COUNT(*) as indexed, MAX(updated_at) as last_updated
                FROM kdb_search
                {where_clause}
                GROUP BY entity_name
            """),
                params,
            )

            return [
                IndexStatus(
                    entity=row[0],
                    indexed=row[1],
                    pending=0,  # TODO: Calculate pending from entity record count
                    last_updated=row[2],
                )
                for row in result.fetchall()
            ]
