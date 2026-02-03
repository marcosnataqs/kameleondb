# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0-alpha] - 2026-02-02

### Added

- **Hybrid Storage Architecture (ADR-001)**: Foundation for per-entity tables
  - `storage_mode` field on entities (`shared` or `dedicated`)
  - `dedicated_table_name` field for future materialization
  - New `RelationshipDefinition` model for entity relationships
  - New `JunctionTable` model for many-to-many relationships
  - Relationship types: `many_to_one`, `one_to_many`, `many_to_many`, `one_to_one`
  - On-delete actions: `CASCADE`, `SET_NULL`, `RESTRICT`, `NO_ACTION`

- **Relationship Management API**
  - `schema_engine.add_relationship()` - Create relationships between entities
  - `schema_engine.remove_relationship()` - Soft-delete relationships
  - `schema_engine.get_relationships()` - Get relationships for an entity
  - `schema_engine.list_relationships()` - List all relationships
  - Auto-creation of foreign key fields when adding relationships

- **Updated Schema Discovery**
  - `describe()` now includes relationships per entity
  - `describe_entity()` includes `storage_mode` and `relationships`
  - `RelationshipInfo` type for relationship output

- **New MCP Tools**
  - `kameleondb_add_relationship` - Add relationships between entities
  - `kameleondb_remove_relationship` - Remove relationships
  - `kameleondb_list_relationships` - List all relationships

- **New Types and Exceptions**
  - `StorageModeType`, `RelationshipTypeEnum`, `OnDeleteActionType` enums
  - `RelationshipSpec`, `RelationshipInfo` Pydantic models
  - `RelationshipNotFoundError`, `RelationshipAlreadyExistsError`
  - `InvalidRelationshipTypeError`, `InvalidOnDeleteActionError`
  - `CircularRelationshipError`, `StorageModeError`, `MaterializationError`

- **Architecture Decision Records**
  - ADR-001: Hybrid Storage Architecture
  - ADR-002: LLM-Native Query Generation (planned)

## [0.1.0] - 2026-XX-XX

### Added

- Initial release of KameleonDB
- JSONB-first architecture optimized for PostgreSQL
- Dynamic Schema Engine with metadata-driven approach
- PostgreSQL JSONB storage for semantic locality
- Entity and field management API
- CRUD operations with JSONB queries
- Schema discovery (`describe()`, `describe_entity()`)
- Tool registry for agent integrations
- Idempotent operations (`if_not_exists` parameter)
- Schema changelog for audit trail
- Comprehensive test suite
