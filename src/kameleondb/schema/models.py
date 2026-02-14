"""SQLAlchemy ORM models for KameleonDB meta-tables and JSONB data.

These tables store schema definitions (entities, fields, relationships)
as data, enabling dynamic schema management without migrations.

The Record table uses PostgreSQL JSONB to store all field values in a
single column, providing semantic locality and better agent reasoning.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from kameleondb.core.compat import UTC

# Dialect-aware JSON type: JSONB on PostgreSQL, JSON on SQLite
# This allows the same models to work with both databases
JSONType = JSONB().with_variant(JSON(), "sqlite")


def generate_uuid() -> str:
    """Generate a new UUID as string."""
    return str(uuid4())


def utc_now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for all KameleonDB models."""

    pass


class StorageMode:
    """Constants for entity storage modes."""

    SHARED = "shared"  # All records in kdb_records table (default, maximum flexibility)
    DEDICATED = "dedicated"  # Entity has its own table (enables foreign keys)


class EntityDefinition(Base):
    """Stores entity type definitions (like Contact, Deal, Company)."""

    __tablename__ = "kdb_entity_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Hybrid storage architecture (ADR-001)
    storage_mode: Mapped[str] = mapped_column(
        String(20), default=StorageMode.SHARED, nullable=False
    )
    dedicated_table_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    fields: Mapped[list[FieldDefinition]] = relationship(
        "FieldDefinition", back_populates="entity", cascade="all, delete-orphan"
    )
    # Relationships where this entity is the source
    outgoing_relationships: Mapped[list[RelationshipDefinition]] = relationship(
        "RelationshipDefinition",
        back_populates="source_entity",
        foreign_keys="RelationshipDefinition.source_entity_id",
        cascade="all, delete-orphan",
    )
    # Relationships where this entity is the target
    incoming_relationships: Mapped[list[RelationshipDefinition]] = relationship(
        "RelationshipDefinition",
        back_populates="target_entity",
        foreign_keys="RelationshipDefinition.target_entity_id",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "table_name": self.table_name,
            "description": self.description,
            "storage_mode": self.storage_mode,
            "dedicated_table_name": self.dedicated_table_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "fields": [f.to_dict() for f in self.fields] if self.fields else [],
        }


class FieldDefinition(Base):
    """Stores field definitions for entities."""

    __tablename__ = "kdb_field_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kdb_entity_definitions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_unique: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    entity: Mapped[EntityDefinition] = relationship("EntityDefinition", back_populates="fields")

    # Composite unique constraint: entity_id + name
    __table_args__ = (Index("ix_kdb_field_entity_name", "entity_id", "name", unique=True),)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "name": self.name,
            "column_name": self.column_name,
            "field_type": self.field_type,
            "is_required": self.is_required,
            "is_unique": self.is_unique,
            "is_indexed": self.is_indexed,
            "default_value": self.default_value,
            "description": self.description,
            "previous_name": self.previous_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
        }


class SchemaChangelog(Base):
    """Audit trail for all schema changes."""

    __tablename__ = "kdb_schema_changelog"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    field_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "operation": self.operation,
            "entity_name": self.entity_name,
            "field_name": self.field_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "created_by": self.created_by,
            "reason": self.reason,
        }


# === Relationship Definitions (ADR-001: Hybrid Storage) ===


class RelationshipType:
    """Constants for relationship types."""

    MANY_TO_ONE = "many_to_one"  # e.g., Order -> Customer (many orders per customer)
    ONE_TO_MANY = "one_to_many"  # e.g., Customer -> Orders (inverse of many_to_one)
    MANY_TO_MANY = "many_to_many"  # e.g., Product <-> Tag (requires junction table)
    ONE_TO_ONE = "one_to_one"  # e.g., User -> Profile


class OnDeleteAction:
    """Constants for referential actions on delete."""

    CASCADE = "CASCADE"  # Delete related records
    SET_NULL = "SET_NULL"  # Set foreign key to NULL
    RESTRICT = "RESTRICT"  # Prevent deletion if related records exist
    NO_ACTION = "NO_ACTION"  # Similar to RESTRICT (database default)


class RelationshipDefinition(Base):
    """Stores relationship definitions between entities.

    Relationships enable foreign key constraints when entities use dedicated storage,
    and provide logical relationship metadata for shared storage entities.
    """

    __tablename__ = "kdb_relationship_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Relationship name (e.g., "customer" on Order entity)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Source entity (the entity that "has" the relationship)
    source_entity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("kdb_entity_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Target entity (the entity being referenced)
    target_entity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("kdb_entity_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Relationship type
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # The field on source entity that stores the foreign key (for many_to_one, one_to_one)
    foreign_key_field: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Inverse relationship name on target entity (optional, for bidirectional navigation)
    inverse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Referential actions
    on_delete: Mapped[str] = mapped_column(String(50), default=OnDeleteAction.SET_NULL)
    on_update: Mapped[str] = mapped_column(String(50), default=OnDeleteAction.CASCADE)

    # Description for documentation
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ORM relationships
    source_entity: Mapped[EntityDefinition] = relationship(
        "EntityDefinition",
        back_populates="outgoing_relationships",
        foreign_keys=[source_entity_id],
    )
    target_entity: Mapped[EntityDefinition] = relationship(
        "EntityDefinition",
        back_populates="incoming_relationships",
        foreign_keys=[target_entity_id],
    )

    # Junction table for many-to-many relationships
    junction_table: Mapped[JunctionTable | None] = relationship(
        "JunctionTable", back_populates="relationship", uselist=False, cascade="all, delete-orphan"
    )

    # Composite unique constraint: source_entity_id + name
    __table_args__ = (
        Index("ix_kdb_rel_source_name", "source_entity_id", "name", unique=True),
        Index("ix_kdb_rel_target", "target_entity_id"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "relationship_type": self.relationship_type,
            "foreign_key_field": self.foreign_key_field,
            "inverse_name": self.inverse_name,
            "on_delete": self.on_delete,
            "on_update": self.on_update,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
        }


class JunctionTable(Base):
    """Stores junction table metadata for many-to-many relationships.

    When a many-to-many relationship is created between dedicated entities,
    this table tracks the auto-generated junction table.
    """

    __tablename__ = "kdb_junction_tables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Reference to the relationship this junction table supports
    relationship_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("kdb_relationship_definitions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # The actual PostgreSQL table name for the junction
    table_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    # Column names in the junction table
    source_fk_column: Mapped[str] = mapped_column(String(255), nullable=False)
    target_fk_column: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # ORM relationship
    relationship: Mapped[RelationshipDefinition] = relationship(
        "RelationshipDefinition", back_populates="junction_table"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "relationship_id": self.relationship_id,
            "table_name": self.table_name,
            "source_fk_column": self.source_fk_column,
            "target_fk_column": self.target_fk_column,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# === JSONB Data Tables ===


class Record(Base):
    """Represents a record with all field data stored in a JSONB column.

    Each record belongs to an entity and stores all field values in a single
    PostgreSQL JSONB column, providing semantic locality for better agent reasoning.
    """

    __tablename__ = "kdb_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kdb_entity_definitions.id", ondelete="CASCADE"), nullable=False
    )

    # JSON column stores all field values (JSONB on PostgreSQL, JSON on SQLite)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    entity: Mapped[EntityDefinition] = relationship("EntityDefinition")

    # Indexes for efficient lookups
    __table_args__ = (Index("ix_kdb_records_entity", "entity_id", "is_deleted"),)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "id": self.id,
            "entity_id": self.entity_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "is_deleted": self.is_deleted,
        }
        # Merge JSONB data
        if self.data:
            result.update(self.data)
        return result


# === Query Metrics (ADR-002: Query Intelligence) ===


class QueryMetric(Base):
    """Tracks individual query executions for intelligence and suggestions.

    Used to collect metrics on query performance and patterns, enabling
    intelligent suggestions for entity materialization.
    """

    __tablename__ = "kdb_query_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    # Query details
    entity_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    query_type: Mapped[str] = mapped_column(String(20), nullable=False)  # SELECT, INSERT, etc.
    execution_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Pattern detection
    has_join: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tables_accessed: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    # Context
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Composite index for efficient aggregation
    __table_args__ = (Index("ix_kdb_query_metrics_entity_time", "entity_name", "timestamp"),)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "entity_name": self.entity_name,
            "query_type": self.query_type,
            "execution_time_ms": self.execution_time_ms,
            "row_count": self.row_count,
            "has_join": self.has_join,
            "tables_accessed": self.tables_accessed,
            "created_by": self.created_by,
        }
