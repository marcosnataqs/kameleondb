"""Main KameleonDB engine and Entity class."""

from __future__ import annotations

from types import EllipsisType
from typing import Any

from kameleondb.core.connection import DatabaseConnection
from kameleondb.core.types import EntityInfo
from kameleondb.data.jsonb_query import JSONBQuery
from kameleondb.data.table_manager import TableManager
from kameleondb.exceptions import EntityNotFoundError
from kameleondb.schema.engine import SchemaEngine
from kameleondb.tools.base import ToolDefinition
from kameleondb.tools.registry import ToolRegistry


class Entity:
    """Represents an entity with CRUD operations.

    Provides a high-level API for data operations on a specific entity.
    All methods return JSON-serializable results for agent consumption.
    """

    def __init__(
        self,
        name: str,
        db: KameleonDB,
    ) -> None:
        """Initialize entity.

        Args:
            name: Entity name
            db: Parent KameleonDB instance
        """
        self._name = name
        self._db = db
        self._query: JSONBQuery | None = None

    @property
    def name(self) -> str:
        """Get entity name."""
        return self._name

    def _get_query(self) -> JSONBQuery:
        """Get or create JSONB query builder."""
        if self._query is None:
            # Get entity info
            entity_def = self._db._schema_engine.get_entity(self._name)
            if not entity_def:
                raise EntityNotFoundError(self._name, self._db._schema_engine.list_entities())

            # Get field definitions
            fields = self._db._schema_engine.get_fields(self._name)

            self._query = JSONBQuery(
                engine=self._db._connection.engine,
                entity_id=entity_def.id,
                entity_name=self._name,
                fields=fields,
            )

        return self._query

    def insert(
        self,
        data: dict[str, Any],
        created_by: str | None = None,
    ) -> str:
        """Insert a new record.

        Args:
            data: Record data (field: value pairs)
            created_by: Who created this record

        Returns:
            The new record ID
        """
        return self._get_query().insert(data, created_by=created_by)

    def insert_many(
        self,
        records: list[dict[str, Any]],
        created_by: str | None = None,
    ) -> list[str]:
        """Insert multiple records.

        Args:
            records: List of record data dicts
            created_by: Who created these records

        Returns:
            List of new record IDs
        """
        return self._get_query().insert_many(records, created_by=created_by)

    def find_by_id(self, record_id: str) -> dict[str, Any] | None:
        """Find a record by ID.

        Args:
            record_id: Record ID

        Returns:
            Record dict or None if not found
        """
        return self._get_query().find_by_id(record_id)

    def update(
        self,
        record_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a record.

        Args:
            record_id: Record ID to update
            data: Fields to update

        Returns:
            Updated record dict
        """
        return self._get_query().update(record_id, data)

    def delete(self, record_id: str) -> bool:
        """Delete a record.

        Args:
            record_id: Record ID to delete

        Returns:
            True if deleted
        """
        return self._get_query().delete(record_id)

    def add_field(
        self,
        name: str,
        field_type: str = "string",
        required: bool = False,
        unique: bool = False,
        indexed: bool = False,
        default: Any = None,
        description: str | None = None,
        created_by: str | None = None,
        reason: str | None = None,
        if_not_exists: bool = False,
    ) -> EntityInfo:
        """Add a field to this entity.

        In JSONB architecture, this only updates metadata - no DDL required.

        Args:
            name: Field name
            field_type: Field data type
            required: Whether field is required
            unique: Whether field values must be unique
            indexed: Whether to create an index
            default: Default value
            description: Human-readable description
            created_by: Who/what created this field
            reason: Why the field is being added (for audit)
            if_not_exists: If True, skip if exists (idempotent)

        Returns:
            Updated EntityInfo
        """
        # Add to schema (metadata only - no DDL in JSONB)
        self._db._schema_engine.add_field(
            entity_name=self._name,
            name=name,
            field_type=field_type,
            required=required,
            unique=unique,
            indexed=indexed,
            default=default,
            description=description,
            created_by=created_by,
            reason=reason,
            if_not_exists=if_not_exists,
        )

        # Reset query builder to pick up new field
        self._query = None

        return self._db.describe_entity(self._name)

    def drop_field(
        self,
        name: str,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> EntityInfo:
        """Drop a field from this entity (soft-delete).

        The field is marked as inactive. In JSONB, the values remain
        in the JSON but are no longer accessible through queries.

        Args:
            name: Field name to drop
            created_by: Who/what is dropping this field
            reason: Why the field is being dropped (for audit)

        Returns:
            Updated EntityInfo
        """
        self._db._schema_engine.drop_field(
            entity_name=self._name,
            field_name=name,
            created_by=created_by,
            reason=reason,
        )

        # Reset query builder to exclude dropped field
        self._query = None

        return self._db.describe_entity(self._name)

    def rename_field(
        self,
        old_name: str,
        new_name: str,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> EntityInfo:
        """Rename a field (logical name only).

        In JSONB, this only updates metadata - the JSONB keys
        remain unchanged in existing records.

        Args:
            old_name: Current field name
            new_name: New field name
            created_by: Who/what is renaming this field
            reason: Why the field is being renamed (for audit)

        Returns:
            Updated EntityInfo
        """
        self._db._schema_engine.rename_field(
            entity_name=self._name,
            old_name=old_name,
            new_name=new_name,
            created_by=created_by,
            reason=reason,
        )

        # Reset query builder to pick up new name
        self._query = None

        return self._db.describe_entity(self._name)

    def modify_field(
        self,
        name: str,
        required: bool | None = None,
        unique: bool | None = None,
        indexed: bool | None = None,
        default: Any | EllipsisType = ...,
        description: str | None | EllipsisType = ...,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> EntityInfo:
        """Modify field properties.

        Note: Field type changes are not supported (requires data migration).

        Args:
            name: Field name to modify
            required: New required value (or None to keep)
            unique: New unique value (or None to keep)
            indexed: New indexed value (or None to keep)
            default: New default value (or ... to keep, None to clear)
            description: New description (or ... to keep, None to clear)
            created_by: Who/what is modifying this field
            reason: Why the field is being modified (for audit)

        Returns:
            Updated EntityInfo
        """
        self._db._schema_engine.modify_field(
            entity_name=self._name,
            field_name=name,
            required=required,
            unique=unique,
            indexed=indexed,
            default=default,
            description=description,
            created_by=created_by,
            reason=reason,
        )

        # Reset query builder to pick up changes
        self._query = None

        return self._db.describe_entity(self._name)

    def alter(
        self,
        add_fields: list[dict[str, Any]] | None = None,
        drop_fields: list[str] | None = None,
        rename_fields: dict[str, str] | None = None,
        modify_fields: list[dict[str, Any]] | None = None,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> EntityInfo:
        """Unified schema evolution API.

        Applies multiple schema changes in a single call. Changes are applied
        in order: add -> rename -> modify -> drop.

        In JSONB architecture, all these operations are purely metadata changes
        with zero table locking.

        Args:
            add_fields: List of field specs to add, each with:
                - name: Field name
                - type: Field type (default: "string")
                - required, unique, indexed, default, description (optional)
            drop_fields: List of field names to drop (soft-delete)
            rename_fields: Dict mapping old_name -> new_name
            modify_fields: List of field modifications, each with:
                - name: Field name to modify
                - required, unique, indexed, default, description (optional)
            created_by: Who/what is making these changes
            reason: Why these changes are being made (for audit)

        Returns:
            Updated EntityInfo

        Example:
            entity.alter(
                add_fields=[{"name": "phone", "type": "string", "indexed": True}],
                drop_fields=["legacy_field"],
                rename_fields={"old_name": "new_name"},
                modify_fields=[{"name": "status", "indexed": True}],
                reason="Updating contact schema for new CRM integration",
            )
        """
        # 1. Add new fields
        if add_fields:
            for field_spec in add_fields:
                self.add_field(
                    name=field_spec["name"],
                    field_type=field_spec.get("type", "string"),
                    required=field_spec.get("required", False),
                    unique=field_spec.get("unique", False),
                    indexed=field_spec.get("indexed", False),
                    default=field_spec.get("default"),
                    description=field_spec.get("description"),
                    created_by=created_by,
                    reason=reason,
                    if_not_exists=field_spec.get("if_not_exists", False),
                )

        # 2. Rename fields (before drop, so we can rename then drop if needed)
        if rename_fields:
            for old_name, new_name in rename_fields.items():
                self.rename_field(
                    old_name=old_name,
                    new_name=new_name,
                    created_by=created_by,
                    reason=reason,
                )

        # 3. Modify field properties
        if modify_fields:
            for mod_spec in modify_fields:
                self.modify_field(
                    name=mod_spec["name"],
                    required=mod_spec.get("required"),
                    unique=mod_spec.get("unique"),
                    indexed=mod_spec.get("indexed"),
                    default=mod_spec.get("default", ...),
                    description=mod_spec.get("description", ...),
                    created_by=created_by,
                    reason=reason,
                )

        # 4. Drop fields (last, so we can modify before dropping if needed)
        if drop_fields:
            for field_name in drop_fields:
                self.drop_field(
                    name=field_name,
                    created_by=created_by,
                    reason=reason,
                )

        return self._db.describe_entity(self._name)

    def describe(self) -> EntityInfo:
        """Get entity information.

        Returns:
            EntityInfo with entity details and fields
        """
        return self._db.describe_entity(self._name)


class KameleonDB:
    """Main KameleonDB class - Agent-Native Data Platform.

    Provides a high-level API for dynamic schema management and data operations.
    All methods return JSON-serializable results for agent consumption.

    Uses PostgreSQL JSONB for zero-lock schema evolution and semantic locality.

    Example:
        db = KameleonDB("postgresql://user:pass@localhost/kameleondb")
        contacts = db.create_entity(
            name="Contact",
            fields=[{"name": "email", "type": "string"}],
        )
        record_id = contacts.insert({"email": "test@example.com"})
        print(contacts.find_by_id(record_id))
    """

    def __init__(self, url: str, echo: bool = False) -> None:
        """Initialize KameleonDB.

        Args:
            url: Database connection URL
            echo: Whether to echo SQL statements (for debugging)
        """
        self._connection = DatabaseConnection(url, echo=echo)
        self._schema_engine = SchemaEngine(self._connection)
        self._table_manager = TableManager(self._connection.engine)
        self._tool_registry: ToolRegistry | None = None
        self._entities: dict[str, Entity] = {}

        # Initialize meta-tables (schema definitions)
        self._schema_engine.initialize()

        # Initialize JSONB data tables (kdb_records with JSONB column)
        self._table_manager.ensure_jsonb_tables()

    def close(self) -> None:
        """Close the database connection."""
        self._connection.close()

    def __enter__(self) -> KameleonDB:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()

    # === Schema Discovery (agents call this first) ===

    def describe(self) -> dict[str, Any]:
        """Get full schema as dict.

        Returns the complete database schema including all entities and fields.
        Agents should call this first to understand available data.

        Returns:
            Schema info as JSON-serializable dict
        """
        return self._schema_engine.describe().model_dump()

    def describe_entity(self, entity_name: str) -> EntityInfo:
        """Get information about a specific entity.

        Args:
            entity_name: Entity name

        Returns:
            EntityInfo with entity details and fields

        Raises:
            EntityNotFoundError: If entity doesn't exist (includes available entities)
        """
        return self._schema_engine.describe_entity(entity_name)

    def list_entities(self) -> list[str]:
        """List all entity names.

        Returns:
            List of entity names
        """
        return self._schema_engine.list_entities()

    # === Entity Operations (idempotent for agents) ===

    def create_entity(
        self,
        name: str,
        fields: list[dict[str, Any]] | None = None,
        description: str | None = None,
        created_by: str | None = None,
        if_not_exists: bool = False,
    ) -> Entity:
        """Create a new entity type.

        In JSONB architecture, this only creates metadata - no table DDL required.

        Args:
            name: Entity name (PascalCase recommended)
            fields: List of field specifications
            description: Human-readable description
            created_by: Who/what created this entity
            if_not_exists: If True, return existing entity instead of raising error

        Returns:
            Entity instance for data operations

        Raises:
            EntityAlreadyExistsError: If entity exists and if_not_exists=False
        """
        # Create in schema (metadata only - no DDL in JSONB)
        self._schema_engine.create_entity(
            name=name,
            fields=fields,
            description=description,
            created_by=created_by,
            if_not_exists=if_not_exists,
        )

        # Return entity instance
        return self.entity(name)

    def entity(self, name: str) -> Entity:
        """Get an entity by name.

        Args:
            name: Entity name

        Returns:
            Entity instance for data operations

        Raises:
            EntityNotFoundError: If entity doesn't exist
        """
        if name not in self._entities:
            # Verify entity exists
            if not self._schema_engine.entity_exists(name):
                raise EntityNotFoundError(name, self._schema_engine.list_entities())
            self._entities[name] = Entity(name, self)

        return self._entities[name]

    def drop_entity(
        self,
        name: str,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> bool:
        """Drop an entity (soft delete).

        Args:
            name: Entity name
            created_by: Who/what is dropping this entity
            reason: Why the entity is being dropped

        Returns:
            True if dropped

        Raises:
            EntityNotFoundError: If entity doesn't exist
        """
        result = self._schema_engine.drop_entity(
            name=name,
            created_by=created_by,
            reason=reason,
        )

        # Remove from cache
        if name in self._entities:
            del self._entities[name]

        return result

    # === Hybrid Storage (ADR-001) ===

    def materialize_entity(
        self,
        name: str,
        batch_size: int = 1000,
        on_progress: Any = None,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Migrate an entity from shared to dedicated storage.

        Creates a dedicated table for the entity and migrates all data.
        This enables:
        - Foreign key constraints for relationships
        - Optimized JOIN performance
        - Database-enforced referential integrity

        Args:
            name: Entity name to materialize
            batch_size: Number of records to migrate per batch (default 1000)
            on_progress: Optional progress callback
            created_by: Who/what is performing the migration
            reason: Why the entity is being materialized

        Returns:
            Migration result dict with:
            - success: bool
            - records_migrated: int
            - table_name: str (new dedicated table name)
            - duration_seconds: float
            - error: str (if failed)

        Raises:
            EntityNotFoundError: If entity doesn't exist

        Example:
            >>> result = db.materialize_entity("Customer", reason="Adding FK constraints")
            >>> print(f"Migrated {result['records_migrated']} records to {result['table_name']}")
        """
        from kameleondb.storage.migration import StorageMigration

        # Get entity and fields
        entity = self._schema_engine.get_entity(name)
        if not entity:
            raise EntityNotFoundError(name, self._schema_engine.list_entities())

        fields = self._schema_engine.get_fields(name)

        # Perform migration
        migration = StorageMigration(self._connection.engine)
        result = migration.migrate_to_dedicated(
            entity=entity,
            fields=fields,
            batch_size=batch_size,
            on_progress=on_progress,
        )

        # Log to changelog if successful
        if result.success:
            self._schema_engine._log_materialization(
                entity_name=name,
                operation="materialize",
                old_mode="shared",
                new_mode="dedicated",
                table_name=result.table_name,
                records_migrated=result.records_migrated,
                created_by=created_by,
                reason=reason,
            )

        # Clear entity cache
        if name in self._entities:
            del self._entities[name]

        return {
            "success": result.success,
            "entity_name": result.entity_name,
            "records_migrated": result.records_migrated,
            "table_name": result.table_name,
            "duration_seconds": result.duration_seconds,
            "error": result.error,
        }

    def dematerialize_entity(
        self,
        name: str,
        batch_size: int = 1000,
        on_progress: Any = None,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Migrate an entity from dedicated back to shared storage.

        Moves all data back to the shared kdb_records table and drops
        the dedicated table.

        Args:
            name: Entity name to dematerialize
            batch_size: Number of records to migrate per batch (default 1000)
            on_progress: Optional progress callback
            created_by: Who/what is performing the migration
            reason: Why the entity is being dematerialized

        Returns:
            Migration result dict with:
            - success: bool
            - records_migrated: int
            - duration_seconds: float
            - error: str (if failed)

        Raises:
            EntityNotFoundError: If entity doesn't exist

        Example:
            >>> result = db.dematerialize_entity("Customer", reason="Removing FK constraints")
            >>> print(f"Migrated {result['records_migrated']} records back to shared storage")
        """
        from kameleondb.storage.migration import StorageMigration

        # Get entity and fields
        entity = self._schema_engine.get_entity(name)
        if not entity:
            raise EntityNotFoundError(name, self._schema_engine.list_entities())

        fields = self._schema_engine.get_fields(name)

        # Perform migration
        migration = StorageMigration(self._connection.engine)
        result = migration.migrate_to_shared(
            entity=entity,
            fields=fields,
            batch_size=batch_size,
            on_progress=on_progress,
        )

        # Log to changelog if successful
        if result.success:
            self._schema_engine._log_materialization(
                entity_name=name,
                operation="dematerialize",
                old_mode="dedicated",
                new_mode="shared",
                table_name=None,
                records_migrated=result.records_migrated,
                created_by=created_by,
                reason=reason,
            )

        # Clear entity cache
        if name in self._entities:
            del self._entities[name]

        return {
            "success": result.success,
            "entity_name": result.entity_name,
            "records_migrated": result.records_migrated,
            "duration_seconds": result.duration_seconds,
            "error": result.error,
        }

    # === Tool Export (for agent frameworks) ===

    @property
    def tools(self) -> ToolRegistry:
        """Get tool registry.

        Returns:
            ToolRegistry with all available tools
        """
        if self._tool_registry is None:
            self._tool_registry = ToolRegistry(self)
        return self._tool_registry

    def get_tools(self) -> list[ToolDefinition]:
        """Get all available tools.

        Returns:
            List of ToolDefinitions
        """
        return self.tools.get_all()

    def get_changelog(
        self,
        entity_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get schema changelog entries.

        Args:
            entity_name: Optional filter by entity name
            limit: Maximum entries to return

        Returns:
            List of changelog entries as dicts
        """
        return self._schema_engine.get_changelog(
            entity_name=entity_name,
            limit=limit,
        )

    # === LLM-Native Query Generation (ADR-002) ===

    def get_schema_context(
        self,
        entities: list[str] | None = None,
        include_examples: bool = True,
        include_relationships: bool = True,
    ) -> dict[str, Any]:
        """Get schema context for LLM SQL generation.

        Returns rich schema context that LLMs can use to generate correct
        SQL queries against KameleonDB's JSONB-based storage.

        This is the primary interface for agents that want to generate
        their own SQL queries. The context includes:
        - Entity definitions with fields and types
        - JSONB access patterns for each field type
        - Relationship information and join hints
        - Example queries for common patterns

        Args:
            entities: Optional list of entity names to include (None = all)
            include_examples: Whether to include example queries (default True)
            include_relationships: Whether to include relationship info (default True)

        Returns:
            Schema context dict suitable for LLM prompts

        Example:
            >>> context = db.get_schema_context(entities=["Customer", "Order"])
            >>> # Use context in an LLM prompt to generate SQL
            >>> prompt = f"Given this schema: {context}, write SQL to find..."
        """
        from kameleondb.query.context import SchemaContextBuilder

        builder = SchemaContextBuilder(self)
        return builder.build_context(
            entities=entities,
            include_examples=include_examples,
            include_relationships=include_relationships,
        )

    def execute_sql(
        self,
        sql: str,
        read_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Execute a validated SQL query.

        The query is validated before execution:
        - SELECT only (when read_only=True)
        - Table access verified against KameleonDB tables
        - SQL injection patterns blocked

        Use get_schema_context() first to understand the table structure
        and JSONB access patterns.

        Args:
            sql: SQL query to execute
            read_only: If True, only SELECT statements allowed (default True)

        Returns:
            List of result rows as dicts

        Raises:
            QueryError: If validation fails or execution fails

        Example:
            >>> context = db.get_schema_context()
            >>> # Generate SQL using LLM with context
            >>> sql = '''
            ...     SELECT id, data->>'name' as name
            ...     FROM kdb_records
            ...     WHERE entity_id = '...'
            ...       AND is_deleted = false
            ...     LIMIT 10
            ... '''
            >>> results = db.execute_sql(sql)
        """
        from sqlalchemy import text

        from kameleondb.exceptions import QueryError
        from kameleondb.query.validator import QueryValidator

        # Validate the query
        validator = QueryValidator(db=self)
        result = validator.validate(sql, read_only=read_only)

        if not result.valid:
            raise QueryError(f"Query validation failed: {result.error}")

        # Log warnings (but don't fail)
        for _warning in result.warnings:
            # TODO: Add proper logging
            pass

        # Execute the validated query
        try:
            with self._connection.engine.connect() as conn:
                query_result = conn.execute(text(result.sql))
                rows = query_result.fetchall()
                columns = query_result.keys()

                # Convert to list of dicts
                return [dict(zip(columns, row, strict=True)) for row in rows]
        except Exception as e:
            raise QueryError(f"Query execution failed: {e}") from e
