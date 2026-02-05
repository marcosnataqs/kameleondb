# Hybrid Storage Architecture

Two storage modes for flexibility vs. relational integrity trade-off.

## Storage Modes

| Mode | Table | Use Case |
|------|-------|----------|
| `shared` | `kdb_records` | Default. Maximum flexibility, no DDL |
| `dedicated` | `kdb_{entity}` | Relational integrity, optimized joins |

## How It Works

1. **All entities start in `shared` mode** - single JSONB table, no DDL needed
2. **Entities can be "materialized"** to `dedicated` mode when relationships need FK constraints
3. **Relationships are metadata** - stored in `kdb_relationship_definitions`
4. **Same CRUD API** regardless of storage mode

## API Examples

### Basic Entity (Shared Storage)

```python
# Default: shared storage, no DDL
db.create_entity("Contact", fields=[
    {"name": "email", "type": "string", "unique": True},
    {"name": "name", "type": "string"}
])
```

### Entity with Relationships

```python
# Declaring relationships
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
```

### Materializing an Entity

```python
# Move from shared → dedicated table
db.materialize_entity("Contact", reason="Adding FK constraints")

# Creates kdb_contact table
# Migrates data from kdb_records
# Updates storage_mode in metadata
```

### Querying with Relationships

```python
# Get schema context for SQL generation
context = db.get_schema_context(entities=["Order", "Contact"])

# Execute validated SQL (relationship joins included in context)
results = db.execute_sql("""
    SELECT o.id, o.data->>'total' as total, c.data->>'name' as customer_name
    FROM kdb_records o
    JOIN kdb_records c ON o.data->>'customer_id' = c.id::text
    WHERE o.entity_id = '...' AND o.data->>'status' = 'pending'
""")
```

## Database Schema

### Relationship Metadata

```sql
CREATE TABLE kdb_relationship_definitions (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    source_entity_id UUID REFERENCES kdb_entity_definitions(id),
    target_entity_id UUID REFERENCES kdb_entity_definitions(id),
    relationship_type VARCHAR(50),  -- many_to_one, one_to_many, etc.
    foreign_key_field VARCHAR(255),
    on_delete VARCHAR(50) DEFAULT 'SET NULL',
    on_update VARCHAR(50) DEFAULT 'CASCADE',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Entity Definition Extensions

```sql
ALTER TABLE kdb_entity_definitions
ADD COLUMN storage_mode VARCHAR(20) DEFAULT 'shared';

ALTER TABLE kdb_entity_definitions
ADD COLUMN dedicated_table_name VARCHAR(255);
```

## Relationship Types

| Type | Description | FK Location |
|------|-------------|-------------|
| `many_to_one` | Order → Customer | `order.customer_id` |
| `one_to_many` | Customer → Orders | Inverse of many_to_one |
| `one_to_one` | User → Profile | Either side |
| `many_to_many` | Product ↔ Tag | Junction table |

## Trade-offs

**Shared mode:**
- No DDL permissions needed
- Maximum flexibility
- No database-level FK constraints
- Joins via application logic

**Dedicated mode:**
- Requires CREATE/DROP TABLE permissions
- Database-enforced referential integrity
- Optimized JOIN performance
- Migration overhead for large entities
