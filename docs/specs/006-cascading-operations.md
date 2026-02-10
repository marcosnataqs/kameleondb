# Spec 006: Cascading Operations

Phase 3 of Hybrid Storage — enforce `on_delete` behavior at runtime.

## Problem

Relationships can be defined with `on_delete` actions (CASCADE, SET_NULL, RESTRICT), but these are currently metadata-only. When a record is deleted, related records are not affected.

## Design Principles

1. **SQL is the interface** — no new query builder API; agents use SQL via `execute_sql()`
2. **Storage-aware enforcement** — different mechanisms for shared vs dedicated
3. **Application-level for shared** — JSONB storage can't use DB-level FKs
4. **DB-level for dedicated** — use real FK constraints when possible

## On-Delete Actions

| Action | Behavior |
|--------|----------|
| `CASCADE` | Delete related records |
| `SET_NULL` | Set FK field to null on related records |
| `RESTRICT` | Block delete if related records exist |

## Implementation

### Shared Storage (Application-Level)

For entities in `kdb_records`, enforce cascades in Python:

```python
# In Entity.delete() or JSONBQuery.delete()
def delete(self, record_id: str) -> bool:
    # 1. Check RESTRICT relationships
    for rel in self._get_incoming_relationships():
        if rel.on_delete == "RESTRICT":
            related = self._find_related(rel, record_id)
            if related:
                raise RestrictDeleteError(f"Cannot delete: {len(related)} related {rel.source_entity} records exist")
    
    # 2. Handle CASCADE relationships
    for rel in self._get_incoming_relationships():
        if rel.on_delete == "CASCADE":
            self._cascade_delete(rel, record_id)
    
    # 3. Handle SET_NULL relationships
    for rel in self._get_incoming_relationships():
        if rel.on_delete == "SET_NULL":
            self._set_null_related(rel, record_id)
    
    # 4. Delete the record
    return self._do_delete(record_id)
```

### Dedicated Storage (DB-Level)

For materialized entities, use actual FK constraints:

```sql
-- When materializing, create FK with ON DELETE action
ALTER TABLE kdb_order
ADD CONSTRAINT fk_order_customer
FOREIGN KEY (customer_id) REFERENCES kdb_customer(id)
ON DELETE CASCADE;
```

**Migration consideration**: When materializing an entity with relationships, generate appropriate FK constraints based on `on_delete` metadata.

### Mixed Storage (Cross-Mode)

When source and target have different storage modes:

| Source | Target | Enforcement |
|--------|--------|-------------|
| shared | shared | Application-level |
| shared | dedicated | Application-level (source is JSONB) |
| dedicated | shared | Application-level (target is JSONB) |
| dedicated | dedicated | DB-level FK constraints |

Only dedicated→dedicated can use pure DB enforcement.

## API Changes

### Entity.delete() Enhancement

```python
def delete(
    self,
    record_id: str,
    cascade: bool = True,  # Honor on_delete rules
    force: bool = False,   # Bypass RESTRICT (dangerous)
) -> bool:
```

### New Exceptions

```python
class RestrictDeleteError(KameleonDBError):
    """Raised when RESTRICT prevents deletion."""
    def __init__(self, entity: str, related_entity: str, count: int):
        self.entity = entity
        self.related_entity = related_entity
        self.count = count
        super().__init__(
            f"Cannot delete {entity}: {count} related {related_entity} records exist. "
            f"Delete related records first or change on_delete to CASCADE/SET_NULL."
        )
```

### Schema Context Enhancement

Add cascade information to relationship context so LLMs understand the rules:

```python
{
    "name": "customer",
    "source_entity": "Order",
    "target_entity": "Customer",
    "on_delete": "CASCADE",
    "cascade_note": "Deleting a Customer will CASCADE delete all related Orders"
}
```

## Edge Cases

1. **Circular relationships**: Detect and prevent infinite cascade loops
2. **Self-referential**: Entity referencing itself (e.g., Employee → Manager)
3. **Deep cascades**: A → B → C chain should cascade through all levels
4. **Bulk deletes**: `delete_many()` should batch cascade operations efficiently

## Performance

For shared storage, cascade operations require additional queries:
- 1 query to find related records per relationship
- 1 query to delete/update per relationship

Consider batching for entities with many relationships or large datasets.

## Testing

1. CASCADE deletes related records (shared)
2. CASCADE deletes related records (dedicated with FK)
3. SET_NULL nullifies FK field (shared)
4. SET_NULL nullifies FK field (dedicated)
5. RESTRICT blocks delete when related exist
6. RESTRICT allows delete when no related
7. Mixed storage mode cascades
8. Deep cascade chains (A → B → C)
9. Circular relationship detection
10. Bulk delete with cascades

## Migration Path

1. Add cascade logic to `Entity.delete()` / `JSONBQuery.delete()`
2. Update `DedicatedTableManager` to create FK constraints on materialize
3. Add cascade info to `SchemaContextBuilder` output
4. Add tests for all scenarios
5. Update BACKLOG.md → DONE.md

## Out of Scope

- Many-to-many cascades (Phase 4)
- `on_update` enforcement (future)
- Async/background cascade execution
