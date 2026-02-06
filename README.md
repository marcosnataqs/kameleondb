<p align="center">
  <img src="./assets/kameleondb-logo.png" alt="KameleonDB Logo" width="350"/>
  <p align="center">
  <a href="https://badge.fury.io/py/kameleondb"><img src="https://badge.fury.io/py/kameleondb.svg" alt="PyPI version"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License: Apache 2.0"></a>
  </p>
</p>

# KameleonDB

*Find the true color of your data.*

**The First Database Built for Agents to Own, Not Just Query**

Most databases let agents query data that humans structured. KameleonDB goes further: **agents own the entire data lifecycle**—from schema design to data ingestion to continuous evolution. You provide the goals and policies, agents build and manage the database.

Built on PostgreSQL (JSONB) or SQLite (JSON1) with schema-as-data storage, agents can restructure information on the fly without migrations, DDL, or human intervention.

## Philosophy: Agents as Data Engineers

In traditional databases, **humans are the data engineers**: they design schemas, write migrations, and structure data for agents to query.

KameleonDB **makes agents the data engineers**. Agents don't just consume data—they design the schema, ingest records, evolve structure, and reshape information as they reason about it. Humans shift from data architects to policy makers, defining what agents can do, not how to structure every field.

This is **schema-on-reason**: structure emerges from agent reasoning, not upfront human design. As agents learn more about the data, they adapt the schema to match their understanding.

**Seven First Principles:**

1. **Radical Simplicity** — Perfection is achieved by removing things, not adding them
2. **Agent-First Design** — Built for AI agents as primary users, with APIs optimized for reasoning patterns
3. **Schema-on-Reason** — Schema emerges from agent reasoning, not upfront human design
4. **Provenance & Auditability** — Every decision traceable to agent reasoning chains
5. **Policy-Driven Governance** — Agent autonomy bounded by declarative policies, not manual approvals
6. **Security by Design** — Zero-trust architecture where agents are untrusted by default
7. **Enterprise-Grade Reliability** — Production-ready with ACID guarantees and multi-tenancy

See [AGENTS.md](AGENTS.md) for complete details.

## Features

- **Dynamic Schema**: Create and modify entity fields at runtime without migrations
- **Multi-Database**: PostgreSQL (JSONB) and SQLite (JSON1) support
- **Agent-First Design**: Every operation is a tool for AI agents with JSON-serializable I/O
- **Self-Describing**: Agents can discover schema before querying
- **Idempotent Operations**: Safe for agents to call repeatedly
- **Audit Trail**: Track who made schema changes and why
- **Zero-Lock Evolution**: Schema changes are metadata-only, no table locks

## Installation

```bash
# Core only (SQLite works out of the box)
pip install kameleondb

# With PostgreSQL support
pip install kameleondb[postgresql]

# With MCP server
pip install kameleondb[mcp]

# For development
pip install kameleondb[dev,postgresql]

# Everything
pip install kameleondb[all]
```

**Database Requirements**:
- **SQLite**: 3.9+ with JSON1 extension (included in Python stdlib)
- **PostgreSQL**: 12+ with JSONB support

## Quick Start

```python
from kameleondb import KameleonDB

# Initialize with PostgreSQL
db = KameleonDB("postgresql://user:pass@localhost/kameleondb")

# Or use SQLite for development/testing
# db = KameleonDB("sqlite:///./kameleondb.db")

# Create an entity with fields
contacts = db.create_entity(
    name="Contact",
    fields=[
        {"name": "first_name", "type": "string", "required": True},
        {"name": "email", "type": "string", "unique": True},
    ],
    created_by="my-agent",
    if_not_exists=True,  # Idempotent - safe to call multiple times
)

# Add a field later (with reasoning for audit)
contacts.add_field(
    name="linkedin_url",
    field_type="string",
    created_by="enrichment-agent",
    reason="Found LinkedIn profiles in documents",
    if_not_exists=True,
)

# Insert data
contact_id = contacts.insert({
    "first_name": "John",
    "email": "john@example.com",
})

# Retrieve by ID
contact = contacts.find_by_id(contact_id)
print(contact)  # {"id": "...", "first_name": "John", "email": "john@example.com", ...}

# For complex queries, use SQL generation via schema context
context = db.get_schema_context()
# Use context with an LLM to generate SQL, then:
# results = db.execute_sql("SELECT ... FROM kdb_records WHERE ...")

# Discover schema (agents call this first)
schema = db.describe()
print(schema)
# {
#     "entities": {
#         "Contact": {
#             "fields": ["first_name", "email", "linkedin_url"],
#             ...
#         }
#     }
# }
```

## Command-Line Interface

KameleonDB includes a powerful CLI for database management and agent development.

```bash
# Initialize a database
kameleondb init

# Create an entity
kameleondb schema create Contact \
  --field "name:string:required" \
  --field "email:string:unique"

# Insert data (inline JSON)
kameleondb data insert Contact '{"name": "Alice", "email": "alice@example.com"}'

# Insert from JSON file
kameleondb data insert Contact --from-file contact.json

# Batch insert from JSONL
kameleondb data insert Contact --from-file contacts.jsonl --batch

# List entities
kameleondb schema list

# Query with SQL
kameleondb query run "SELECT * FROM kdb_records LIMIT 10"

# Get schema context for LLM SQL generation
kameleondb schema context

# Check database info
kameleondb info
```

**JSON Output Mode** (for agents and scripts):

```bash
# All commands support --json flag
kameleondb --json schema list | jq .
kameleondb --json data list Contact
```

**Available Commands:**
- `schema` - Create, list, describe, modify entities
- `data` - Insert, get, update, delete, list records
- `query` - Execute and validate SQL
- `storage` - Materialize entities, check storage mode
- `admin` - Initialize, info, changelog

See `kameleondb --help` for full command reference.

## Hybrid Storage

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

### Query Intelligence (Agent Hints Pattern)

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

## Agent Integration

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

## Architecture

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

**Why JSON storage?**
- **Semantic locality**: All record attributes in one row (better for agent reasoning)
- **Simple queries**: PostgreSQL `data->>'name'` or SQLite `json_extract(data, '$.name')`
- **Indexing**: GIN indexes (PostgreSQL) for fast JSON queries
- **Zero-lock evolution**: Adding fields is just metadata, no DDL

## Supported Field Types

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

**PostgreSQL Operators**:
- `data->>'field'` - Extract as text
- `data @> '{"field": "value"}'` - Containment (uses GIN index)
- `data ? 'field'` - Check if key exists

**SQLite Functions**:
- `json_extract(data, '$.field')` - Extract field value
- `json_type(data, '$.field')` - Get JSON type

## Development

```bash
# Clone the repository
git clone https://github.com/marcosnataqs/kameleondb.git
cd kameleondb

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src tests
mypy src/kameleondb

# Run pre-commit hooks
pre-commit install
pre-commit run --all-files
```

## Roadmap

- **v0.1**: Core schema engine ✅
- **v0.2**: Relationships + Hybrid Storage + Query Intelligence ✅
  - Relationship metadata (many-to-one, one-to-many, many-to-many)
  - Schema context for SQL generation
  - Query validation and execution
  - SQLite support
  - Hybrid storage (shared/dedicated modes)
  - Storage migration (materialize/dematerialize)
  - Query metrics and materialization suggestions
- **v0.3**: Relational queries + Many-to-many (planned)
  - Cross-entity queries with JOINs
  - Cascading operations
  - Many-to-many junction tables
- **v0.4**: Natural language queries (planned)
  - LLM-powered query generation
  - Query caching and optimization

See [docs/tasks/BACKLOG.md](docs/tasks/BACKLOG.md) for detailed roadmap.

## License

Apache 2.0 License - see [LICENSE](LICENSE) for details.
