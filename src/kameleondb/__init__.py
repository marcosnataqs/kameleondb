"""KameleonDB - Agent-Native Data Platform with JSONB-First Storage.

A meta-layer on top of PostgreSQL where schema is stored as data, not DDL.
AI agents can create and modify entity schemas dynamically without migrations.
All data stored in PostgreSQL JSONB for semantic locality.

Example:
    from kameleondb import KameleonDB

    db = KameleonDB("postgresql://user:pass@localhost/kameleondb")

    # Create an entity with fields
    contacts = db.create_entity(
        name="Contact",
        fields=[
            {"name": "first_name", "type": "string", "required": True},
            {"name": "email", "type": "string", "unique": True},
        ],
        if_not_exists=True,
    )

    # Insert data and retrieve by ID
    contact_id = contacts.insert({"first_name": "John", "email": "john@example.com"})
    contact = contacts.find_by_id(contact_id)

    # For complex queries, use SQL generation via schema context
    context = db.get_schema_context()
    # Use context with an LLM to generate SQL, then execute with db.execute_sql()

    # Discover schema
    schema = db.describe()
"""

from kameleondb.core.engine import Entity, KameleonDB
from kameleondb.core.types import (
    ChangelogEntry,
    EntityInfo,
    EntitySpec,
    EntityStats,
    FieldInfo,
    FieldSpec,
    FieldType,
    MaterializationPolicy,
    MaterializationSuggestion,
    OnDeleteActionType,
    QueryExecutionResult,
    QueryFilter,
    QueryMetrics,
    QueryResult,
    RelationshipInfo,
    RelationshipSpec,
    RelationshipTypeEnum,
    SchemaInfo,
    StorageModeType,
)
from kameleondb.exceptions import (
    CircularRelationshipError,
    EntityAlreadyExistsError,
    EntityNotFoundError,
    FieldAlreadyExistsError,
    FieldNotFoundError,
    InvalidFieldTypeError,
    InvalidOnDeleteActionError,
    InvalidRelationshipTypeError,
    KameleonDBError,
    MaterializationError,
    QueryError,
    RecordNotFoundError,
    RelationshipAlreadyExistsError,
    RelationshipNotFoundError,
    SchemaChangeError,
    StorageModeError,
    ValidationError,
)
from kameleondb.query import (
    QueryValidator,
    SchemaContextBuilder,
    ValidationResult,
    get_schema_context,
)
from kameleondb.tools import ToolDefinition, ToolRegistry

__version__ = "0.2.0-alpha"

__all__ = [
    # Main classes
    "KameleonDB",
    "Entity",
    # Types
    "FieldType",
    "FieldSpec",
    "EntitySpec",
    "FieldInfo",
    "EntityInfo",
    "SchemaInfo",
    "ChangelogEntry",
    "QueryFilter",
    "QueryResult",
    # Relationship types (ADR-001)
    "RelationshipTypeEnum",
    "RelationshipSpec",
    "RelationshipInfo",
    "StorageModeType",
    "OnDeleteActionType",
    # Tools
    "ToolDefinition",
    "ToolRegistry",
    # LLM-Native Query Generation (ADR-002)
    "SchemaContextBuilder",
    "QueryValidator",
    "ValidationResult",
    "get_schema_context",
    # Query Intelligence (ADR-002)
    "QueryMetrics",
    "MaterializationSuggestion",
    "QueryExecutionResult",
    "MaterializationPolicy",
    "EntityStats",
    # Exceptions
    "KameleonDBError",
    "EntityNotFoundError",
    "EntityAlreadyExistsError",
    "FieldNotFoundError",
    "FieldAlreadyExistsError",
    "InvalidFieldTypeError",
    "ValidationError",
    "RecordNotFoundError",
    "SchemaChangeError",
    "QueryError",
    # Relationship exceptions (ADR-001)
    "RelationshipNotFoundError",
    "RelationshipAlreadyExistsError",
    "InvalidRelationshipTypeError",
    "InvalidOnDeleteActionError",
    "CircularRelationshipError",
    "StorageModeError",
    "MaterializationError",
]
