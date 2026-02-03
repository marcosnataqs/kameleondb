# KameleonDB Agent Context

This file provides guidance to AI agents working with code in this repository.

## First Principles

KameleonDB is built on six foundational principles that guide all architectural decisions:

### 1. Agent-First Design

All capabilities are built for AI agents as primary users, not humans.

- APIs optimized for agent reasoning patterns (observe → reason → act)
- Operations return reasoning context, not just results
- Documentation written for LLM consumption (structured, unambiguous)
- Human interfaces are observability layers, not operational requirements

**Implication:** We don't ask "Can a human use this?" We ask "Can an agent reason about this?"

### 2. Schema-on-Reason

Schema emerges from continuous agent reasoning, not upfront human design.

- Agents discover, propose, and evolve ontologies dynamically
- Schema changes are data operations, not migrations
- Multiple schema views can coexist (different agents, different understandings)
- Schema evolution is versioned and reversible

**Implication:** The database adapts to what agents learn, not what humans predicted.

### 3. Provenance & Auditability

Every schema decision and data transformation must be traceable to agent reasoning.

- All schema changes logged with justification chains
- Complete lineage: source → extraction → field → query
- Reasoning traces are queryable metadata
- Rollback capability for any ontological change
- "Why does this field exist?" is always answerable

**Implication:** Trust comes from transparency, not black-box magic.

### 4. Policy-Driven Governance

Agent autonomy is bounded by declarative policies, not manual approvals.

- Governance rules defined as policies agents must follow
- Agents operate freely within policy bounds
- Policy violations trigger human review, not silent failures
- Compliance requirements (PII handling, data retention) encoded as constraints
- Quality gates (validation rules, consistency checks) enforced automatically

**Implication:** Governance scales through automation, not gatekeepers.

### 5. Security by Design

Zero-trust architecture where agents are untrusted by default.

- Least-privilege access for all agent operations
- Credential isolation (agents never handle source authentication directly)
- Capability-based permissions (grant specific powers, not broad access)
- All agent actions audited with identity tracking
- Data access controls respected through dynamic schema layer

**Implication:** Agents are powerful tools, not privileged users.

### 6. Enterprise-Grade Reliability

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

KameleonDB is an Agent-Native Data Platform with JSONB-first storage. It provides a meta-layer on top of PostgreSQL where schema is stored as data, not DDL, and all record data is stored in native JSONB columns for semantic locality.

### Core Pattern: Metadata-driven + JSONB Storage

The system uses two layers of tables:
1. **Meta-tables** (`kdb_entity_definitions`, `kdb_field_definitions`, `kdb_schema_changelog`) - Store schema definitions as data
2. **Data table** (`kdb_records`) - Single table with PostgreSQL JSONB column storing all field values

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

3. Agent calls `entity.find(filters={"name": "John"})`:
   - `JSONBQuery` builds PostgreSQL JSONB queries: `WHERE data->>'name' = 'John'`
   - Uses GIN indexes for efficient JSONB queries

### Agent-First Design

All public methods:
- Accept JSON-serializable parameters (primitives, dicts, lists)
- Return JSON-serializable results
- Support `if_not_exists` for idempotency
- Include actionable error messages with available options

### Type Mapping (PostgreSQL JSONB)

All field values are stored in a PostgreSQL JSONB column and cast when querying:

| KameleonDB Type | Storage in JSONB | Query Cast Example |
|-----------------|------------------|-------------------|
| string | text | `data->>'field'` |
| text | text | `data->>'field'` |
| int | number | `(data->>'field')::int` |
| float | number | `(data->>'field')::numeric` |
| bool | boolean | `(data->>'field')::boolean` |
| datetime | TEXT | TIMESTAMP |
| json | TEXT | JSONB |
| uuid | TEXT | UUID |
