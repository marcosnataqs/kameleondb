# Layer 2 Phase 2 - CLI Commands Plan

**Goal:** Expose hybrid search + embedding management through CLI

## Commands to Add

### 1. `kameleondb search` (NEW)

```bash
# Basic search
kameleondb search Entity "query text"

# With options
kameleondb search Entity "query" \
  --limit 10 \
  --mode hybrid  # hybrid|vector|keyword \
  --threshold 0.5

# JSON output
kameleondb search Entity "query" --json
```

**Output format:**
```json
{
  "results": [
    {
      "record_id": "...",
      "score": 0.95,
      "content": "...",
      "data": {...}
    }
  ],
  "count": 5,
  "mode": "hybrid"
}
```

### 2. `kameleondb embeddings status` (NEW)

```bash
# Show embedding configuration and stats
kameleondb embeddings status

# JSON output
kameleondb embeddings status --json
```

**Output:**
```json
{
  "provider": "fastembed",
  "model": "all-MiniLM-L6-v2",
  "dimensions": 384,
  "indexed_entities": [
    {
      "name": "Contact",
      "embedded_fields": ["name", "bio"],
      "record_count": 1234,
      "indexed_count": 1234
    }
  ]
}
```

### 3. `kameleondb embeddings reindex` (NEW)

```bash
# Reindex all entities
kameleondb embeddings reindex

# Reindex specific entity
kameleondb embeddings reindex Contact

# Force reindex (even if already indexed)
kameleondb embeddings reindex Contact --force
```

## Implementation Checklist

- [ ] Create `src/kameleondb/cli/commands/search.py`
- [ ] Add `search` subcommand with query, limit, mode, threshold args
- [ ] Add `embeddings` subcommand group
- [ ] Add `embeddings status` - show provider, stats, indexed entities
- [ ] Add `embeddings reindex` - trigger reindexing
- [ ] Wire up to main CLI app
- [ ] Add CLI tests for all new commands
- [ ] Update docs/CLI.md with new commands

## Auto-reindex on Update

**Approach:** Hook into `entity.update()` to trigger re-embedding

```python
# In core/entity.py
def update(self, record_id: str, updates: dict, ...):
    # ... existing update logic ...
    
    # If entity has embeddings configured, reindex
    if self._has_embeddings():
        self._db.search.reindex_record(self.name, record_id)
```

## Files to Create/Modify

```
src/kameleondb/cli/commands/
  ├── search.py          # NEW - search + embeddings commands
  
src/kameleondb/core/
  ├── entity.py          # MODIFY - add auto-reindex on update
  
tests/unit/
  ├── test_cli_search.py # NEW - CLI search tests
```

## Open Questions

1. **Default search mode:** hybrid or vector? (Suggest: hybrid)
2. **Reindex scope:** Should `reindex` batch all records or one-by-one?
3. **Background jobs:** Should reindex run async for large datasets?

---

**Next Steps:**
1. Get approval on CLI interface design
2. Implement `search.py` command file
3. Add auto-reindex hook
4. Write tests
