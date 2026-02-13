# Enhancement #44: Entity Name Filtering

**Problem:** `kdb_records` uses `entity_id` (UUID), making direct SQL filtering by name cumbersome.

## Proposed Solution: Database View

Create a `kdb_records_with_entity` view that includes entity metadata.

### Implementation

**SQLite & PostgreSQL:**
```sql
CREATE VIEW kdb_records_with_entity AS
SELECT 
    r.id,
    r.entity_id,
    e.name AS entity_name,
    r.data,
    r.created_at,
    r.updated_at,
    r.created_by,
    r.updated_by,
    r.is_deleted
FROM kdb_records r
JOIN kdb_entity_definitions e ON r.entity_id = e.id;
```

### Usage

**Before (requires JOIN):**
```sql
SELECT r.* FROM kdb_records r 
JOIN kdb_entity_definitions e ON r.entity_id = e.id 
WHERE e.name = 'Contact' 
LIMIT 10;
```

**After (simple query):**
```sql
SELECT * FROM kdb_records_with_entity 
WHERE entity_name = 'Contact' 
LIMIT 10;
```

### Benefits

1. **Zero migration** - just add view creation to schema setup
2. **Backward compatible** - `kdb_records` table unchanged
3. **Works everywhere** - SQL queries, tools, CLI, programmatic
4. **No storage overhead** - views are computed on-the-fly
5. **Simple** - ~10 lines of SQL in schema setup

### Implementation Checklist

- [ ] Add view creation to `src/kameleondb/core/schema.py`
- [ ] Run on both SQLite and PostgreSQL during `ensure_schema_tables()`
- [ ] Add test: verify view returns correct entity_name
- [ ] Update docs to recommend using view for ad-hoc queries
- [ ] Mention in CLI docs / schema context output

### Code Location

**File:** `src/kameleondb/core/schema.py`  
**Function:** `ensure_schema_tables()` (after kdb_records table creation)

```python
# After creating kdb_records table
with Session(self._engine) as session:
    session.execute(text("""
        CREATE VIEW IF NOT EXISTS kdb_records_with_entity AS
        SELECT 
            r.id,
            r.entity_id,
            e.name AS entity_name,
            r.data,
            r.created_at,
            r.updated_at,
            r.created_by,
            r.updated_by,
            r.is_deleted
        FROM kdb_records r
        JOIN kdb_entity_definitions e ON r.entity_id = e.id
    """))
    session.commit()
```

---

**Estimated effort:** 30 minutes  
**Risk:** Very low (views are non-destructive)  
**Impact:** Improves DX for SQL users significantly
