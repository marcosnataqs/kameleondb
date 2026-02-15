# Layer 2 - Phase 3: Search Optimizations

**Status:** PLANNED  
**Dependencies:** Phase 1 ✅, Phase 2 ✅  
**Goal:** Performance optimizations for production workloads

---

## Overview

Phase 1 delivered the hybrid search engine. Phase 2 delivered CLI integration. Phase 3 focuses on **production readiness** through batch processing, background indexing, and query optimization.

---

## Features

### 1. Batch Embedding Generation
**Problem:** Currently embeddings are generated one-at-a-time on insert/update.  
**Solution:** Batch multiple texts together for providers that support it (OpenAI, FastEmbed).

**Benefits:**
- Faster bulk inserts (stress tests insert 30k+ records)
- Lower API costs (OpenAI charges per request overhead)
- Better throughput

**Implementation:**
- Queue embeddings during transaction
- Flush queue at commit time
- Use provider-specific batch sizes (OpenAI: 2048 max)

---

### 2. Background Indexing
**Problem:** Large reindex operations block the CLI.  
**Solution:** Async reindex with progress tracking.

**Benefits:**
- Non-blocking CLI experience
- Progress visibility for large datasets
- Cancellable operations

**Implementation:**
- Thread-based async reindex
- Status command to check progress
- Cancel command to stop in-flight reindex

---

### 3. Query Optimization
**Problem:** Hybrid search involves multiple queries (BM25 + vector + RRF).  
**Solution:** Query plan caching, index hints, parallel execution.

**Opportunities:**
- Cache BM25 tokenization results
- Parallel vector + BM25 execution
- EXPLAIN QUERY PLAN analysis for SQLite
- Index covering optimizations for PostgreSQL

---

### 4. Embedding Cache
**Problem:** Re-embedding identical text wastes compute.  
**Solution:** Content-addressed cache (hash → embedding).

**Benefits:**
- Faster reindex for unchanged records
- Lower API costs
- Deterministic embeddings

**Implementation:**
- `kdb_embedding_cache` table (text_hash, model, embedding, created_at)
- SHA256 hash of normalized text
- Automatic cleanup of old cache entries

---

## CLI Commands (New)

```bash
# Background reindex with progress
kameleondb embeddings reindex --background
kameleondb embeddings status  # shows progress

# Cancel in-flight reindex
kameleondb embeddings cancel

# Manage embedding cache
kameleondb embeddings cache status
kameleondb embeddings cache clear [--older-than 30d]
```

---

## Success Metrics

- [ ] Batch insert 30k records in <30 seconds (currently ~2min)
- [ ] Reindex 100k records with progress tracking
- [ ] Cache hit rate >50% on typical reindex
- [ ] Search latency <100ms p95 on 100k records

---

## Implementation Order

1. **Batch embedding** (biggest performance win)
2. **Embedding cache** (reduces API costs)
3. **Background indexing** (UX improvement)
4. **Query optimization** (fine-tuning)

---

## Open Questions

- Should batch size be configurable per provider?
- Cache eviction policy: LRU, time-based, or size-based?
- Background indexing: threads or multiprocessing?
- How to handle schema changes that invalidate embeddings?

---

**Next Step:** Get Marcos's approval, then start with batch embedding implementation.
