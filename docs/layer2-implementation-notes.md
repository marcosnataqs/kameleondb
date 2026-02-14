# Layer 2 Implementation Notes

Quick reference for implementing Spec 008 (Hybrid Search).

## Phase 1: Core Infrastructure ✅ (PR #39)

**Goal:** Embedding provider interface + basic search API

### Files to Create/Modify

```
kameleondb/
├── embeddings/
│   ├── __init__.py          # Export provider interface
│   ├── provider.py          # EmbeddingProvider protocol
│   ├── fastembed.py         # FastEmbedProvider (default)
│   └── openai.py            # OpenAIProvider
├── search.py                # Search methods on KameleonDB class
└── schema.py                # Add embed_fields to create_entity()
```

### Provider Interface (provider.py)

```python
from typing import Protocol

class EmbeddingProvider(Protocol):
    """Interface for embedding providers."""
    
    def embed(self, text: str) -> list[float]:
        """Embed single text. Returns vector."""
        ...
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts efficiently."""
        ...
    
    @property
    def dimensions(self) -> int:
        """Vector dimensions (e.g., 384)."""
        ...
    
    @property
    def model_name(self) -> str:
        """Model identifier for storage (e.g., 'all-MiniLM-L6-v2')."""
        ...
```

### Database Schema

**PostgreSQL:**
```sql
CREATE TABLE kdb_search (
    id VARCHAR(36) PRIMARY KEY,
    entity_name VARCHAR(255) NOT NULL,
    record_id VARCHAR(36) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(384),
    model VARCHAR(100) NOT NULL,
    dimensions INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    UNIQUE(entity_name, record_id)
);

-- Indexes
CREATE INDEX ix_search_entity ON kdb_search(entity_name);
CREATE INDEX ix_search_record ON kdb_search(record_id);
CREATE INDEX ix_search_vector ON kdb_search USING hnsw (embedding vector_cosine_ops);

-- Full-text search
ALTER TABLE kdb_search ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX ix_search_fts ON kdb_search USING gin(tsv);
```

**SQLite:**
```sql
-- FTS5 for BM25
CREATE VIRTUAL TABLE kdb_search_fts USING fts5(
    entity_name,
    record_id UNINDEXED,
    content,
    tokenize='porter unicode61'
);

-- sqlite-vec for vectors (separate virtual table)
CREATE VIRTUAL TABLE kdb_search_vec USING vec0(
    record_id TEXT PRIMARY KEY,
    embedding FLOAT[384]
);

-- Metadata table
CREATE TABLE kdb_search_meta (
    record_id VARCHAR(36) PRIMARY KEY,
    entity_name VARCHAR(255) NOT NULL,
    model VARCHAR(100) NOT NULL,
    dimensions INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

### API Changes

**create_entity() with embed_fields:**
```python
db.create_entity(
    "Article",
    fields=[
        {"name": "title", "type": "string"},
        {"name": "body", "type": "text"},
        {"name": "author_id", "type": "uuid"},
    ],
    embed_fields=["title", "body"],  # NEW
)
```

**Search API:**
```python
# Global search
results = db.search("complaint about shipping", limit=10)

# Per-entity
results = db.search("complaint", entity="Ticket", limit=10)

# Multi-entity
results = db.search("Johnson", entities=["Customer", "Contact"], limit=10)
```

**Result format:**
```python
@dataclass
class SearchResult:
    entity: str
    id: str
    score: float
    data: dict
    matched_text: str  # The embedded content
```

## Phase 2: CLI Commands ✅ COMPLETE (Feb 14, 2026)

**Goal:** Expose search + embeddings management through CLI

- [x] Hybrid search with RRF (Reciprocal Rank Fusion) — ✅ PR #39
- [x] OpenAI provider — ✅ PR #39
- [x] CLI commands (`kameleondb search`, `kameleondb embeddings status`) — ✅ Feb 14
  - `kameleondb search "query" [--entity] [--limit] [--threshold]`
  - `kameleondb embeddings status` — show provider, model, indexed entities
  - `kameleondb embeddings reindex [Entity] [--force]`
- [x] Auto-reindex on record update — ✅ Already implemented (Entity.update() line 133)

## Phase 3: Optimizations

- [ ] Batch embedding on bulk insert
- [ ] Background indexing
- [ ] Incremental reindex

## Key Design Decisions

1. **Default to fastembed** — no API key required, ONNX runs locally
2. **384 dimensions** — fastembed and OpenAI both support this, allows seamless migration
3. **Single search table** (PostgreSQL) or two virtual tables (SQLite) — simpler queries
4. **Selective field indexing** — only embed configured text fields, not entire records
5. **Hybrid by default** — always combine BM25 + vectors with RRF

## Dependencies

```toml
[project.optional-dependencies]
embeddings = [
    "fastembed>=0.2.0",
]
embeddings-openai = [
    "openai>=1.0.0",
]
postgresql = [
    "psycopg[binary]>=3.0.0",
    "pgvector>=0.2.0",
]
sqlite-vec = [
    "sqlite-vec>=0.1.0",
]
```

## Testing Strategy

- Unit tests for each provider
- Integration tests for search (SQLite + PostgreSQL)
- Bulk insert + search stress test (10k records)
- Verify RRF ranking correctness

## Open Questions

1. Should we support structured filters in search? `db.search("complaint", where={"status": "open"})`
2. Re-index on every update, or batch periodically?
3. Custom tokenizer/stemming config?

---

*This is a living doc — update as implementation progresses.*
