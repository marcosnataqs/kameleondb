"""MCP server for KameleonDB.

Exposes KameleonDB operations as MCP tools for AI agents.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from kameleondb import KameleonDB

# Configure logging to stderr (important for stdio transport)
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

# Create MCP server
mcp = FastMCP("kameleondb")

# Global database instance (set during server startup)
_db: KameleonDB | None = None


def get_db() -> KameleonDB:
    """Get the database instance."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call create_server() first.")
    return _db


# === Schema Discovery Tools ===


@mcp.tool()
def kameleondb_describe() -> str:
    """Get the full database schema including all entities and fields.

    Use this first to understand what data is available.
    Returns JSON with all entities, their fields, and metadata.
    """
    return json.dumps(get_db().describe(), default=str)


@mcp.tool()
def kameleondb_describe_entity(entity_name: str) -> str:
    """Get detailed information about a specific entity.

    Args:
        entity_name: Name of the entity to describe

    Returns:
        JSON with entity details including all fields.
    """
    try:
        info = get_db().describe_entity(entity_name)
        return json.dumps(info.model_dump(), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_list_entities() -> str:
    """List all entity names in the database.

    Returns:
        JSON array of entity names.
    """
    return json.dumps(get_db().list_entities())


# === Entity Management Tools ===


@mcp.tool()
def kameleondb_create_entity(
    name: str,
    fields: list[dict[str, Any]] | None = None,
    description: str | None = None,
    if_not_exists: bool = True,
) -> str:
    """Create a new entity type with optional fields.

    Args:
        name: Entity name (PascalCase recommended, e.g., "Contact", "Product")
        fields: List of field definitions, each with:
            - name: Field name (snake_case)
            - type: One of string, text, int, float, bool, datetime, json, uuid
            - required: Whether field is required (default: false)
            - unique: Whether values must be unique (default: false)
            - indexed: Whether to create index (default: false)
            - default: Default value (optional)
            - description: Field description (optional)
        description: Human-readable entity description
        if_not_exists: If true, skip if entity exists (default: true, idempotent)

    Returns:
        JSON with created entity info.
    """
    try:
        entity = get_db().create_entity(
            name=name,
            fields=fields,
            description=description,
            created_by="mcp",
            if_not_exists=if_not_exists,
        )
        return json.dumps(get_db().describe_entity(entity.name).model_dump(), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_drop_entity(
    entity_name: str,
    reason: str | None = None,
) -> str:
    """Soft-delete an entity.

    Args:
        entity_name: Name of the entity to drop
        reason: Why the entity is being dropped (for audit trail)

    Returns:
        JSON with success status.
    """
    try:
        result = get_db().drop_entity(
            name=entity_name,
            created_by="mcp",
            reason=reason,
        )
        return json.dumps({"success": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_get_changelog(
    entity_name: str | None = None,
    limit: int = 100,
) -> str:
    """Get schema changelog entries (audit trail).

    Args:
        entity_name: Optional filter by entity name
        limit: Maximum entries to return (default: 100)

    Returns:
        JSON array of changelog entries.
    """
    try:
        entries = get_db().get_changelog(entity_name=entity_name, limit=limit)
        return json.dumps(entries, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# === Generic CRUD Tools ===


@mcp.tool()
def kameleondb_insert(
    entity_name: str,
    data: dict[str, Any],
) -> str:
    """Insert a new record into an entity.

    Args:
        entity_name: Name of the entity
        data: Record data as field:value pairs

    Returns:
        JSON with the new record ID.
    """
    try:
        entity = get_db().entity(entity_name)
        record_id = entity.insert(data, created_by="mcp")
        return json.dumps({"id": record_id, "success": True})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_insert_many(
    entity_name: str,
    records: list[dict[str, Any]],
) -> str:
    """Insert multiple records into an entity.

    Args:
        entity_name: Name of the entity
        records: List of record data dicts

    Returns:
        JSON with list of new record IDs.
    """
    try:
        entity = get_db().entity(entity_name)
        record_ids = entity.insert_many(records, created_by="mcp")
        return json.dumps({"ids": record_ids, "count": len(record_ids), "success": True})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_find_by_id(
    entity_name: str,
    record_id: str,
) -> str:
    """Find a record by ID.

    Args:
        entity_name: Name of the entity
        record_id: The record ID to find

    Returns:
        JSON with the record or null if not found.
    """
    try:
        entity = get_db().entity(entity_name)
        record = entity.find_by_id(record_id)
        return json.dumps(record, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_update(
    entity_name: str,
    record_id: str,
    data: dict[str, Any],
) -> str:
    """Update a record.

    Args:
        entity_name: Name of the entity
        record_id: The record ID to update
        data: Fields to update as field:value pairs

    Returns:
        JSON with the updated record.
    """
    try:
        entity = get_db().entity(entity_name)
        updated = entity.update(record_id, data)
        return json.dumps(updated, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_delete(
    entity_name: str,
    record_id: str,
) -> str:
    """Delete a record.

    Args:
        entity_name: Name of the entity
        record_id: The record ID to delete

    Returns:
        JSON with success status.
    """
    try:
        entity = get_db().entity(entity_name)
        result = entity.delete(record_id)
        return json.dumps({"success": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_alter_entity(
    entity_name: str,
    add_fields: list[dict[str, Any]] | None = None,
    drop_fields: list[str] | None = None,
    rename_fields: dict[str, str] | None = None,
    modify_fields: list[dict[str, Any]] | None = None,
    reason: str | None = None,
) -> str:
    """Alter an entity's schema (add, drop, rename, or modify fields).

    This is the unified schema evolution API. Changes are applied in order:
    add -> rename -> modify -> drop.

    Args:
        entity_name: Name of the entity to modify
        add_fields: List of field specs to add, each with:
            - name: Field name (snake_case)
            - type: One of string, text, int, float, bool, datetime, json, uuid
            - required, unique, indexed, default, description (optional)
        drop_fields: List of field names to drop (soft-delete, data preserved)
        rename_fields: Dict mapping old_name -> new_name
        modify_fields: List of field modifications, each with:
            - name: Field name to modify
            - required, unique, indexed, default, description (optional)
        reason: Why these changes are being made (for audit trail)

    Returns:
        JSON with updated entity info.

    Example:
        kameleondb_alter_entity(
            entity_name="Contact",
            add_fields=[{"name": "phone", "type": "string", "indexed": true}],
            drop_fields=["legacy_field"],
            rename_fields={"old_name": "new_name"},
            reason="Updating schema for CRM integration"
        )
    """
    try:
        entity = get_db().entity(entity_name)
        info = entity.alter(
            add_fields=add_fields,
            drop_fields=drop_fields,
            rename_fields=rename_fields,
            modify_fields=modify_fields,
            created_by="mcp",
            reason=reason,
        )
        return json.dumps(info.model_dump(), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# === Relationship Management Tools (ADR-001: Hybrid Storage) ===


@mcp.tool()
def kameleondb_add_relationship(
    source_entity: str,
    name: str,
    target_entity: str,
    relationship_type: str = "many_to_one",
    foreign_key_field: str | None = None,
    inverse_name: str | None = None,
    on_delete: str = "SET_NULL",
    description: str | None = None,
    reason: str | None = None,
) -> str:
    """Add a relationship between two entities.

    Relationships define how entities are connected. The source entity "has"
    the relationship pointing to the target entity.

    Args:
        source_entity: Entity that has the relationship (e.g., "Order")
        name: Relationship name (e.g., "customer")
        target_entity: Entity being referenced (e.g., "Customer")
        relationship_type: Type of relationship:
            - many_to_one: Many source records -> one target (default)
            - one_to_many: One source record -> many targets
            - many_to_many: Many source records <-> many targets
            - one_to_one: One source record -> one target
        foreign_key_field: Field storing the FK (auto-generated as "{name}_id" if not provided)
        inverse_name: Name of inverse relationship on target entity (optional)
        on_delete: Action when target is deleted:
            - SET_NULL: Set FK to null (default)
            - CASCADE: Delete source records too
            - RESTRICT: Prevent deletion if related records exist
        description: Human-readable description
        reason: Why the relationship is being created (for audit trail)

    Returns:
        JSON with the created relationship info.

    Example:
        # Order has a customer (many orders per customer)
        kameleondb_add_relationship(
            source_entity="Order",
            name="customer",
            target_entity="Customer",
            relationship_type="many_to_one",
            inverse_name="orders",
            on_delete="SET_NULL"
        )
    """
    try:
        db = get_db()
        relationship = db._schema_engine.add_relationship(
            source_entity_name=source_entity,
            name=name,
            target_entity_name=target_entity,
            relationship_type=relationship_type,
            foreign_key_field=foreign_key_field,
            inverse_name=inverse_name,
            on_delete=on_delete,
            description=description,
            created_by="mcp",
            reason=reason,
        )
        result = relationship.to_dict()
        result["source_entity"] = source_entity
        result["target_entity"] = target_entity
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_remove_relationship(
    source_entity: str,
    relationship_name: str,
    reason: str | None = None,
) -> str:
    """Remove a relationship from an entity.

    This soft-deletes the relationship metadata. The foreign key field
    and any existing data are preserved.

    Args:
        source_entity: Entity that has the relationship
        relationship_name: Name of the relationship to remove
        reason: Why the relationship is being removed (for audit trail)

    Returns:
        JSON with success status.
    """
    try:
        db = get_db()
        result = db._schema_engine.remove_relationship(
            source_entity_name=source_entity,
            relationship_name=relationship_name,
            created_by="mcp",
            reason=reason,
        )
        return json.dumps({"success": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_list_relationships(
    entity_name: str | None = None,
) -> str:
    """List all relationships, optionally filtered by entity.

    Args:
        entity_name: Optional filter by source entity name

    Returns:
        JSON array of relationship info including source and target entity names.
    """
    try:
        db = get_db()
        relationships = db._schema_engine.list_relationships(entity_name=entity_name)
        return json.dumps(relationships, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# === LLM-Native Query Generation Tools (ADR-002) ===


@mcp.tool()
def kameleondb_get_schema_context(
    entities: list[str] | None = None,
    include_examples: bool = True,
    include_relationships: bool = True,
) -> str:
    """Get schema context for LLM SQL generation.

    Returns rich schema context that can be used to generate correct SQL
    queries against KameleonDB's JSONB-based storage. This is the primary
    tool for agents that want to generate their own SQL.

    The context includes:
    - Entity definitions with fields and types
    - JSONB access patterns for each field type
    - Relationship information and join hints
    - Example queries for common patterns (optional)

    Use this tool BEFORE generating SQL to understand the schema structure.

    Args:
        entities: Optional list of entity names to include (None = all)
        include_examples: Include example SQL queries (default: true)
        include_relationships: Include relationship info (default: true)

    Returns:
        JSON with full schema context including:
        - database: "postgresql"
        - storage_info: JSONB storage patterns
        - entities: Array of entity definitions with fields
        - relationships: Array of relationship definitions
        - jsonb_patterns: How to access different field types
        - example_queries: Common query patterns
        - guidelines: Best practices for query generation

    Example workflow:
        1. Call kameleondb_get_schema_context() to get schema
        2. Generate SQL using the context
        3. Call kameleondb_execute_sql() to run the query
    """
    try:
        return json.dumps(
            get_db().get_schema_context(
                entities=entities,
                include_examples=include_examples,
                include_relationships=include_relationships,
            ),
            default=str,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def kameleondb_execute_sql(
    sql: str,
    read_only: bool = True,
    entity_name: str | None = None,
) -> str:
    """Execute a SQL query with validation, metrics, and optimization hints.

    The query is validated before execution:
    - SELECT only (when read_only=true, the default)
    - Table access verified against KameleonDB tables
    - SQL injection patterns blocked

    Returns results with performance metrics and actionable optimization hints.
    This follows the agent-first principle - all operations provide intelligence inline.

    IMPORTANT: Use kameleondb_get_schema_context() first to understand
    the table structure and JSONB access patterns!

    Key points for writing SQL:
    - All entity data is in kdb_records table
    - Field values are in the 'data' JSONB column
    - Use data->>'field' for text, (data->>'field')::type for casting
    - Always filter by entity_id and is_deleted = false

    Args:
        sql: SQL query to execute
        read_only: Only allow SELECT statements (default: true)
        entity_name: Primary entity being queried (enables better optimization hints)

    Returns:
        JSON with:
        - rows: Array of result rows as objects
        - metrics: {execution_time_ms, row_count, has_join, query_type}
        - suggestions: Array of optimization hints (e.g., materialize suggestions)
        - warnings: Array of validation warnings
        - error: Error message if query failed

    Example SQL for JSONB:
        SELECT id, data->>'name' as name, (data->>'total')::numeric as total
        FROM kdb_records
        WHERE entity_id = '<uuid>'
          AND data->>'status' = 'active'
          AND is_deleted = false
        LIMIT 50

    Example result:
        {
            "rows": [...],
            "metrics": {
                "execution_time_ms": 45.2,
                "row_count": 127,
                "has_join": false,
                "query_type": "SELECT"
            },
            "suggestions": [
                {
                    "entity_name": "Contact",
                    "reason": "Query took 450ms (threshold: 100ms)",
                    "action": "db.materialize_entity('Contact')",
                    "priority": "high"
                }
            ]
        }
    """
    try:
        result = get_db().execute_sql(
            sql=sql,
            read_only=read_only,
            entity_name=entity_name,
            created_by="mcp",
        )
        # Result is QueryExecutionResult, convert to dict
        return json.dumps(
            {
                "rows": result.rows,
                "metrics": result.metrics.model_dump(),
                "suggestions": [s.model_dump() for s in result.suggestions],
                "warnings": result.warnings,
            },
            default=str,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


# === Storage Management Tools (ADR-001: Hybrid Storage Phase 2) ===


@mcp.tool()
def kameleondb_materialize_entity(
    entity_name: str,
    batch_size: int = 1000,
    reason: str | None = None,
) -> str:
    """Migrate an entity from shared to dedicated storage.

    Creates a dedicated table with foreign key constraints for better
    relational integrity and JOIN performance.

    Args:
        entity_name: Name of entity to materialize
        batch_size: Records per batch (default 1000, larger for big tables)
        reason: Why materializing (for audit trail)

    Returns:
        JSON with migration result:
        - success: bool
        - entity_name: str
        - records_migrated: int
        - table_name: str (e.g., "kdb_contact")
        - duration_seconds: float
        - error: str (if failed)

    Example:
        kameleondb_materialize_entity(
            entity_name="Contact",
            reason="Adding foreign key constraints for Order relationships"
        )
    """
    try:
        result = get_db().materialize_entity(
            name=entity_name,
            batch_size=batch_size,
            created_by="mcp",
            reason=reason,
        )
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
def kameleondb_dematerialize_entity(
    entity_name: str,
    batch_size: int = 1000,
    reason: str | None = None,
) -> str:
    """Migrate an entity from dedicated back to shared storage.

    Moves data back to kdb_records table and drops the dedicated table.
    Useful when foreign key constraints are no longer needed.

    Args:
        entity_name: Name of entity to dematerialize
        batch_size: Records per batch (default 1000)
        reason: Why dematerializing (for audit trail)

    Returns:
        JSON with migration result:
        - success: bool
        - entity_name: str
        - records_migrated: int
        - duration_seconds: float
        - error: str (if failed)
    """
    try:
        result = get_db().dematerialize_entity(
            name=entity_name,
            batch_size=batch_size,
            created_by="mcp",
            reason=reason,
        )
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# === Query Intelligence Tools (ADR-002: Query Metrics) ===




@mcp.tool()
def kameleondb_get_entity_stats(
    entity_name: str,
) -> str:
    """Get aggregated statistics for an entity.

    Returns query performance metrics and patterns to help decide
    whether to materialize an entity to dedicated storage.

    Args:
        entity_name: Entity to get stats for

    Returns:
        JSON with:
        - entity_name: str
        - total_queries: int (lifetime query count)
        - avg_execution_time_ms: float
        - max_execution_time_ms: float
        - total_rows_returned: int
        - join_count_24h: int (joins in last 24 hours)
        - storage_mode: "shared" or "dedicated"
        - record_count: int (current records)
        - suggestion: str (materialization recommendation, if any)

    Example:
        stats = kameleondb_get_entity_stats("Contact")
        # If stats.suggestion exists, consider materialization
    """
    try:
        stats = get_db().get_entity_stats(entity_name)
        return json.dumps(stats.model_dump(), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def create_server(database_url: str, echo: bool = False) -> FastMCP:
    """Create and configure the MCP server with a database connection.

    Args:
        database_url: PostgreSQL database URL (e.g., "postgresql://user:pass@localhost/db")
        echo: Whether to echo SQL statements

    Returns:
        Configured FastMCP server instance
    """
    global _db
    _db = KameleonDB(database_url, echo=echo)
    logger.info(f"KameleonDB initialized with {database_url}")
    return mcp


def main() -> None:
    """Entry point for running the MCP server."""
    parser = argparse.ArgumentParser(description="KameleonDB MCP Server")
    parser.add_argument(
        "--database",
        "-d",
        default="postgresql://localhost/kameleondb",
        help="PostgreSQL database URL (default: postgresql://localhost/kameleondb)",
    )
    parser.add_argument(
        "--echo",
        action="store_true",
        help="Echo SQL statements",
    )
    args = parser.parse_args()

    create_server(args.database, echo=args.echo)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
