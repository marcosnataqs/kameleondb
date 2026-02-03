# ADR-002: LLM-Native Query Generation

**Status**: Proposed
**Date**: 2026-02-02
**Authors**: KameleonDB Team
**Related**: [ADR-001 Hybrid Storage Architecture](./001-hybrid-storage-architecture.md)

## Context

Traditional ORMs and query builders attempt to abstract SQL behind programmatic APIs:

```python
# Complex find() API that tries to cover all cases
orders = db.entity("Order").find(
    filters={
        "status": {"$in": ["pending", "processing"]},
        "total": {"$gte": 100},
        "customer.tier": "premium"
    },
    include=["customer", "items.product"],
    order_by=["-created_at", "customer.name"],
    group_by=["status"],
    having={"count": {"$gt": 5}},
    limit=50
)
```

This approach has problems:

1. **Infinite complexity** - Every new query pattern requires new API surface
2. **Leaky abstraction** - Complex queries eventually need raw SQL anyway
3. **Agent friction** - Agents must learn proprietary query DSLs
4. **Maintenance burden** - Query builder code grows unbounded

Meanwhile, LLMs are exceptionally good at:
- Understanding natural language intent
- Generating syntactically correct SQL
- Adapting to schema context
- Handling edge cases through reasoning

## Decision

**Embrace LLM-native query generation as the primary advanced query mechanism.**

Keep the simple `find()` API for basic CRUD, but delegate complex queries to LLM-generated SQL with proper guardrails.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Agent Request                           │
│  "Find premium customers who spent over $1000 last month"       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Schema Context Builder                      │
│  • Entity definitions (fields, types, descriptions)             │
│  • Relationship graph                                           │
│  • Storage modes (shared vs dedicated)                          │
│  • Sample data (optional)                                       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         LLM SQL Generator                        │
│  • Receives schema context + natural language query             │
│  • Generates PostgreSQL-compatible SQL                          │
│  • Handles JSONB operators for shared tables                    │
│  • Generates JOINs for dedicated tables                         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Query Validator                          │
│  • Parse and validate SQL syntax                                │
│  • Enforce read-only (SELECT only by default)                   │
│  • Check table/column access against schema                     │
│  • Detect injection patterns                                    │
│  • Apply row-level security policies                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Query Executor                            │
│  • Execute validated SQL                                        │
│  • Transform results to entity format                           │
│  • Apply output policies (field masking, limits)                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Query Results                             │
│  [{"id": "...", "name": "John", "total_spent": 1250.00}, ...]   │
└─────────────────────────────────────────────────────────────────┘
```

### API Design

#### Simple Queries: Keep `find()` Simple

```python
# Basic CRUD - no changes needed
contacts = db.entity("Contact").find(filters={"status": "active"})
contact = db.entity("Contact").find_by_id(id)
```

#### Complex Queries: `query()` with Natural Language

```python
# Natural language query
results = db.query(
    "Find all orders over $500 from customers in California,
     grouped by product category, for the last 30 days"
)

# With explicit entity context
results = db.query(
    "Which customers haven't ordered in 6 months?",
    entities=["Customer", "Order"]  # Hint for schema context
)

# With output format hints
results = db.query(
    "Monthly revenue by region",
    format="aggregation"  # Hints: "records", "aggregation", "scalar"
)
```

#### Raw SQL: `execute()` for Full Control

```python
# When agents need precise control, they can generate SQL directly
sql = """
    SELECT c.data->>'name' as customer_name,
           SUM((o.data->>'total')::numeric) as total_spent
    FROM kdb_records c
    JOIN kdb_records o ON o.data->>'customer_id' = c.id::text
    WHERE c.entity_id = (SELECT id FROM kdb_entity_definitions WHERE name = 'Customer')
      AND o.entity_id = (SELECT id FROM kdb_entity_definitions WHERE name = 'Order')
    GROUP BY c.data->>'name'
    HAVING SUM((o.data->>'total')::numeric) > 1000
"""

results = db.execute(sql, read_only=True)
```

### Schema Context for LLM

The key to good SQL generation is rich schema context:

```python
def get_schema_context(entities: list[str] | None = None) -> dict:
    """Generate schema context for LLM SQL generation."""
    return {
        "database": "postgresql",
        "storage_info": {
            "shared_table": "kdb_records",
            "shared_columns": {
                "id": "UUID primary key",
                "entity_id": "UUID foreign key to kdb_entity_definitions",
                "data": "JSONB containing all field values",
                "created_at": "TIMESTAMPTZ",
                "updated_at": "TIMESTAMPTZ",
                "is_active": "BOOLEAN (soft delete flag)"
            },
            "jsonb_access": {
                "text_field": "data->>'field_name'",
                "numeric_field": "(data->>'field_name')::numeric",
                "boolean_field": "(data->>'field_name')::boolean",
                "json_field": "data->'field_name'",
                "containment": "data @> '{\"field\": \"value\"}'"
            }
        },
        "entities": [
            {
                "name": "Customer",
                "description": "Customer accounts",
                "storage_mode": "dedicated",
                "table_name": "kdb_customer",
                "fields": [
                    {"name": "name", "type": "string", "description": "Full name"},
                    {"name": "email", "type": "string", "description": "Email address", "unique": True},
                    {"name": "tier", "type": "string", "description": "Customer tier: free, premium, enterprise"}
                ]
            },
            {
                "name": "Order",
                "description": "Customer orders",
                "storage_mode": "shared",
                "table_name": "kdb_records",
                "entity_id": "550e8400-e29b-41d4-a716-446655440000",
                "fields": [
                    {"name": "total", "type": "float", "description": "Order total in USD"},
                    {"name": "status", "type": "string", "description": "Order status: pending, shipped, delivered"},
                    {"name": "customer_id", "type": "uuid", "description": "Reference to Customer"}
                ]
            }
        ],
        "relationships": [
            {
                "name": "customer",
                "source": "Order",
                "target": "Customer",
                "type": "many_to_one",
                "join_condition": "Order.customer_id = Customer.id"
            }
        ],
        "examples": [
            {
                "question": "Find active customers",
                "sql": "SELECT * FROM kdb_customer WHERE is_active = true"
            },
            {
                "question": "Find orders over $100",
                "sql": "SELECT * FROM kdb_records WHERE entity_id = '550e8400-...' AND (data->>'total')::numeric > 100"
            }
        ]
    }
```

### Query Validation & Security

```python
class QueryValidator:
    """Validate LLM-generated SQL before execution."""

    def validate(self, sql: str, context: dict) -> ValidationResult:
        # 1. Parse SQL to AST
        ast = sqlparse.parse(sql)

        # 2. Check statement type (SELECT only for read operations)
        if not self._is_select_only(ast):
            return ValidationResult(
                valid=False,
                error="Only SELECT statements allowed for query()"
            )

        # 3. Extract referenced tables and columns
        tables, columns = self._extract_references(ast)

        # 4. Verify access against schema
        for table in tables:
            if not self._can_access_table(table, context):
                return ValidationResult(
                    valid=False,
                    error=f"Access denied to table: {table}"
                )

        # 5. Check for injection patterns
        if self._has_injection_risk(sql):
            return ValidationResult(
                valid=False,
                error="Query contains potentially unsafe patterns"
            )

        # 6. Apply row-level security
        sql = self._apply_rls_policies(sql, context)

        return ValidationResult(valid=True, sql=sql)
```

### MCP Tools

```python
# Natural language query tool
@mcp.tool()
def kameleondb_query(
    question: str,
    entities: list[str] | None = None,
    limit: int = 100
) -> list[dict]:
    """
    Query the database using natural language.

    The question will be converted to SQL using the current schema context.
    Only read operations are allowed.

    Args:
        question: Natural language question about the data
        entities: Optional list of entity names to include in context
        limit: Maximum number of results (default 100)

    Examples:
        - "How many orders were placed last week?"
        - "Find customers who haven't logged in for 30 days"
        - "What's the average order value by customer tier?"
    """
    ...

# Schema context tool (for agents that want to generate SQL themselves)
@mcp.tool()
def kameleondb_get_schema_context(
    entities: list[str] | None = None,
    include_examples: bool = True
) -> dict:
    """
    Get schema context for SQL generation.

    Returns entity definitions, relationships, storage details,
    and example queries to help generate correct SQL.
    """
    ...

# Direct SQL execution (with validation)
@mcp.tool()
def kameleondb_execute_sql(
    sql: str,
    read_only: bool = True
) -> list[dict]:
    """
    Execute a SQL query directly.

    The query is validated before execution:
    - SELECT only (when read_only=True)
    - Table access verified against schema
    - Injection patterns blocked

    Use kameleondb_get_schema_context() first to understand
    the table structure and JSONB access patterns.
    """
    ...
```

## Implementation Plan

### Phase 1: Schema Context API (v0.2.0)

1. **Implement `get_schema_context()`**
   - Entity definitions with descriptions
   - Field types and constraints
   - Storage mode information
   - JSONB access pattern documentation

2. **Add MCP tool `kameleondb_get_schema_context`**
   - Agents can request context for SQL generation
   - Filterable by entity list

3. **Create example query library**
   - Common query patterns for JSONB
   - Join patterns for relationships
   - Aggregation examples

### Phase 2: Query Validation (v0.2.1)

1. **Implement `QueryValidator`**
   - SQL parsing with sqlparse
   - Statement type validation
   - Table/column access control
   - Injection detection

2. **Implement `execute()` method**
   - Validated SQL execution
   - Result transformation
   - Error handling with context

3. **Add MCP tool `kameleondb_execute_sql`**
   - Direct SQL with guardrails
   - Read-only by default

### Phase 3: LLM Query Generation (v0.2.2)

1. **Implement `query()` method**
   - Schema context building
   - LLM integration (provider-agnostic)
   - SQL generation prompt engineering
   - Validation and execution pipeline

2. **Add MCP tool `kameleondb_query`**
   - Natural language interface
   - Automatic schema context

3. **Query caching and optimization**
   - Cache common query patterns
   - Query plan analysis

### Phase 4: Advanced Features (v0.3.0)

1. **Write operations via LLM**
   - `db.mutate("Mark all orders over 30 days old as archived")`
   - Strict validation and confirmation flow

2. **Query explanation**
   - `db.explain("Find premium customers")` → Returns SQL + explanation

3. **Query suggestions**
   - Based on schema, suggest useful queries
   - "Did you mean..." for ambiguous requests

## Consequences

### Benefits

1. **Infinite query flexibility** - Any question expressible in SQL
2. **Zero query API maintenance** - LLM handles the complexity
3. **Agent-native interface** - Natural language is the agent's native tongue
4. **Schema-aware generation** - Context ensures correct table/column references
5. **Graceful degradation** - Agents can fall back to raw SQL if needed

### Trade-offs

1. **LLM dependency** - Requires LLM call for complex queries
2. **Latency** - LLM generation adds ~500ms-2s per query
3. **Cost** - Token usage for schema context + generation
4. **Non-determinism** - Same question might generate different SQL

### Mitigations

| Concern | Mitigation |
|---------|------------|
| Latency | Cache common queries, use fast models (Haiku) |
| Cost | Compress schema context, cache results |
| Non-determinism | Validate SQL, test with golden queries |
| Security | Strict validation, read-only default, RLS policies |

### What We're NOT Building

1. ❌ Complex filter DSL (`$and`, `$or`, `$elemMatch`)
2. ❌ Query builder fluent API (`.where().join().select()`)
3. ❌ GraphQL-style nested resolvers
4. ❌ Custom query language

## Alternatives Considered

### 1. Comprehensive Query Builder API
- **Rejected**: Infinite API surface, still needs raw SQL escape hatch

### 2. GraphQL Layer
- **Rejected**: Another abstraction to maintain, agents still need to learn it

### 3. MongoDB-style Query DSL
- **Rejected**: Complex DSL that agents must learn, limited to predefined patterns

### 4. SQL-only (No `find()`)
- **Rejected**: Simple CRUD shouldn't require SQL, keep `find()` for basics

## Example: Full Query Flow

```python
# Agent asks a question
result = db.query("Which products have never been ordered?")

# Internally:
# 1. Build schema context
context = db.get_schema_context(entities=["Product", "Order", "OrderItem"])

# 2. LLM generates SQL
sql = """
SELECT p.*
FROM kdb_product p
LEFT JOIN kdb_records oi
  ON oi.entity_id = (SELECT id FROM kdb_entity_definitions WHERE name = 'OrderItem')
  AND oi.data->>'product_id' = p.id::text
WHERE oi.id IS NULL
  AND p.is_active = true
"""

# 3. Validate SQL
validation = validator.validate(sql, context)
# ✓ SELECT only
# ✓ Tables accessible
# ✓ No injection patterns

# 4. Execute and return
return db._execute_validated(validation.sql)
```

## References

- [Text-to-SQL with LLMs](https://arxiv.org/abs/2308.15363) - Academic survey
- [DIN-SQL](https://arxiv.org/abs/2304.11015) - Schema linking approach
- [SQL injection prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
- [PostgreSQL JSONB operators](https://www.postgresql.org/docs/current/functions-json.html)
