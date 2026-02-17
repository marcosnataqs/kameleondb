# Query Optimization Implementation Spec

**Status:** DRAFT  
**Phase:** Layer 2 - Phase 3  
**Priority:** #4 (final Phase 3 optimization)  
**Author:** Byte  
**Date:** 2026-02-15

---

## Problem

Hybrid search involves multiple sequential operations:
1. **BM25 search** (full-text keyword matching)
2. **Vector search** (semantic similarity)
3. **RRF fusion** (combine results)
4. **Structured filtering** (apply WHERE conditions)

**Current bottlenecks:**
- Sequential execution: vector search waits for BM25
- No query plan caching
- Repeated tokenization for similar queries
- Suboptimal index usage

**Target:** <100ms p95 latency on 100k records

---

## Optimization Strategies

### 1. Parallel Query Execution
### 2. Query Result Caching
### 3. Index Optimizations
### 4. Query Plan Analysis

---

## 1. Parallel Query Execution

### Problem
BM25 and vector search run sequentially:
```python
bm25_results = self._bm25_search(query, entity, entities, limit)
vector_results = self._vector_search(query, entity, entities, limit)  # Waits for BM25
```

**Current latency:** BM25 (30ms) + Vector (50ms) = 80ms  
**Parallel latency:** max(30ms, 50ms) = 50ms

### Solution

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

class SearchEngine:
    def __init__(self, engine, embedding_provider=None):
        # ... existing init ...
        self._search_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="search")
    
    def search(
        self,
        query: str,
        entity: str | None = None,
        entities: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Hybrid search with parallel execution."""
        fetch_limit = limit * 4 if where else limit * 2
        
        # Submit both searches in parallel
        futures = {}
        futures["bm25"] = self._search_executor.submit(
            self._bm25_search, query, entity, entities, fetch_limit
        )
        
        if self._provider:
            futures["vector"] = self._search_executor.submit(
                self._vector_search, query, entity, entities, fetch_limit
            )
        
        # Wait for results
        bm25_results = futures["bm25"].result()
        vector_results = futures.get("vector", lambda: []).result() if "vector" in futures else []
        
        # Combine with RRF
        results = self._reciprocal_rank_fusion(bm25_results, vector_results, fetch_limit, min_score)
        
        # Apply filters
        if where:
            results = self._apply_where_filters(results, where)
        
        return results[:limit]
```

**Impact:** 30-40% latency reduction on typical queries

---

## 2. Query Result Caching

### Problem
Identical queries re-execute full search:
- Dashboard refreshes
- Pagination (same query, different offset)
- Autocomplete (typing "prod" → "produ" → "product")

### Solution: LRU Cache

```python
from functools import lru_cache
import hashlib
import json

class SearchEngine:
    # Cache key components: query + entity + limit + filters
    
    def _cache_key(
        self,
        query: str,
        entity: str | None,
        entities: list[str] | None,
        limit: int,
        where: dict[str, Any] | None,
    ) -> str:
        """Generate cache key for search params."""
        key_parts = {
            "query": query.strip().lower(),
            "entity": entity,
            "entities": sorted(entities) if entities else None,
            "limit": limit,
            "where": json.dumps(where, sort_keys=True) if where else None,
        }
        key_json = json.dumps(key_parts, sort_keys=True)
        return hashlib.sha256(key_json.encode()).hexdigest()[:16]
    
    def search(
        self,
        query: str,
        entity: str | None = None,
        entities: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search with result caching."""
        # Check cache
        cache_key = self._cache_key(query, entity, entities, limit, where)
        cached = self._get_cached_results(cache_key)
        if cached:
            return cached
        
        # Execute search (parallel as above)
        results = self._execute_search(query, entity, entities, limit, min_score, where)
        
        # Cache results (TTL: 60 seconds)
        self._cache_results(cache_key, results, ttl=60)
        
        return results
```

**Cache Storage Options:**

**Option A: In-memory (simplest)**
```python
from collections import OrderedDict
import time

class SearchEngine:
    def __init__(self, engine, embedding_provider=None):
        # ... existing init ...
        self._result_cache: OrderedDict = OrderedDict()
        self._cache_max_size = 100  # Number of queries to cache
    
    def _get_cached_results(self, cache_key: str) -> list[SearchResult] | None:
        if cache_key in self._result_cache:
            results, timestamp = self._result_cache[cache_key]
            if time.time() - timestamp < 60:  # 60s TTL
                # Move to end (LRU)
                self._result_cache.move_to_end(cache_key)
                return results
            else:
                del self._result_cache[cache_key]
        return None
    
    def _cache_results(self, cache_key: str, results: list[SearchResult], ttl: int) -> None:
        self._result_cache[cache_key] = (results, time.time())
        # Evict oldest if over limit
        while len(self._result_cache) > self._cache_max_size:
            self._result_cache.popitem(last=False)
```

**Option B: Database table (persistent)**
```sql
CREATE TABLE kdb_search_cache (
    cache_key VARCHAR(16) PRIMARY KEY,
    results TEXT NOT NULL,  -- JSON serialized
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_cache_created (created_at)
);
```

**Recommendation:** Start with in-memory (Option A), add DB cache in Phase 4 if needed.

**Impact:** Near-instant response for repeated queries (cache hit)

---

## 3. Index Optimizations

### Current Indexes

**PostgreSQL:**
```sql
CREATE INDEX idx_search_entity ON kdb_search (entity_name);
CREATE INDEX idx_search_tsvector ON kdb_search USING GIN (search_vector);
CREATE INDEX idx_search_embedding ON kdb_search USING ivfflat (embedding vector_cosine_ops);
```

**SQLite:**
```sql
CREATE INDEX idx_search_entity ON kdb_search (entity_name);
-- FTS5 virtual table for BM25
-- sqlite-vec virtual table for vectors
```

### Optimization 1: Covering Indexes (PostgreSQL)

**Problem:** Current indexes require table lookups for content/data.

**Solution:** Include frequently accessed columns in index.

```sql
-- Covering index for entity + content
CREATE INDEX idx_search_entity_content ON kdb_search (entity_name) INCLUDE (content, record_id);
```

**Benefit:** Avoids heap lookup for BM25-only searches (10-20% faster).

### Optimization 2: Composite Indexes

**Problem:** Entity filtering happens after full-table scan.

**Solution:** Composite index for entity + search.

```sql
-- PostgreSQL: entity + tsvector
CREATE INDEX idx_search_entity_tsvector ON kdb_search (entity_name, search_vector);

-- PostgreSQL: entity + embedding (for filtered vector search)
CREATE INDEX idx_search_entity_embedding ON kdb_search (entity_name) INCLUDE (embedding);
```

**Benefit:** Faster entity-scoped searches (25-40% improvement).

### Optimization 3: Vector Index Tuning (PostgreSQL pgvector)

**Current:** IVFFlat index (approximate nearest neighbor)

**Tuning parameters:**
```sql
-- Increase lists for larger datasets
CREATE INDEX idx_search_embedding ON kdb_search 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);  -- Default, increase to 500-1000 for >100k records

-- At query time, tune probes
SET ivfflat.probes = 10;  -- Search 10 lists (balance speed/accuracy)
```

**Alternative:** HNSW (better for high-recall scenarios)
```sql
CREATE INDEX idx_search_embedding ON kdb_search 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);  -- Tunable for speed/accuracy
```

**Recommendation:** Benchmark IVFFlat vs HNSW on real data, default to IVFFlat (faster build).

---

## 4. Query Plan Analysis

### EXPLAIN ANALYZE for Profiling

```python
class SearchEngine:
    def explain_search(
        self,
        query: str,
        entity: str | None = None,
    ) -> dict:
        """Analyze query execution plan."""
        with Session(self._engine) as session:
            # BM25 query
            bm25_query = self._build_bm25_query(query, entity)
            bm25_plan = session.execute(
                text(f"EXPLAIN ANALYZE {bm25_query}")
            ).fetchall()
            
            # Vector query
            if self._provider:
                vector_query = self._build_vector_query(query, entity)
                vector_plan = session.execute(
                    text(f"EXPLAIN ANALYZE {vector_query}")
                ).fetchall()
            else:
                vector_plan = None
            
            return {
                "bm25_plan": [str(row) for row in bm25_plan],
                "vector_plan": [str(row) for row in vector_plan] if vector_plan else None,
            }
```

**Usage:**
```bash
kameleondb search "coffee maker" --explain
# Output: Query execution plan with timing breakdown
```

**Insights to extract:**
- Index usage (seq scan vs index scan)
- Row estimates vs actual
- Bottleneck operations

---

## CLI Commands

```bash
# Explain query execution plan
kameleondb search "query" --explain
# Output:
# BM25 Plan:
#   -> Index Scan using idx_search_tsvector (cost=0.42..8.44 rows=5 actual time=0.123..0.156)
#   -> Heap Lookup (cost=0.00..3.21 rows=5 actual time=0.045..0.067)
# Vector Plan:
#   -> IVFFlat Index Scan (cost=0.00..12.34 rows=10 actual time=1.234..2.345)
# Total Time: 2.568ms

# Benchmark search performance
kameleondb search "query" --benchmark --runs 100
# Output:
# Search Performance (100 runs):
#   Mean: 45.2ms
#   p50:  42.1ms
#   p95:  67.8ms
#   p99:  89.3ms
#   Cache hit rate: 23%

# Clear result cache
kameleondb search cache clear
# Cleared 47 cached queries
```

---

## Performance Targets

### Before Optimizations (Baseline)
- **BM25 only:** ~30ms p95
- **Vector only:** ~50ms p95  
- **Hybrid (sequential):** ~80ms p95
- **Cache hit rate:** 0%

### After Optimizations (Target)
- **BM25 only:** ~20ms p95 (covering indexes)
- **Vector only:** ~40ms p95 (index tuning)
- **Hybrid (parallel):** ~50ms p95 (parallel execution)
- **Cache hit rate:** 20-40% (result caching)

**Overall target:** <100ms p95 on 100k records ✅

---

## Implementation Plan

### Phase 1: Parallel Execution (1-2 hours)
1. Add `ThreadPoolExecutor` for parallel BM25 + vector
2. Refactor `search()` to submit concurrent futures
3. Benchmark: verify 30-40% latency reduction
4. Unit tests: parallel execution correctness

### Phase 2: Result Caching (2 hours)
1. Implement in-memory LRU cache
2. Add `_cache_key()` generation
3. Add `--benchmark` CLI flag
4. Tests: cache hit/miss scenarios

### Phase 3: Index Optimizations (2-3 hours)
1. Add covering indexes migration
2. Add composite entity+search indexes
3. Document index tuning parameters
4. Benchmark: measure improvement on real data

### Phase 4: Query Analysis (1 hour)
1. Implement `explain_search()` method
2. Add `--explain` CLI flag
3. Format output for readability
4. Documentation: query optimization guide

**Total estimate: 6-8 hours**

---

## Migration Strategy

### Index Migration

Add to `migrations.py`:

```python
def migration_004_search_indexes(engine: Engine) -> None:
    """Add optimized search indexes."""
    with Session(engine) as session:
        if engine.dialect.name == "postgresql":
            # Covering index for BM25
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_search_entity_content 
                ON kdb_search (entity_name) 
                INCLUDE (content, record_id)
            """))
            
            # Composite entity + tsvector
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_search_entity_tsvector 
                ON kdb_search (entity_name, search_vector)
            """))
            
            # Entity + embedding (covering)
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_search_entity_embedding 
                ON kdb_search (entity_name) 
                INCLUDE (embedding)
            """))
        
        # SQLite optimizations handled by FTS5/sqlite-vec virtual tables
        
        session.commit()
```

**Backward compatible:** New indexes don't break existing queries.

---

## Testing Strategy

### Performance Benchmarks
- 1k, 10k, 100k record datasets
- Varied query patterns (short/long, specific/broad)
- Entity-scoped vs cross-entity searches

### Cache Tests
- `test_cache_hit_returns_cached_results()`
- `test_cache_miss_executes_search()`
- `test_cache_ttl_expires_old_results()`
- `test_cache_lru_evicts_oldest()`

### Parallel Execution Tests
- `test_parallel_search_faster_than_sequential()`
- `test_parallel_search_correctness()`
- `test_parallel_search_handles_errors()`

---

## Monitoring & Observability

### Search Metrics to Track

```python
class SearchEngine:
    def __init__(self, engine, embedding_provider=None):
        # ... existing init ...
        self._metrics = {
            "total_searches": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "bm25_latency": [],
            "vector_latency": [],
            "total_latency": [],
        }
    
    def get_metrics(self) -> dict:
        """Get search performance metrics."""
        return {
            "total_searches": self._metrics["total_searches"],
            "cache_hit_rate": self._metrics["cache_hits"] / max(1, self._metrics["total_searches"]),
            "avg_bm25_latency": sum(self._metrics["bm25_latency"]) / len(self._metrics["bm25_latency"]),
            "avg_vector_latency": sum(self._metrics["vector_latency"]) / len(self._metrics["vector_latency"]),
            "p95_total_latency": self._percentile(self._metrics["total_latency"], 95),
        }
```

**CLI:**
```bash
kameleondb search metrics
# Output:
# Total searches: 1,234
# Cache hit rate: 34.2%
# Avg BM25 latency: 18.3ms
# Avg vector latency: 42.1ms
# p95 total latency: 67.8ms
```

---

## Advanced Optimizations (Phase 4+)

### 1. Query Result Preloading
Pre-fetch popular queries on startup:
```python
# Load top 10 most common queries from analytics
common_queries = ["coffee maker", "laptop", "phone case", ...]
for query in common_queries:
    self.search(query, limit=20)  # Warm cache
```

### 2. Approximate Top-K
For very large result sets, use approximate algorithms:
```python
# Return top-k results with 95% confidence (faster)
results = self.search(query, limit=100, approximate=True, confidence=0.95)
```

### 3. Query Rewriting
Optimize user queries before execution:
```python
# Expand synonyms: "phone" → "phone OR mobile OR smartphone"
# Remove stopwords: "the coffee maker" → "coffee maker"
# Spell correction: "cofee" → "coffee"
```

**Complexity:** High  
**Impact:** 10-20% improvement  
**Recommendation:** Defer to Phase 4

---

## Success Metrics

- [ ] Hybrid search <50ms p95 (100k records)
- [ ] Cache hit rate 20-40% on typical workloads
- [ ] Parallel execution 30-40% faster than sequential
- [ ] Index optimizations reduce BM25 latency by 25%+

---

## Next Steps

1. **Get approval** - Review with Marcos
2. **Implement after background indexing** - Complete Phase 3 stack
3. **Benchmark rigorously** - Validate improvements on real data

---

## References

- Phase 3 Plan: `docs/layer2-phase3-plan.md`
- Batch Embedding Spec: `docs/batch-embedding-spec.md`
- Embedding Cache Spec: `docs/embedding-cache-spec.md`
- Background Indexing Spec: `docs/background-indexing-spec.md`
- SearchEngine: `src/kameleondb/search/engine.py`
- PostgreSQL pgvector: https://github.com/pgvector/pgvector
