"""Schema Engine for managing entity and field definitions."""

from __future__ import annotations

import json
from types import EllipsisType
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from kameleondb.core.types import (
    EntityInfo,
    FieldInfo,
    FieldSpec,
    FieldType,
    OnDeleteActionType,
    RelationshipInfo,
    RelationshipTypeEnum,
    SchemaInfo,
)
from kameleondb.exceptions import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    FieldAlreadyExistsError,
    FieldNotFoundError,
    InvalidFieldTypeError,
    InvalidOnDeleteActionError,
    InvalidRelationshipTypeError,
    RelationshipAlreadyExistsError,
    RelationshipNotFoundError,
)
from kameleondb.schema.models import (
    Base,
    EntityDefinition,
    FieldDefinition,
    RelationshipDefinition,
    SchemaChangelog,
)

if TYPE_CHECKING:
    from kameleondb.core.connection import DatabaseConnection


class SchemaEngine:
    """Manages schema definitions stored in meta-tables.

    This engine handles CRUD operations on EntityDefinition and FieldDefinition
    models, providing the "schema as data" functionality.
    """

    def __init__(self, connection: DatabaseConnection) -> None:
        """Initialize the schema engine.

        Args:
            connection: Database connection to use
        """
        self._connection = connection
        self._initialized = False

    def initialize(self) -> None:
        """Create meta-tables if they don't exist."""
        if not self._initialized:
            Base.metadata.create_all(self._connection.engine)
            self._initialized = True

    def _get_session(self) -> Session:
        """Get a new database session."""
        return self._connection.get_session()

    def _to_table_name(self, entity_name: str) -> str:
        """Convert entity name to table name (e.g., Contact -> kdb_contact)."""
        # Convert PascalCase to snake_case
        result = []
        for i, char in enumerate(entity_name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return f"kdb_{''.join(result)}"

    def _validate_field_type(self, field_type: str) -> FieldType:
        """Validate and return a FieldType enum value."""
        try:
            return FieldType(field_type)
        except ValueError as e:
            raise InvalidFieldTypeError(field_type) from e

    def _validate_relationship_type(self, relationship_type: str) -> RelationshipTypeEnum:
        """Validate and return a RelationshipTypeEnum value."""
        try:
            return RelationshipTypeEnum(relationship_type)
        except ValueError as e:
            raise InvalidRelationshipTypeError(relationship_type) from e

    def _validate_on_delete_action(self, action: str) -> OnDeleteActionType:
        """Validate and return an OnDeleteActionType value."""
        try:
            return OnDeleteActionType(action)
        except ValueError as e:
            raise InvalidOnDeleteActionError(action) from e

    def _log_change(
        self,
        session: Session,
        operation: str,
        entity_name: str,
        field_name: str | None = None,
        old_value: Any = None,
        new_value: Any = None,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Log a schema change to the changelog."""
        entry = SchemaChangelog(
            operation=operation,
            entity_name=entity_name,
            field_name=field_name,
            old_value=json.dumps(old_value) if old_value is not None else None,
            new_value=json.dumps(new_value) if new_value is not None else None,
            created_by=created_by,
            reason=reason,
        )
        session.add(entry)

    def _log_materialization(
        self,
        entity_name: str,
        operation: str,
        old_mode: str,
        new_mode: str,
        table_name: str | None,
        records_migrated: int,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Log a materialization/dematerialization change to the changelog."""
        with self._get_session() as session:
            entry = SchemaChangelog(
                operation=operation,
                entity_name=entity_name,
                old_value=json.dumps(
                    {
                        "storage_mode": old_mode,
                    }
                ),
                new_value=json.dumps(
                    {
                        "storage_mode": new_mode,
                        "dedicated_table_name": table_name,
                        "records_migrated": records_migrated,
                    }
                ),
                created_by=created_by,
                reason=reason,
            )
            session.add(entry)
            session.commit()

    def list_entities(self) -> list[str]:
        """List all entity names.

        Returns:
            List of entity names
        """
        self.initialize()
        with self._get_session() as session:
            entities = session.query(EntityDefinition.name).filter_by(is_active=True).all()
            return [e[0] for e in entities]

    def get_entity(self, name: str) -> EntityDefinition | None:
        """Get an entity definition by name.

        Args:
            name: Entity name

        Returns:
            EntityDefinition or None if not found
        """
        self.initialize()
        with self._get_session() as session:
            return session.query(EntityDefinition).filter_by(name=name, is_active=True).first()

    def entity_exists(self, name: str) -> bool:
        """Check if an entity exists.

        Args:
            name: Entity name

        Returns:
            True if entity exists
        """
        return self.get_entity(name) is not None

    def create_entity(
        self,
        name: str,
        fields: list[dict[str, Any]] | None = None,
        description: str | None = None,
        created_by: str | None = None,
        if_not_exists: bool = False,
    ) -> EntityDefinition:
        """Create a new entity definition.

        Args:
            name: Entity name (PascalCase recommended)
            fields: List of field specifications
            description: Human-readable description
            created_by: Who/what created this entity
            if_not_exists: If True, return existing entity instead of raising error

        Returns:
            The created or existing EntityDefinition

        Raises:
            EntityAlreadyExistsError: If entity exists and if_not_exists=False
        """
        self.initialize()

        with self._get_session() as session:
            # Check if entity already exists
            existing = session.query(EntityDefinition).filter_by(name=name, is_active=True).first()

            if existing:
                if if_not_exists:
                    return existing
                raise EntityAlreadyExistsError(name)

            # Create new entity
            table_name = self._to_table_name(name)
            entity = EntityDefinition(
                name=name,
                table_name=table_name,
                description=description,
                created_by=created_by,
            )
            session.add(entity)
            session.flush()  # Get the ID

            # Add fields
            if fields:
                for field_spec in fields:
                    spec = FieldSpec(**field_spec)
                    self._validate_field_type(
                        spec.type.value if isinstance(spec.type, FieldType) else spec.type
                    )
                    field = FieldDefinition(
                        entity_id=entity.id,
                        name=spec.name,
                        column_name=spec.name,  # Use same name for column
                        field_type=spec.type.value
                        if isinstance(spec.type, FieldType)
                        else spec.type,
                        is_required=spec.required,
                        is_unique=spec.unique,
                        is_indexed=spec.indexed,
                        default_value=json.dumps(spec.default)
                        if spec.default is not None
                        else None,
                        description=spec.description,
                        created_by=created_by,
                    )
                    session.add(field)

            # Log the change
            self._log_change(
                session,
                operation="create_entity",
                entity_name=name,
                new_value={"description": description, "fields": fields},
                created_by=created_by,
            )

            session.commit()

            # Refresh to get relationships
            session.refresh(entity)
            return entity

    def drop_entity(
        self,
        name: str,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> bool:
        """Soft-delete an entity (set is_active=False).

        Args:
            name: Entity name to drop
            created_by: Who/what is dropping this entity
            reason: Why the entity is being dropped

        Returns:
            True if entity was dropped

        Raises:
            EntityNotFoundError: If entity doesn't exist
        """
        self.initialize()

        with self._get_session() as session:
            entity = session.query(EntityDefinition).filter_by(name=name, is_active=True).first()

            if not entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(name, available)

            entity.is_active = False

            self._log_change(
                session,
                operation="drop_entity",
                entity_name=name,
                old_value=entity.to_dict(),
                created_by=created_by,
                reason=reason,
            )

            session.commit()
            return True

    def get_fields(self, entity_name: str) -> list[FieldDefinition]:
        """Get all fields for an entity.

        Args:
            entity_name: Entity name

        Returns:
            List of FieldDefinition objects

        Raises:
            EntityNotFoundError: If entity doesn't exist
        """
        self.initialize()

        with self._get_session() as session:
            entity = (
                session.query(EntityDefinition).filter_by(name=entity_name, is_active=True).first()
            )

            if not entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(entity_name, available)

            return (
                session.query(FieldDefinition)
                .filter_by(entity_id=entity.id, is_active=True)
                .order_by(FieldDefinition.created_at)
                .all()
            )

    def field_exists(self, entity_name: str, field_name: str) -> bool:
        """Check if a field exists on an entity.

        Args:
            entity_name: Entity name
            field_name: Field name

        Returns:
            True if field exists
        """
        self.initialize()

        with self._get_session() as session:
            entity = (
                session.query(EntityDefinition).filter_by(name=entity_name, is_active=True).first()
            )

            if not entity:
                return False

            field = (
                session.query(FieldDefinition)
                .filter_by(entity_id=entity.id, name=field_name, is_active=True)
                .first()
            )

            return field is not None

    def add_field(
        self,
        entity_name: str,
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
    ) -> FieldDefinition:
        """Add a field to an entity.

        Args:
            entity_name: Entity to add field to
            name: Field name
            field_type: Field data type
            required: Whether field is required
            unique: Whether field values must be unique
            indexed: Whether to create an index
            default: Default value
            description: Human-readable description
            created_by: Who/what created this field
            reason: Why the field is being added
            if_not_exists: If True, return existing field instead of raising error

        Returns:
            The created or existing FieldDefinition

        Raises:
            EntityNotFoundError: If entity doesn't exist
            FieldAlreadyExistsError: If field exists and if_not_exists=False
            InvalidFieldTypeError: If field_type is invalid
        """
        self.initialize()
        self._validate_field_type(field_type)

        with self._get_session() as session:
            entity = (
                session.query(EntityDefinition).filter_by(name=entity_name, is_active=True).first()
            )

            if not entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(entity_name, available)

            # Check if field already exists
            existing = (
                session.query(FieldDefinition)
                .filter_by(entity_id=entity.id, name=name, is_active=True)
                .first()
            )

            if existing:
                if if_not_exists:
                    return existing
                raise FieldAlreadyExistsError(name, entity_name)

            field = FieldDefinition(
                entity_id=entity.id,
                name=name,
                column_name=name,
                field_type=field_type,
                is_required=required,
                is_unique=unique,
                is_indexed=indexed,
                default_value=json.dumps(default) if default is not None else None,
                description=description,
                created_by=created_by,
            )
            session.add(field)

            self._log_change(
                session,
                operation="add_field",
                entity_name=entity_name,
                field_name=name,
                new_value={
                    "field_type": field_type,
                    "required": required,
                    "unique": unique,
                    "indexed": indexed,
                    "default": default,
                },
                created_by=created_by,
                reason=reason,
            )

            session.commit()
            session.refresh(field)
            return field

    def drop_field(
        self,
        entity_name: str,
        field_name: str,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> bool:
        """Soft-delete a field (set is_active=False).

        Args:
            entity_name: Entity name
            field_name: Field to drop
            created_by: Who/what is dropping this field
            reason: Why the field is being dropped

        Returns:
            True if field was dropped

        Raises:
            EntityNotFoundError: If entity doesn't exist
            FieldNotFoundError: If field doesn't exist
        """
        self.initialize()

        with self._get_session() as session:
            entity = (
                session.query(EntityDefinition).filter_by(name=entity_name, is_active=True).first()
            )

            if not entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(entity_name, available)

            field = (
                session.query(FieldDefinition)
                .filter_by(entity_id=entity.id, name=field_name, is_active=True)
                .first()
            )

            if not field:
                available = [
                    f[0]
                    for f in session.query(FieldDefinition.name)
                    .filter_by(entity_id=entity.id, is_active=True)
                    .all()
                ]
                raise FieldNotFoundError(field_name, entity_name, available)

            field.is_active = False

            self._log_change(
                session,
                operation="drop_field",
                entity_name=entity_name,
                field_name=field_name,
                old_value=field.to_dict(),
                created_by=created_by,
                reason=reason,
            )

            session.commit()
            return True

    def rename_field(
        self,
        entity_name: str,
        old_name: str,
        new_name: str,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> FieldDefinition:
        """Rename a field (logical name only, column stays the same).

        This follows Metadata-as-Truth architecture: the logical field name
        changes, but the physical column_name remains unchanged.

        Args:
            entity_name: Entity name
            old_name: Current field name
            new_name: New field name
            created_by: Who/what is renaming this field
            reason: Why the field is being renamed

        Returns:
            Updated FieldDefinition

        Raises:
            EntityNotFoundError: If entity doesn't exist
            FieldNotFoundError: If field doesn't exist
            FieldAlreadyExistsError: If new_name already exists
        """
        self.initialize()

        with self._get_session() as session:
            entity = (
                session.query(EntityDefinition).filter_by(name=entity_name, is_active=True).first()
            )

            if not entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(entity_name, available)

            # Find the field to rename
            field = (
                session.query(FieldDefinition)
                .filter_by(entity_id=entity.id, name=old_name, is_active=True)
                .first()
            )

            if not field:
                available = [
                    f[0]
                    for f in session.query(FieldDefinition.name)
                    .filter_by(entity_id=entity.id, is_active=True)
                    .all()
                ]
                raise FieldNotFoundError(old_name, entity_name, available)

            # Check if new name already exists
            existing = (
                session.query(FieldDefinition)
                .filter_by(entity_id=entity.id, name=new_name, is_active=True)
                .first()
            )

            if existing:
                raise FieldAlreadyExistsError(new_name, entity_name)

            # Update field: change logical name, preserve column_name, track previous_name
            field.previous_name = old_name
            field.name = new_name
            # column_name stays the same - this is the key to Metadata-as-Truth

            self._log_change(
                session,
                operation="rename_field",
                entity_name=entity_name,
                field_name=new_name,
                old_value={"name": old_name},
                new_value={"name": new_name, "previous_name": old_name},
                created_by=created_by,
                reason=reason,
            )

            session.commit()
            session.refresh(field)
            return field

    def modify_field(
        self,
        entity_name: str,
        field_name: str,
        required: bool | None = None,
        unique: bool | None = None,
        indexed: bool | None = None,
        default: Any | EllipsisType = ...,  # Use ... as sentinel to distinguish from None
        description: str | None | EllipsisType = ...,  # Use ... as sentinel
        created_by: str | None = None,
        reason: str | None = None,
    ) -> FieldDefinition:
        """Modify field properties (not type - that requires migration).

        Args:
            entity_name: Entity name
            field_name: Field to modify
            required: New required value (or None to keep)
            unique: New unique value (or None to keep)
            indexed: New indexed value (or None to keep)
            default: New default value (or ... to keep, None to clear)
            description: New description (or ... to keep, None to clear)
            created_by: Who/what is modifying this field
            reason: Why the field is being modified

        Returns:
            Updated FieldDefinition

        Raises:
            EntityNotFoundError: If entity doesn't exist
            FieldNotFoundError: If field doesn't exist
        """
        self.initialize()

        with self._get_session() as session:
            entity = (
                session.query(EntityDefinition).filter_by(name=entity_name, is_active=True).first()
            )

            if not entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(entity_name, available)

            field = (
                session.query(FieldDefinition)
                .filter_by(entity_id=entity.id, name=field_name, is_active=True)
                .first()
            )

            if not field:
                available = [
                    f[0]
                    for f in session.query(FieldDefinition.name)
                    .filter_by(entity_id=entity.id, is_active=True)
                    .all()
                ]
                raise FieldNotFoundError(field_name, entity_name, available)

            # Track changes for changelog
            old_values: dict[str, Any] = {}
            new_values: dict[str, Any] = {}

            if required is not None and required != field.is_required:
                old_values["required"] = field.is_required
                new_values["required"] = required
                field.is_required = required

            if unique is not None and unique != field.is_unique:
                old_values["unique"] = field.is_unique
                new_values["unique"] = unique
                field.is_unique = unique

            if indexed is not None and indexed != field.is_indexed:
                old_values["indexed"] = field.is_indexed
                new_values["indexed"] = indexed
                field.is_indexed = indexed

            if default is not ...:
                old_default = json.loads(field.default_value) if field.default_value else None
                if default != old_default:
                    old_values["default"] = old_default
                    new_values["default"] = default
                    field.default_value = json.dumps(default) if default is not None else None

            if description is not ... and description != field.description:
                old_values["description"] = field.description
                new_values["description"] = description
                field.description = description

            if new_values:  # Only log if something changed
                self._log_change(
                    session,
                    operation="modify_field",
                    entity_name=entity_name,
                    field_name=field_name,
                    old_value=old_values,
                    new_value=new_values,
                    created_by=created_by,
                    reason=reason,
                )

            session.commit()
            session.refresh(field)
            return field

    def describe(self) -> SchemaInfo:
        """Get full schema information.

        Returns:
            SchemaInfo with all entities and fields
        """
        self.initialize()

        with self._get_session() as session:
            entities = session.query(EntityDefinition).filter_by(is_active=True).all()

            entity_infos: dict[str, EntityInfo] = {}
            total_fields = 0

            for entity in entities:
                fields = (
                    session.query(FieldDefinition)
                    .filter_by(entity_id=entity.id, is_active=True)
                    .order_by(FieldDefinition.created_at)
                    .all()
                )

                field_infos = [
                    FieldInfo(
                        name=f.name,
                        type=f.field_type,
                        required=f.is_required,
                        unique=f.is_unique,
                        indexed=f.is_indexed,
                        default=json.loads(f.default_value) if f.default_value else None,
                        description=f.description,
                        created_at=f.created_at,
                        created_by=f.created_by,
                    )
                    for f in fields
                ]

                # Get outgoing relationships
                relationships = (
                    session.query(RelationshipDefinition)
                    .filter_by(source_entity_id=entity.id, is_active=True)
                    .all()
                )

                relationship_infos = []
                for rel in relationships:
                    target = (
                        session.query(EntityDefinition).filter_by(id=rel.target_entity_id).first()
                    )
                    relationship_infos.append(
                        RelationshipInfo(
                            name=rel.name,
                            target_entity=target.name if target else "unknown",
                            relationship_type=rel.relationship_type,
                            foreign_key_field=rel.foreign_key_field,
                            inverse_name=rel.inverse_name,
                            on_delete=rel.on_delete,
                            on_update=rel.on_update,
                            description=rel.description,
                            created_at=rel.created_at,
                            created_by=rel.created_by,
                        )
                    )

                entity_infos[entity.name] = EntityInfo(
                    name=entity.name,
                    table_name=entity.table_name,
                    description=entity.description,
                    storage_mode=entity.storage_mode,
                    dedicated_table_name=entity.dedicated_table_name,
                    fields=field_infos,
                    relationships=relationship_infos,
                    created_at=entity.created_at,
                    created_by=entity.created_by,
                )

                total_fields += len(field_infos)

            return SchemaInfo(
                entities=entity_infos,
                total_entities=len(entity_infos),
                total_fields=total_fields,
            )

    def describe_entity(self, entity_name: str) -> EntityInfo:
        """Get information about a specific entity.

        Args:
            entity_name: Entity name

        Returns:
            EntityInfo with entity details and fields

        Raises:
            EntityNotFoundError: If entity doesn't exist
        """
        self.initialize()

        with self._get_session() as session:
            entity = (
                session.query(EntityDefinition).filter_by(name=entity_name, is_active=True).first()
            )

            if not entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(entity_name, available)

            fields = (
                session.query(FieldDefinition)
                .filter_by(entity_id=entity.id, is_active=True)
                .order_by(FieldDefinition.created_at)
                .all()
            )

            field_infos = [
                FieldInfo(
                    name=f.name,
                    type=f.field_type,
                    required=f.is_required,
                    unique=f.is_unique,
                    indexed=f.is_indexed,
                    default=json.loads(f.default_value) if f.default_value else None,
                    description=f.description,
                    created_at=f.created_at,
                    created_by=f.created_by,
                )
                for f in fields
            ]

            # Get outgoing relationships
            relationships = (
                session.query(RelationshipDefinition)
                .filter_by(source_entity_id=entity.id, is_active=True)
                .all()
            )

            relationship_infos = []
            for rel in relationships:
                target = session.query(EntityDefinition).filter_by(id=rel.target_entity_id).first()
                relationship_infos.append(
                    RelationshipInfo(
                        name=rel.name,
                        target_entity=target.name if target else "unknown",
                        relationship_type=rel.relationship_type,
                        foreign_key_field=rel.foreign_key_field,
                        inverse_name=rel.inverse_name,
                        on_delete=rel.on_delete,
                        on_update=rel.on_update,
                        description=rel.description,
                        created_at=rel.created_at,
                        created_by=rel.created_by,
                    )
                )

            return EntityInfo(
                name=entity.name,
                table_name=entity.table_name,
                description=entity.description,
                storage_mode=entity.storage_mode,
                dedicated_table_name=entity.dedicated_table_name,
                fields=field_infos,
                relationships=relationship_infos,
                created_at=entity.created_at,
                created_by=entity.created_by,
            )

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
        self.initialize()

        with self._get_session() as session:
            query = session.query(SchemaChangelog).order_by(SchemaChangelog.timestamp.desc())

            if entity_name:
                query = query.filter_by(entity_name=entity_name)

            entries = query.limit(limit).all()
            return [e.to_dict() for e in entries]

    # === Relationship Methods (ADR-001: Hybrid Storage) ===

    def add_relationship(
        self,
        source_entity_name: str,
        name: str,
        target_entity_name: str,
        relationship_type: str = "many_to_one",
        foreign_key_field: str | None = None,
        inverse_name: str | None = None,
        on_delete: str = "SET_NULL",
        on_update: str = "CASCADE",
        description: str | None = None,
        created_by: str | None = None,
        reason: str | None = None,
        if_not_exists: bool = False,
    ) -> RelationshipDefinition:
        """Add a relationship between two entities.

        Args:
            source_entity_name: Entity that "has" the relationship (e.g., Order)
            name: Relationship name (e.g., "customer")
            target_entity_name: Entity being referenced (e.g., Customer)
            relationship_type: Type of relationship (many_to_one, one_to_many, etc.)
            foreign_key_field: Field storing the FK (auto-generated if not provided)
            inverse_name: Name of inverse relationship on target (optional)
            on_delete: Action when target is deleted (CASCADE, SET_NULL, RESTRICT)
            on_update: Action when target is updated
            description: Human-readable description
            created_by: Who/what created this relationship
            reason: Why the relationship is being created
            if_not_exists: If True, return existing relationship instead of raising error

        Returns:
            The created or existing RelationshipDefinition

        Raises:
            EntityNotFoundError: If source or target entity doesn't exist
            RelationshipAlreadyExistsError: If relationship exists and if_not_exists=False
            InvalidRelationshipTypeError: If relationship_type is invalid
            InvalidOnDeleteActionError: If on_delete/on_update is invalid
        """
        self.initialize()

        # Validate inputs
        rel_type = self._validate_relationship_type(relationship_type)
        self._validate_on_delete_action(on_delete)
        self._validate_on_delete_action(on_update)

        with self._get_session() as session:
            # Get source entity
            source_entity = (
                session.query(EntityDefinition)
                .filter_by(name=source_entity_name, is_active=True)
                .first()
            )
            if not source_entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(source_entity_name, available)

            # Get target entity
            target_entity = (
                session.query(EntityDefinition)
                .filter_by(name=target_entity_name, is_active=True)
                .first()
            )
            if not target_entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(target_entity_name, available)

            # Check if relationship already exists
            existing = (
                session.query(RelationshipDefinition)
                .filter_by(source_entity_id=source_entity.id, name=name, is_active=True)
                .first()
            )
            if existing:
                if if_not_exists:
                    return existing
                raise RelationshipAlreadyExistsError(name, source_entity_name)

            # Auto-generate foreign_key_field if not provided (for many_to_one, one_to_one)
            if foreign_key_field is None and rel_type in (
                RelationshipTypeEnum.MANY_TO_ONE,
                RelationshipTypeEnum.ONE_TO_ONE,
            ):
                foreign_key_field = f"{name}_id"

            # Create the relationship
            relationship = RelationshipDefinition(
                name=name,
                source_entity_id=source_entity.id,
                target_entity_id=target_entity.id,
                relationship_type=rel_type.value,
                foreign_key_field=foreign_key_field,
                inverse_name=inverse_name,
                on_delete=on_delete,
                on_update=on_update,
                description=description,
                created_by=created_by,
            )
            session.add(relationship)

            # If foreign_key_field is specified, ensure the field exists on source entity
            if foreign_key_field and rel_type in (
                RelationshipTypeEnum.MANY_TO_ONE,
                RelationshipTypeEnum.ONE_TO_ONE,
            ):
                existing_field = (
                    session.query(FieldDefinition)
                    .filter_by(entity_id=source_entity.id, name=foreign_key_field, is_active=True)
                    .first()
                )
                if not existing_field:
                    # Auto-create the foreign key field
                    fk_field = FieldDefinition(
                        entity_id=source_entity.id,
                        name=foreign_key_field,
                        column_name=foreign_key_field,
                        field_type="uuid",
                        is_required=False,
                        is_indexed=True,  # FKs should be indexed
                        description=f"Foreign key to {target_entity_name}",
                        created_by=created_by,
                    )
                    session.add(fk_field)

            # Log the change
            self._log_change(
                session,
                operation="add_relationship",
                entity_name=source_entity_name,
                field_name=name,
                new_value={
                    "target_entity": target_entity_name,
                    "relationship_type": rel_type.value,
                    "foreign_key_field": foreign_key_field,
                    "inverse_name": inverse_name,
                    "on_delete": on_delete,
                },
                created_by=created_by,
                reason=reason,
            )

            session.commit()
            session.refresh(relationship)
            return relationship

    def remove_relationship(
        self,
        source_entity_name: str,
        relationship_name: str,
        created_by: str | None = None,
        reason: str | None = None,
    ) -> bool:
        """Remove (soft-delete) a relationship.

        Args:
            source_entity_name: Entity that has the relationship
            relationship_name: Name of the relationship to remove
            created_by: Who/what is removing this relationship
            reason: Why the relationship is being removed

        Returns:
            True if relationship was removed

        Raises:
            EntityNotFoundError: If source entity doesn't exist
            RelationshipNotFoundError: If relationship doesn't exist
        """
        self.initialize()

        with self._get_session() as session:
            # Get source entity
            source_entity = (
                session.query(EntityDefinition)
                .filter_by(name=source_entity_name, is_active=True)
                .first()
            )
            if not source_entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(source_entity_name, available)

            # Get the relationship
            relationship = (
                session.query(RelationshipDefinition)
                .filter_by(
                    source_entity_id=source_entity.id, name=relationship_name, is_active=True
                )
                .first()
            )
            if not relationship:
                available = [
                    r[0]
                    for r in session.query(RelationshipDefinition.name)
                    .filter_by(source_entity_id=source_entity.id, is_active=True)
                    .all()
                ]
                raise RelationshipNotFoundError(relationship_name, source_entity_name, available)

            # Soft delete
            relationship.is_active = False

            # Log the change
            self._log_change(
                session,
                operation="remove_relationship",
                entity_name=source_entity_name,
                field_name=relationship_name,
                old_value=relationship.to_dict(),
                created_by=created_by,
                reason=reason,
            )

            session.commit()
            return True

    def get_relationships(
        self,
        entity_name: str,
        include_incoming: bool = False,
    ) -> list[RelationshipDefinition]:
        """Get relationships for an entity.

        Args:
            entity_name: Entity name
            include_incoming: If True, include relationships where this entity is the target

        Returns:
            List of RelationshipDefinition objects

        Raises:
            EntityNotFoundError: If entity doesn't exist
        """
        self.initialize()

        with self._get_session() as session:
            entity = (
                session.query(EntityDefinition).filter_by(name=entity_name, is_active=True).first()
            )
            if not entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(entity_name, available)

            # Get outgoing relationships
            relationships = (
                session.query(RelationshipDefinition)
                .filter_by(source_entity_id=entity.id, is_active=True)
                .all()
            )

            if include_incoming:
                incoming = (
                    session.query(RelationshipDefinition)
                    .filter_by(target_entity_id=entity.id, is_active=True)
                    .all()
                )
                relationships.extend(incoming)

            return relationships

    def relationship_exists(self, source_entity_name: str, relationship_name: str) -> bool:
        """Check if a relationship exists on an entity.

        Args:
            source_entity_name: Entity name
            relationship_name: Relationship name

        Returns:
            True if relationship exists
        """
        self.initialize()

        with self._get_session() as session:
            entity = (
                session.query(EntityDefinition)
                .filter_by(name=source_entity_name, is_active=True)
                .first()
            )
            if not entity:
                return False

            relationship = (
                session.query(RelationshipDefinition)
                .filter_by(source_entity_id=entity.id, name=relationship_name, is_active=True)
                .first()
            )
            return relationship is not None

    def get_incoming_relationships(
        self,
        entity_name: str,
    ) -> list[dict[str, Any]]:
        """Get relationships where this entity is the target.

        Used for cascade operations - when deleting a record, we need to know
        what other entities reference it and what on_delete action to apply.

        Args:
            entity_name: Target entity name

        Returns:
            List of relationship dicts with source_entity, fk_field, on_delete info

        Raises:
            EntityNotFoundError: If entity doesn't exist
        """
        self.initialize()

        with self._get_session() as session:
            entity = (
                session.query(EntityDefinition).filter_by(name=entity_name, is_active=True).first()
            )
            if not entity:
                available = [
                    e[0]
                    for e in session.query(EntityDefinition.name).filter_by(is_active=True).all()
                ]
                raise EntityNotFoundError(entity_name, available)

            # Get incoming relationships (where this entity is the target)
            incoming = (
                session.query(RelationshipDefinition)
                .filter_by(target_entity_id=entity.id, is_active=True)
                .all()
            )

            result = []
            for rel in incoming:
                # Get source entity name
                source_entity = (
                    session.query(EntityDefinition)
                    .filter_by(id=rel.source_entity_id, is_active=True)
                    .first()
                )
                if source_entity:
                    result.append(
                        {
                            "relationship_name": rel.name,
                            "source_entity": source_entity.name,
                            "target_entity": entity_name,
                            "foreign_key_field": rel.foreign_key_field,
                            "on_delete": rel.on_delete,
                            "relationship_type": rel.relationship_type,
                        }
                    )

            return result

    def list_relationships(self, entity_name: str | None = None) -> list[dict[str, Any]]:
        """List all relationships, optionally filtered by entity.

        Args:
            entity_name: Optional filter by source entity name

        Returns:
            List of relationship info dicts
        """
        self.initialize()

        with self._get_session() as session:
            query = session.query(RelationshipDefinition).filter_by(is_active=True)

            if entity_name:
                entity = (
                    session.query(EntityDefinition)
                    .filter_by(name=entity_name, is_active=True)
                    .first()
                )
                if entity:
                    query = query.filter_by(source_entity_id=entity.id)
                else:
                    return []

            relationships = query.all()

            # Build response with entity names
            result = []
            for rel in relationships:
                source = session.query(EntityDefinition).filter_by(id=rel.source_entity_id).first()
                target = session.query(EntityDefinition).filter_by(id=rel.target_entity_id).first()

                rel_dict = rel.to_dict()
                rel_dict["source_entity"] = source.name if source else None
                rel_dict["target_entity"] = target.name if target else None
                result.append(rel_dict)

            return result
