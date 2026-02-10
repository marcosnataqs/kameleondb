# Current Tasks

Active work in progress.

---

## In Progress

### Hybrid Storage Phase 3: Cascading Operations (Spec 006)

Implementing `on_delete` enforcement at runtime.

- [x] Add `RestrictDeleteError` and `CascadeError` exceptions
- [x] Add `get_incoming_relationships()` to SchemaEngine
- [x] Implement cascade logic in `Entity.delete()`
  - [x] RESTRICT: Block delete if related records exist
  - [x] CASCADE: Delete related records recursively
  - [x] SET_NULL: Clear FK field on related records
- [x] Add `cascade` and `force` parameters to delete()
- [x] Add tests (11 new tests)
- [ ] Create PR

---

## Up Next

_Pull from [BACKLOG.md](./BACKLOG.md)_
