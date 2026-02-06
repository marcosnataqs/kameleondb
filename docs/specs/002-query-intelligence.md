# Query Intelligence - Progressive Materialization

**Status:** Implemented (v0.1.0), Extended by [Spec 005 - Agent Hints Pattern](005-agent-hints-pattern.md)

Intelligent query monitoring that tracks execution metrics and suggests materialization when performance thresholds are exceeded.

**Note:** As of Spec 005, the separate `execute_sql_with_metrics()` method has been consolidated into `execute_sql()`, which now always returns metrics and hints. The core concepts below still apply.

## Core Concept

```
Agent Query → Execute → Measure → Track Pattern → Return Result + Suggestion
                                                          ↓
                              "Consider materializing Contact (450ms, 1247 rows)"
                                                          ↓
                                    Agent decides → db.materialize_entity("Contact")
```

**Key principle**: No scheduler, no background service. Intelligence emerges from query feedback during normal operations. Agents make the final decision.

## Why This Approach?

1. **Library-first**: Works as a pip-installable package, no infrastructure
2. **Agent-first**: Suggestions are actionable, not prescriptive
3. **Zero friction**: Normal queries just work; suggestions appear when relevant
4. **Decoupled**: Metrics tracking works independently of materialization

## API Examples

### Query with Metrics

```python
# All SQL queries now return metrics and suggestions (Agent Hints Pattern)
result = db.execute_sql("""
    SELECT o.id, o.data->>'total' as total, c.data->>'name' as customer
    FROM kdb_records o
    JOIN kdb_records c ON c.id::text = o.data->>'customer_id'
    WHERE o.entity_id = '...'
""", entity_name="Order")

# Result structure (QueryExecutionResult)
result.rows        # list[dict] - the actual data
result.metrics     # QueryMetrics - execution time, row count, etc.
result.suggestions # list[MaterializationSuggestion] - actionable suggestions
result.warnings    # list[str] - validation warnings
```

### Handling Suggestions

```python
if result.suggestions:
    for s in result.suggestions:
        print(f"Entity: {s.entity_name}")
        print(f"Reason: {s.reason}")
        print(f"Evidence: {s.evidence}")
        print(f"Action: {s.action}")

# Example output:
# Entity: Contact
# Reason: Query took 450ms (threshold: 100ms)
# Evidence: {"execution_time_ms": 450, "row_count": 1247, "has_join": true}
# Action: db.materialize_entity('Contact')
```

### Acting on Suggestions

```python
# Agent decides to materialize based on suggestion
db.materialize_entity(
    "Contact",
    reason="Slow query performance detected",
    created_by="agent:data-analyzer"
)

# Future queries automatically use dedicated table
```

## Data Model

### QueryMetric

Tracks individual query executions.

```sql
CREATE TABLE kdb_query_metrics (
    id VARCHAR(36) PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Query details
    entity_name VARCHAR(255),          -- Primary entity accessed
    query_type VARCHAR(20) NOT NULL,   -- SELECT, INSERT, UPDATE, DELETE
    execution_time_ms REAL NOT NULL,
    row_count INTEGER,

    -- Pattern detection
    has_join BOOLEAN DEFAULT FALSE,
    tables_accessed JSONB,             -- ["kdb_records", "kdb_entity_definitions"]

    -- Context
    created_by VARCHAR(255),           -- Agent/user identifier

    -- Index for efficient aggregation
    INDEX ix_query_metrics_entity (entity_name, timestamp),
    INDEX ix_query_metrics_time (timestamp)
);
```

### MaterializationPolicy

Configuration for suggestion thresholds.

```python
class MaterializationPolicy(BaseModel):
    # Immediate triggers (per-query)
    execution_time_threshold_ms: float = 100.0  # Suggest if query > 100ms
    row_count_threshold: int = 1000             # Suggest if rows > 1000

    # Historical triggers (aggregated)
    join_frequency_threshold: int = 10          # Joins in last 24 hours
    join_frequency_window_hours: int = 24
    access_frequency_threshold: int = 50        # Queries in last hour
    access_frequency_window_hours: int = 1

    # Feature flags
    enabled: bool = True                        # Disable in production if needed
    store_sql_text: bool = False                # Store raw SQL (PII concern)
    retention_days: int = 7                     # Auto-cleanup old metrics
```

## Result Types

### QueryMetrics

```python
class QueryMetrics(BaseModel):
    """Metrics from a single query execution."""
    execution_time_ms: float
    row_count: int
    entities_accessed: list[str]
    has_join: bool
    query_type: str  # SELECT, INSERT, etc.
```

### MaterializationSuggestion

```python
class MaterializationSuggestion(BaseModel):
    """Actionable suggestion for an agent."""
    entity_name: str
    reason: str         # Human-readable: "Query took 450ms (threshold: 100ms)"
    evidence: dict      # Machine-readable: {"execution_time_ms": 450, ...}
    action: str         # Copy-paste action: "db.materialize_entity('Contact')"
    priority: str       # "high", "medium", "low"
```

### QueryExecutionResult

```python
class QueryExecutionResult(BaseModel):
    """Enhanced query result with metrics and suggestions."""
    rows: list[dict[str, Any]]
    metrics: QueryMetrics
    suggestions: list[MaterializationSuggestion]
    warnings: list[str]  # From QueryValidator
```

## Suggestion Logic

### Immediate Triggers (Per-Query)

Checked after each query execution:

| Trigger | Condition | Priority |
|---------|-----------|----------|
| Slow query | `execution_time_ms > threshold` | high |
| Large result | `row_count > threshold` | medium |
| Join on shared table | `has_join AND storage_mode == 'shared'` | medium |

### Historical Triggers (Aggregated)

Checked against recent metrics:

| Trigger | Condition | Priority |
|---------|-----------|----------|
| Frequent joins | Entity joined > N times in 24h | high |
| High access | Entity queried > N times in 1h | medium |
| Growing entity | Record count increased > 50% in 7d | low |

### Suggestion Generation

```python
def generate_suggestions(
    entity_name: str,
    metrics: QueryMetrics,
    policy: MaterializationPolicy,
    historical_stats: EntityStats,
) -> list[MaterializationSuggestion]:
    suggestions = []

    # Immediate: slow query
    if metrics.execution_time_ms > policy.execution_time_threshold_ms:
        suggestions.append(MaterializationSuggestion(
            entity_name=entity_name,
            reason=f"Query took {metrics.execution_time_ms:.0f}ms (threshold: {policy.execution_time_threshold_ms:.0f}ms)",
            evidence={"execution_time_ms": metrics.execution_time_ms},
            action=f"db.materialize_entity('{entity_name}')",
            priority="high"
        ))

    # Immediate: large result
    if metrics.row_count > policy.row_count_threshold:
        suggestions.append(MaterializationSuggestion(
            entity_name=entity_name,
            reason=f"Query returned {metrics.row_count} rows (threshold: {policy.row_count_threshold})",
            evidence={"row_count": metrics.row_count},
            action=f"db.materialize_entity('{entity_name}')",
            priority="medium"
        ))

    # Historical: frequent joins
    if historical_stats.join_count_24h > policy.join_frequency_threshold:
        suggestions.append(MaterializationSuggestion(
            entity_name=entity_name,
            reason=f"Entity joined {historical_stats.join_count_24h} times in last 24h",
            evidence={"join_count_24h": historical_stats.join_count_24h},
            action=f"db.materialize_entity('{entity_name}')",
            priority="high"
        ))

    return suggestions
```

## Configuration

### Default (Development)

```python
db = KameleonDB("sqlite:///data.db")
# Metrics enabled by default
# Default thresholds apply
```

### Custom Thresholds

```python
db = KameleonDB(
    url="postgresql://...",
    materialization_policy=MaterializationPolicy(
        execution_time_threshold_ms=50.0,  # More aggressive
        row_count_threshold=500,
        enabled=True
    )
)
```

### Disabled (Production)

```python
db = KameleonDB(
    url="postgresql://...",
    materialization_policy=MaterializationPolicy(enabled=False)
)
```

## Metrics API

### Get Entity Statistics

```python
stats = db.get_entity_stats("Contact")
# Returns:
{
    "entity_name": "Contact",
    "total_queries": 847,
    "avg_execution_time_ms": 125.4,
    "max_execution_time_ms": 892,
    "total_rows_returned": 45230,
    "join_count_24h": 23,
    "storage_mode": "shared",
    "record_count": 5432,
    "suggestion": "Consider materialization - high join frequency"
}
```

### List Materialization Candidates

```python
candidates = db.get_materialization_candidates()
# Returns entities sorted by materialization score
[
    {"entity": "Contact", "score": 0.92, "top_reason": "high_join_frequency"},
    {"entity": "Order", "score": 0.78, "top_reason": "slow_queries"},
    {"entity": "Product", "score": 0.45, "top_reason": "large_table"},
]
```

## Integration with Materialization

This spec provides the **intelligence layer**. The actual materialization is handled by [001-hybrid-storage.md](./001-hybrid-storage.md).

```
Query Intelligence (this spec)     Hybrid Storage (001)
         ↓                                ↓
   Track metrics               Create dedicated tables
   Generate suggestions   ←→   Migrate data
   Return with results         Update storage_mode
```

## File Structure

```
src/kameleondb/
├── query/
│   ├── metrics.py       # MetricsCollector class
│   └── suggestions.py   # SuggestionEngine class
├── core/
│   ├── types.py         # QueryMetrics, MaterializationSuggestion, etc.
│   └── engine.py        # execute_sql_with_metrics(), get_entity_stats()
└── schema/
    └── models.py        # QueryMetric model
```

## Trade-offs

| Aspect | This Approach | Alternative |
|--------|---------------|-------------|
| Infrastructure | None (library-only) | Background scheduler service |
| When suggestions appear | During queries | Proactive notifications |
| Agent autonomy | Agent decides when to act | System auto-materializes |
| Complexity | Low | Higher |
| Predictability | Suggestions may vary | Consistent scheduled analysis |

We chose the library-only approach to align with KameleonDB's agent-first, zero-infrastructure philosophy. Agents are intelligent participants who can make their own decisions based on suggestions.

## Future Enhancements

1. **Materialization simulation**: Estimate performance improvement before materializing
2. **Auto-dematerialization**: Suggest reverting rarely-used dedicated tables
3. **Query pattern clustering**: Group similar queries for batch optimization
4. **Cost estimation**: Include storage/compute cost in suggestions
