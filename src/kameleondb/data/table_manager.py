"""JSONB table management.

In the JSONB architecture, we have a single data table (kdb_records) with a
JSONB column. Schema changes are purely metadata operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kameleondb.schema.models import Base, Record

if TYPE_CHECKING:
    from sqlalchemy import Engine


class TableManager:
    """Manages JSONB data tables.

    In JSONB architecture, there is only one data table:
    - kdb_records: One row per record with JSONB column for all field values

    No DDL is needed for schema changes - they're purely metadata operations.
    """

    def __init__(self, engine: Engine) -> None:
        """Initialize table manager.

        Args:
            engine: SQLAlchemy engine
        """
        self._engine = engine
        self._initialized = False

    def ensure_jsonb_tables(self) -> None:
        """Ensure JSONB tables exist.

        Creates kdb_records table if it doesn't exist.
        This is idempotent - safe to call multiple times.
        """
        if self._initialized:
            return

        # Create JSONB table using SQLAlchemy's create_all
        # This only creates tables that don't exist
        # Note: Record.__table__ returns Table which is a subclass of FromClause
        Base.metadata.create_all(self._engine, tables=[Record.__table__])  # type: ignore[list-item]
        self._initialized = True
