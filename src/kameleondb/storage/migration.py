"""Storage migration for KameleonDB.

Handles data migration between shared and dedicated storage modes
with transaction safety, batching, and progress callbacks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from kameleondb.schema.models import (
    EntityDefinition,
    FieldDefinition,
    Record,
    StorageMode,
)
from kameleondb.storage.dedicated import DedicatedTableManager

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass
class MigrationProgress:
    """Progress information for migration callbacks."""

    total_records: int
    migrated_records: int
    current_batch: int
    total_batches: int
    entity_name: str
    direction: str  # "to_dedicated" or "to_shared"

    @property
    def percentage(self) -> float:
        """Get completion percentage."""
        if self.total_records == 0:
            return 100.0
        return (self.migrated_records / self.total_records) * 100


@dataclass
class MigrationResult:
    """Result of a storage migration."""

    success: bool
    entity_name: str
    direction: str
    records_migrated: int
    old_storage_mode: str
    new_storage_mode: str
    table_name: str | None
    error: str | None = None
    duration_seconds: float = 0.0


ProgressCallback = Callable[[MigrationProgress], None]


class StorageMigration:
    """Handles data migration between storage modes.

    Provides safe migration with:
    - Transaction safety with rollback on error
    - Batch processing for large datasets
    - Progress callbacks for monitoring
    """

    def __init__(self, engine: Engine) -> None:
        """Initialize the migration handler.

        Args:
            engine: SQLAlchemy engine
        """
        self._engine = engine
        self._table_manager = DedicatedTableManager(engine)
        self._is_postgresql = engine.dialect.name == "postgresql"

    def migrate_to_dedicated(
        self,
        entity: EntityDefinition,
        fields: list[FieldDefinition],
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
    ) -> MigrationResult:
        """Migrate an entity from shared to dedicated storage.

        Args:
            entity: The entity definition
            fields: List of field definitions
            batch_size: Number of records per batch
            on_progress: Optional progress callback

        Returns:
            MigrationResult with details
        """
        start_time = datetime.now(UTC)
        table_name = self._table_manager.generate_table_name(entity.name)

        try:
            # 1. Create the dedicated table
            self._table_manager.create_dedicated_table(entity, fields)

            # 2. Count records to migrate
            with Session(self._engine) as session:
                total_records = (
                    session.query(Record)
                    .filter(Record.entity_id == entity.id)
                    .filter(Record.is_deleted == False)  # noqa: E712
                    .count()
                )

            if total_records == 0:
                # No data to migrate, just update metadata
                self._update_entity_storage_mode(entity.id, StorageMode.DEDICATED, table_name)
                return MigrationResult(
                    success=True,
                    entity_name=entity.name,
                    direction="to_dedicated",
                    records_migrated=0,
                    old_storage_mode=StorageMode.SHARED,
                    new_storage_mode=StorageMode.DEDICATED,
                    table_name=table_name,
                    duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
                )

            # 3. Migrate data in batches
            total_batches = (total_records + batch_size - 1) // batch_size
            migrated = 0

            # Build column list for INSERT
            active_fields = [f for f in fields if f.is_active]
            field_columns = [f.column_name for f in active_fields]
            all_columns = ["id", "created_at", "updated_at", "created_by", "is_deleted"] + field_columns

            for batch_num in range(total_batches):
                offset = batch_num * batch_size

                with Session(self._engine) as session:
                    # Fetch batch of records
                    records = (
                        session.query(Record)
                        .filter(Record.entity_id == entity.id)
                        .filter(Record.is_deleted == False)  # noqa: E712
                        .order_by(Record.created_at)
                        .offset(offset)
                        .limit(batch_size)
                        .all()
                    )

                    if not records:
                        break

                    # Build INSERT values
                    for record in records:
                        values = {
                            "id": record.id,
                            "created_at": record.created_at,
                            "updated_at": record.updated_at,
                            "created_by": record.created_by,
                            "is_deleted": record.is_deleted,
                        }
                        # Extract field values from JSONB data
                        for field in active_fields:
                            values[field.column_name] = (
                                record.data.get(field.column_name) if record.data else None
                            )

                        # Insert into dedicated table
                        columns_str = ", ".join(f'"{c}"' for c in all_columns)
                        placeholders = ", ".join(f":{c}" for c in all_columns)
                        session.execute(
                            text(f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders})'),
                            values,
                        )

                    session.commit()
                    migrated += len(records)

                    # Progress callback
                    if on_progress:
                        on_progress(
                            MigrationProgress(
                                total_records=total_records,
                                migrated_records=migrated,
                                current_batch=batch_num + 1,
                                total_batches=total_batches,
                                entity_name=entity.name,
                                direction="to_dedicated",
                            )
                        )

            # 4. Update entity metadata
            self._update_entity_storage_mode(entity.id, StorageMode.DEDICATED, table_name)

            # 5. Mark old records as deleted (soft delete from shared table)
            with Session(self._engine) as session:
                session.execute(
                    text(
                        """
                    UPDATE kdb_records
                    SET is_deleted = true
                    WHERE entity_id = :entity_id
                """
                    ),
                    {"entity_id": entity.id},
                )
                session.commit()

            return MigrationResult(
                success=True,
                entity_name=entity.name,
                direction="to_dedicated",
                records_migrated=migrated,
                old_storage_mode=StorageMode.SHARED,
                new_storage_mode=StorageMode.DEDICATED,
                table_name=table_name,
                duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
            )

        except Exception as e:
            # Rollback: drop the dedicated table if created
            if self._table_manager.table_exists(table_name):
                self._table_manager.drop_dedicated_table(table_name)

            return MigrationResult(
                success=False,
                entity_name=entity.name,
                direction="to_dedicated",
                records_migrated=0,
                old_storage_mode=StorageMode.SHARED,
                new_storage_mode=StorageMode.SHARED,
                table_name=None,
                error=str(e),
                duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
            )

    def migrate_to_shared(
        self,
        entity: EntityDefinition,
        fields: list[FieldDefinition],
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
    ) -> MigrationResult:
        """Migrate an entity from dedicated to shared storage.

        Args:
            entity: The entity definition
            fields: List of field definitions
            batch_size: Number of records per batch
            on_progress: Optional progress callback

        Returns:
            MigrationResult with details
        """
        start_time = datetime.now(UTC)

        if entity.storage_mode != StorageMode.DEDICATED:
            return MigrationResult(
                success=False,
                entity_name=entity.name,
                direction="to_shared",
                records_migrated=0,
                old_storage_mode=entity.storage_mode,
                new_storage_mode=entity.storage_mode,
                table_name=entity.dedicated_table_name,
                error=f"Entity '{entity.name}' is not in dedicated mode",
            )

        table_name = entity.dedicated_table_name
        if not table_name:
            return MigrationResult(
                success=False,
                entity_name=entity.name,
                direction="to_shared",
                records_migrated=0,
                old_storage_mode=entity.storage_mode,
                new_storage_mode=entity.storage_mode,
                table_name=None,
                error="No dedicated table name found",
            )

        try:
            # 1. Count records to migrate
            total_records = self._table_manager.get_row_count(table_name)

            if total_records == 0:
                # No data, just update metadata and drop table
                self._update_entity_storage_mode(entity.id, StorageMode.SHARED, None)
                self._table_manager.drop_dedicated_table(table_name)
                return MigrationResult(
                    success=True,
                    entity_name=entity.name,
                    direction="to_shared",
                    records_migrated=0,
                    old_storage_mode=StorageMode.DEDICATED,
                    new_storage_mode=StorageMode.SHARED,
                    table_name=None,
                    duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
                )

            # 2. Migrate data in batches
            total_batches = (total_records + batch_size - 1) // batch_size
            migrated = 0
            active_fields = [f for f in fields if f.is_active]

            for batch_num in range(total_batches):
                offset = batch_num * batch_size

                with Session(self._engine) as session:
                    # Fetch batch from dedicated table
                    result = session.execute(
                        text(
                            f"""
                        SELECT * FROM "{table_name}"
                        WHERE is_deleted = false
                        ORDER BY created_at
                        LIMIT :limit OFFSET :offset
                    """
                        ),
                        {"limit": batch_size, "offset": offset},
                    )
                    rows = result.mappings().all()

                    if not rows:
                        break

                    for row in rows:
                        # Build JSONB data from columns
                        data = {}
                        for field in active_fields:
                            if field.column_name in row and row[field.column_name] is not None:
                                data[field.column_name] = row[field.column_name]

                        # Insert into shared table
                        record = Record(
                            id=row["id"],
                            entity_id=entity.id,
                            data=data,
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                            created_by=row.get("created_by"),
                            is_deleted=False,
                        )
                        session.add(record)

                    session.commit()
                    migrated += len(rows)

                    # Progress callback
                    if on_progress:
                        on_progress(
                            MigrationProgress(
                                total_records=total_records,
                                migrated_records=migrated,
                                current_batch=batch_num + 1,
                                total_batches=total_batches,
                                entity_name=entity.name,
                                direction="to_shared",
                            )
                        )

            # 3. Update entity metadata
            self._update_entity_storage_mode(entity.id, StorageMode.SHARED, None)

            # 4. Drop dedicated table
            self._table_manager.drop_dedicated_table(table_name)

            return MigrationResult(
                success=True,
                entity_name=entity.name,
                direction="to_shared",
                records_migrated=migrated,
                old_storage_mode=StorageMode.DEDICATED,
                new_storage_mode=StorageMode.SHARED,
                table_name=None,
                duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
            )

        except Exception as e:
            return MigrationResult(
                success=False,
                entity_name=entity.name,
                direction="to_shared",
                records_migrated=0,
                old_storage_mode=StorageMode.DEDICATED,
                new_storage_mode=StorageMode.DEDICATED,
                table_name=table_name,
                error=str(e),
                duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
            )

    def _update_entity_storage_mode(
        self,
        entity_id: str,
        storage_mode: str,
        table_name: str | None,
    ) -> None:
        """Update entity's storage mode in metadata."""
        with Session(self._engine) as session:
            session.execute(
                text(
                    """
                UPDATE kdb_entity_definitions
                SET storage_mode = :mode, dedicated_table_name = :table
                WHERE id = :id
            """
                ),
                {"mode": storage_mode, "table": table_name, "id": entity_id},
            )
            session.commit()
