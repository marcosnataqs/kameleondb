# Spec 008: Semantic Search (Layer 2)

Layer 2 of KameleonDB — vector embeddings for semantic search across entities.

## Problem

Agents often need to find records by meaning, not just exact matches. Current structured queries work well for precise lookups but fail for:

- "Find customers who complained about shipping"
- "Show me products similar to this one"
- "Any notes mentioning the Johnson account?"

## Goals

1. Selective field vectorization (not full records)
2. Single embeddings table for simplicity
3. Global search across all entities
4. Per-entity and multi-entity search
5. Lightweight local model (no API key required for dev)
6. Production-ready model option (OpenAI)

## Design Decisions

### 1. Selective Field Embedding

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

### 2. Single Embeddings Table

```sql
CREATE TABLE kdb_embeddings (
    id VARCHAR(36) PRIMARY KEY,
    entity_name VARCHAR(255) NOT NULL,
    record_id VARCHAR(36) NOT NULL,
    embedding VECTOR(384),          -- pgvector for PostgreSQL
    -- embedding BLOB,              -- sqlite-vec for SQLite
    embedded_text TEXT,             -- Source text (for debugging/reindexing)
    model VARCHAR(100) NOT NULL,    -- 'all-MiniLM-L6-v2', 'text-embedding-3-small'
    dimensions INTEGER NOT NULL,    -- 384
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    
    UNIQUE(entity_name, record_id)
);

-- Indexes
CREATE INDEX ix_embeddings_entity ON kdb_embeddings(entity_name);
CREATE INDEX ix_embeddings_record ON kdb_embeddings(record_id);

-- Vector index (pgvector)
CREATE INDEX ix_embeddings_vector ON kdb_embeddings 
    USING hnsw (embedding vector_cosine_ops);
```

**Rationale:**
- Global search = one query, no UNIONs
- Per-entity search = `WHERE entity_name = ?`
- Simpler migrations and backups
- pgvector handles millions of vectors with HNSW

### 3. Search Modes

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

### 4. Embedding Models

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

### PostgreSQL (pgvector)

```sql
-- Enable extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Embedding column
embedding VECTOR(384)

-- HNSW index for fast similarity search
CREATE INDEX ix_embeddings_vector ON kdb_embeddings 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Search query
SELECT entity_name, record_id, 1 - (embedding <=> $1) AS score
FROM kdb_embeddings
WHERE entity_name = $2  -- optional filter
ORDER BY embedding <=> $1
LIMIT $3;
```

### SQLite (sqlite-vec)

```python
# sqlite-vec uses different syntax
import sqlite_vec

# Load extension
db.execute("SELECT load_extension('vec0')")

# Create virtual table
db.execute("""
    CREATE VIRTUAL TABLE kdb_vec_embeddings USING vec0(
        id TEXT PRIMARY KEY,
        embedding FLOAT[384]
    )
""")

# Search query
db.execute("""
    SELECT id, distance
    FROM kdb_vec_embeddings
    WHERE embedding MATCH ?
    ORDER BY distance
    LIMIT ?
""", [query_embedding, limit])
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

1. **Hybrid search?** Combine vector similarity with structured filters:
   ```python
   db.search("complaint", entity="Ticket", where={"status": "open"})
   ```

2. **Embedding updates:** Re-embed on every update, or batch periodically?

3. **Multiple embedding models per entity?** Probably overkill for v1.

## Success Metrics

- Zero-config local embeddings (no API key)
- <100ms search latency for 100k records
- Seamless dev→prod transition (same dimensions)
- Clear CLI for indexing status
