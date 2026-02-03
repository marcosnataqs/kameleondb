"""Custom exceptions for KameleonDB.

All exceptions are designed with agent-first principles:
- Actionable error messages that tell what went wrong AND how to fix it
- Include context about available options when relevant
"""

from __future__ import annotations

from typing import Any


class KameleonDBError(Exception):
    """Base exception for all KameleonDB errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        """Return error as JSON-serializable dict for agent consumption."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "context": self.context,
        }


class ConnectionError(KameleonDBError):
    """Failed to connect to the database."""

    pass


class EntityNotFoundError(KameleonDBError):
    """Entity does not exist."""

    def __init__(self, entity_name: str, available_entities: list[str] | None = None) -> None:
        available = available_entities or []
        if available:
            message = (
                f"Entity '{entity_name}' not found. Available entities: {', '.join(available)}"
            )
        else:
            message = f"Entity '{entity_name}' not found. No entities exist yet."

        super().__init__(message, {"entity_name": entity_name, "available_entities": available})
        self.entity_name = entity_name
        self.available_entities = available


class EntityAlreadyExistsError(KameleonDBError):
    """Entity already exists (when if_not_exists=False)."""

    def __init__(self, entity_name: str) -> None:
        message = (
            f"Entity '{entity_name}' already exists. "
            f"Use if_not_exists=True to skip creation if it exists."
        )
        super().__init__(message, {"entity_name": entity_name})
        self.entity_name = entity_name


class FieldNotFoundError(KameleonDBError):
    """Field does not exist on entity."""

    def __init__(
        self, field_name: str, entity_name: str, available_fields: list[str] | None = None
    ) -> None:
        available = available_fields or []
        if available:
            message = (
                f"Field '{field_name}' not found on '{entity_name}'. "
                f"Available fields: {', '.join(available)}"
            )
        else:
            message = f"Field '{field_name}' not found on '{entity_name}'. No fields defined."

        super().__init__(
            message,
            {
                "field_name": field_name,
                "entity_name": entity_name,
                "available_fields": available,
            },
        )
        self.field_name = field_name
        self.entity_name = entity_name
        self.available_fields = available


class FieldAlreadyExistsError(KameleonDBError):
    """Field already exists on entity (when if_not_exists=False)."""

    def __init__(self, field_name: str, entity_name: str) -> None:
        message = (
            f"Field '{field_name}' already exists on '{entity_name}'. "
            f"Use if_not_exists=True to skip creation if it exists."
        )
        super().__init__(message, {"field_name": field_name, "entity_name": entity_name})
        self.field_name = field_name
        self.entity_name = entity_name


class InvalidFieldTypeError(KameleonDBError):
    """Invalid field type specified."""

    VALID_TYPES = ["string", "text", "int", "float", "bool", "datetime", "json", "uuid"]

    def __init__(self, field_type: str) -> None:
        message = f"Invalid field type '{field_type}'. Valid types: {', '.join(self.VALID_TYPES)}"
        super().__init__(message, {"field_type": field_type, "valid_types": self.VALID_TYPES})
        self.field_type = field_type


class ValidationError(KameleonDBError):
    """Data validation failed."""

    def __init__(self, message: str, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message, {"field_errors": field_errors or {}})
        self.field_errors = field_errors or {}


class RecordNotFoundError(KameleonDBError):
    """Record with given ID does not exist."""

    def __init__(self, record_id: str, entity_name: str) -> None:
        message = f"Record '{record_id}' not found in '{entity_name}'."
        super().__init__(message, {"record_id": record_id, "entity_name": entity_name})
        self.record_id = record_id
        self.entity_name = entity_name


class SchemaChangeError(KameleonDBError):
    """Schema change operation failed."""

    pass


class QueryError(KameleonDBError):
    """Query execution failed."""

    pass


# === Relationship Errors (ADR-001: Hybrid Storage) ===


class RelationshipNotFoundError(KameleonDBError):
    """Relationship does not exist on entity."""

    def __init__(
        self,
        relationship_name: str,
        entity_name: str,
        available_relationships: list[str] | None = None,
    ) -> None:
        available = available_relationships or []
        if available:
            message = (
                f"Relationship '{relationship_name}' not found on '{entity_name}'. "
                f"Available relationships: {', '.join(available)}"
            )
        else:
            message = (
                f"Relationship '{relationship_name}' not found on '{entity_name}'. "
                "No relationships defined."
            )

        super().__init__(
            message,
            {
                "relationship_name": relationship_name,
                "entity_name": entity_name,
                "available_relationships": available,
            },
        )
        self.relationship_name = relationship_name
        self.entity_name = entity_name
        self.available_relationships = available


class RelationshipAlreadyExistsError(KameleonDBError):
    """Relationship already exists on entity."""

    def __init__(self, relationship_name: str, entity_name: str) -> None:
        message = (
            f"Relationship '{relationship_name}' already exists on '{entity_name}'. "
            f"Use a different name or remove the existing relationship first."
        )
        super().__init__(
            message, {"relationship_name": relationship_name, "entity_name": entity_name}
        )
        self.relationship_name = relationship_name
        self.entity_name = entity_name


class InvalidRelationshipTypeError(KameleonDBError):
    """Invalid relationship type specified."""

    VALID_TYPES = ["many_to_one", "one_to_many", "many_to_many", "one_to_one"]

    def __init__(self, relationship_type: str) -> None:
        message = (
            f"Invalid relationship type '{relationship_type}'. "
            f"Valid types: {', '.join(self.VALID_TYPES)}"
        )
        super().__init__(
            message, {"relationship_type": relationship_type, "valid_types": self.VALID_TYPES}
        )
        self.relationship_type = relationship_type


class CircularRelationshipError(KameleonDBError):
    """Circular relationship detected that would cause issues."""

    def __init__(self, entity_path: list[str]) -> None:
        path_str = " -> ".join(entity_path)
        message = f"Circular relationship detected: {path_str}. This may cause cascade issues."
        super().__init__(message, {"entity_path": entity_path})
        self.entity_path = entity_path


class InvalidOnDeleteActionError(KameleonDBError):
    """Invalid on_delete action specified."""

    VALID_ACTIONS = ["CASCADE", "SET_NULL", "RESTRICT", "NO_ACTION"]

    def __init__(self, action: str) -> None:
        message = (
            f"Invalid on_delete action '{action}'. Valid actions: {', '.join(self.VALID_ACTIONS)}"
        )
        super().__init__(message, {"action": action, "valid_actions": self.VALID_ACTIONS})
        self.action = action


class StorageModeError(KameleonDBError):
    """Error related to entity storage mode."""

    pass


class MaterializationError(StorageModeError):
    """Error during entity materialization."""

    def __init__(self, entity_name: str, reason: str) -> None:
        message = f"Cannot materialize entity '{entity_name}': {reason}"
        super().__init__(message, {"entity_name": entity_name, "reason": reason})
        self.entity_name = entity_name
        self.reason = reason
