# Backlog

Future work, ideas, and deferred items.

---

## Hybrid Storage - Phase 3: Relational Queries

(Phase 1 & 2 complete - see DONE.md)

Cross-entity queries with joins. See [spec](../specs/001-hybrid-storage.md).

- `RelationalQueryBuilder` class
  - JOIN generation for dedicated tables
  - Subquery fallback for shared tables
  - `include` parameter for eager loading
- Cascading operations
  - `on_delete` behavior (application-level for shared, DB-level for dedicated)

---

## Hybrid Storage - Phase 4: Many-to-Many

Complete relational support. See [spec](../specs/001-hybrid-storage.md).

- Many-to-many relationships
  - Auto-generate junction tables
  - `add_to_relationship()` / `remove_from_relationship()` APIs
- Relationship constraints
  - Required relationships (NOT NULL FK)
  - Unique relationships (one-to-one)
  - Self-referential relationships
- Bulk operations
  - `connect_many()` / `disconnect_many()`

---

## Query Intelligence - Progressive Materialization

Track query metrics and provide intelligent materialization suggestions. See [spec](../specs/002-query-intelligence.md).

**Concept**: When queries exceed performance thresholds, return results + actionable suggestions for agents to materialize entities. No scheduler needed—intelligence emerges from query feedback.

### Phase 2: Suggestion Engine

(Phase 1 complete - see DONE.md)

Enhanced suggestions based on historical patterns. See [spec](../specs/002-query-intelligence.md).

- Create `SuggestionEngine` class (`query/suggestions.py`)
  - `evaluate_query()` - check immediate thresholds
  - `evaluate_entity()` - check historical patterns
  - Generate actionable suggestions
- Wire suggestion engine to query execution
  - Attach suggestions to `QueryExecutionResult`

