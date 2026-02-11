# Changelog

All notable changes to KameleonDB will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-02-11

### Added

**Many-to-Many Relationships (Spec 007)**
- Junction table auto-creation when defining `many_to_many` relationships
- `link()` / `unlink()` operations for managing many-to-many connections
- `get_linked()` to retrieve linked record IDs
- `link_many()` / `unlink_many()` optimized bulk operations
- Cascade cleanup: deleting source or target removes junction entries
- Target existence validation on link operations

**Cascading Operations (Spec 006)**
- `on_delete` enforcement at runtime (CASCADE, SET_NULL, RESTRICT)
- `RestrictDeleteError` when RESTRICT blocks deletion
- Recursive cascade for nested relationships
- `force` parameter to bypass RESTRICT when needed

**Storage-Aware JOIN Hints**
- Query engine now suggests JOINs between materialized entities
- Hints guide agents to use proper SQL JOINs instead of in-memory lookups

**CLI Commands for Relationships**
- `schema add-relationship` - define relationships between entities
- `schema add-m2m` - create many-to-many relationships with junction tables
- `data link` - link records (single, multiple via `-t`, or bulk via `--from-file`)
- `data unlink` - unlink records (single, multiple, or `--all`)
- `data get-linked` - retrieve linked record IDs
- `data info` - show record count and entity statistics
- `schema info` - show entity field and relationship details

**MCP Tools for Relationships**
- `link` - link records in many-to-many relationships
- `unlink` - unlink records from many-to-many relationships

**Documentation**
- Spec 008: Semantic Search (Layer 2) design document

### Changed

**CLI Simplification**
- Consolidated `schema alter` with `--add`, `--drop`, `--rename` options (replaces separate `add-field`/`drop-field`)
- Merged `link` + `link-many` into single `data link` command
- Merged `unlink` + `unlink-many` into single `data unlink` command  
- Renamed `data stats` → `data info`
- Renamed `schema stats` → `schema info`

### Fixed

**Reserved Field Names**
- Field definitions now reject reserved system column names (`id`, `entity_id`, `data`, `created_at`, `updated_at`, `is_deleted`)
- Raises `InvalidFieldNameError` with clear message

**SQLite Locking in M2M Operations**
- Fixed nested connection issue during `add_relationship(type=many_to_many)` on SQLite file databases
- Junction table creation now reuses the existing session connection

## [0.1.2] - 2026-02-07

### Fixed

**CLI Bug Fixes**
- Fixed `data list` command: properly access `.rows` attribute of `QueryExecutionResult` object
- Fixed `admin info` command: properly access `.rows` attribute when counting records
- Both commands now correctly handle the QueryExecutionResult object returned by `execute_sql()`

### Added

**OpenClaw Integration**
- Added OpenClaw skill in `skills/openclaw/` directory for OpenClaw agent framework
- Includes comprehensive SKILL.md with agent-centric use cases
- Examples: schema evolution workflow, contact tracking, batch imports
- Ready for ClawHub deployment
- Gating configuration for environment validation (KAMELEONDB_URL, kameleondb binary)

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

[Unreleased]: https://github.com/marcosnataqs/kameleondb/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/marcosnataqs/kameleondb/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/marcosnataqs/kameleondb/compare/v0.1.0...v0.1.2
[0.1.0]: https://github.com/marcosnataqs/kameleondb/releases/tag/v0.1.0
