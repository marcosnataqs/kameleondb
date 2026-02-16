# Embedding Cache Implementation Spec

**Status:** DRAFT  
**Phase:** Layer 2 - Phase 3  
**Priority:** #2 (complements batch embedding)  
**Author:** Byte  
**Date:** 2026-02-15

---

## Problem

Re-embedding identical content wastes resources:
- **Reindex scenarios:** Record updated but content unchanged → re-embed same text
- **API costs:** OpenAI charges per token, even for duplicate text
- **Compute waste:** FastEmbed re-runs inference on identical inputs
- **Latency:** Unnecessary network/compute time

**Example:** User updates 10k Product records changing only `price` field. `description` field (used for search) unchanged → 10k redundant embeddings.

---

## Solution Overview

Content-addressed cache using cryptographic hashing:
1. Hash normalized text content
2. Check cache for (hash, model) → embedding
3. On hit: return cached embedding
4. On miss: generate embedding, store in cache

---

## Database Schema

### New Table: kdb_embedding_cache

```sql
CREATE TABLE kdb_embedding_cache (
    text_hash VARCHAR(64) PRIMARY KEY,      -- SHA256 hash of normalized text
    model VARCHAR(255) NOT NULL,            -- Model identifier (e.g., "BAAI/bge-small-en-v1.5")
    embedding VECTOR(384) NOT NULL,         -- PostgreSQL: vector type
    -- embedding BLOB NOT NULL,             -- SQLite: raw bytes
    dimensions INTEGER NOT NULL,            -- Embedding dimensions
    hit_count INTEGER DEFAULT 1,            -- Number of cache hits (for analytics)
    created_at TIMESTAMP DEFAULT NOW(),     -- First cache time
    last_hit_at TIMESTAMP DEFAULT NOW(),    -- Most recent hit
    
    INDEX idx_cache_model_hash (model, text_hash),
    INDEX idx_cache_last_hit (last_hit_at)  -- For cleanup queries
);
```

**Key design decisions:**
- **Hash as primary key:** Fast lookups, deterministic
- **Model in key:** Different models = different embeddings for same text
- **Hit tracking:** Enables analytics (cache hit rate, popular content)
- **Timestamp indexes:** Efficient cleanup of stale entries

---

## Text Normalization

**Critical:** Hash must be deterministic across identical semantic content.

```python
def normalize_text(text: str) -> str:
    """Normalize text for cache key generation.
    
    Ensures identical semantic content produces identical hash.
    """
    # Strip leading/trailing whitespace
    normalized = text.strip()
    
    # Collapse multiple whitespace to single space
    normalized = " ".join(normalized.split())
    
    # Lowercase (optional - depends on model case-sensitivity)
    # normalized = normalized.lower()  # Skip for now - models are case-aware
    
    return normalized

def hash_text(text: str) -> str:
    """Generate SHA256 hash of normalized text."""
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

**Why SHA256:**
- Fast (hardware-accelerated on modern CPUs)
- Collision-resistant (probability negligible for our use case)
- Fixed 64-char output (efficient indexing)

---

## API Design

### SearchEngine Methods

```python
class SearchEngine:
    def _get_cached_embedding(
        self,
        text: str,
    ) -> list[float] | None:
        """Get cached embedding if available.
        
        Returns:
            Embedding vector or None if cache miss.
        """
        if not self._provider:
            return None
        
        text_hash = hash_text(text)
        model = self._provider.model_name
        
        with Session(self._engine) as session:
            result = session.execute(
                text("""
                    SELECT embedding, dimensions
                    FROM kdb_embedding_cache
                    WHERE text_hash = :hash AND model = :model
                """),
                {"hash": text_hash, "model": model},
            ).fetchone()
            
            if result:
                # Update hit metrics
                session.execute(
                    text("""
                        UPDATE kdb_embedding_cache
                        SET hit_count = hit_count + 1,
                            last_hit_at = NOW()
                        WHERE text_hash = :hash AND model = :model
                    """),
                    {"hash": text_hash, "model": model},
                )
                session.commit()
                
                # Parse embedding from storage format
                embedding = self._parse_embedding(result[0], result[1])
                return embedding
        
        return None
    
    def _cache_embedding(
        self,
        text: str,
        embedding: list[float],
    ) -> None:
        """Store embedding in cache."""
        if not self._provider:
            return
        
        text_hash = hash_text(text)
        model = self._provider.model_name
        dimensions = self._provider.dimensions
        
        with Session(self._engine) as session:
            if self._is_postgresql:
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                session.execute(
                    text("""
                        INSERT INTO kdb_embedding_cache (text_hash, model, embedding, dimensions)
                        VALUES (:hash, :model, :embedding::vector, :dimensions)
                        ON CONFLICT (text_hash) DO NOTHING
                    """),
                    {
                        "hash": text_hash,
                        "model": model,
                        "embedding": embedding_str,
                        "dimensions": dimensions,
                    },
                )
            else:
                # SQLite: store as JSON array
                import json
                embedding_json = json.dumps(embedding)
                session.execute(
                    text("""
                        INSERT OR IGNORE INTO kdb_embedding_cache (text_hash, model, embedding, dimensions)
                        VALUES (:hash, :model, :embedding, :dimensions)
                    """),
                    {
                        "hash": text_hash,
                        "model": model,
                        "embedding": embedding_json,
                        "dimensions": dimensions,
                    },
                )
            session.commit()
```

### Integration with index_record()

```python
def index_record(self, entity_name: str, record_id: str, content: str) -> None:
    """Index a record (with cache support)."""
    embedding = None
    
    if self._provider:
        # Try cache first
        embedding = self._get_cached_embedding(content)
        
        if embedding is None:
            # Cache miss - generate and cache
            embedding = self._provider.embed(content)
            self._cache_embedding(content, embedding)
    
    # Rest of indexing logic...
```

### Integration with batch API

```python
def index_records_batch(
    self,
    records: list[tuple[str, str, str]],
) -> None:
    """Batch index with cache support."""
    if not self._provider:
        self._batch_insert_bm25_only(records)
        return
    
    embeddings = []
    texts_to_embed = []
    cache_indices = []
    
    # Check cache for each record
    for i, (entity_name, record_id, content) in enumerate(records):
        cached = self._get_cached_embedding(content)
        if cached:
            embeddings.append(cached)
        else:
            embeddings.append(None)  # Placeholder
            texts_to_embed.append(content)
            cache_indices.append(i)
    
    # Batch embed cache misses
    if texts_to_embed:
        new_embeddings = self._provider.embed_batch(texts_to_embed)
        
        # Fill in placeholders and cache new embeddings
        for idx, embedding in zip(cache_indices, new_embeddings):
            embeddings[idx] = embedding
            self._cache_embedding(texts_to_embed[cache_indices.index(idx)], embedding)
    
    # Batch insert all records
    # ...
```

---

## CLI Commands

```bash
# View cache statistics
kameleondb embeddings cache status
# Output:
# Model                      Entries  Total Hits  Hit Rate  Disk Size
# BAAI/bge-small-en-v1.5     12,453   45,892     78.5%     47.2 MB
# text-embedding-3-small      3,201    8,450     62.1%     12.1 MB

# Clear old cache entries
kameleondb embeddings cache clear --older-than 30d
# Removed 2,341 entries older than 30 days

# Clear entire cache
kameleondb embeddings cache clear --all
# Confirm: Clear entire embedding cache? (y/N): y
# Removed 15,654 entries

# Clear cache for specific model
kameleondb embeddings cache clear --model "BAAI/bge-small-en-v1.5"
# Removed 12,453 entries for model BAAI/bge-small-en-v1.5
```

---

## Performance Impact

### Cache Hit Rate Scenarios

**Scenario 1: Reindex unchanged data**
- Hit rate: ~95%
- Speedup: 10-20x (no embedding generation)

**Scenario 2: Partial updates (price changes, metadata edits)**
- Hit rate: 60-80%
- Speedup: 3-5x

**Scenario 3: New data insertion**
- Hit rate: 0%
- Overhead: <5% (hash computation + cache miss query)

### Storage Overhead

**Per cached embedding:**
- Hash: 64 bytes
- Model name: ~30 bytes avg
- Embedding: 384 dims × 4 bytes = 1,536 bytes (float32)
- Metadata: ~50 bytes
- **Total: ~1,680 bytes per entry**

**Example: 100k cached embeddings = ~160 MB**

---

## Cache Eviction Strategy

### Automatic Cleanup (LRU-based)

```python
def cleanup_stale_cache(
    self,
    max_age_days: int = 30,
    max_entries: int | None = None,
) -> int:
    """Remove stale cache entries.
    
    Args:
        max_age_days: Remove entries older than N days
        max_entries: Keep only N most recently used entries
    
    Returns:
        Number of entries removed
    """
    with Session(self._engine) as session:
        if max_age_days:
            result = session.execute(
                text("""
                    DELETE FROM kdb_embedding_cache
                    WHERE last_hit_at < NOW() - INTERVAL :days DAY
                    RETURNING text_hash
                """),
                {"days": max_age_days},
            )
            count = len(result.fetchall())
        
        if max_entries:
            # Keep top N by hit count or last_hit_at
            session.execute(
                text("""
                    DELETE FROM kdb_embedding_cache
                    WHERE text_hash NOT IN (
                        SELECT text_hash FROM kdb_embedding_cache
                        ORDER BY last_hit_at DESC
                        LIMIT :limit
                    )
                """),
                {"limit": max_entries},
            )
        
        session.commit()
        return count
```

### Cron Job (Optional)

```bash
# Weekly cache cleanup
0 2 * * 0 kameleondb embeddings cache clear --older-than 30d
```

---

## Testing Strategy

### Unit Tests
- `test_hash_text_deterministic()` - same input → same hash
- `test_hash_text_normalization()` - whitespace variants → same hash
- `test_cache_hit()` - embed once, get from cache on second call
- `test_cache_miss()` - new text generates embedding
- `test_cache_model_isolation()` - different models don't share cache
- `test_cache_hit_tracking()` - hit_count increments

### Integration Tests
- Reindex with cache: verify hit rate >90% on second run
- Batch insert with partial cache hits
- Cache cleanup: verify old entries removed

### Performance Tests
- 10k cache lookups: <10ms p95
- Cache overhead on new inserts: <5%

---

## Migration Strategy

### Schema Migration

Add to `migrations.py`:

```python
def migration_002_embedding_cache(engine: Engine) -> None:
    """Add embedding cache table."""
    with Session(engine) as session:
        if engine.dialect.name == "postgresql":
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS kdb_embedding_cache (
                    text_hash VARCHAR(64) PRIMARY KEY,
                    model VARCHAR(255) NOT NULL,
                    embedding vector(384) NOT NULL,
                    dimensions INTEGER NOT NULL,
                    hit_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_hit_at TIMESTAMP DEFAULT NOW()
                )
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cache_model_hash 
                ON kdb_embedding_cache (model, text_hash)
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cache_last_hit 
                ON kdb_embedding_cache (last_hit_at)
            """))
        else:  # SQLite
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS kdb_embedding_cache (
                    text_hash TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    hit_count INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    last_hit_at TEXT DEFAULT (datetime('now'))
                )
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cache_model_hash 
                ON kdb_embedding_cache (model, text_hash)
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cache_last_hit 
                ON kdb_embedding_cache (last_hit_at)
            """))
        session.commit()
```

---

## Implementation Plan

### Phase 1: Core Cache (2-3 hours)
1. Add schema migration for `kdb_embedding_cache` table
2. Implement `hash_text()` and `normalize_text()` utilities
3. Add `_get_cached_embedding()` and `_cache_embedding()` methods
4. Unit tests for hash determinism and cache hit/miss

### Phase 2: Integration (1-2 hours)
1. Integrate cache into `index_record()`
2. Integrate cache into `index_records_batch()`
3. Integration tests for reindex scenarios

### Phase 3: CLI & Cleanup (1-2 hours)
1. Add `embeddings cache status` command
2. Add `embeddings cache clear` command with filters
3. Add automatic cleanup on old entries
4. Performance benchmarks

**Total estimate: 4-7 hours**

---

## Open Questions

1. **Should we cache BM25-only mode?**
   - Pro: Could cache tokenization results
   - Con: BM25 is fast enough already
   - **Recommendation:** No - focus on embedding cache only

2. **Cache size limits?**
   - Pro: Prevents unbounded growth
   - Con: Adds complexity
   - **Recommendation:** Start with time-based cleanup (30d), add size limits later if needed

3. **Should we dedupe embeddings across models?**
   - Pro: Saves storage if using multiple models
   - Con: Breaks cache isolation
   - **Recommendation:** No - keep models isolated for safety

---

## Success Metrics

- [ ] Cache hit rate >90% on reindex of unchanged data
- [ ] Cache hit rate >60% on typical updates (partial field changes)
- [ ] Cache lookup latency <1ms p95
- [ ] Cache overhead on new inserts <5%

---

## Next Steps

1. **Get approval** - Review with Marcos
2. **Implement after batch embedding** - Cache complements batch API
3. **Monitor hit rates** - Collect metrics to validate effectiveness

---

## References

- Phase 3 Plan: `docs/layer2-phase3-plan.md`
- Batch Embedding Spec: `docs/batch-embedding-spec.md`
- SearchEngine: `src/kameleondb/search/engine.py`
- Migrations: `src/kameleondb/schema/migrations.py`
