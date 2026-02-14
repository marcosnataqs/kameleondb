"""Main KameleonDB engine and Entity class."""

from __future__ import annotations

from types import EllipsisType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kameleondb.search import SearchEngine

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
                storage_mode=entity_def.storage_mode,
                dedicated_table_name=entity_def.dedicated_table_name,
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
        record_id = self._get_query().insert(data, created_by=created_by)

        # Index for search if embeddings enabled
        self._db._index_record_for_search(self._name, record_id, data)

        return record_id

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
        result = self._get_query().update(record_id, data)

        # Reindex for search if embeddings enabled
        self._db._index_record_for_search(self._name, record_id, result)

        return result

    def delete(
        self,
        record_id: str,
        cascade: bool = True,
        force: bool = False,
    ) -> bool:
        """Delete a record with cascade handling.

        Honors on_delete rules from relationships:
        - CASCADE: Deletes related records in other entities
        - SET_NULL: Sets FK field to null on related records
        - RESTRICT: Blocks delete if related records exist

        Args:
            record_id: Record ID to delete
            cascade: If True, honor on_delete rules (default True)
            force: If True, bypass RESTRICT checks (dangerous, default False)

        Returns:
            True if deleted

        Raises:
            RestrictDeleteError: If RESTRICT blocks deletion
            RecordNotFoundError: If record doesn't exist
        """
        from kameleondb.exceptions import RestrictDeleteError

        # Verify record exists before cascade checks
        existing = self.find_by_id(record_id)
        if not existing:
            from kameleondb.exceptions import RecordNotFoundError

            raise RecordNotFoundError(record_id, self._name)

        if cascade:
            # Get incoming relationships (where this entity is the target)
            incoming_rels = self._db._schema_engine.get_incoming_relationships(self._name)

            for rel in incoming_rels:
                source_entity_name = rel["source_entity"]
                fk_field = rel["foreign_key_field"]
                on_delete = rel["on_delete"]
                rel_type = rel.get("relationship_type", "many_to_one")

                # Handle many-to-many specially - delete junction entries only
                if rel_type == "many_to_many":
                    self._delete_junction_entries_for_target(
                        source_entity_name, rel["relationship_name"], record_id
                    )
                    continue

                if not fk_field:
                    continue  # Skip relationships without FK field

                # Find related records in source entity
                related_count = self._count_related_records(source_entity_name, fk_field, record_id)

                if related_count == 0:
                    continue  # No related records, nothing to do

                # Handle based on on_delete action
                if on_delete == "RESTRICT" and not force:
                    raise RestrictDeleteError(self._name, source_entity_name, related_count)

                elif on_delete == "CASCADE":
                    # Delete related records (this will recursively cascade)
                    self._cascade_delete_related(source_entity_name, fk_field, record_id)

                elif on_delete == "SET_NULL":
                    # Set FK field to null on related records
                    self._set_null_related(source_entity_name, fk_field, record_id)

            # Also clean up many-to-many where this entity is the SOURCE
            self._delete_junction_entries_for_source(record_id)

        # Finally, delete the record itself
        return self._get_query().delete(record_id)

    def _count_related_records(
        self,
        source_entity_name: str,
        fk_field: str,
        target_id: str,
    ) -> int:
        """Count records in source entity that reference the target.

        Args:
            source_entity_name: Entity that has the FK field
            fk_field: Name of the FK field
            target_id: ID being referenced

        Returns:
            Count of related records
        """
        from sqlalchemy import text

        # Build query based on storage mode
        entity_info = self._db._schema_engine.get_entity(source_entity_name)
        if not entity_info:
            return 0

        is_postgresql = self._db._connection.engine.dialect.name == "postgresql"

        if entity_info.storage_mode == "dedicated" and entity_info.dedicated_table_name:
            # Dedicated table - direct column access
            sql = f"""
                SELECT COUNT(*) FROM {entity_info.dedicated_table_name}
                WHERE {fk_field} = :target_id AND is_deleted = {"false" if is_postgresql else "0"}
            """
        else:
            # Shared storage - JSON access
            if is_postgresql:
                sql = f"""
                    SELECT COUNT(*) FROM kdb_records
                    WHERE entity_id = :entity_id
                      AND data->>'{fk_field}' = :target_id
                      AND is_deleted = false
                """
            else:
                sql = f"""
                    SELECT COUNT(*) FROM kdb_records
                    WHERE entity_id = :entity_id
                      AND json_extract(data, '$.{fk_field}') = :target_id
                      AND is_deleted = 0
                """

        with self._db._connection.engine.connect() as conn:
            result = conn.execute(
                text(sql),
                {"entity_id": entity_info.id, "target_id": target_id},
            )
            return result.scalar() or 0

    def _cascade_delete_related(
        self,
        source_entity_name: str,
        fk_field: str,
        target_id: str,
    ) -> int:
        """Delete all records in source entity that reference the target.

        Args:
            source_entity_name: Entity that has the FK field
            fk_field: Name of the FK field
            target_id: ID being referenced

        Returns:
            Count of deleted records
        """
        from sqlalchemy import text

        entity_info = self._db._schema_engine.get_entity(source_entity_name)
        if not entity_info:
            return 0

        is_postgresql = self._db._connection.engine.dialect.name == "postgresql"

        # First, get all related record IDs
        if entity_info.storage_mode == "dedicated" and entity_info.dedicated_table_name:
            sql = f"""
                SELECT id FROM {entity_info.dedicated_table_name}
                WHERE {fk_field} = :target_id AND is_deleted = {"false" if is_postgresql else "0"}
            """
        else:
            if is_postgresql:
                sql = f"""
                    SELECT id FROM kdb_records
                    WHERE entity_id = :entity_id
                      AND data->>'{fk_field}' = :target_id
                      AND is_deleted = false
                """
            else:
                sql = f"""
                    SELECT id FROM kdb_records
                    WHERE entity_id = :entity_id
                      AND json_extract(data, '$.{fk_field}') = :target_id
                      AND is_deleted = 0
                """

        with self._db._connection.engine.connect() as conn:
            result = conn.execute(
                text(sql),
                {"entity_id": entity_info.id, "target_id": target_id},
            )
            related_ids = [row[0] for row in result.fetchall()]

        # Delete each related record (recursively handles cascades)
        source_entity = self._db.entity(source_entity_name)
        deleted_count = 0
        for related_id in related_ids:
            try:
                source_entity.delete(related_id, cascade=True)
                deleted_count += 1
            except Exception:
                # Log but continue - partial cascade is better than none
                pass

        return deleted_count

    def _set_null_related(
        self,
        source_entity_name: str,
        fk_field: str,
        target_id: str,
    ) -> int:
        """Set FK field to null on all records that reference the target.

        Args:
            source_entity_name: Entity that has the FK field
            fk_field: Name of the FK field
            target_id: ID being referenced

        Returns:
            Count of updated records
        """
        from sqlalchemy import text

        entity_info = self._db._schema_engine.get_entity(source_entity_name)
        if not entity_info:
            return 0

        is_postgresql = self._db._connection.engine.dialect.name == "postgresql"

        if entity_info.storage_mode == "dedicated" and entity_info.dedicated_table_name:
            # Dedicated table - direct column update
            sql = f"""
                UPDATE {entity_info.dedicated_table_name}
                SET {fk_field} = NULL, updated_at = {"NOW()" if is_postgresql else "datetime('now')"}
                WHERE {fk_field} = :target_id AND is_deleted = {"false" if is_postgresql else "0"}
            """
        else:
            # Shared storage - JSON update
            if is_postgresql:
                sql = f"""
                    UPDATE kdb_records
                    SET data = data - '{fk_field}', updated_at = NOW()
                    WHERE entity_id = :entity_id
                      AND data->>'{fk_field}' = :target_id
                      AND is_deleted = false
                """
            else:
                sql = f"""
                    UPDATE kdb_records
                    SET data = json_remove(data, '$.{fk_field}'), updated_at = datetime('now')
                    WHERE entity_id = :entity_id
                      AND json_extract(data, '$.{fk_field}') = :target_id
                      AND is_deleted = 0
                """

        with self._db._connection.engine.connect() as conn:
            result = conn.execute(
                text(sql),
                {"entity_id": entity_info.id, "target_id": target_id},
            )
            conn.commit()
            return result.rowcount

    def _delete_junction_entries_for_target(
        self,
        source_entity_name: str,
        relationship_name: str,
        target_id: str,
    ) -> int:
        """Delete junction entries when target record is deleted.

        For many-to-many relationships, CASCADE means deleting the junction
        entries (links), not the records on the other side.

        Args:
            source_entity_name: Entity that has the many-to-many relationship
            relationship_name: Name of the relationship
            target_id: ID of the target record being deleted

        Returns:
            Count of deleted junction entries
        """
        from sqlalchemy import text

        from kameleondb.schema.models import (
            EntityDefinition,
            JunctionTable,
            RelationshipDefinition,
        )

        with self._db._connection.get_session() as session:
            # Get source entity
            source_entity = (
                session.query(EntityDefinition)
                .filter_by(name=source_entity_name, is_active=True)
                .first()
            )
            if not source_entity:
                return 0

            # Get relationship
            relationship = (
                session.query(RelationshipDefinition)
                .filter_by(
                    source_entity_id=source_entity.id,
                    name=relationship_name,
                    is_active=True,
                )
                .first()
            )
            if not relationship:
                return 0

            # Get junction table
            junction = (
                session.query(JunctionTable).filter_by(relationship_id=relationship.id).first()
            )
            if not junction:
                return 0

        # Delete junction entries where target matches
        with self._db._connection.engine.connect() as conn:
            result = conn.execute(
                text(
                    f"""
                    DELETE FROM {junction.table_name}
                    WHERE {junction.target_fk_column} = :target_id
                """
                ),
                {"target_id": target_id},
            )
            conn.commit()
            return result.rowcount

    def _delete_junction_entries_for_source(
        self,
        source_id: str,
    ) -> int:
        """Delete all junction entries where this entity is the source.

        Called when deleting a record to clean up its many-to-many links.

        Args:
            source_id: ID of the source record being deleted

        Returns:
            Total count of deleted junction entries
        """
        from sqlalchemy import text

        from kameleondb.schema.models import (
            EntityDefinition,
            JunctionTable,
            RelationshipDefinition,
        )

        total_deleted = 0

        with self._db._connection.get_session() as session:
            # Get this entity
            entity = (
                session.query(EntityDefinition).filter_by(name=self._name, is_active=True).first()
            )
            if not entity:
                return 0

            # Get all many-to-many relationships where this entity is the source
            relationships = (
                session.query(RelationshipDefinition)
                .filter_by(
                    source_entity_id=entity.id,
                    relationship_type="many_to_many",
                    is_active=True,
                )
                .all()
            )

            for rel in relationships:
                junction = session.query(JunctionTable).filter_by(relationship_id=rel.id).first()
                if not junction:
                    continue

                # Delete junction entries where source matches
                with self._db._connection.engine.connect() as conn:
                    result = conn.execute(
                        text(
                            f"""
                            DELETE FROM {junction.table_name}
                            WHERE {junction.source_fk_column} = :source_id
                        """
                        ),
                        {"source_id": source_id},
                    )
                    conn.commit()
                    total_deleted += result.rowcount

        return total_deleted

    # === Many-to-Many Link Operations (Spec 007) ===

    def _get_junction_info(
        self,
        relationship_name: str,
    ) -> dict[str, Any]:
        """Get junction table info for a many-to-many relationship.

        Args:
            relationship_name: Name of the relationship

        Returns:
            Dict with junction table info

        Raises:
            ValueError: If relationship is not many-to-many or doesn't exist
        """
        from kameleondb.schema.models import JunctionTable, RelationshipDefinition

        with self._db._connection.get_session() as session:
            # Get entity
            from kameleondb.schema.models import EntityDefinition

            entity = (
                session.query(EntityDefinition).filter_by(name=self._name, is_active=True).first()
            )
            if not entity:
                raise ValueError(f"Entity '{self._name}' not found")

            # Get relationship
            relationship = (
                session.query(RelationshipDefinition)
                .filter_by(source_entity_id=entity.id, name=relationship_name, is_active=True)
                .first()
            )
            if not relationship:
                raise ValueError(f"Relationship '{relationship_name}' not found on '{self._name}'")

            if relationship.relationship_type != "many_to_many":
                raise ValueError(f"'{relationship_name}' is not a many-to-many relationship")

            # Get junction table
            junction = (
                session.query(JunctionTable).filter_by(relationship_id=relationship.id).first()
            )
            if not junction:
                raise ValueError(f"Junction table not found for relationship '{relationship_name}'")

            # Get target entity name for validation
            target_entity = (
                session.query(EntityDefinition)
                .filter_by(id=relationship.target_entity_id, is_active=True)
                .first()
            )
            target_entity_name = target_entity.name if target_entity else None

            return {
                "table_name": junction.table_name,
                "source_fk_column": junction.source_fk_column,
                "target_fk_column": junction.target_fk_column,
                "target_entity_name": target_entity_name,
            }

    def link(
        self,
        relationship_name: str,
        record_id: str,
        target_id: str,
        created_by: str | None = None,
    ) -> bool:
        """Add a link in a many-to-many relationship.

        Args:
            relationship_name: Name of the many-to-many relationship
            record_id: ID of this entity's record
            target_id: ID of the target record to link

        Returns:
            True if link was created, False if already exists

        Raises:
            ValueError: If relationship is not many-to-many
            RecordNotFoundError: If source or target record doesn't exist
        """
        from datetime import datetime
        from uuid import uuid4

        from sqlalchemy import text

        from kameleondb.core.compat import UTC
        from kameleondb.exceptions import RecordNotFoundError

        # Verify source record exists
        if not self.find_by_id(record_id):
            raise RecordNotFoundError(record_id, self._name)

        junction = self._get_junction_info(relationship_name)

        # Verify target record exists
        target_entity_name = junction.get("target_entity_name")
        if target_entity_name:
            target_entity = self._db.entity(target_entity_name)
            if not target_entity.find_by_id(target_id):
                raise RecordNotFoundError(target_id, target_entity_name)

        # Insert into junction table (ignore if exists due to unique constraint)
        link_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        from sqlalchemy.exc import IntegrityError

        try:
            with self._db._connection.engine.connect() as conn:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {junction["table_name"]}
                        (id, {junction["source_fk_column"]}, {junction["target_fk_column"]}, created_at, created_by)
                        VALUES (:id, :source_id, :target_id, :created_at, :created_by)
                    """
                    ),
                    {
                        "id": link_id,
                        "source_id": record_id,
                        "target_id": target_id,
                        "created_at": now,
                        "created_by": created_by,
                    },
                )
                conn.commit()
                return True
        except IntegrityError:
            # Duplicate link - unique constraint violation
            return False

    def unlink(
        self,
        relationship_name: str,
        record_id: str,
        target_id: str,
    ) -> bool:
        """Remove a link in a many-to-many relationship.

        Args:
            relationship_name: Name of the many-to-many relationship
            record_id: ID of this entity's record
            target_id: ID of the target record to unlink

        Returns:
            True if link was removed, False if didn't exist
        """
        from sqlalchemy import text

        junction = self._get_junction_info(relationship_name)

        with self._db._connection.engine.connect() as conn:
            result = conn.execute(
                text(
                    f"""
                    DELETE FROM {junction["table_name"]}
                    WHERE {junction["source_fk_column"]} = :source_id
                      AND {junction["target_fk_column"]} = :target_id
                """
                ),
                {"source_id": record_id, "target_id": target_id},
            )
            conn.commit()
            return result.rowcount > 0

    def unlink_all(
        self,
        relationship_name: str,
        record_id: str,
    ) -> int:
        """Remove all links for a record in a many-to-many relationship.

        Args:
            relationship_name: Name of the many-to-many relationship
            record_id: ID of this entity's record

        Returns:
            Count of removed links
        """
        from sqlalchemy import text

        junction = self._get_junction_info(relationship_name)

        with self._db._connection.engine.connect() as conn:
            result = conn.execute(
                text(
                    f"""
                    DELETE FROM {junction["table_name"]}
                    WHERE {junction["source_fk_column"]} = :source_id
                """
                ),
                {"source_id": record_id},
            )
            conn.commit()
            return result.rowcount

    def get_linked(
        self,
        relationship_name: str,
        record_id: str,
    ) -> list[str]:
        """Get all linked record IDs for a many-to-many relationship.

        Args:
            relationship_name: Name of the many-to-many relationship
            record_id: ID of this entity's record

        Returns:
            List of linked target record IDs
        """
        from sqlalchemy import text

        junction = self._get_junction_info(relationship_name)

        with self._db._connection.engine.connect() as conn:
            result = conn.execute(
                text(
                    f"""
                    SELECT {junction["target_fk_column"]}
                    FROM {junction["table_name"]}
                    WHERE {junction["source_fk_column"]} = :source_id
                """
                ),
                {"source_id": record_id},
            )
            return [row[0] for row in result.fetchall()]

    def link_many(
        self,
        relationship_name: str,
        record_id: str,
        target_ids: list[str],
        created_by: str | None = None,
    ) -> int:
        """Add multiple links in a many-to-many relationship.

        Optimized batch operation - fetches junction info once.

        Args:
            relationship_name: Name of the many-to-many relationship
            record_id: ID of this entity's record
            target_ids: List of target record IDs to link

        Returns:
            Count of links created (excludes duplicates)
        """
        if not target_ids:
            return 0

        from datetime import datetime
        from uuid import uuid4

        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        from kameleondb.core.compat import UTC
        from kameleondb.exceptions import RecordNotFoundError

        # Verify source record exists
        if not self.find_by_id(record_id):
            raise RecordNotFoundError(record_id, self._name)

        junction = self._get_junction_info(relationship_name)
        now = datetime.now(UTC).isoformat()
        count = 0

        # Batch insert - one transaction, individual inserts to handle duplicates
        with self._db._connection.engine.connect() as conn:
            for target_id in target_ids:
                try:
                    conn.execute(
                        text(
                            f"""
                            INSERT INTO {junction["table_name"]}
                            (id, {junction["source_fk_column"]}, {junction["target_fk_column"]}, created_at, created_by)
                            VALUES (:id, :source_id, :target_id, :created_at, :created_by)
                        """
                        ),
                        {
                            "id": str(uuid4()),
                            "source_id": record_id,
                            "target_id": target_id,
                            "created_at": now,
                            "created_by": created_by,
                        },
                    )
                    count += 1
                except IntegrityError:
                    # Duplicate - skip
                    pass
            conn.commit()

        return count

    def unlink_many(
        self,
        relationship_name: str,
        record_id: str,
        target_ids: list[str],
    ) -> int:
        """Remove multiple links in a many-to-many relationship.

        Optimized batch operation - single DELETE with IN clause.

        Args:
            relationship_name: Name of the many-to-many relationship
            record_id: ID of this entity's record
            target_ids: List of target record IDs to unlink

        Returns:
            Count of links removed
        """
        if not target_ids:
            return 0

        from sqlalchemy import text

        junction = self._get_junction_info(relationship_name)

        # Build placeholders for IN clause
        placeholders = ", ".join(f":target_{i}" for i in range(len(target_ids)))
        params = {"source_id": record_id}
        params.update({f"target_{i}": tid for i, tid in enumerate(target_ids)})

        with self._db._connection.engine.connect() as conn:
            result = conn.execute(
                text(
                    f"""
                    DELETE FROM {junction["table_name"]}
                    WHERE {junction["source_fk_column"]} = :source_id
                      AND {junction["target_fk_column"]} IN ({placeholders})
                """
                ),
                params,
            )
            conn.commit()
            return result.rowcount

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

    def __init__(
        self,
        url: str,
        echo: bool = False,
        materialization_policy: Any = None,
        embeddings: bool = False,
        embedding_provider: str | Any = "fastembed",
        embedding_model: str | None = None,
        embedding_dimensions: int | None = None,
    ) -> None:
        """Initialize KameleonDB.

        Args:
            url: Database connection URL
            echo: Whether to echo SQL statements (for debugging)
            materialization_policy: Optional policy for query intelligence
            embeddings: Enable semantic search with embeddings
            embedding_provider: Provider name ("fastembed", "openai") or instance
            embedding_model: Model name (provider-specific)
            embedding_dimensions: Vector dimensions (default: 384)
        """
        from kameleondb.core.types import MaterializationPolicy
        from kameleondb.query.metrics import MetricsCollector
        from kameleondb.query.suggestions import SuggestionEngine

        self._connection = DatabaseConnection(url, echo=echo)
        self._schema_engine = SchemaEngine(self._connection)
        self._table_manager = TableManager(self._connection.engine)
        self._tool_registry: ToolRegistry | None = None
        self._entities: dict[str, Entity] = {}

        # Query Intelligence (ADR-002)
        self._materialization_policy = materialization_policy or MaterializationPolicy()
        self._metrics_collector = MetricsCollector(
            self._connection.engine, self._materialization_policy
        )
        self._suggestion_engine = SuggestionEngine(self._materialization_policy)

        # Semantic Search (Layer 2)
        self._embeddings_enabled = embeddings
        self._search_engine: SearchEngine | None = None
        if embeddings:
            self._init_search_engine(embedding_provider, embedding_model, embedding_dimensions)

        # Initialize meta-tables (schema definitions)
        self._schema_engine.initialize()

        # Initialize JSONB data tables (kdb_records with JSONB column)
        self._table_manager.ensure_jsonb_tables()

    def _init_search_engine(
        self,
        provider: str | Any,
        model: str | None,
        dimensions: int | None,
    ) -> None:
        """Initialize the search engine with embedding provider."""
        from kameleondb.embeddings import EmbeddingProvider, get_provider
        from kameleondb.search import SearchEngine

        # Build provider kwargs
        kwargs: dict[str, Any] = {}
        if model:
            kwargs["model"] = model
        if dimensions:
            kwargs["dimensions"] = dimensions

        # Get or create provider
        if isinstance(provider, EmbeddingProvider):
            embedding_provider = provider
        else:
            embedding_provider = get_provider(provider, **kwargs)

        self._search_engine = SearchEngine(
            self._connection.engine,
            embedding_provider,
        )

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
        entity_name: str | None = None,
        created_by: str | None = None,
    ) -> Any:
        """Execute a validated SQL query with metrics and optimization hints.

        The query is validated before execution:
        - SELECT only (when read_only=True)
        - Table access verified against KameleonDB tables
        - SQL injection patterns blocked

        Returns results with performance metrics and actionable optimization hints.
        This is the agent-first design - all operations provide intelligence inline.

        Use get_schema_context() first to understand the table structure
        and JSONB access patterns.

        Args:
            sql: SQL query to execute
            read_only: If True, only SELECT statements allowed (default True)
            entity_name: Primary entity being queried (enables better hints)
            created_by: Agent/user identifier (for metrics tracking)

        Returns:
            QueryExecutionResult with:
            - rows: Query results as list of dicts
            - metrics: Performance data (execution time, row count, etc.)
            - suggestions: Optimization hints (e.g., materialization suggestions)
            - warnings: Validation warnings

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
            >>> result = db.execute_sql(sql, entity_name="Contact")
            >>> print(f"Returned {len(result.rows)} rows in {result.metrics.execution_time_ms}ms")
            >>> if result.suggestions:
            ...     print(f"Hint: {result.suggestions[0].reason}")
        """
        import time

        from sqlalchemy import text

        from kameleondb.core.types import QueryExecutionResult, QueryMetrics
        from kameleondb.exceptions import QueryError
        from kameleondb.query.validator import QueryValidator

        # Validate the query
        validator = QueryValidator(db=self)
        validation = validator.validate(sql, read_only=read_only)

        if not validation.valid:
            raise QueryError(f"Query validation failed: {validation.error}")

        # Execute with timing
        start_time = time.perf_counter()
        try:
            with self._connection.engine.connect() as conn:
                query_result = conn.execute(text(validation.sql))
                rows_raw = query_result.fetchall()
                columns = query_result.keys()
                rows = [dict(zip(columns, row, strict=True)) for row in rows_raw]
        except Exception as e:
            raise QueryError(f"Query execution failed: {e}") from e

        execution_time_ms = (time.perf_counter() - start_time) * 1000

        # Build metrics
        metrics = QueryMetrics(
            execution_time_ms=execution_time_ms,
            row_count=len(rows),
            entities_accessed=[entity_name] if entity_name else [],
            has_join="JOIN" in sql.upper(),
            query_type=validation.query_type.value if validation.query_type else "UNKNOWN",
        )

        # Record metrics (if enabled)
        if self._metrics_collector.enabled:
            self._metrics_collector.record_query(
                metrics=metrics,
                entity_name=entity_name,
                tables_accessed=list(validation.tables_accessed)
                if validation.tables_accessed
                else None,
                created_by=created_by,
            )

        # Generate suggestions (agent hints)
        suggestions = []
        if entity_name:
            # Get entity info for storage mode
            entity_info = self._schema_engine.get_entity(entity_name)
            storage_mode = entity_info.storage_mode if entity_info else "shared"

            suggestions = self._suggestion_engine.generate_suggestions(
                entity_name=entity_name,
                metrics=metrics,
                storage_mode=storage_mode,
            )

        return QueryExecutionResult(
            rows=rows,
            metrics=metrics,
            suggestions=suggestions,
            warnings=validation.warnings,
        )

    def get_entity_stats(self, entity_name: str) -> Any:
        """Get aggregated statistics for an entity.

        Returns metrics about query performance and patterns for the entity.

        Args:
            entity_name: Entity to get stats for

        Returns:
            EntityStats with aggregated metrics

        Example:
            >>> stats = db.get_entity_stats("Contact")
            >>> print(f"Total queries: {stats.total_queries}")
            >>> print(f"Avg time: {stats.avg_execution_time_ms}ms")
            >>> if stats.suggestion:
            ...     print(f"Suggestion: {stats.suggestion}")
        """
        from sqlalchemy import text

        # Get entity info
        entity = self._schema_engine.get_entity(entity_name)
        storage_mode = entity.storage_mode if entity else "shared"

        # Get record count
        record_count = 0
        if entity:
            with self._connection.engine.connect() as conn:
                result = conn.execute(
                    text(
                        """
                    SELECT COUNT(*) FROM kdb_records
                    WHERE entity_id = :entity_id AND is_deleted = false
                """
                    ),
                    {"entity_id": entity.id},
                )
                record_count = result.scalar() or 0

        return self._metrics_collector.get_entity_stats(
            entity_name=entity_name,
            storage_mode=storage_mode,
            record_count=record_count,
        )

    # === Semantic Search (Layer 2) ===

    def search(
        self,
        query: str,
        entity: str | None = None,
        entities: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search records using hybrid BM25 + vector search.

        Combines keyword (BM25) and semantic (vector) search using
        Reciprocal Rank Fusion for best results.

        Args:
            query: Search query text
            entity: Single entity to search (optional)
            entities: List of entities to search (optional)
            limit: Maximum results to return (default 10)
            min_score: Minimum score threshold (default 0.0)
            where: Structured filters (e.g., {"status": "open", "priority": "high"})

        Returns:
            List of search results with:
            - entity: Entity name
            - id: Record ID
            - score: Relevance score
            - data: Full record data
            - matched_text: Text that matched

        Raises:
            RuntimeError: If embeddings not enabled

        Example:
            >>> db = KameleonDB("sqlite:///app.db", embeddings=True)
            >>> results = db.search("shipping complaint")
            >>> for r in results:
            ...     print(f"{r['entity']}/{r['id']}: {r['score']:.2f}")

            # With structured filters
            >>> results = db.search("complaint", entity="Ticket", where={"status": "open"})
        """
        if not self._search_engine:
            raise RuntimeError(
                "Search requires embeddings. Initialize with: KameleonDB(..., embeddings=True)"
            )

        results = self._search_engine.search(
            query=query,
            entity=entity,
            entities=entities,
            limit=limit,
            min_score=min_score,
            where=where,
        )

        # Convert to dicts for JSON serialization
        return [
            {
                "entity": r.entity,
                "id": r.id,
                "score": r.score,
                "data": r.data,
                "matched_text": r.matched_text,
            }
            for r in results
        ]

    def reindex_embeddings(self, entity_name: str | None = None) -> dict[str, Any]:
        """Reindex embeddings for an entity or all entities.

        Use after changing embed_fields or to refresh embeddings.

        Args:
            entity_name: Entity to reindex, or None for all entities

        Returns:
            Dict with reindex status

        Raises:
            RuntimeError: If embeddings not enabled
        """
        if not self._search_engine:
            raise RuntimeError(
                "Reindex requires embeddings. Initialize with: KameleonDB(..., embeddings=True)"
            )

        # Get entities to reindex
        entities = [entity_name] if entity_name else self.list_entities()

        total_indexed = 0
        for name in entities:
            entity_def = self._schema_engine.get_entity(name)
            if not entity_def:
                continue

            # Get embed_fields from entity metadata
            embed_fields = self._get_embed_fields(name)
            if not embed_fields:
                continue

            # Get all records
            entity = self.entity(name)
            # Use query to get all records (simplified - could use pagination)
            query = entity._get_query()

            # TODO: Add proper pagination for large datasets
            records = query.find_all(limit=10000)

            for record in records:
                content = self._build_embed_content(record, embed_fields)
                if content:
                    self._search_engine.index_record(name, record["id"], content)
                    total_indexed += 1

        return {
            "status": "complete",
            "entities_processed": len(entities),
            "records_indexed": total_indexed,
        }

    def embedding_status(self, entity_name: str | None = None) -> list[dict[str, Any]]:
        """Get embedding index status.

        Args:
            entity_name: Optional entity to filter

        Returns:
            List of status dicts per entity
        """
        if not self._search_engine:
            return []

        statuses = self._search_engine.get_status(entity_name)
        return [
            {
                "entity": s.entity,
                "indexed": s.indexed,
                "pending": s.pending,
                "last_updated": s.last_updated.isoformat() if s.last_updated else None,
            }
            for s in statuses
        ]

    def _get_embed_fields(self, entity_name: str) -> list[str] | None:
        """Get embed_fields for an entity from metadata.

        TODO: Store embed_fields in entity definition metadata.
        For now, returns text/string fields as default.
        """
        fields = self._schema_engine.get_fields(entity_name)
        # Default: embed all text and string fields
        return [f.name for f in fields if f.field_type in ("text", "string")]

    def _build_embed_content(
        self,
        record: dict[str, Any],
        embed_fields: list[str],
    ) -> str:
        """Build embeddable content from record fields.

        Format: "field1: value1 | field2: value2"
        """
        parts = []
        for field in embed_fields:
            value = record.get(field)
            if value:
                parts.append(f"{field}: {value}")
        return " | ".join(parts)

    def _index_record_for_search(
        self,
        entity_name: str,
        record_id: str,
        data: dict[str, Any],
    ) -> None:
        """Index a record for search after insert/update.

        Called automatically when embeddings are enabled.
        """
        if not self._search_engine:
            return

        embed_fields = self._get_embed_fields(entity_name)
        if not embed_fields:
            return

        # Build content
        content = self._build_embed_content({"id": record_id, **data}, embed_fields)
        if content:
            self._search_engine.index_record(entity_name, record_id, content)
