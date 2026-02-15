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
WHERE entity_name = 'Customer'
  AND is_deleted = false
""",
    },
    {
        "description": "Filter by text field (exact match)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_name = 'Order'
  AND data->>'status' = 'active'
  AND is_deleted = false
""",
    },
    {
        "description": "Filter by numeric field (comparison)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_name = 'Order'
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
WHERE entity_name = 'Customer'
  AND is_deleted = 0
""",
    },
    {
        "description": "Filter by text field (exact match)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_name = 'Order'
  AND json_extract(data, '$.status') = 'active'
  AND is_deleted = 0
""",
    },
    {
        "description": "Filter by numeric field (comparison)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_name = 'Order'
  AND CAST(json_extract(data, '$.total') AS REAL) > 100.00
  AND is_deleted = 0
""",
    },
    {
        "description": "Search text field (case-insensitive)",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_name = 'Contact'
  AND json_extract(data, '$.name') LIKE '%search_term%' COLLATE NOCASE
  AND is_deleted = 0
""",
    },
    {
        "description": "Check if field value is in a list",
        "sql": """
SELECT id, data
FROM kdb_records
WHERE entity_name = 'Order'
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
        """Build storage info section based on dialect.

        Documents both shared (JSON) and dedicated (typed column) storage
        modes so LLMs understand how to query each type.
        """
        is_deleted_type = "BOOLEAN" if dialect == "postgresql" else "INTEGER (0/1)"
        is_deleted_false = "false" if dialect == "postgresql" else "0"
        data_type = "JSONB" if dialect == "postgresql" else "JSON"

        base_info: dict[str, Any] = {
            "storage_modes": {
                "shared": (
                    "Default mode. All records stored in 'kdb_records' table with field "
                    f"values in a {data_type} 'data' column. Must filter by entity_id."
                ),
                "dedicated": (
                    "Materialized mode. Entity has its own table with typed columns. "
                    "Fields are direct columns — no JSON extraction needed. "
                    "No entity_id filter needed (table is entity-specific)."
                ),
            },
            "shared_table": "kdb_records",
            "shared_columns": {
                "id": "UUID primary key (stored as VARCHAR(36))",
                "entity_id": "UUID foreign key to kdb_entity_definitions",
                "data": f"{data_type} containing all field values",
                "created_at": "TIMESTAMP - record creation time",
                "updated_at": "TIMESTAMP - last update time",
                "created_by": "VARCHAR(255) - who created the record",
                "is_deleted": f"{is_deleted_type} - soft delete flag",
            },
            "dedicated_columns": {
                "id": "UUID primary key (stored as VARCHAR(36))",
                "<field_name>": "Typed column matching the field definition",
                "created_at": "TIMESTAMP - record creation time",
                "updated_at": "TIMESTAMP - last update time",
                "created_by": "VARCHAR(255) - who created the record",
                "is_deleted": f"{is_deleted_type} - soft delete flag",
            },
            "join_patterns": {
                "shared_to_shared": (
                    f"JOIN kdb_records target_alias ON target_alias.id"
                    f"{'::text' if dialect == 'postgresql' else ''} = "
                    f"{'source_alias.data->>$fk_field' if dialect == 'postgresql' else 'json_extract(source_alias.data, $fk_field)'}"
                ),
                "shared_to_dedicated": (
                    "JOIN dedicated_table target_alias ON target_alias.id"
                    f"{'::text' if dialect == 'postgresql' else ''} = "
                    f"{'source_alias.data->>$fk_field' if dialect == 'postgresql' else 'json_extract(source_alias.data, $fk_field)'}"
                ),
                "dedicated_to_shared": (
                    f"JOIN kdb_records target_alias ON target_alias.id"
                    f"{'::text' if dialect == 'postgresql' else ''} = "
                    "source_alias.fk_column"
                ),
                "dedicated_to_dedicated": (
                    "JOIN dedicated_table target_alias ON target_alias.id = source_alias.fk_column"
                ),
            },
            "meta_tables": {
                "kdb_entity_definitions": "Entity type definitions",
                "kdb_field_definitions": "Field definitions per entity",
                "kdb_relationship_definitions": "Relationship definitions",
                "kdb_schema_changelog": "Audit trail of schema changes",
            },
            "important": (
                f"Always check each entity's storage_mode and table_name. "
                f"Always filter is_deleted = {is_deleted_false}. "
                "For shared entities, always include entity_id in WHERE clause."
            ),
        }

        if dialect == "postgresql":
            base_info["json_notes"] = [
                "JSONB provides binary storage with GIN index support",
                "Use @> operator for fast containment checks",
                "Use ->> for text extraction, -> for JSON object access",
            ]
        else:
            base_info["json_notes"] = [
                "JSON1 extension provides json_extract() and json_each()",
                "Boolean values are stored as 0/1 integers",
                "Use CAST() for type conversions",
                "Array containment requires EXISTS with json_each()",
            ]

        return base_info

    def _resolve_table_name(self, info: dict[str, Any]) -> str:
        """Resolve the actual table name for an entity based on storage mode.

        Args:
            info: Entity info from describe()

        Returns:
            The table name to use in SQL queries
        """
        storage_mode = info.get("storage_mode", "shared")
        if storage_mode == "dedicated":
            dedicated_name = info.get("dedicated_table_name")
            if dedicated_name:
                return str(dedicated_name)
        return "kdb_records"

    def _is_dedicated(self, info: dict[str, Any]) -> bool:
        """Check if an entity uses dedicated storage.

        Args:
            info: Entity info from describe()

        Returns:
            True if the entity is materialized to a dedicated table
        """
        return (
            info.get("storage_mode") == "dedicated" and info.get("dedicated_table_name") is not None
        )

    def _build_entity_context(self, name: str, info: dict[str, Any]) -> dict[str, Any]:
        """Build context for a single entity.

        Generates storage-aware field access patterns. For shared entities,
        fields are accessed via JSON operators. For dedicated entities,
        fields are accessed as direct columns.

        Args:
            name: Entity name
            info: Entity info from describe()

        Returns:
            Entity context dict
        """
        entity_id = info.get("id")
        fields = info.get("fields", [])
        dedicated = self._is_dedicated(info)
        table_name = self._resolve_table_name(info)

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

            # Add SQL access pattern based on storage mode, type, and dialect
            field_type = field.get("type", "string")
            field_name = field.get("name")
            if dedicated:
                # Dedicated tables use direct column access
                field_ctx["sql_access"] = field_name
            else:
                # Shared storage uses JSON access patterns
                field_ctx["sql_access"] = self._get_sql_access_pattern(field_name, field_type)

            field_contexts.append(field_ctx)

        entity_ctx: dict[str, Any] = {
            "name": name,
            "description": info.get("description"),
            "entity_id": entity_id,
            "storage_mode": info.get("storage_mode", "shared"),
            "table_name": table_name,
            "fields": field_contexts,
            "record_count": info.get("record_count"),
        }

        # Add storage-specific notes to help LLM generate correct SQL
        if dedicated:
            entity_ctx["storage_notes"] = (
                f"This entity uses a dedicated table '{table_name}' with typed columns. "
                "Access fields directly by column name (no JSON extraction needed). "
                "Filter soft-deleted records with is_deleted = "
                f"{'false' if self.dialect == 'postgresql' else '0'}."
            )
        else:
            entity_ctx["storage_notes"] = (
                f"This entity uses shared storage in 'kdb_records'. "
                "Access fields via JSON operators on the 'data' column. "
                f"Always filter by entity_id = '{entity_id}' and is_deleted = "
                f"{'false' if self.dialect == 'postgresql' else '0'}."
            )

        return entity_ctx

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

    def _build_join_hint(
        self,
        source_name: str,
        source_info: dict[str, Any],
        target_name: str,
        target_info: dict[str, Any] | None,
        fk_field: str,
    ) -> str:
        """Build a storage-aware JOIN hint for a relationship.

        Generates the correct JOIN syntax based on the storage mode of both
        the source and target entities. Handles all four combinations:
        - shared → shared: JSON field to JSON id
        - shared → dedicated: JSON field to column id
        - dedicated → shared: column to JSON id
        - dedicated → dedicated: column to column (standard SQL)

        Args:
            source_name: Source entity name
            source_info: Source entity info from describe()
            target_name: Target entity name
            target_info: Target entity info from describe() (None if not in filtered set)
            fk_field: Foreign key field name on source entity

        Returns:
            SQL JOIN clause string
        """
        source_dedicated = self._is_dedicated(source_info)
        target_dedicated = target_info is not None and self._is_dedicated(target_info)

        target_table = self._resolve_table_name(target_info) if target_info else "kdb_records"

        src_alias = source_name.lower()
        tgt_alias = target_name.lower()

        # Build the FK access expression (how source references target)
        if source_dedicated:
            fk_expr = f"{src_alias}.{fk_field}"
        elif self.dialect == "postgresql":
            fk_expr = f"{src_alias}.data->>'{fk_field}'"
        else:  # sqlite
            fk_expr = f"json_extract({src_alias}.data, '$.{fk_field}')"

        # Build the target ID expression (what the FK points to)
        if target_dedicated:
            id_expr = f"{tgt_alias}.id"
        elif self.dialect == "postgresql":
            id_expr = f"{tgt_alias}.id::text"
        else:  # sqlite
            id_expr = f"{tgt_alias}.id"

        return f"JOIN {target_table} {tgt_alias} ON {id_expr} = {fk_expr}"

    def _build_relationships(self, entities: dict[str, Any]) -> list[dict[str, Any]]:
        """Build storage-aware relationship context.

        Generates JOIN hints that account for the storage mode of both source
        and target entities in each relationship. This allows LLMs to generate
        correct SQL regardless of whether entities use shared JSON storage or
        dedicated typed tables.

        Args:
            entities: Filtered entities dict

        Returns:
            List of relationship contexts with storage-aware join hints
        """
        # Build a lookup of all entities for resolving targets
        all_entities = self._db.describe().get("entities", {})

        relationships = []

        for entity_name, entity_info in entities.items():
            entity_relationships = entity_info.get("relationships", [])
            for rel in entity_relationships:
                target_name = rel.get("target_entity")
                fk_field = rel.get("foreign_key_field")

                rel_ctx: dict[str, Any] = {
                    "name": rel.get("name"),
                    "source_entity": entity_name,
                    "target_entity": target_name,
                    "relationship_type": rel.get("relationship_type"),
                    "foreign_key_field": fk_field,
                    "description": rel.get("description"),
                }

                # Build storage-aware join hint
                if fk_field and target_name:
                    # Look up target entity info (may not be in filtered set)
                    target_info = all_entities.get(target_name)

                    rel_ctx["join_hint"] = self._build_join_hint(
                        source_name=entity_name,
                        source_info=entity_info,
                        target_name=target_name,
                        target_info=target_info,
                        fk_field=fk_field,
                    )

                    # Add a note about storage modes for clarity
                    source_mode = entity_info.get("storage_mode", "shared")
                    target_mode = (
                        target_info.get("storage_mode", "shared") if target_info else "shared"
                    )
                    if source_mode != target_mode:
                        rel_ctx["storage_note"] = (
                            f"Cross-storage JOIN: {entity_name} ({source_mode}) → "
                            f"{target_name} ({target_mode})"
                        )

                relationships.append(rel_ctx)

        return relationships

    def _build_guidelines(self, dialect: str) -> list[str]:
        """Build SQL generation guidelines.

        Includes storage-aware guidance for both shared (JSON) and dedicated
        (typed columns) entities, as well as cross-storage JOIN patterns.

        Args:
            dialect: Database dialect

        Returns:
            List of guideline strings
        """
        common = [
            "Check each entity's storage_mode and table_name before writing SQL",
            "For shared entities: filter by entity_id and use JSON access patterns on 'data' column",
            "For dedicated entities: use direct column names (no JSON extraction needed)",
            "Always exclude soft-deleted records (is_deleted = false/0)",
            "Use LIMIT and OFFSET for pagination",
            "Prefer SELECT specific fields over SELECT * for performance",
            "Use the join_hint from relationships for correct cross-entity JOINs",
            "When JOINing entities with different storage modes, use the provided join_hint — "
            "it handles the correct access pattern for each side",
        ]

        if dialect == "postgresql":
            return common + [
                "Shared entities: use data->>'field' for text, (data->>'field')::type for casts",
                "Shared entities: use ILIKE for case-insensitive text search",
                "Shared entities: use @> for JSONB containment checks (fast with GIN index)",
                "Shared entities: for JOINs, cast id with id::text when matching against JSON fields",
                "Dedicated entities: use standard SQL column access and type operators",
                "Dedicated entities: no entity_id filter needed (table is entity-specific)",
            ]
        else:  # sqlite
            return common + [
                "Shared entities: use json_extract(data, '$.field') for field access",
                "Shared entities: use CAST(... AS INTEGER/REAL) for numeric comparisons",
                "Shared entities: use LIKE with COLLATE NOCASE for case-insensitive search",
                "Shared entities: for array containment, use EXISTS with json_each()",
                "Dedicated entities: use standard SQL column access",
                "Dedicated entities: no entity_id filter needed (table is entity-specific)",
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
