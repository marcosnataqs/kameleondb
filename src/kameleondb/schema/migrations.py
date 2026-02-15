"""Schema migrations for KameleonDB internal tables.

This module handles automatic migrations when users upgrade the package.
Each migration is a function that takes a connection and applies changes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from kameleondb.core.compat import UTC
from kameleondb.schema.models import SchemaVersion

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Current schema version - increment when adding new migrations
CURRENT_VERSION = 1

# Migration registry: version -> (description, migration_function)
MIGRATIONS: dict[int, tuple[str, Callable[[Engine], None]]] = {}


def migration(
    version: int, description: str
) -> Callable[[Callable[[Engine], None]], Callable[[Engine], None]]:
    """Decorator to register a migration function."""

    def decorator(func: Callable[[Engine], None]) -> Callable[[Engine], None]:
        MIGRATIONS[version] = (description, func)
        return func

    return decorator


def get_schema_version(engine: Engine) -> int:
    """Get the current schema version from the database.

    Returns 0 if the version table doesn't exist or is empty.
    """
    inspector = inspect(engine)

    # Check if version table exists
    if "kdb_schema_version" not in inspector.get_table_names():
        return 0

    with Session(engine) as session:
        version_record = session.query(SchemaVersion).first()
        if version_record is None:
            return 0
        return version_record.version


def set_schema_version(engine: Engine, version: int, description: str | None = None) -> None:
    """Set the schema version in the database."""
    from datetime import datetime

    with Session(engine) as session:
        version_record = session.query(SchemaVersion).first()
        if version_record is None:
            version_record = SchemaVersion(id=1, version=version, description=description)
            session.add(version_record)
        else:
            version_record.version = version
            version_record.description = description
            version_record.applied_at = datetime.now(UTC)
        session.commit()


def column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def index_exists(engine: Engine, table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
    return index_name in indexes


def run_migrations(engine: Engine) -> list[str]:
    """Run all pending migrations.

    Returns a list of applied migration descriptions.
    """
    current_version = get_schema_version(engine)
    applied = []

    logger.info(f"Current schema version: {current_version}, target: {CURRENT_VERSION}")

    for version in sorted(MIGRATIONS.keys()):
        if version > current_version:
            description, migrate_func = MIGRATIONS[version]
            logger.info(f"Applying migration {version}: {description}")
            try:
                migrate_func(engine)
                set_schema_version(engine, version, description)
                applied.append(f"v{version}: {description}")
                logger.info(f"Migration {version} applied successfully")
            except Exception as e:
                logger.error(f"Migration {version} failed: {e}")
                raise

    return applied


# === Migration Definitions ===


@migration(1, "Add entity_name column to kdb_records for direct filtering")
def migrate_v1_entity_name(engine: Engine) -> None:
    """Add denormalized entity_name column to kdb_records table.

    This enables direct filtering by entity name without JOINs:
        SELECT * FROM kdb_records WHERE entity_name = 'Customer'
    """
    dialect = engine.dialect.name

    with engine.begin() as conn:
        # Step 1: Add column if it doesn't exist
        if not column_exists(engine, "kdb_records", "entity_name"):
            logger.info("Adding entity_name column to kdb_records")

            if dialect == "postgresql":
                # PostgreSQL: Add column with default, then backfill
                conn.execute(
                    text("ALTER TABLE kdb_records ADD COLUMN entity_name VARCHAR(255) DEFAULT ''")
                )
            else:
                # SQLite: Add column (no DEFAULT needed, will be NULL initially)
                conn.execute(text("ALTER TABLE kdb_records ADD COLUMN entity_name VARCHAR(255)"))

        # Step 2: Backfill entity_name from entity_definitions
        logger.info("Backfilling entity_name from kdb_entity_definitions")
        if dialect == "postgresql":
            conn.execute(
                text(
                    """
                    UPDATE kdb_records
                    SET entity_name = kdb_entity_definitions.name
                    FROM kdb_entity_definitions
                    WHERE kdb_records.entity_id = kdb_entity_definitions.id
                    AND (kdb_records.entity_name IS NULL OR kdb_records.entity_name = '')
                    """
                )
            )
        else:
            # SQLite doesn't support UPDATE...FROM, use subquery
            conn.execute(
                text(
                    """
                    UPDATE kdb_records
                    SET entity_name = (
                        SELECT name FROM kdb_entity_definitions
                        WHERE kdb_entity_definitions.id = kdb_records.entity_id
                    )
                    WHERE entity_name IS NULL OR entity_name = ''
                    """
                )
            )

        # Step 3: Add index if it doesn't exist
        if not index_exists(engine, "kdb_records", "ix_kdb_records_entity_name"):
            logger.info("Creating index ix_kdb_records_entity_name")
            conn.execute(
                text(
                    "CREATE INDEX ix_kdb_records_entity_name "
                    "ON kdb_records(entity_name, is_deleted)"
                )
            )

        # Step 4: Set NOT NULL constraint (PostgreSQL only, SQLite doesn't support ALTER COLUMN)
        if dialect == "postgresql":
            # First ensure no NULLs remain
            conn.execute(text("UPDATE kdb_records SET entity_name = '' WHERE entity_name IS NULL"))
            conn.execute(text("ALTER TABLE kdb_records ALTER COLUMN entity_name SET NOT NULL"))

    logger.info("Migration v1 complete: entity_name column added and populated")
