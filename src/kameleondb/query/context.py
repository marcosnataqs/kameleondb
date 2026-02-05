"""Schema Context Builder for LLM SQL Generation.

Generates rich schema context that LLMs can use to write correct SQL queries
against KameleonDB's JSON-based storage.

The context includes:
- Database info (PostgreSQL with JSONB or SQLite with JSON1)
- Entity definitions with fields and types
- Relationship information
- JSON access patterns and examples (dialect-specific)
- Common query patterns
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from kameleondb import KameleonDB


# PostgreSQL JSONB access patterns
POSTGRESQL_ACCESS_PATTERNS = {
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

# SQLite JSON1 access patterns
SQLITE_ACCESS_PATTERNS = {
    "text_field": "json_extract(data, '$.field_name')",
    "numeric_field": "CAST(json_extract(data, '$.field_name') AS REAL)",
    "integer_field": "CAST(json_extract(data, '$.field_name') AS INTEGER)",
    "boolean_field": "json_extract(data, '$.field_name')",  # Returns 0/1
    "datetime_field": "datetime(json_extract(data, '$.field_name'))",
    "uuid_field": "json_extract(data, '$.field_name')",
    "json_nested": "json_extract(data, '$.field_name')",
    "containment_check": "EXISTS (SELECT 1 FROM json_each(json_extract(data, '$.array_field')) WHERE value = 'target')",
    "key_exists": "json_type(data, '$.field_name') IS NOT NULL",
    "array_contains": "EXISTS (SELECT 1 FROM json_each(json_extract(data, '$.array_field')) WHERE value = 'target')",
}

# PostgreSQL example queries
POSTGRESQL_EXAMPLE_QUERIES = [
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

# SQLite example queries
SQLITE_EXAMPLE_QUERIES = [
    {
        "description": "Find active records of a specific entity",
        "sql": """
SELECT id, data, created_at
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND is_deleted = 0
""",
    },
    {
        "description": "Filter by text field (exact match)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND json_extract(data, '$.status') = 'active'
  AND is_deleted = 0
""",
    },
    {
        "description": "Filter by numeric field (comparison)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND CAST(json_extract(data, '$.total') AS REAL) > 100.00
  AND is_deleted = 0
""",
    },
    {
        "description": "Search text field (case-insensitive)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND json_extract(data, '$.name') LIKE '%search_term%' COLLATE NOCASE
  AND is_deleted = 0
""",
    },
    {
        "description": "Check if field value is in a list",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND json_extract(data, '$.status') IN ('pending', 'processing')
  AND is_deleted = 0
""",
    },
    {
        "description": "Aggregate with GROUP BY",
        "sql": """
SELECT json_extract(data, '$.status') as status,
       COUNT(*) as count,
       SUM(CAST(json_extract(data, '$.total') AS REAL)) as total
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND is_deleted = 0
GROUP BY json_extract(data, '$.status')
""",
    },
    {
        "description": "Join two entities via foreign key field",
        "sql": """
SELECT o.id as order_id,
       o.data as order_data,
       json_extract(c.data, '$.name') as customer_name
FROM kdb_records o
JOIN kdb_records c ON c.id = json_extract(o.data, '$.customer_id')
WHERE o.entity_id = '<order_entity_uuid>'
  AND c.entity_id = '<customer_entity_uuid>'
  AND o.is_deleted = 0
  AND c.is_deleted = 0
""",
    },
    {
        "description": "Date range filter",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND date(json_extract(data, '$.created_date')) >= '2024-01-01'
  AND date(json_extract(data, '$.created_date')) < '2024-02-01'
  AND is_deleted = 0
""",
    },
    {
        "description": "Order by field with pagination",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND is_deleted = 0
ORDER BY CAST(json_extract(data, '$.total') AS REAL) DESC
LIMIT 50 OFFSET 0
""",
    },
    {
        "description": "Check if JSON array contains value",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_id = '<entity_uuid>'
  AND EXISTS (
    SELECT 1 FROM json_each(json_extract(data, '$.tags'))
    WHERE value = 'important'
  )
  AND is_deleted = 0
""",
    },
]


class SchemaContextBuilder:
    """Builds rich schema context for LLM SQL generation.

    The context includes everything an LLM needs to generate correct SQL
    queries against KameleonDB's JSON-based storage model.

    Supports both PostgreSQL (JSONB) and SQLite (JSON1) with dialect-specific
    access patterns and examples.
    """

    def __init__(self, db: KameleonDB) -> None:
        """Initialize the context builder.

        Args:
            db: KameleonDB instance
        """
        self._db = db

    @property
    def dialect(self) -> Literal["postgresql", "sqlite"]:
        """Get the database dialect."""
        return self._db._connection.dialect

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
        dialect = self.dialect

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

        # Select dialect-specific patterns
        if dialect == "postgresql":
            json_patterns = POSTGRESQL_ACCESS_PATTERNS
            storage_model = "JSONB"
            db_version = "15+"
        else:  # sqlite
            json_patterns = SQLITE_ACCESS_PATTERNS
            storage_model = "JSON1"
            db_version = "3.38+"

        # Build the full context
        context: dict[str, Any] = {
            "dialect": dialect,
            "database": dialect,
            "version": db_version,
            "storage_model": storage_model,
            "storage_info": self._build_storage_info(dialect),
            "json_patterns": json_patterns,
            "entities": entity_contexts,
            "relationships": relationships,
        }

        if include_examples:
            if dialect == "postgresql":
                context["example_queries"] = POSTGRESQL_EXAMPLE_QUERIES
            else:
                context["example_queries"] = SQLITE_EXAMPLE_QUERIES

        # Add query guidelines
        context["guidelines"] = self._build_guidelines(dialect)

        return context

    def _build_storage_info(self, dialect: str) -> dict[str, Any]:
        """Build storage info section based on dialect."""
        base_info = {
            "shared_table": "kdb_records",
            "shared_columns": {
                "id": "UUID primary key (stored as VARCHAR(36))",
                "entity_id": "UUID foreign key to kdb_entity_definitions",
                "data": f"{'JSONB' if dialect == 'postgresql' else 'JSON'} containing all field values",
                "created_at": "TIMESTAMP - record creation time",
                "updated_at": "TIMESTAMP - last update time",
                "created_by": "VARCHAR(255) - who created the record",
                "is_deleted": f"{'BOOLEAN' if dialect == 'postgresql' else 'INTEGER (0/1)'} - soft delete flag",
            },
            "meta_tables": {
                "kdb_entity_definitions": "Entity type definitions",
                "kdb_field_definitions": "Field definitions per entity",
                "kdb_relationship_definitions": "Relationship definitions",
                "kdb_schema_changelog": "Audit trail of schema changes",
            },
        }

        if dialect == "postgresql":
            base_info["notes"] = [
                "JSONB provides binary storage with GIN index support",
                "Use @> operator for fast containment checks",
                "Use ->> for text extraction, -> for JSON object access",
            ]
        else:
            base_info["notes"] = [
                "JSON1 extension provides json_extract() and json_each()",
                "Boolean values are stored as 0/1 integers",
                "Use CAST() for type conversions",
                "Array containment requires EXISTS with json_each()",
            ]

        return base_info

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

            # Add SQL access pattern based on type and dialect
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
        if self.dialect == "postgresql":
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
        else:  # sqlite
            type_patterns = {
                "string": f"json_extract(data, '$.{field_name}')",
                "text": f"json_extract(data, '$.{field_name}')",
                "int": f"CAST(json_extract(data, '$.{field_name}') AS INTEGER)",
                "float": f"CAST(json_extract(data, '$.{field_name}') AS REAL)",
                "bool": f"json_extract(data, '$.{field_name}')",  # 0/1
                "datetime": f"datetime(json_extract(data, '$.{field_name}'))",
                "uuid": f"json_extract(data, '$.{field_name}')",
                "json": f"json_extract(data, '$.{field_name}')",
            }

        default = (
            f"data->>'{field_name}'"
            if self.dialect == "postgresql"
            else f"json_extract(data, '$.{field_name}')"
        )
        return type_patterns.get(field_type, default)

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

                # Add join hint based on dialect
                fk_field = rel.get("foreign_key_field")
                target = rel.get("target_entity")
                if fk_field and target:
                    if self.dialect == "postgresql":
                        rel_ctx["join_hint"] = (
                            f"JOIN kdb_records {target.lower()} "
                            f"ON {target.lower()}.id::text = "
                            f"{entity_name.lower()}.data->>'{fk_field}'"
                        )
                    else:  # sqlite
                        rel_ctx["join_hint"] = (
                            f"JOIN kdb_records {target.lower()} "
                            f"ON {target.lower()}.id = "
                            f"json_extract({entity_name.lower()}.data, '$.{fk_field}')"
                        )

                relationships.append(rel_ctx)

        return relationships

    def _build_guidelines(self, dialect: str) -> list[str]:
        """Build SQL generation guidelines.

        Args:
            dialect: Database dialect

        Returns:
            List of guideline strings
        """
        common = [
            "Always filter by entity_id to target the correct entity type",
            "Use LIMIT and OFFSET for pagination",
            "Prefer SELECT specific fields over SELECT * for performance",
            "Use indexes: entity_id + is_deleted have a composite index",
        ]

        if dialect == "postgresql":
            return common + [
                "Always include 'is_deleted = false' to exclude soft-deleted records",
                "Use data->>'field' for text extraction, data->'field' for nested JSON",
                "Cast numeric fields: (data->>'field')::numeric or ::int",
                "Cast boolean fields: (data->>'field')::boolean",
                "Cast datetime fields: (data->>'field')::timestamptz",
                "Use ILIKE for case-insensitive text search",
                "Use @> operator for JSONB containment checks (fast with GIN index)",
                "Use ? operator to check if a key exists in JSONB",
                "For JOINs, match id::text with data->>'foreign_key_field'",
            ]
        else:  # sqlite
            return common + [
                "Always include 'is_deleted = 0' to exclude soft-deleted records",
                "Use json_extract(data, '$.field') for field access",
                "Use CAST(... AS INTEGER) or CAST(... AS REAL) for numeric casts",
                "Boolean values are 0 (false) or 1 (true) - compare directly",
                "Use datetime() for date/time conversions",
                "Use LIKE with COLLATE NOCASE for case-insensitive text search",
                "For array containment, use EXISTS with json_each()",
                "Use json_type(data, '$.field') IS NOT NULL to check key exists",
                "For JOINs, match id with json_extract(data, '$.foreign_key_field')",
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
