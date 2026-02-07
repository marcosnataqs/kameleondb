# KameleonDB Architecture

This document provides technical implementation details for KameleonDB's architecture, storage systems, and agent integration patterns.

## Overview

KameleonDB uses a **Metadata-driven + JSON Storage** approach:

1. **Meta-tables** store schema definitions as data
2. **Single data table** (`kdb_records`) with JSON column stores all records
3. **No DDL for schema changes** - just metadata updates

```
kdb_entity_definitions  - Entity types (Contact, Deal, Company)
kdb_field_definitions   - Fields for each entity
kdb_schema_changelog    - Audit trail of schema changes

kdb_records            - All data in JSON column (one row per record)
  ├─ id, entity_id, created_at, updated_at (system columns)
  └─ data JSON         - All field values in single JSON document
```

### Why JSON Storage?

- **Semantic locality**: All record attributes in one row (better for agent reasoning)
- **Simple queries**: PostgreSQL `data->>'name'` or SQLite `json_extract(data, '$.name')`
- **Indexing**: GIN indexes (PostgreSQL) for fast JSON queries
- **Zero-lock evolution**: Adding fields is just metadata, no DDL

## Hybrid Storage System

KameleonDB supports two storage modes:

- **Shared storage** (default): All entities store records in the `kdb_records` JSONB table. Maximum flexibility, zero DDL for schema changes.
- **Dedicated storage**: Each entity gets its own table with typed columns and foreign key constraints. Enables database-enforced referential integrity and optimized JOINs.

### When to Use Dedicated Storage

Materialize an entity to dedicated storage when:
- You need foreign key constraints for data integrity
- Queries frequently JOIN this entity with others
- Query performance is slow (>100ms) and the entity has many records (>10k)

### Materialization Example

```python
from kameleondb import KameleonDB

db = KameleonDB("postgresql://localhost/mydb")

# Create entities with relationships
db.create_entity("Customer", fields=[
    {"name": "name", "type": "string"},
    {"name": "email", "type": "string", "unique": True},
])

db.create_entity("Order", fields=[
    {"name": "total", "type": "float"},
    {"name": "status", "type": "string"},
])

# Add relationship (stored as metadata initially)
orders = db.entity("Order")
orders.add_relationship(
    name="customer",
    target="Customer",
    relationship_type="many_to_one",
)

# Later, materialize for FK constraints and better JOIN performance
result = db.materialize_entity("Customer", reason="Enabling FK constraints")
print(f"Migrated {result['records_migrated']} records to {result['table_name']}")

# Now foreign key constraints are enforced at database level
# Queries with JOINs will be faster
```

## Query Intelligence (Agent Hints Pattern)

**Agent-First Principle**: All query operations return performance metrics and optimization hints inline. Agents don't need to know about special "with_metrics" functions - intelligence is always included.

```python
# Execute SQL - always returns metrics and hints
result = db.execute_sql("""
    SELECT o.id, o.data->>'total' as total, c.data->>'name' as customer
    FROM kdb_records o
    JOIN kdb_records c ON c.id::text = o.data->>'customer_id'
    WHERE o.entity_id = '...'
""", entity_name="Order")

# Access query results
print(f"Found {len(result.rows)} orders")

# Check performance metrics (always included)
print(f"Query took {result.metrics.execution_time_ms}ms")

# Check optimization hints (always included)
for suggestion in result.suggestions:
    print(f"{suggestion.priority}: {suggestion.reason}")
    print(f"Action: {suggestion.action}")
    # Example: "high: Query took 450ms (threshold: 100ms)"
    #          "Action: db.materialize_entity('Order')"

# Get historical stats for deeper analysis
stats = db.get_entity_stats("Customer")
if stats.suggestion:
    print(f"Historical pattern: {stats.suggestion}")
```

**Why this matters for agents**: All operations proactively provide actionable intelligence. No need to know about special "metrics" functions - hints are always included. This follows the agent-first principle - the database helps agents self-optimize.

## Field Types and Database Mapping

All types are stored in JSON and cast when querying:

| Type | PostgreSQL Query | SQLite Query |
|------|------------------|--------------|
| string | `data->>'field'` | `json_extract(data, '$.field')` |
| text | `data->>'field'` | `json_extract(data, '$.field')` |
| int | `(data->>'field')::int` | `CAST(json_extract(data, '$.field') AS INTEGER)` |
| float | `(data->>'field')::numeric` | `CAST(json_extract(data, '$.field') AS REAL)` |
| bool | `(data->>'field')::boolean` | `json_extract(data, '$.field')` |
| datetime | `(data->>'field')::timestamptz` | `json_extract(data, '$.field')` |
| json | `data->'field'` | `json_extract(data, '$.field')` |
| uuid | `(data->>'field')::uuid` | `json_extract(data, '$.field')` |

> **Note**: In dedicated storage mode, these types map to native PostgreSQL/SQLite column types with proper constraints. In shared storage mode (default), all values are stored in JSONB/JSON and cast when querying.

### PostgreSQL Operators

- `data->>'field'` - Extract as text
- `data @> '{"field": "value"}'` - Containment (uses GIN index)
- `data ? 'field'` - Check if key exists

### SQLite Functions

- `json_extract(data, '$.field')` - Extract field value
- `json_type(data, '$.field')` - Get JSON type

## Agent Integration Patterns

KameleonDB is designed for AI agents. All operations are tool-friendly:

```python
# Get all operations as tools
tools = db.get_tools()

# Each tool has:
# - name: "kameleondb_create_entity"
# - description: Human-readable description
# - parameters: JSON Schema for inputs
# - function: Callable to execute
```

### Error Messages Guide Agents

```python
# Instead of cryptic errors:
# "KeyError: 'email'"

# KameleonDB returns actionable messages:
# "Field 'email' not found on 'Contact'. Available fields: first_name, last_name, phone"
```

All public methods:
- Accept JSON-serializable parameters (primitives, dicts, lists)
- Return JSON-serializable results
- Support `if_not_exists` for idempotency
- Include actionable error messages with available options

---

## See Also

- [README.md](../README.md) - Getting started guide
- [FIRST-PRINCIPLES.md](../FIRST-PRINCIPLES.md) - Design philosophy
- [AGENTS.md](../AGENTS.md) - Complete agent-native design guide
- [CLAUDE.md](../CLAUDE.md) - Project documentation for Claude Code
