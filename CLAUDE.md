# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Documentation

```
docs/
├── tasks/
│   ├── BACKLOG.md    # Future work and ideas
│   ├── CURRENT.md    # Active tasks (check this first!)
│   └── DONE.md       # Completed work log
├── specs/            # Feature specifications
│   └── 001-hybrid-storage.md
└── notes/            # Research and scratchpad
```

**Workflow:**
1. Check `docs/tasks/CURRENT.md` at session start
2. Move tasks from `BACKLOG.md` → `CURRENT.md` when starting work
3. Move completed tasks to `DONE.md` with date
4. Create specs in `docs/specs/` before building complex features

## First Principles

KameleonDB follows six core principles (see [AGENTS.md](AGENTS.md) for full details):

1. **Agent-First Design** - APIs optimized for agent reasoning patterns, not human convenience
2. **Schema-on-Reason** - Schema emerges from agent reasoning, not upfront human design
3. **Provenance & Auditability** - All decisions traceable to reasoning chains
4. **Policy-Driven Governance** - Agent autonomy bounded by declarative policies
5. **Security by Design** - Zero-trust architecture, agents are untrusted by default
6. **Enterprise-Grade Reliability** - Production-ready with ACID guarantees and multi-tenancy

When making design decisions, always align with these principles.

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
