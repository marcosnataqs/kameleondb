# KameleonDB

**Agent-Native Data Platform**

[![PyPI version](https://badge.fury.io/py/kameleondb.svg)](https://badge.fury.io/py/kameleondb)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

KameleonDB is a meta-layer on top of PostgreSQL where schema is stored as data, not DDL. AI agents can create and modify entity schemas dynamically without migrations. All data is stored in PostgreSQL JSONB for semantic locality and better agent reasoning.

## Philosophy: Schema-on-Reason

Traditional databases use **schema-on-write** (define structure before inserting data) or **schema-on-read** (interpret structure when querying). KameleonDB introduces **schema-on-reason** — where AI agents continuously structure and restructure data as they understand it better.

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
- **PostgreSQL JSONB**: All data stored in native JSONB for semantic locality
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

**Requirements**: PostgreSQL 12+ with JSONB support

## Quick Start

```python
from kameleondb import KameleonDB

# Initialize with PostgreSQL
db = KameleonDB("postgresql://user:pass@localhost/kameleondb")

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

# Query data
results = contacts.find(filters={"first_name": "John"})
print(results)  # [{"id": "...", "first_name": "John", "email": "john@example.com", ...}]

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

KameleonDB uses a **Metadata-driven + JSONB Storage** approach:

1. **Meta-tables** store schema definitions as data
2. **Single data table** (`kdb_records`) with PostgreSQL JSONB column stores all records
3. **No DDL for schema changes** - just metadata updates

```
kdb_entity_definitions  - Entity types (Contact, Deal, Company)
kdb_field_definitions   - Fields for each entity
kdb_schema_changelog    - Audit trail of schema changes

kdb_records            - All data in JSONB column (one row per record)
  ├─ id, entity_id, created_at, updated_at (system columns)
  └─ data JSONB        - All field values in single JSON document
```

**Why JSONB?**
- **Semantic locality**: All record attributes in one row (better for agent reasoning)
- **Simple queries**: `data->>'name' = 'John'` instead of complex joins
- **GIN indexes**: Fast queries on JSONB paths
- **Zero-lock evolution**: Adding fields is just metadata, no DDL

## Supported Field Types

All types are stored in PostgreSQL JSONB and cast when querying:

| Type | Storage in JSONB | Query Example |
|------|------------------|---------------|
| string | text | `data->>'field'` |
| text | text | `data->>'field'` |
| int | number | `(data->>'field')::int` |
| float | number | `(data->>'field')::numeric` |
| bool | boolean | `(data->>'field')::boolean` |
| datetime | text (ISO) | `(data->>'field')::timestamptz` |
| json | nested JSONB | `data->'field'` |
| uuid | text | `(data->>'field')::uuid` |

**PostgreSQL JSONB Operators**:
- `data->>'field'` - Extract as text
- `data @> '{"field": "value"}'` - Containment (uses GIN index)
- `data ? 'field'` - Check if key exists

## Development

```bash
# Clone the repository
git clone https://github.com/kameleondb/kameleondb.git
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

- **v0.1**: Core schema engine (current)
- **v0.2**: Agent framework integrations (LangChain, Claude, OpenAI)
- **v0.3**: Vector search integration
- **v0.4**: LLM-based structured extraction

## License

MIT License - see [LICENSE](LICENSE) for details.
