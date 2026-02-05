"""Dedicated table management for KameleonDB.

Provides DDL operations for creating, modifying, and dropping
entity-specific tables with foreign key support.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from kameleondb.schema.models import (
    EntityDefinition,
    FieldDefinition,
    OnDeleteAction,
    RelationshipDefinition,
    StorageMode,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine


# Mapping from KameleonDB field types to SQLAlchemy column types
FIELD_TYPE_MAP = {
    "string": lambda: String(255),
    "text": lambda: Text(),
    "int": lambda: Integer(),
    "float": lambda: Float(),
    "bool": lambda: Boolean(),
    "datetime": lambda: DateTime(timezone=True),
    "uuid": lambda: String(36),
    "json": lambda: JSONB(),
}


def _map_on_delete(action: str) -> str:
    """Map OnDeleteAction to SQL ON DELETE clause."""
    mapping = {
        OnDeleteAction.CASCADE: "CASCADE",
        OnDeleteAction.SET_NULL: "SET NULL",
        OnDeleteAction.RESTRICT: "RESTRICT",
        OnDeleteAction.NO_ACTION: "NO ACTION",
    }
    return mapping.get(action, "SET NULL")


class DedicatedTableManager:
    """Manages dedicated table DDL operations.

    Creates and manages entity-specific tables that enable:
    - Foreign key constraints for relationships
    - Optimized JOIN performance
    - Database-enforced referential integrity
    """

    def __init__(self, engine: Engine) -> None:
        """Initialize the manager.

        Args:
            engine: SQLAlchemy engine
        """
        self._engine = engine
        self._metadata = MetaData()
        self._is_postgresql = engine.dialect.name == "postgresql"

    def generate_table_name(self, entity_name: str) -> str:
        """Generate dedicated table name for an entity.

        Converts PascalCase/camelCase to snake_case.

        Args:
            entity_name: The entity name (e.g., "CustomerOrder")

        Returns:
            Table name (e.g., "kdb_customer_order")
        """
        # Convert PascalCase to snake_case
        # This handles both regular words and acronyms
        result = []
        for i, char in enumerate(entity_name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        # Replace spaces/dashes with underscores, collapse multiple underscores
        safe_name = "".join(result).replace(" ", "_").replace("-", "_")
        # Collapse multiple consecutive underscores
        while "__" in safe_name:
            safe_name = safe_name.replace("__", "_")
        return f"kdb_{safe_name}"

    def create_dedicated_table(
        self,
        entity: EntityDefinition,
        fields: list[FieldDefinition],
    ) -> str:
        """Create a dedicated table for an entity.

        Args:
            entity: The entity definition
            fields: List of field definitions

        Returns:
            The created table name

        Raises:
            ValueError: If entity is already in dedicated mode
        """
        if entity.storage_mode == StorageMode.DEDICATED:
            raise ValueError(f"Entity '{entity.name}' is already in dedicated mode")

        table_name = self.generate_table_name(entity.name)

        # Build columns
        columns: list[Column[Any]] = [
            Column("id", String(36), primary_key=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
            Column("created_by", String(255), nullable=True),
            Column("is_deleted", Boolean, default=False, nullable=False),
        ]

        # Add field columns
        for field in fields:
            if not field.is_active:
                continue

            col_type = FIELD_TYPE_MAP.get(field.field_type, lambda: String(255))()
            columns.append(
                Column(
                    field.column_name,
                    col_type,
                    nullable=not field.is_required,
                )
            )

        # Build indexes to include in table definition
        indexes: list[Index] = [
            Index(f"ix_{table_name}_is_deleted", "is_deleted"),
        ]

        # Add unique/indexed constraints from field definitions
        for field in fields:
            if not field.is_active:
                continue
            if field.is_unique:
                indexes.append(
                    Index(
                        f"ix_{table_name}_{field.column_name}_unique",
                        field.column_name,
                        unique=True,
                    )
                )
            elif field.is_indexed:
                indexes.append(
                    Index(
                        f"ix_{table_name}_{field.column_name}",
                        field.column_name,
                    )
                )

        # Create table definition with a fresh metadata to avoid conflicts
        # Include indexes in table args so they're created with the table
        metadata = MetaData()
        table = Table(table_name, metadata, *columns, *indexes)

        # Execute DDL - creates table and indexes together
        with self._engine.begin() as conn:
            table.create(conn)

        return table_name

    def drop_dedicated_table(self, table_name: str) -> None:
        """Drop a dedicated table.

        Args:
            table_name: The table name to drop
        """
        with self._engine.begin() as conn:
            if self._is_postgresql:
                conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
            else:
                # SQLite doesn't support CASCADE
                conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))

    def add_foreign_key(
        self,
        relationship: RelationshipDefinition,
        source_table: str,
        target_table: str,
    ) -> str:
        """Add a foreign key constraint for a relationship.

        Args:
            relationship: The relationship definition
            source_table: Source table name
            target_table: Target table name

        Returns:
            The constraint name
        """
        if not relationship.foreign_key_field:
            raise ValueError(
                f"Relationship '{relationship.name}' has no foreign key field defined"
            )

        constraint_name = f"fk_{source_table}_{relationship.name}"
        on_delete = _map_on_delete(relationship.on_delete)

        # Add the FK column if it doesn't exist
        fk_column = f"{relationship.name}_id"

        with self._engine.begin() as conn:
            # Check if column exists
            if self._is_postgresql:
                result = conn.execute(
                    text(
                        """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = :table AND column_name = :column
                """
                    ),
                    {"table": source_table, "column": fk_column},
                )
                if not result.fetchone():
                    conn.execute(
                        text(f'ALTER TABLE "{source_table}" ADD COLUMN "{fk_column}" VARCHAR(36)')
                    )
            else:
                # SQLite - try to add, ignore if exists
                with contextlib.suppress(Exception):
                    conn.execute(
                        text(f'ALTER TABLE "{source_table}" ADD COLUMN "{fk_column}" VARCHAR(36)')
                    )

            # Add FK constraint (PostgreSQL only - SQLite doesn't support ALTER ADD CONSTRAINT)
            if self._is_postgresql:
                conn.execute(
                    text(
                        f"""
                    ALTER TABLE "{source_table}"
                    ADD CONSTRAINT "{constraint_name}"
                    FOREIGN KEY ("{fk_column}")
                    REFERENCES "{target_table}" ("id")
                    ON DELETE {on_delete}
                """
                    )
                )

        return constraint_name

    def remove_foreign_key(self, source_table: str, constraint_name: str) -> None:
        """Remove a foreign key constraint.

        Args:
            source_table: Source table name
            constraint_name: The constraint name to remove
        """
        if self._is_postgresql:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        f'ALTER TABLE "{source_table}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'
                    )
                )
        # SQLite doesn't support dropping constraints, would need to recreate table

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists.

        Args:
            table_name: The table name to check

        Returns:
            True if table exists
        """
        with self._engine.connect() as conn:
            if self._is_postgresql:
                result = conn.execute(
                    text(
                        """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = :table
                    )
                """
                    ),
                    {"table": table_name},
                )
                return result.scalar() or False
            else:
                # SQLite
                result = conn.execute(
                    text(
                        """
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name = :table
                """
                    ),
                    {"table": table_name},
                )
                return result.fetchone() is not None

    def get_row_count(self, table_name: str) -> int:
        """Get the number of rows in a table.

        Args:
            table_name: The table name

        Returns:
            Row count
        """
        with self._engine.connect() as conn:
            result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
            return result.scalar() or 0
