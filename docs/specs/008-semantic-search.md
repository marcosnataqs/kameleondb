# Spec 008: Hybrid Search (Layer 2)

Layer 2 of KameleonDB — hybrid search combining BM25 (keyword) and vector embeddings (semantic).

## Problem

Agents often need to find records by meaning, not just exact matches. Current structured queries work well for precise lookups but fail for:

- "Find customers who complained about shipping"
- "Show me products similar to this one"
- "Any notes mentioning the Johnson account?"

Neither keyword search nor semantic search alone is sufficient:
- **Keywords miss synonyms:** "angry customer" won't find "frustrated client"
- **Vectors miss exact terms:** "order #12345" may not match precisely

## Goals

1. **Hybrid search by default** — combine BM25 + vectors automatically
2. Selective field indexing (not full records)
3. Single table for both FTS and embeddings
4. Global search across all entities
5. Per-entity and multi-entity search
6. Lightweight local model (no API key required for dev)
7. Production-ready model option (OpenAI)

## Design Decisions

### 1. Hybrid Search Architecture

Every search query runs both BM25 and vector similarity, then combines results.

**Why hybrid by default:**

| Query | BM25 (keyword) | Vectors (semantic) | Hybrid |
|-------|----------------|-------------------|--------|
| "order #12345" | ✅ Exact match | ❌ May miss | ✅ |
| "angry customer" | ❌ Misses "frustrated" | ✅ Semantic match | ✅ |
| "Johnson shipping" | ✅ Proper noun | ✅ Context | ✅✅ |

**Algorithm: Reciprocal Rank Fusion (RRF)**

```python
def hybrid_search(query: str, limit: int = 10) -> list[SearchResult]:
    # Run both searches
    bm25_results = bm25_search(query, limit=limit * 2)
    vector_results = vector_search(query, limit=limit * 2)
    
    # Combine with RRF
    scores = {}
    k = 60  # RRF constant
    
    for rank, result in enumerate(bm25_results):
        scores[result.id] = scores.get(result.id, 0) + 1 / (k + rank + 1)
    
    for rank, result in enumerate(vector_results):
        scores[result.id] = scores.get(result.id, 0) + 1 / (k + rank + 1)
    
    # Sort by combined score
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return [get_record(id) for id, score in ranked[:limit]]
```

**Rationale for RRF:**
- Simple, no tuning required
- Works well when scores aren't comparable (BM25 vs cosine similarity)
- Used by Elasticsearch, Weaviate, and others

### 2. Selective Field Indexing

Only embed configured text fields, not entire records.

**Rationale:**
- Reduces noise (IDs, timestamps, booleans aren't semantic)
- Respects embedding token limits
- Faster re-indexing on field changes
- Agents search by meaning, which lives in text fields

```python
db.create_entity(
    "Product",
    fields=[
        {"name": "sku", "type": "string"},
        {"name": "name", "type": "string"},
        {"name": "description", "type": "text"},
        {"name": "price", "type": "float"},
    ],
    embed_fields=["name", "description"],  # Only these get vectorized
)
```

**Embedding format:**
```
"name: Wireless Headphones | description: Premium noise-cancelling headphones with 30-hour battery life"
```

### 3. Single Search Table (Embeddings + FTS)

```sql
CREATE TABLE kdb_search (
    id VARCHAR(36) PRIMARY KEY,
    entity_name VARCHAR(255) NOT NULL,
    record_id VARCHAR(36) NOT NULL,
    
    -- Text content (for BM25)
    content TEXT NOT NULL,
    
    -- Vector embedding (for semantic)
    embedding VECTOR(384),          -- pgvector for PostgreSQL
    
    -- Metadata
    model VARCHAR(100) NOT NULL,    -- 'all-MiniLM-L6-v2'
    dimensions INTEGER NOT NULL,    -- 384
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    
    UNIQUE(entity_name, record_id)
);

-- Indexes
CREATE INDEX ix_search_entity ON kdb_search(entity_name);
CREATE INDEX ix_search_record ON kdb_search(record_id);

-- Vector index (pgvector HNSW)
CREATE INDEX ix_search_vector ON kdb_search 
    USING hnsw (embedding vector_cosine_ops);

-- Full-text search index (PostgreSQL)
ALTER TABLE kdb_search ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX ix_search_fts ON kdb_search USING gin(tsv);
```

**SQLite variant (FTS5 + sqlite-vec):**

```sql
-- FTS5 for BM25
CREATE VIRTUAL TABLE kdb_search_fts USING fts5(
    entity_name,
    record_id UNINDEXED,
    content,
    tokenize='porter unicode61'
);

-- sqlite-vec for vectors
CREATE VIRTUAL TABLE kdb_search_vec USING vec0(
    record_id TEXT PRIMARY KEY,
    embedding FLOAT[384]
);
```

**Rationale:**
- Single table = simpler queries and maintenance
- Both BM25 and vector search in one place
- Global search = one query (PostgreSQL) or two queries merged (SQLite)
- Per-entity search = add `WHERE entity_name = ?`

### 4. Search Modes

#### Global Search (all entities)
```python
results = db.search("shipping complaint Johnson", limit=10)
# Returns mixed results from any entity
# [
#   {"entity": "SupportTicket", "id": "...", "score": 0.92, "data": {...}},
#   {"entity": "Customer", "id": "...", "score": 0.87, "data": {...}},
#   {"entity": "Order", "id": "...", "score": 0.81, "data": {...}},
# ]
```

#### Per-Entity Search
```python
results = db.search("shipping complaint", entity="SupportTicket", limit=10)
# Only searches SupportTicket records
```

#### Multi-Entity Search
```python
results = db.search("Johnson", entities=["Customer", "Contact"], limit=10)
# Searches both Customer and Contact
```

### 5. Embedding Models

| Environment | Model | Dimensions | Provider |
|-------------|-------|------------|----------|
| Local/Dev | `all-MiniLM-L6-v2` | 384 | fastembed (ONNX) |
| Production | `text-embedding-3-small` | 384* | OpenAI API |

*OpenAI supports `dimensions` parameter — request 384 to match local model.

**Key insight:** Same dimensions = same index. Develop locally, deploy without re-indexing.

#### Provider Interface
```python
class EmbeddingProvider(Protocol):
    """Interface for embedding providers."""
    
    def embed(self, text: str) -> list[float]:
        """Embed a single text."""
        ...
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts efficiently."""
        ...
    
    @property
    def dimensions(self) -> int:
        """Vector dimensions."""
        ...
    
    @property
    def model_name(self) -> str:
        """Model identifier for storage."""
        ...
```

#### Built-in Providers

```python
# Local provider (default, no API key)
class FastEmbedProvider(EmbeddingProvider):
    """Uses fastembed (ONNX) for local embeddings."""
    
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        from fastembed import TextEmbedding
        self._model = TextEmbedding(model)
        self._dimensions = 384
    
    def embed(self, text: str) -> list[float]:
        return list(self._model.embed([text]))[0]
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return list(self._model.embed(texts))

# OpenAI provider
class OpenAIProvider(EmbeddingProvider):
    """Uses OpenAI API for embeddings."""
    
    def __init__(
        self, 
        model: str = "text-embedding-3-small",
        dimensions: int = 384,
        api_key: str | None = None,
    ):
        import openai
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model
        self._dimensions = dimensions
    
    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self._dimensions,
        )
        return response.data[0].embedding
```

## API Design

### Configuration

```python
# Default: fastembed, no API key needed
db = KameleonDB("sqlite:///app.db", embeddings=True)

# With OpenAI
db = KameleonDB(
    "postgresql://...",
    embeddings=True,
    embedding_provider="openai",
    embedding_model="text-embedding-3-small",
    embedding_dimensions=384,
)

# Custom provider
db = KameleonDB(
    "sqlite:///app.db",
    embedding_provider=MyCustomProvider(),
)
```

### Entity Configuration

```python
# Explicit embed fields
db.create_entity(
    "Article",
    fields=[
        {"name": "title", "type": "string"},
        {"name": "body", "type": "text"},
        {"name": "author_id", "type": "uuid"},
        {"name": "published_at", "type": "datetime"},
    ],
    embed_fields=["title", "body"],
)

# Auto-detect text fields (optional behavior)
db.create_entity(
    "Note",
    fields=[...],
    embed_fields="auto",  # Embeds all string/text fields
)

# Disable embedding for entity
db.create_entity(
    "AuditLog",
    fields=[...],
    embed_fields=None,  # No embeddings
)
```

### Inserting Records

```python
# Embedding happens automatically on insert
record = db.insert("Article", {
    "title": "Breaking News",
    "body": "Something important happened today...",
    "author_id": "...",
})
# → Generates embedding for "title: Breaking News | body: Something important..."
# → Stores in kdb_embeddings
```

### Searching

```python
# Global search
results = db.search("important news", limit=5)

# Per-entity
results = db.search("important news", entity="Article", limit=5)

# Multi-entity
results = db.search("important", entities=["Article", "Note"], limit=5)

# With minimum score threshold
results = db.search("news", min_score=0.7, limit=10)
```

### Search Result Schema

```python
@dataclass
class SearchResult:
    entity: str           # Entity name
    id: str               # Record ID
    score: float          # Similarity score (0-1)
    data: dict            # Full record data
    matched_text: str     # The embedded text that matched
```

### Re-indexing

```python
# Re-index single entity (e.g., after changing embed_fields)
db.reindex_embeddings("Article")

# Re-index all entities
db.reindex_embeddings()

# Check indexing status
status = db.embedding_status("Article")
# {"indexed": 1523, "pending": 0, "last_updated": "..."}
```

## CLI Commands

```bash
# Search
kameleondb search "shipping complaint" --limit 10
kameleondb search "Johnson" --entity Customer --limit 5
kameleondb search "order issue" --entities Customer,Order,SupportTicket

# Indexing
kameleondb embeddings status
kameleondb embeddings reindex Article
kameleondb embeddings reindex --all

# Configuration
kameleondb embeddings config --provider openai --model text-embedding-3-small
```

## Backend-Specific Implementation

### PostgreSQL (pgvector + tsvector)

```sql
-- Enable extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Hybrid search query
WITH bm25_results AS (
    SELECT record_id, ts_rank(tsv, query) AS score,
           ROW_NUMBER() OVER (ORDER BY ts_rank(tsv, query) DESC) AS rank
    FROM kdb_search, plainto_tsquery('english', $1) query
    WHERE tsv @@ query
      AND ($2 IS NULL OR entity_name = $2)
    LIMIT $3 * 2
),
vector_results AS (
    SELECT record_id, 1 - (embedding <=> $4) AS score,
           ROW_NUMBER() OVER (ORDER BY embedding <=> $4) AS rank
    FROM kdb_search
    WHERE ($2 IS NULL OR entity_name = $2)
    ORDER BY embedding <=> $4
    LIMIT $3 * 2
),
rrf_scores AS (
    SELECT record_id, SUM(1.0 / (60 + rank)) AS score
    FROM (
        SELECT record_id, rank FROM bm25_results
        UNION ALL
        SELECT record_id, rank FROM vector_results
    ) combined
    GROUP BY record_id
)
SELECT r.record_id, r.score, s.entity_name, s.content
FROM rrf_scores r
JOIN kdb_search s ON s.record_id = r.record_id
ORDER BY r.score DESC
LIMIT $3;
```

### SQLite (FTS5 + sqlite-vec)

```python
def hybrid_search_sqlite(query: str, entity: str = None, limit: int = 10):
    # BM25 search via FTS5
    bm25_sql = """
        SELECT record_id, bm25(kdb_search_fts) AS score
        FROM kdb_search_fts
        WHERE kdb_search_fts MATCH ?
        ORDER BY bm25(kdb_search_fts)
        LIMIT ?
    """
    bm25_results = db.execute(bm25_sql, [query, limit * 2])
    
    # Vector search via sqlite-vec
    query_embedding = embed(query)
    vec_sql = """
        SELECT record_id, distance
        FROM kdb_search_vec
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?
    """
    vec_results = db.execute(vec_sql, [query_embedding, limit * 2])
    
    # Combine with RRF
    return reciprocal_rank_fusion(bm25_results, vec_results, limit)
```

## Dependencies

```toml
# pyproject.toml
[project.optional-dependencies]
embeddings = [
    "fastembed>=0.2.0",  # Local embeddings (ONNX)
]
embeddings-openai = [
    "openai>=1.0.0",     # OpenAI provider
]
postgresql = [
    "psycopg[binary]>=3.0.0",
    "pgvector>=0.2.0",   # pgvector support
]
sqlite-vec = [
    "sqlite-vec>=0.1.0", # sqlite-vec support
]
```

## Migration Path

1. **Phase 1:** Core embedding infrastructure
   - `kdb_embeddings` table
   - `EmbeddingProvider` interface
   - `FastEmbedProvider` (default)
   - Basic `db.search()` API

2. **Phase 2:** Full search features
   - `OpenAIProvider`
   - Global/per-entity/multi-entity search
   - CLI commands
   - Auto-reindex on record update

3. **Phase 3:** Optimizations
   - Batch embedding on bulk insert
   - Background indexing
   - Incremental reindex

## Open Questions

1. **Structured filters in search?** Combine hybrid search with SQL filters:
   ```python
   db.search("complaint", entity="Ticket", where={"status": "open"})
   ```

2. **Index updates:** Re-index on every update, or batch periodically?

3. **Stemming/tokenization config?** Porter stemmer is default, but may need options.

## Success Metrics

- Zero-config local embeddings (no API key)
- <100ms search latency for 100k records
- Seamless dev→prod transition (same dimensions)
- Clear CLI for indexing status
