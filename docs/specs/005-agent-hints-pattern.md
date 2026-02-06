# Spec 005: Agent Hints Pattern

**Status:** Draft
**Created:** 2026-02-06
**ADR:** Extends ADR-002 (Query Intelligence)

## Problem

Currently, agents need to choose between two functions:
- `execute_sql()` - Returns just the query results
- `execute_sql_with_metrics()` - Returns results + metrics + suggestions

This violates our agent-first principle. Agents shouldn't need to know about a special "with_metrics" variant to get optimization hints. All tools should proactively return actionable intelligence.

## Solution: Agent Hints Pattern

**Core Principle:** Every function exposed to agents (via MCP, CLI, or SDK) returns both:
1. **Results** - The requested data/operation result
2. **Hints** - Actionable suggestions for optimization

### Design

```python
# All query results follow this pattern
class QueryResult:
    rows: list[dict[str, Any]]       # The actual data
    metrics: QueryMetrics            # Performance data
    hints: list[Hint]                # Actionable suggestions

class Hint:
    category: str                    # "performance", "schema", "security"
    message: str                     # Human-readable description
    action: str | None               # Executable code (e.g., "db.materialize_entity('Contact')")
    priority: str                    # "low", "medium", "high"
    evidence: dict[str, Any]         # Supporting data
```

### Changes

1. **Consolidate `execute_sql` methods:**
   - Remove `execute_sql_with_metrics()`
   - Make `execute_sql()` always return `QueryExecutionResult`
   - Metrics collection enabled by default (can be disabled via policy)

2. **Extend pattern to all operations:**
   - `entity.find_by_id()` → returns `{data: ..., hints: [...]}`
   - `entity.insert()` → returns `{id: ..., hints: [...]}`
   - Schema operations can suggest migrations, indexes, etc.

3. **MCP server simplification:**
   - Remove `kameleondb_execute_sql_with_metrics` tool
   - Update `kameleondb_execute_sql` to return hints inline

### Phased Implementation

**Phase 1: Consolidate SQL execution** (this spec)
- Remove `execute_sql_with_metrics()`
- Update `execute_sql()` to always return structured results with hints
- Update MCP server
- Update CLI
- Update tests

**Phase 2: Extend to CRUD operations** (future)
- Entity.insert() returns hints (e.g., "Consider adding index on 'email'")
- Entity.find_by_id() returns hints (e.g., "Frequent lookups, materialize?")
- Schema operations return migration hints

**Phase 3: Expand hint categories** (future)
- Performance hints (current: materialization suggestions)
- Schema hints (missing indexes, denormalization opportunities)
- Security hints (unindexed PII fields, audit log gaps)
- Data quality hints (null fields, outliers, schema drift)

## Benefits

1. **Agent-First:** Agents get intelligence without needing special knowledge
2. **Progressive Discovery:** Hints guide agents to better patterns over time
3. **Consistent API:** All operations follow the same result structure
4. **Simpler MCP Surface:** Fewer tools, clearer purpose
5. **Future-Proof:** Pattern extends naturally to new hint categories

## Migration Path

1. Deprecate `execute_sql_with_metrics()` (mark with warning)
2. Update internal callers to use new `execute_sql()`
3. Remove deprecated method in next major version

## Example Usage

```python
# Before (confusing - which one to use?)
results = db.execute_sql("SELECT ...")  # Just data
result = db.execute_sql_with_metrics("SELECT ...", entity_name="Contact")  # Data + hints

# After (always get hints)
result = db.execute_sql("SELECT ...", entity_name="Contact")
# result.rows = data
# result.hints = [Hint(...), ...]

# Agent can always check for hints
if result.hints:
    for hint in result.hints:
        if hint.priority == "high":
            # Execute suggested action
            eval(hint.action)
```

## Open Questions

1. Should hints be opt-out rather than opt-in? (Propose: yes, via policy)
2. Should we track hint acceptance rates for learning?
3. Should hints be stored in audit log for provenance?
