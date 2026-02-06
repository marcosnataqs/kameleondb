# Changelog

All notable changes to KameleonDB will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

**Agent Hints Pattern (Spec 005)**
- `execute_sql()` now always returns `QueryExecutionResult` with metrics and optimization hints
- Follows agent-first principle: all operations provide intelligence inline
- No need to choose between `execute_sql()` and `execute_sql_with_metrics()`
- MCP tool `kameleondb_execute_sql` now returns hints by default
- CLI `query run` command shows metrics and hints automatically

### Removed

- `execute_sql_with_metrics()` method (consolidated into `execute_sql()`)
- `kameleondb_execute_sql_with_metrics` MCP tool (functionality merged into `kameleondb_execute_sql`)

## [0.1.0] - 2026-02-05

### Added

**Core Engine**
- `KameleonDB` class - main entry point for all operations
- `Entity` class - high-level CRUD operations per entity
- Dynamic schema management - create, modify, drop entities and fields at runtime
- Zero-migration schema evolution - field changes are metadata-only, no DDL

**Storage Architecture**
- PostgreSQL backend with JSONB storage for maximum flexibility
- SQLite backend with JSON1 extension for lightweight/local usage
- Hybrid Storage Phase 1: Shared storage mode (all records in `kdb_records` table)
- Hybrid Storage Phase 2: Dedicated storage mode with materialization support
  - `materialize_entity()` - migrate entity to dedicated table for FK constraints
  - `dematerialize_entity()` - migrate back to shared storage

**Schema Features**
- Entity definitions stored as data in `kdb_entity_definitions`
- Field definitions stored in `kdb_field_definitions`
- Support for field types: string, text, int, float, bool, datetime, json, uuid
- Field constraints: required, unique, indexed, default values
- Schema changelog for audit trails

**Relationships (ADR-001)**
- Relationship definitions in `kdb_relationship_definitions`
- Support for: many-to-one, one-to-many, many-to-many (planned)
- Junction table metadata for many-to-many relationships
- On-delete actions: CASCADE, SET_NULL, RESTRICT, NO_ACTION

**Query Intelligence (ADR-002)**
- Schema context builder for LLM SQL generation
- Dialect-aware SQL patterns (PostgreSQL vs SQLite)
- Query validation with SQL injection protection
- `execute_sql()` - execute validated SQL queries
- `execute_sql_with_metrics()` - query with performance tracking
- Query metrics collection and storage
- Materialization suggestions based on performance patterns
- `get_entity_stats()` - aggregated entity statistics

**MCP Integration**
- Model Context Protocol (MCP) server implementation
- CLI entry point: `kameleondb-mcp`
- Tools: create_entity, list_entities, describe_entity, add_field, etc.

**Tool Registry**
- Export tools for agent frameworks (OpenAI, Anthropic formats)
- Automatic tool generation from entity definitions
- Custom tool registration

**Developer Experience**
- Full type hints with py.typed marker
- Pydantic models for all data types
- Comprehensive error hierarchy with helpful messages
- JSON-serializable results for agent consumption

### Architecture Decisions

- **ADR-001**: Hybrid Storage Architecture - shared vs dedicated storage modes
- **ADR-002**: LLM-Native Query Generation - schema context for SQL generation

### Dependencies

- SQLAlchemy >= 2.0 (required)
- Pydantic >= 2.0 (required)
- psycopg >= 3.1 (optional, for PostgreSQL)
- mcp >= 1.2.0 (optional, for MCP server)

### Python Support

- Python 3.11+
- Python 3.12
- Python 3.13

[Unreleased]: https://github.com/marcosnataqs/kameleondb/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/marcosnataqs/kameleondb/releases/tag/v0.1.0
