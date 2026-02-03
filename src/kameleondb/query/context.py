"""Schema Context Builder for LLM SQL Generation.

Generates rich schema context that LLMs can use to write correct SQL queries
against KameleonDB's JSONB-based storage.

The context includes:
- Database info (PostgreSQL, JSONB storage patterns)
- Entity definitions with fields and types
- Relationship information
- JSONB access patterns and examples
- Common query patterns
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kameleondb import KameleonDB


# Standard JSONB access patterns for different field types
JSONB_ACCESS_PATTERNS = {
    "text_field": "data->>'field_name'",
    "numeric_field": "(data->>'field_name')::numeric",
    "integer_field": "(data->>'field_name')::int",
    "boolean_field": "(data->>'field_name')::boolean",
    "datetime_field": "(data->>'field_name')::timestamptz",
    "uuid_field": "(data->>'field_name')::uuid",
    "json_nested": "data->'field_name'",
    "containment_check": 'data @> \'{"field": "value"}\'::jsonb',
    "key_exists": "data ? 'field_name'",
    "any_key_exists": "data ?| array['field1', 'field2']",
    "all_keys_exist": "data ?& array['field1', 'field2']",
}

# Example queries for common patterns
EXAMPLE_QUERIES = [
    {
        "description": "Find active records of a specific entity",
        "sql": """
SELECT id, data, created_at
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND is_deleted = false
""",
    },
    {
        "description": "Filter by text field (exact match)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND data->>'status' = 'active'
  AND is_deleted = false
""",
    },
    {
        "description": "Filter by numeric field (comparison)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND (data->>'total')::numeric > 100.00
  AND is_deleted = false
""",
    },
    {
        "description": "Search text field (case-insensitive)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND data->>'name' ILIKE '%search_term%'
  AND is_deleted = false
""",
    },
    {
        "description": "Check if field value is in a list",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND data->>'status' IN ('pending', 'processing')
  AND is_deleted = false
""",
    },
    {
        "description": "Aggregate with GROUP BY",
        "sql": """
SELECT data->>'status' as status,
       COUNT(*) as count,
       SUM((data->>'total')::numeric) as total
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND is_deleted = false
GROUP BY data->>'status'
""",
    },
    {
        "description": "Join two entities via foreign key field",
        "sql": """
SELECT o.id as order_id,
       o.data as order_data,
       c.data->>'name' as customer_name
FROM kdb_records o
JOIN kdb_records c ON c.id::text = o.data->>'customer_id'
WHERE o.entity_id = '<order_entity_uuid>'
  AND c.entity_id = '<customer_entity_uuid>'
  AND o.is_deleted = false
  AND c.is_deleted = false
""",
    },
    {
        "description": "Date range filter",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND (data->>'created_date')::date >= '2024-01-01'
  AND (data->>'created_date')::date < '2024-02-01'
  AND is_deleted = false
""",
    },
    {
        "description": "Order by field with pagination",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND is_deleted = false
ORDER BY (data->>'total')::numeric DESC
LIMIT 50 OFFSET 0
""",
    },
    {
        "description": "Check if JSON field contains value",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND data @> '{"tags": ["important"]}'::jsonb
  AND is_deleted = false
""",
    },
]


class SchemaContextBuilder:
    """Builds rich schema context for LLM SQL generation.

    The context includes everything an LLM needs to generate correct SQL
    queries against KameleonDB's JSONB-based storage model.
    """

    def __init__(self, db: KameleonDB) -> None:
        """Initialize the context builder.

        Args:
            db: KameleonDB instance
        """
        self._db = db

    def build_context(
        self,
        entities: list[str] | None = None,
        include_examples: bool = True,
        include_relationships: bool = True,
    ) -> dict[str, Any]:
        """Build schema context for LLM SQL generation.

        Args:
            entities: Optional list of entity names to include (None = all)
            include_examples: Whether to include example queries
            include_relationships: Whether to include relationship info

        Returns:
            Schema context dict suitable for LLM prompts
        """
        # Get full schema
        schema = self._db.describe()

        # Filter entities if specified
        all_entities = schema.get("entities", {})
        if entities:
            filtered_entities = {
                name: info for name, info in all_entities.items() if name in entities
            }
        else:
            filtered_entities = all_entities

        # Build entity contexts
        entity_contexts = []
        for name, info in filtered_entities.items():
            entity_ctx = self._build_entity_context(name, info)
            entity_contexts.append(entity_ctx)

        # Build relationships if requested
        relationships = []
        if include_relationships:
            relationships = self._build_relationships(filtered_entities)

        # Build the full context
        context: dict[str, Any] = {
            "database": "postgresql",
            "version": "15+",
            "storage_model": "JSONB",
            "storage_info": {
                "shared_table": "kdb_records",
                "shared_columns": {
                    "id": "UUID primary key (stored as VARCHAR(36))",
                    "entity_id": "UUID foreign key to kdb_entity_definitions",
                    "data": "JSONB containing all field values",
                    "created_at": "TIMESTAMPTZ - record creation time",
                    "updated_at": "TIMESTAMPTZ - last update time",
                    "created_by": "VARCHAR(255) - who created the record",
                    "is_deleted": "BOOLEAN - soft delete flag (default false)",
                },
                "meta_tables": {
                    "kdb_entity_definitions": "Entity type definitions",
                    "kdb_field_definitions": "Field definitions per entity",
                    "kdb_relationship_definitions": "Relationship definitions",
                    "kdb_schema_changelog": "Audit trail of schema changes",
                },
            },
            "jsonb_patterns": JSONB_ACCESS_PATTERNS,
            "entities": entity_contexts,
            "relationships": relationships,
        }

        if include_examples:
            context["example_queries"] = EXAMPLE_QUERIES

        # Add query guidelines
        context["guidelines"] = self._build_guidelines()

        return context

    def _build_entity_context(self, name: str, info: dict[str, Any]) -> dict[str, Any]:
        """Build context for a single entity.

        Args:
            name: Entity name
            info: Entity info from describe()

        Returns:
            Entity context dict
        """
        entity_id = info.get("id")
        fields = info.get("fields", [])

        field_contexts = []
        for field in fields:
            field_ctx = {
                "name": field.get("name"),
                "type": field.get("type"),
                "description": field.get("description"),
                "required": field.get("required", False),
                "unique": field.get("unique", False),
                "indexed": field.get("indexed", False),
            }

            # Add SQL access pattern based on type
            field_type = field.get("type", "string")
            field_name = field.get("name")
            field_ctx["sql_access"] = self._get_sql_access_pattern(field_name, field_type)

            field_contexts.append(field_ctx)

        return {
            "name": name,
            "description": info.get("description"),
            "entity_id": entity_id,
            "storage_mode": info.get("storage_mode", "shared"),
            "table_name": "kdb_records",  # Always shared for now
            "fields": field_contexts,
            "record_count": info.get("record_count"),
        }

    def _get_sql_access_pattern(self, field_name: str, field_type: str) -> str:
        """Get the SQL access pattern for a field.

        Args:
            field_name: Field name
            field_type: Field type (string, int, float, etc.)

        Returns:
            SQL access pattern string
        """
        type_patterns = {
            "string": f"data->>'{field_name}'",
            "text": f"data->>'{field_name}'",
            "int": f"(data->>'{field_name}')::int",
            "float": f"(data->>'{field_name}')::numeric",
            "bool": f"(data->>'{field_name}')::boolean",
            "datetime": f"(data->>'{field_name}')::timestamptz",
            "uuid": f"(data->>'{field_name}')::uuid",
            "json": f"data->'{field_name}'",
        }
        return type_patterns.get(field_type, f"data->>'{field_name}'")

    def _build_relationships(self, entities: dict[str, Any]) -> list[dict[str, Any]]:
        """Build relationship context.

        Args:
            entities: Filtered entities dict

        Returns:
            List of relationship contexts
        """
        relationships = []

        for entity_name, entity_info in entities.items():
            entity_relationships = entity_info.get("relationships", [])
            for rel in entity_relationships:
                rel_ctx = {
                    "name": rel.get("name"),
                    "source_entity": entity_name,
                    "target_entity": rel.get("target_entity"),
                    "relationship_type": rel.get("relationship_type"),
                    "foreign_key_field": rel.get("foreign_key_field"),
                    "description": rel.get("description"),
                }

                # Add join hint
                fk_field = rel.get("foreign_key_field")
                target = rel.get("target_entity")
                if fk_field and target:
                    rel_ctx["join_hint"] = (
                        f"JOIN kdb_records {target.lower()} "
                        f"ON {target.lower()}.id::text = "
                        f"{entity_name.lower()}.data->>'{fk_field}'"
                    )

                relationships.append(rel_ctx)

        return relationships

    def _build_guidelines(self) -> list[str]:
        """Build SQL generation guidelines.

        Returns:
            List of guideline strings
        """
        return [
            "Always filter by entity_id to target the correct entity type",
            "Always include 'is_deleted = false' to exclude soft-deleted records",
            "Use data->>'field' for text extraction, data->'field' for nested JSON",
            "Cast numeric fields: (data->>'field')::numeric or ::int",
            "Cast boolean fields: (data->>'field')::boolean",
            "Cast datetime fields: (data->>'field')::timestamptz",
            "Use ILIKE for case-insensitive text search",
            "Use @> operator for JSONB containment checks (fast with GIN index)",
            "Use ? operator to check if a key exists in JSONB",
            "For JOINs, match id::text with data->>'foreign_key_field'",
            "Use LIMIT and OFFSET for pagination",
            "Prefer SELECT specific fields over SELECT * for performance",
            "Use indexes: entity_id + is_deleted have a composite index",
        ]


def get_schema_context(
    db: KameleonDB,
    entities: list[str] | None = None,
    include_examples: bool = True,
    include_relationships: bool = True,
) -> dict[str, Any]:
    """Convenience function to get schema context.

    Args:
        db: KameleonDB instance
        entities: Optional list of entity names to include
        include_examples: Whether to include example queries
        include_relationships: Whether to include relationship info

    Returns:
        Schema context dict for LLM SQL generation
    """
    builder = SchemaContextBuilder(db)
    return builder.build_context(
        entities=entities,
        include_examples=include_examples,
        include_relationships=include_relationships,
    )
