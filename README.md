<p align="center">
  <img src="./assets/kameleondb-logo.png" alt="KameleonDB Logo" width="350"/>
  <p align="center">
  <a href="https://badge.fury.io/py/kameleondb"><img src="https://badge.fury.io/py/kameleondb.svg" alt="PyPI version"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License: Apache 2.0"></a>
  </p>
</p>

# KameleonDB

**The First Database Built for Agents to Own, Not Just Query**

Most databases let agents query data that humans structured. KameleonDB goes further: **agents own the entire data lifecycle**—from schema design to data ingestion to continuous evolution. You provide the goals and policies, agents build and manage the database.

Built on PostgreSQL (JSONB) or SQLite (JSON1) with schema-as-data storage, agents can restructure information on the fly without migrations, DDL, or human intervention.

## Philosophy: Agents as Data Engineers

In traditional databases, **humans are the data engineers**: they design schemas, write migrations, and structure data for agents to query.

KameleonDB **makes agents the data engineers**. Agents don't just consume data—they design the schema, ingest records, evolve structure, and reshape information as they reason about it. Humans shift from data architects to policy makers, defining what agents can do, not how to structure every field.

This is **schema-on-reason**: structure emerges from agent reasoning, not upfront human design. As agents learn more about the data, they adapt the schema to match their understanding.

**Six First Principles:**

1. **Agent-First Design** — Built for AI agents as primary users, with APIs optimized for reasoning patterns
2. **Schema-on-Reason** — Schema emerges from agent reasoning, not upfront human design
3. **Provenance & Auditability** — Every decision traceable to agent reasoning chains
4. **Policy-Driven Governance** — Agent autonomy bounded by declarative policies, not manual approvals
5. **Security by Design** — Zero-trust architecture where agents are untrusted by default
6. **Enterprise-Grade Reliability** — Production-ready with ACID guarantees and multi-tenancy

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
# Basic installation
pip install kameleondb

# For development
pip install kameleondb[dev]
```

**Requirements**: PostgreSQL 12+ (JSONB) or SQLite 3.9+ (JSON1)

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
- **v0.2**: Relationships + LLM query support ✅
  - Relationship metadata (many-to-one, one-to-many, many-to-many)
  - Schema context for SQL generation
  - Query validation and execution
  - SQLite support
- **v0.3**: Dedicated storage + relational queries (planned)
  - Per-entity tables with FK constraints
  - Cross-entity queries with JOINs
  - Cascading operations
- **v0.4**: Natural language queries (planned)
  - LLM-powered query generation
  - Query caching and optimization

See [docs/tasks/BACKLOG.md](docs/tasks/BACKLOG.md) for detailed roadmap.

## License

Apache 2.0 License - see [LICENSE](LICENSE) for details.
