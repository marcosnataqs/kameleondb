# KameleonDB Agent Context

This file provides guidance to AI agents working with code in this repository.

## Project Documentation

- **[docs/tasks/](docs/tasks/)** - Task tracking (BACKLOG, CURRENT, DONE)
- **[docs/specs/](docs/specs/)** - Feature specifications before implementation
- **[docs/notes/](docs/notes/)** - Research and exploration notes

## First Principles

KameleonDB is built on seven foundational principles that guide all architectural decisions:

### 1. Radical Simplicity

Perfection is achieved by removing things, not adding them.

- The most sophisticated systems are the simplest ones that solve the problem
- Every abstraction, layer, and feature must justify its existence
- When in doubt, remove it—complexity is the enemy of reliability
- Code that doesn't exist has no bugs, needs no maintenance, and runs infinitely fast
- "Keep it simple, stupid" is not a limitation, it's the highest engineering discipline

**Implication:** Before adding anything, ask "Can we solve this by removing something instead?"

### 2. Agent-First Design

All capabilities are built for AI agents as primary users, not humans.

- APIs optimized for agent reasoning patterns (observe → reason → act)
- Operations return reasoning context, not just results
- Documentation written for LLM consumption (structured, unambiguous)
- Human interfaces are observability layers, not operational requirements

**Implication:** We don't ask "Can a human use this?" We ask "Can an agent reason about this?"

### 3. Schema-on-Reason

Schema emerges from continuous agent reasoning, not upfront human design.

- Agents discover, propose, and evolve ontologies dynamically
- Schema changes are data operations, not migrations
- Multiple schema views can coexist (different agents, different understandings)
- Schema evolution is versioned and reversible

**Implication:** The database adapts to what agents learn, not what humans predicted.

### 4. Provenance & Auditability

Every schema decision and data transformation must be traceable to agent reasoning.

- All schema changes logged with justification chains
- Complete lineage: source → extraction → field → query
- Reasoning traces are queryable metadata
- Rollback capability for any ontological change
- "Why does this field exist?" is always answerable

**Implication:** Trust comes from transparency, not black-box magic.

### 5. Policy-Driven Governance

Agent autonomy is bounded by declarative policies, not manual approvals.

- Governance rules defined as policies agents must follow
- Agents operate freely within policy bounds
- Policy violations trigger human review, not silent failures
- Compliance requirements (PII handling, data retention) encoded as constraints
- Quality gates (validation rules, consistency checks) enforced automatically

**Implication:** Governance scales through automation, not gatekeepers.

### 6. Security by Design

Zero-trust architecture where agents are untrusted by default.

- Least-privilege access for all agent operations
- Credential isolation (agents never handle source authentication directly)
- Capability-based permissions (grant specific powers, not broad access)
- All agent actions audited with identity tracking
- Data access controls respected through dynamic schema layer

**Implication:** Agents are powerful tools, not privileged users.

### 7. Enterprise-Grade Reliability

Built for production workloads where downtime and data loss are unacceptable.

- Multi-tenancy with strong isolation guarantees
- ACID transactions for schema operations
- High availability and disaster recovery built-in
- Performance at scale (millions of documents, thousands of concurrent agents)
- SLA-grade monitoring and observability
- Migration paths from existing systems (not rip-and-replace)

**Implication:** Innovative architecture, production-grade execution.

## Build & Development Commands

```bash
# Create virtual environment and install
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run all tests
pytest tests/

# Run single test file
pytest tests/unit/test_query.py

# Run single test
pytest tests/unit/test_query.py::TestQueryOperations::test_insert_and_find -v

# Run with coverage
pytest tests/ --cov=src/kameleondb

# Linting
ruff check src tests
ruff format src tests

# Type checking
mypy src/kameleondb --ignore-missing-imports
```

## Architecture

KameleonDB is an Agent-Native Data Platform with JSON-first storage. It provides a meta-layer on top of PostgreSQL or SQLite where schema is stored as data, not DDL, and all record data is stored in JSON columns for semantic locality.

**Supported Databases:**
- PostgreSQL 12+ (JSONB with GIN indexes)
- SQLite 3.9+ (JSON1 extension)

### Core Pattern: Metadata-driven + JSON Storage

The system uses two layers of tables:
1. **Meta-tables** (`kdb_entity_definitions`, `kdb_field_definitions`, `kdb_schema_changelog`) - Store schema definitions as data
2. **Data table** (`kdb_records`) - Single table with JSON column storing all field values

### Key Components

- **`core/engine.py`** - `KameleonDB` (main entry point) and `Entity` (per-entity CRUD operations)
- **`schema/engine.py`** - `SchemaEngine` manages entity/field definitions in meta-tables
- **`data/table_manager.py`** - `TableManager` ensures JSONB tables exist (no DDL for schema changes)
- **`data/jsonb_query.py`** - `JSONBQuery` handles CRUD operations using PostgreSQL JSONB operators
- **`tools/registry.py`** - `ToolRegistry` exports operations as agent tools (OpenAI/Anthropic format)

### Data Flow

1. Agent calls `db.create_entity("Contact", fields=[...])`:
   - `SchemaEngine` stores entity/field metadata in `kdb_entity_definitions` and `kdb_field_definitions`
   - No table DDL required - `kdb_records` already exists with JSONB column

2. Agent calls `entity.add_field("phone", field_type="string")`:
   - `SchemaEngine` adds field to `kdb_field_definitions`
   - No DDL required - new records can include `phone` in JSONB data
   - Old records show `phone=None` when queried

3. Agent generates SQL via `db.get_schema_context()` and `db.execute_sql()`:
   - `SchemaContextBuilder` provides schema info for LLM SQL generation
   - `QueryValidator` validates SQL before execution (injection protection)
   - Uses JSONB queries: `WHERE data->>'name' = 'John'`

### Agent-First Design

All public methods:
- Accept JSON-serializable parameters (primitives, dicts, lists)
- Return JSON-serializable results
- Support `if_not_exists` for idempotency
- Include actionable error messages with available options

### Type Mapping

All field values are stored in JSON and cast when querying:

| Type | PostgreSQL | SQLite |
|------|------------|--------|
| string | `data->>'field'` | `json_extract(data, '$.field')` |
| int | `(data->>'field')::int` | `CAST(json_extract(...) AS INTEGER)` |
| float | `(data->>'field')::numeric` | `CAST(json_extract(...) AS REAL)` |
| bool | `(data->>'field')::boolean` | `json_extract(data, '$.field')` |
| datetime | `(data->>'field')::timestamptz` | `json_extract(data, '$.field')` |
| json | `data->'field'` | `json_extract(data, '$.field')` |

**PostgreSQL Operators**: `data->>'field'`, `data @> '{...}'`, `data ? 'field'`
**SQLite Functions**: `json_extract(data, '$.field')`, `json_type(data, '$.field')`

## Query Generation

For complex queries, agents should use the schema context API:

```python
# Get schema context for SQL generation
context = db.get_schema_context(entities=["Customer", "Order"])

# Execute validated SQL
results = db.execute_sql("SELECT ... FROM kdb_records WHERE ...", read_only=True)
```

See `query/context.py` and `query/validator.py` for implementation details.
