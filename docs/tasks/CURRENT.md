# Current Tasks

Active work in progress.

---

## In Progress

### Hybrid Storage Phase 4: Many-to-Many (Spec 007)

Implementing junction tables and link/unlink operations.

- [x] Add `create_junction_table()` to DedicatedTableManager
- [x] Update `add_relationship()` to create junction tables for many-to-many
- [x] Add `_create_junction_table()` to SchemaEngine
- [x] Add link operations to Entity:
  - [x] `link()` - add single link
  - [x] `unlink()` - remove single link
  - [x] `unlink_all()` - remove all links for record
  - [x] `get_linked()` - get all linked IDs
  - [x] `link_many()` - bulk add
  - [x] `unlink_many()` - bulk remove
- [x] Update cascade logic for many-to-many (delete junction entries)
- [x] Add tests (13 new tests)
- [ ] Create PR

---

## Up Next

_Pull from [BACKLOG.md](./BACKLOG.md)_
