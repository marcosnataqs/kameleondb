# Backlog

Future work, ideas, and deferred items.

---

## Hybrid Storage - Phase 2: Dedicated Storage

Enable per-entity tables with foreign keys. See [spec](../specs/001-hybrid-storage.md).

- [ ] Create `DedicatedTableManager` class
  - [ ] `create_dedicated_table(entity)` - DDL generation
  - [ ] `drop_dedicated_table(entity)`
  - [ ] `add_foreign_key(relationship)`
  - [ ] `remove_foreign_key(relationship)`

- [ ] Create `StorageMigration` class
  - [ ] `migrate_to_dedicated(entity, batch_size)` - shared → dedicated
  - [ ] `migrate_to_shared(entity, batch_size)` - dedicated → shared
  - [ ] Transaction safety with rollback
  - [ ] Progress callbacks for large migrations

- [ ] Schema Engine updates
  - [ ] `materialize_entity()` method
  - [ ] `dematerialize_entity()` method
  - [ ] Log to schema changelog

- [ ] Query Router
  - [ ] Route queries based on `storage_mode`
  - [ ] Same API for both storage modes

- [ ] MCP Tools
  - [ ] `kameleondb_materialize_entity`
  - [ ] `kameleondb_dematerialize_entity`

---

## Hybrid Storage - Phase 3: Relational Queries

Cross-entity queries with joins. See [spec](../specs/001-hybrid-storage.md).

- [ ] `RelationalQueryBuilder` class
  - [ ] JOIN generation for dedicated tables
  - [ ] Subquery fallback for shared tables
  - [ ] `include` parameter for eager loading

- [ ] Cascading operations
  - [ ] `on_delete` behavior (application-level for shared, DB-level for dedicated)

---

## Hybrid Storage - Phase 4: Many-to-Many

Complete relational support. See [spec](../specs/001-hybrid-storage.md).

- [ ] Many-to-many relationships
  - [ ] Auto-generate junction tables
  - [ ] `add_to_relationship()` / `remove_from_relationship()` APIs

- [ ] Relationship constraints
  - [ ] Required relationships (NOT NULL FK)
  - [ ] Unique relationships (one-to-one)
  - [ ] Self-referential relationships

- [ ] Bulk operations
  - [ ] `connect_many()` / `disconnect_many()`

