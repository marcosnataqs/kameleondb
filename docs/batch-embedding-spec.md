# Batch Embedding Implementation Spec

**Status:** DRAFT  
**Phase:** Layer 2 - Phase 3  
**Priority:** #1 (biggest performance win)  
**Author:** Byte  
**Date:** 2026-02-15

---

## Problem

Current implementation calls `provider.embed(text)` individually for each record:
- Stress test: 30k inserts take ~2 minutes
- Target: <30 seconds
- Bottleneck: One-by-one embedding calls despite providers supporting batching

---

## Solution Overview

Introduce batch embedding API that:
1. Collects texts from multiple records
2. Calls `provider.embed_batch(texts)` once
3. Batch inserts all search index rows

---

## Current State Analysis

### ✅ Already Implemented
- `EmbeddingProvider.embed_batch()` interface (provider.py:44-53)
- `FastEmbedProvider.embed_batch()` implementation (fastembed.py:63-73)
- `OpenAIProvider.embed_batch()` implementation (openai.py:65-93)

### 🔴 Missing
- Batch API in `SearchEngine`
- CLI integration for batch operations
- Transaction-scoped embedding queue

---

## Proposed API

### SearchEngine Methods

```python
class SearchEngine:
    def index_records_batch(
        self,
        records: list[tuple[str, str, str]],  # [(entity_name, record_id, content)]
    ) -> None:
        """Index multiple records in one batch.
        
        Significantly faster than calling index_record() in a loop.
        """
        if not records:
            return
        
        if not self._provider:
            # BM25 only - can still batch insert
            self._batch_insert_bm25_only(records)
            return
        
        # Extract texts and generate embeddings in batch
        texts = [content for _, _, content in records]
        embeddings = self._provider.embed_batch(texts)
        
        # Batch insert into kdb_search
        with Session(self._engine) as session:
            if self._is_postgresql:
                self._batch_insert_postgresql(session, records, embeddings)
            else:
                self._batch_insert_sqlite(session, records, embeddings)
            session.commit()
```

### CLI Integration

```bash
# Reindex with batch processing (default behavior)
kameleondb embeddings reindex Contact --batch-size 100

# Manual batch index from JSONL
kameleondb data insert Contact < records.jsonl --batch-size 100
```

---

## Implementation Plan

### Phase 1: Core Batch API (1-2 hours)
1. Add `SearchEngine.index_records_batch()` method
2. Add `_batch_insert_postgresql()` helper
3. Add `_batch_insert_sqlite()` helper
4. Unit tests: batch insert 100/1000 records

### Phase 2: CLI Integration (1 hour)
1. Modify `data insert` to detect batch input (list of dicts)
2. Add `--batch-size` parameter for reindex
3. Update `embeddings reindex` to use batch API
4. Integration tests: CLI batch insert

### Phase 3: Auto-batching in Transactions (2 hours)
1. Add `_embedding_queue` to SearchEngine
2. Queue embeddings during `index_record()` calls
3. Flush queue on transaction commit
4. Tests: transaction-scoped batching

---

## PostgreSQL Batch Insert

```sql
-- Multi-row INSERT with ON CONFLICT
INSERT INTO kdb_search (id, entity_name, record_id, content, embedding, model, dimensions)
VALUES 
    ($1, $2, $3, $4, $5::vector, $6, $7),
    ($8, $9, $10, $11, $12::vector, $13, $14),
    ...
ON CONFLICT (entity_name, record_id) DO UPDATE SET
    content = EXCLUDED.content,
    embedding = EXCLUDED.embedding,
    updated_at = NOW()
```

**Note:** PostgreSQL supports multi-row VALUES efficiently. Can batch up to 1000 rows per statement.

---

## SQLite Batch Insert

```sql
-- Use executemany() with INSERT OR REPLACE
INSERT OR REPLACE INTO kdb_search (id, entity_name, record_id, content, embedding, model, dimensions, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
```

**Note:** SQLite executemany() handles batching internally. No need for manual multi-row VALUES.

---

## Batch Size Recommendations

| Provider | Default Batch Size | Max Batch Size | Notes |
|----------|-------------------|----------------|-------|
| FastEmbed | 100 | 1000 | Limited by memory, not API |
| OpenAI | 100 | 2048 | API limit per request |
| PostgreSQL | 100 | 1000 | Multi-row INSERT sweet spot |
| SQLite | 100 | 10000 | executemany() handles large batches |

**Recommendation:** Default to 100, allow CLI override.

---

## Performance Impact Estimate

**Current (stress test baseline):**
- 30k inserts: ~120 seconds
- Bottleneck: 30k individual `provider.embed()` calls

**After batch embedding:**
- 30k inserts: ~25-30 seconds (4-5x speedup)
- Breakdown:
  - Embedding: 300 batches × 100ms = 30s → 3s (10x faster)
  - Insert: 15s → 10s (batch SQL inserts)

**Conservative estimate:** **4x overall speedup**, hitting Phase 3 target.

---

## Testing Strategy

### Unit Tests
- `test_index_records_batch_empty()` - empty list handling
- `test_index_records_batch_small()` - 10 records
- `test_index_records_batch_large()` - 1000 records
- `test_index_records_batch_no_provider()` - BM25-only mode

### Integration Tests
- Stress test: 30k records in <30s
- CLI: `data insert` with JSONL array
- Reindex: existing records with batch API

### Regression Tests
- Single `index_record()` still works
- Batch with mixed entity types
- Transaction rollback behavior

---

## Migration Path

### Backward Compatibility
- Keep existing `index_record()` method unchanged
- Add new `index_records_batch()` method
- CLI detects batch input automatically

### Opt-in for Phase 3.1
- `embeddings reindex` uses batch API (internal change)
- `data insert` auto-detects list input (backward compatible)
- No breaking changes

---

## Next Steps

1. **Get approval** - Review with Marcos
2. **Create issue** - `[Phase 3] Implement batch embedding API`
3. **Implement Phase 1** - Core batch API + tests
4. **Validate performance** - Run stress test
5. **Ship it** - Merge and update Phase 3 status

---

## Open Questions

1. **Should we make batching automatic?** (queue during transaction, flush on commit)
   - Pro: Zero API changes, transparent optimization
   - Con: More complex, harder to debug
   - **Recommendation:** Start with explicit batch API, add auto-batching in Phase 3.3

2. **Batch size tuning?** 
   - Pro: User can optimize for their workload
   - Con: More configuration complexity
   - **Recommendation:** Default to 100, expose `--batch-size` for power users

3. **Progress reporting for large batches?**
   - Pro: Better UX for 10k+ record operations
   - Con: Adds complexity
   - **Recommendation:** Add in Phase 3.2 (background indexing)

---

## References

- Phase 3 Plan: `docs/layer2-phase3-plan.md`
- Provider Interface: `src/kameleondb/embeddings/provider.py`
- FastEmbed Implementation: `src/kameleondb/embeddings/fastembed.py`
- SearchEngine: `src/kameleondb/search/engine.py`
