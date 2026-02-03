# ADR-001 Implementation Checklist

Quick reference for implementing the Hybrid Storage Architecture.

## Phase 1: Foundation (v0.2.0) ✅ COMPLETE

### Database Schema Changes
- [x] Add `storage_mode` column to `kdb_entity_definitions` (default: 'shared')
- [x] Add `dedicated_table_name` column to `kdb_entity_definitions`
- [x] Create `kdb_relationship_definitions` table
- [x] Create `kdb_junction_tables` table
- [ ] Add migration script for existing deployments

### Schema Engine (`src/kameleondb/schema/`)
- [x] Create `RelationshipDefinition` model in `models.py`
- [x] Create `JunctionTable` model in `models.py`
- [x] Add `add_relationship()` to `SchemaEngine`
- [x] Add `remove_relationship()` to `SchemaEngine`
- [x] Add `list_relationships()` to `SchemaEngine`
- [x] Add `get_relationships()` to `SchemaEngine` (renamed from get_relationships_for_entity)
- [x] Add relationship validation (valid types, valid target entities)
- [x] Update `describe()` to include relationships
- [ ] Add circular reference detection (deferred to Phase 2)

### Core Engine (`src/kameleondb/core/`)
- [x] Add `storage_mode` to EntityInfo type
- [x] Add `relationships` to EntityInfo type
- [ ] Add `storage_mode` property to `Entity` class (deferred to Phase 2)
- [ ] Add `relationships` property to `Entity` class (deferred to Phase 2)
- [ ] Update `create_entity()` to accept `relationships` parameter (deferred to Phase 2)

### MCP Tools (`src/kameleondb/integrations/mcp/`)
- [x] Add `kameleondb_add_relationship` tool
- [x] Add `kameleondb_remove_relationship` tool
- [x] Add `kameleondb_list_relationships` tool
- [x] Update `kameleondb_describe` to include relationships (via SchemaEngine)

### Tests
- [x] Unit tests for relationship types and constants
- [x] Unit tests for relationship exceptions
- [x] Unit tests for relationship models
- [ ] Integration tests for relationship metadata (requires database)
- [ ] Test circular reference detection (deferred)

---

## Phase 2: Dedicated Storage (v0.2.1)

### New Module: `src/kameleondb/data/dedicated_table.py`
- [ ] Create `DedicatedTableManager` class
- [ ] Implement `create_dedicated_table(entity)`
- [ ] Implement `drop_dedicated_table(entity)`
- [ ] Implement `add_foreign_key(relationship)`
- [ ] Implement `remove_foreign_key(relationship)`
- [ ] Implement `table_exists(entity)`

### Data Migration: `src/kameleondb/data/migration.py`
- [ ] Create `StorageMigration` class
- [ ] Implement `migrate_to_dedicated(entity, batch_size)`
- [ ] Implement `migrate_to_shared(entity, batch_size)`
- [ ] Implement progress callbacks for large migrations
- [ ] Transaction safety with rollback

### Schema Engine Updates
- [ ] Add `materialize_entity()` method
- [ ] Add `dematerialize_entity()` method
- [ ] Log materialization to schema changelog
- [ ] Validate materialization prerequisites

### Query Router: `src/kameleondb/data/query_router.py`
- [ ] Create `QueryRouter` class
- [ ] Route to `JSONBQuery` for shared entities
- [ ] Route to `DedicatedQuery` for dedicated entities
- [ ] Maintain consistent API

### Core Engine Updates
- [ ] Add `materialize()` method to `Entity`
- [ ] Add `dematerialize()` method to `Entity`
- [ ] Update CRUD methods to use QueryRouter

### MCP Tools
- [ ] Add `kameleondb_materialize_entity` tool
- [ ] Add `kameleondb_dematerialize_entity` tool
- [ ] Update entity describe to show `storage_mode`

### Tests
- [ ] Unit tests for DedicatedTableManager
- [ ] Unit tests for migration (shared → dedicated)
- [ ] Unit tests for migration (dedicated → shared)
- [ ] Integration tests for mixed storage queries
- [ ] Performance benchmarks

---

## Phase 3: Relational Queries (v0.2.2)

### New Module: `src/kameleondb/data/relational_query.py`
- [ ] Create `RelationalQueryBuilder` class
- [ ] Implement JOIN generation for dedicated tables
- [ ] Implement subquery fallback for shared tables
- [ ] Implement eager loading (`include` parameter)
- [ ] Implement related entity filtering

### Query API Extensions
- [ ] Add `include` parameter to `find()`
- [ ] Add `filters` support for `relationship.field` syntax
- [ ] Implement automatic join optimization
- [ ] Handle nested includes (`include=["customer.address"]`)

### Cascading Operations
- [ ] Implement `on_delete` behavior for shared tables (application-level)
- [ ] Implement `on_delete` behavior for dedicated tables (DB-level)
- [ ] Add cascade validation before delete

### MCP Tools
- [ ] Update `kameleondb_find` with `include` parameter
- [ ] Add `kameleondb_find_related` tool

### Tests
- [ ] Unit tests for join generation
- [ ] Unit tests for eager loading
- [ ] Unit tests for cascading deletes
- [ ] Integration tests for cross-entity queries
- [ ] Performance tests for large joins

---

## Phase 4: Many-to-Many & Advanced (v0.3.0)

### Many-to-Many Support
- [ ] Auto-generate junction tables for M2M relationships
- [ ] Implement `add_to_relationship(entity_id, related_ids)`
- [ ] Implement `remove_from_relationship(entity_id, related_ids)`
- [ ] Implement junction table queries

### Relationship Constraints
- [ ] Required relationships (NOT NULL FK)
- [ ] Unique relationships (one-to-one enforcement)
- [ ] Self-referential relationships (e.g., `parent_id`)

### Indexing
- [ ] Auto-index foreign key columns
- [ ] Composite indexes for junction tables
- [ ] GIN indexes for JSONB relationship fields (shared mode)

### Bulk Operations
- [ ] Implement `connect_many(source_ids, target_ids)`
- [ ] Implement `disconnect_many(source_ids, target_ids)`
- [ ] Batch FK updates for performance

### MCP Tools
- [ ] Add `kameleondb_connect` tool
- [ ] Add `kameleondb_disconnect` tool
- [ ] Add `kameleondb_bulk_connect` tool

### Tests
- [ ] Unit tests for M2M relationships
- [ ] Unit tests for relationship constraints
- [ ] Integration tests for complex relationship graphs
- [ ] Performance tests for bulk operations

---

## Documentation Updates

- [ ] Update README.md with relationship examples
- [ ] Update CLAUDE.md with new architecture details
- [ ] Add relationship section to API documentation
- [ ] Create migration guide for existing users
- [ ] Update MCP tool documentation

## Breaking Changes to Track

| Change | Migration Path |
|--------|----------------|
| New columns in `kdb_entity_definitions` | Alembic migration |
| New metadata tables | Alembic migration |
| `describe()` output format change | Additive (backward compatible) |
