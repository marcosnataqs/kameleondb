# ADR-001: Hybrid Storage Architecture

**Status**: Proposed
**Date**: 2026-02-02
**Authors**: KameleonDB Team

## Context

KameleonDB currently uses a single-table design (`kdb_records`) where all entities store their data in one shared table with a JSONB column. This provides maximum flexibility for agents to create and modify schemas on-the-fly without DDL operations.

However, as agent-built applications mature, they often need:
- **Referential integrity** between entities (foreign keys)
- **Cascading operations** (delete customer → delete orders)
- **Optimized joins** for cross-entity queries
- **Table-level isolation** for performance and maintenance

The challenge: How do we support relational structures without sacrificing the flexibility that makes KameleonDB agent-native?

## Decision

Implement a **hybrid storage architecture** with two storage modes:

### Storage Modes

| Mode | Table | Use Case |
|------|-------|----------|
| `shared` | `kdb_records` | Default. Maximum flexibility, no DDL required |
| `dedicated` | `kdb_{entity_name}` | Relational integrity, optimized queries |

### Core Concepts

1. **All entities start in `shared` mode** - preserving current behavior
2. **Entities can be "materialized"** to `dedicated` mode when relationships are needed
3. **Relationships are first-class citizens** with their own metadata tables
4. **Storage mode is transparent** to CRUD operations - same API, different backend

### New Metadata Tables

```sql
-- Track relationships between entities
CREATE TABLE kdb_relationship_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,                    -- e.g., "customer"
    source_entity_id UUID NOT NULL REFERENCES kdb_entity_definitions(id),
    target_entity_id UUID NOT NULL REFERENCES kdb_entity_definitions(id),
    relationship_type VARCHAR(50) NOT NULL,        -- many_to_one, one_to_many, many_to_many
    foreign_key_field VARCHAR(255),                -- field name storing the FK
    on_delete VARCHAR(50) DEFAULT 'SET NULL',      -- CASCADE, SET NULL, RESTRICT
    on_update VARCHAR(50) DEFAULT 'CASCADE',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(255),
    UNIQUE(source_entity_id, name)
);

-- For many-to-many relationships
CREATE TABLE kdb_junction_tables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    relationship_id UUID NOT NULL REFERENCES kdb_relationship_definitions(id),
    table_name VARCHAR(255) NOT NULL,
    source_fk_column VARCHAR(255) NOT NULL,
    target_fk_column VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Entity Definition Changes

```sql
-- Add to kdb_entity_definitions
ALTER TABLE kdb_entity_definitions ADD COLUMN storage_mode VARCHAR(20) DEFAULT 'shared';
ALTER TABLE kdb_entity_definitions ADD COLUMN dedicated_table_name VARCHAR(255);
```

## API Design

### Creating Entities (Unchanged for Basic Use)

```python
# Default: shared storage, maximum flexibility
db.create_entity("Contact", fields=[
    {"name": "email", "type": "string", "unique": True},
    {"name": "name", "type": "string"}
])
# → Stored in kdb_records, no DDL
```

### Creating Entities with Relationships

```python
# When relationships are declared, target entity must be dedicated
db.create_entity("Order", fields=[
    {"name": "total", "type": "float"},
    {"name": "status", "type": "string"}
], relationships=[
    {
        "name": "customer",
        "target": "Contact",
        "type": "many_to_one",
        "on_delete": "CASCADE"
    }
])
# → Auto-materializes Contact if needed
# → Creates kdb_order with customer_id FK
```

### Materializing Existing Entities

```python
# Explicit materialization when relationships emerge
db.materialize_entity("Contact", reason="Adding order relationships")
# → Creates kdb_contact table
# → Migrates data from kdb_records
# → Updates storage_mode in metadata
# → Logs to schema changelog
```

### Defining Relationships Post-Creation

```python
contact = db.entity("Contact")
contact.add_relationship(
    name="orders",
    target="Order",
    type="one_to_many",
    inverse="customer"  # Links to Order.customer
)
```

### Querying Across Relationships

```python
# Find orders with customer data
orders = db.entity("Order").find(
    filters={"status": "pending"},
    include=["customer"]  # Eager load relationship
)
# Returns: [{"id": "...", "total": 99.99, "customer": {"name": "John", ...}}]

# Filter by related entity
orders = db.entity("Order").find(
    filters={"customer.email": "john@example.com"}
)
```

## Implementation Plan

### Phase 1: Foundation (v0.2.0)

**Goal**: Add relationship metadata without changing storage behavior

1. **Create relationship metadata tables**
   - `kdb_relationship_definitions`
   - `kdb_junction_tables`
   - Add `storage_mode` to entity definitions

2. **Extend SchemaEngine**
   - `add_relationship()` method
   - `remove_relationship()` method
   - `list_relationships()` method
   - Relationship validation (circular refs, valid types)

3. **Update schema discovery**
   - Include relationships in `describe()` output
   - Add `describe_relationships()` method

4. **Add MCP tools**
   - `kameleondb_add_relationship`
   - `kameleondb_remove_relationship`
   - `kameleondb_list_relationships`

**Deliverables**:
- Agents can declare relationships as metadata
- No storage changes yet (relationships are "logical")
- Foundation for Phase 2

### Phase 2: Dedicated Storage (v0.2.1)

**Goal**: Enable per-entity tables with foreign keys

1. **Implement DedicatedTableManager**
   - `create_dedicated_table(entity)` - DDL generation
   - `drop_dedicated_table(entity)` - Safe removal
   - `add_foreign_key(relationship)` - FK constraints
   - `remove_foreign_key(relationship)` - FK removal

2. **Implement data migration**
   - `migrate_to_dedicated(entity)` - Move data from shared → dedicated
   - `migrate_to_shared(entity)` - Move data back (for flexibility)
   - Transaction-safe with rollback

3. **Extend JSONBQuery for dedicated tables**
   - Route queries based on storage_mode
   - Same JSONB operators, different table target

4. **Add `materialize_entity()` API**
   - Validates entity is eligible
   - Creates dedicated table
   - Migrates data
   - Updates metadata
   - Logs to changelog

**Deliverables**:
- Agents can materialize entities on demand
- Data migration is safe and reversible
- Same CRUD API works for both modes

### Phase 3: Relational Queries (v0.2.2)

**Goal**: Enable cross-entity queries with joins

1. **Implement RelationalQueryBuilder**
   - JOIN generation for dedicated tables
   - Subquery fallback for shared tables
   - `include` parameter for eager loading

2. **Extend find() API**
   - `include=["relationship_name"]` for eager loading
   - `filters={"relationship.field": value}` for related filtering
   - Automatic join optimization

3. **Implement cascading operations**
   - Honor `on_delete` settings
   - Application-level cascade for shared tables
   - Database-level cascade for dedicated tables

4. **Add relationship-aware MCP tools**
   - Update `kameleondb_find` with `include` parameter
   - Add `kameleondb_find_related`

**Deliverables**:
- Agents can query across relationships
- Cascading deletes work correctly
- Performance optimized for common patterns

### Phase 4: Many-to-Many & Advanced (v0.3.0)

**Goal**: Complete relational support

1. **Implement many-to-many relationships**
   - Auto-generate junction tables
   - `add_to_relationship()` / `remove_from_relationship()` APIs
   - Junction table queries

2. **Add relationship constraints**
   - Required relationships (NOT NULL FK)
   - Unique relationships (one-to-one)
   - Self-referential relationships

3. **Implement relationship indexes**
   - Auto-index foreign key columns
   - Composite indexes for junction tables

4. **Add bulk relationship operations**
   - `connect_many()` / `disconnect_many()`
   - Efficient batch FK updates

**Deliverables**:
- Full relational modeling capability
- Performance at scale
- Feature parity with traditional ORMs

## Migration Strategy

### For Existing Deployments

```python
# Check current storage mode
entity = db.entity("Contact")
print(entity.storage_mode)  # "shared"

# Materialize with zero downtime
db.materialize_entity("Contact",
    reason="Enabling order relationships",
    batch_size=1000  # Migrate in batches
)

# Verify migration
print(entity.storage_mode)  # "dedicated"
print(entity.table_name)    # "kdb_contact"
```

### Rollback Support

```python
# If issues arise, revert to shared storage
db.dematerialize_entity("Contact",
    reason="Reverting due to performance issues"
)
# → Migrates data back to kdb_records
# → Drops dedicated table
# → Relationships become logical-only
```

## Consequences

### Benefits

1. **Progressive complexity** - Start simple, add structure when needed
2. **Agent autonomy preserved** - Shared mode requires no elevated privileges
3. **Relational integrity when needed** - Database-enforced FKs for mature models
4. **Transparent API** - Same CRUD operations regardless of storage mode
5. **Auditable transitions** - All materializations logged to changelog
6. **Reversible decisions** - Can dematerialize if needed

### Trade-offs

1. **Increased complexity** - Two code paths for queries
2. **DDL permissions** - Dedicated mode needs CREATE/DROP TABLE
3. **Migration overhead** - Materializing large entities takes time
4. **Mixed-mode queries** - Joining shared + dedicated entities is complex

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Data loss during migration | Transaction-wrapped, test in staging first |
| Performance regression | Benchmark before/after materialization |
| Agent confusion about modes | Clear error messages, `storage_mode` in describe() |
| Orphaned dedicated tables | Cleanup job, soft-delete pattern |

## Alternatives Considered

### 1. Always Per-Entity Tables
- **Rejected**: Requires DDL for every entity, reduces agent flexibility

### 2. Always Single Table with Application-Level Relationships
- **Rejected**: Can't leverage database FK constraints, poor join performance

### 3. Separate "Relational Mode" Database
- **Rejected**: Complicates deployment, data synchronization issues

### 4. GraphQL-style Resolvers
- **Considered for future**: Could complement this approach for complex queries

## References

- [PostgreSQL JSONB Documentation](https://www.postgresql.org/docs/current/datatype-json.html)
- [Rails Single Table Inheritance](https://api.rubyonrails.org/classes/ActiveRecord/Inheritance.html) - Similar hybrid pattern
- [Prisma Schema Evolution](https://www.prisma.io/docs/concepts/components/prisma-migrate) - Migration patterns
