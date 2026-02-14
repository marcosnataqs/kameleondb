"""Core types and specifications for KameleonDB.

All types are designed to be JSON-serializable for agent consumption.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from kameleondb.core.compat import StrEnum


class FieldType(StrEnum):
    """Supported field types in KameleonDB."""

    STRING = "string"
    TEXT = "text"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DATETIME = "datetime"
    JSON = "json"
    UUID = "uuid"

    @classmethod
    def values(cls) -> list[str]:
        """Return all valid field type values."""
        return [t.value for t in cls]


class StorageModeType(StrEnum):
    """Storage modes for entities (ADR-001: Hybrid Storage)."""

    SHARED = "shared"  # All records in kdb_records table (default, maximum flexibility)
    DEDICATED = "dedicated"  # Entity has its own table (enables foreign keys)

    @classmethod
    def values(cls) -> list[str]:
        """Return all valid storage mode values."""
        return [m.value for m in cls]


class RelationshipTypeEnum(StrEnum):
    """Relationship types between entities."""

    MANY_TO_ONE = "many_to_one"  # e.g., Order -> Customer
    ONE_TO_MANY = "one_to_many"  # e.g., Customer -> Orders
    MANY_TO_MANY = "many_to_many"  # e.g., Product <-> Tag
    ONE_TO_ONE = "one_to_one"  # e.g., User -> Profile

    @classmethod
    def values(cls) -> list[str]:
        """Return all valid relationship type values."""
        return [t.value for t in cls]


class OnDeleteActionType(StrEnum):
    """Referential actions when a related record is deleted."""

    CASCADE = "CASCADE"  # Delete related records
    SET_NULL = "SET_NULL"  # Set foreign key to NULL
    RESTRICT = "RESTRICT"  # Prevent deletion if related records exist
    NO_ACTION = "NO_ACTION"  # Database default

    @classmethod
    def values(cls) -> list[str]:
        """Return all valid on_delete action values."""
        return [a.value for a in cls]


class FieldSpec(BaseModel):
    """Specification for a field definition.

    This is the input format for creating fields. Agents pass this as a dict.
    """

    name: str = Field(..., description="Field name (snake_case recommended)")
    type: FieldType = Field(default=FieldType.STRING, description="Field data type")
    required: bool = Field(default=False, description="Whether field is required")
    unique: bool = Field(default=False, description="Whether field values must be unique")
    indexed: bool = Field(default=False, description="Whether to create an index on this field")
    default: Any = Field(default=None, description="Default value for the field")
    description: str | None = Field(default=None, description="Human-readable field description")

    model_config = {"use_enum_values": True}


class RelationshipSpec(BaseModel):
    """Specification for a relationship definition.

    This is the input format for creating relationships. Agents pass this as a dict.
    """

    name: str = Field(..., description="Relationship name (e.g., 'customer' on Order)")
    target: str = Field(..., description="Target entity name (e.g., 'Customer')")
    type: RelationshipTypeEnum = Field(
        default=RelationshipTypeEnum.MANY_TO_ONE, description="Relationship type"
    )
    foreign_key_field: str | None = Field(
        default=None,
        description="Field storing the FK (auto-generated as '{name}_id' if not provided)",
    )
    inverse_name: str | None = Field(
        default=None, description="Name of inverse relationship on target entity"
    )
    on_delete: OnDeleteActionType = Field(
        default=OnDeleteActionType.SET_NULL, description="Action when target is deleted"
    )
    description: str | None = Field(default=None, description="Relationship description")

    model_config = {"use_enum_values": True}


class EntitySpec(BaseModel):
    """Specification for creating an entity.

    This is the input format for creating entities. Agents pass this as a dict.
    """

    name: str = Field(..., description="Entity name (PascalCase recommended)")
    fields: list[FieldSpec] = Field(default_factory=list, description="List of field definitions")
    relationships: list[RelationshipSpec] = Field(
        default_factory=list, description="List of relationship definitions"
    )
    description: str | None = Field(default=None, description="Human-readable entity description")

    model_config = {"use_enum_values": True}


class FieldInfo(BaseModel):
    """Information about an existing field (output format)."""

    name: str
    type: str
    required: bool
    unique: bool
    indexed: bool
    default: Any
    description: str | None
    created_at: datetime | None = None
    created_by: str | None = None


class RelationshipInfo(BaseModel):
    """Information about an existing relationship (output format)."""

    name: str
    target_entity: str
    relationship_type: str
    foreign_key_field: str | None = None
    inverse_name: str | None = None
    on_delete: str
    on_update: str
    description: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None


class EntityInfo(BaseModel):
    """Information about an existing entity (output format)."""

    name: str
    table_name: str
    description: str | None
    storage_mode: str = "shared"
    dedicated_table_name: str | None = None
    fields: list[FieldInfo]
    relationships: list[RelationshipInfo] = Field(default_factory=list)
    record_count: int | None = None
    created_at: datetime | None = None
    created_by: str | None = None


class SchemaInfo(BaseModel):
    """Full schema information (output format)."""

    entities: dict[str, EntityInfo]
    total_entities: int
    total_fields: int


class ChangelogEntry(BaseModel):
    """A schema change log entry."""

    id: str
    timestamp: datetime
    operation: Literal["create_entity", "drop_entity", "add_field", "drop_field", "modify_field"]
    entity_name: str
    field_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    reason: str | None = None


class QueryFilter(BaseModel):
    """A query filter specification."""

    field: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "like", "in", "is_null"] = "eq"
    value: Any


class QueryResult(BaseModel):
    """Result from a query operation."""

    records: list[dict[str, Any]]
    total_count: int
    limit: int | None = None
    offset: int | None = None


# === Query Intelligence Types (ADR-002) ===


class QueryMetrics(BaseModel):
    """Metrics from a single query execution."""

    execution_time_ms: float
    row_count: int
    entities_accessed: list[str] = Field(default_factory=list)
    has_join: bool = False
    query_type: str  # SELECT, INSERT, UPDATE, DELETE


class MaterializationSuggestion(BaseModel):
    """Actionable suggestion for an agent to materialize an entity."""

    entity_name: str
    reason: str  # Human-readable: "Query took 450ms (threshold: 100ms)"
    evidence: dict[str, Any] = Field(default_factory=dict)  # Machine-readable details
    action: str  # Copy-paste action: "db.materialize_entity('Contact')"
    priority: Literal["high", "medium", "low"] = "medium"


class QueryExecutionResult(BaseModel):
    """Enhanced query result with metrics and suggestions."""

    rows: list[dict[str, Any]]
    metrics: QueryMetrics
    suggestions: list[MaterializationSuggestion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MaterializationPolicy(BaseModel):
    """Configuration for materialization suggestion thresholds."""

    # Immediate triggers (per-query)
    execution_time_threshold_ms: float = 100.0  # Suggest if query > 100ms
    row_count_threshold: int = 1000  # Suggest if rows > 1000

    # Historical triggers (aggregated)
    join_frequency_threshold: int = 10  # Joins in last 24 hours
    join_frequency_window_hours: int = 24
    access_frequency_threshold: int = 50  # Queries in last hour
    access_frequency_window_hours: int = 1

    # Feature flags
    enabled: bool = True  # Enable/disable metrics collection
    store_sql_text: bool = False  # Store raw SQL (PII concern)
    retention_days: int = 7  # Auto-cleanup old metrics


class EntityStats(BaseModel):
    """Aggregated statistics for an entity."""

    entity_name: str
    total_queries: int = 0
    avg_execution_time_ms: float = 0.0
    max_execution_time_ms: float = 0.0
    total_rows_returned: int = 0
    join_count_24h: int = 0
    storage_mode: str = "shared"
    record_count: int = 0
    suggestion: str | None = None
