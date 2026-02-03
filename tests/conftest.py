"""Shared test fixtures for KameleonDB."""

import os
from collections.abc import Generator

import pytest

from kameleondb import KameleonDB


@pytest.fixture
def postgresql_url() -> str:
    """Get PostgreSQL URL from environment or use default."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        # Default to local PostgreSQL
        url = "postgresql://localhost/kameleondb_test"
    return url


@pytest.fixture
def db(postgresql_url: str) -> Generator[KameleonDB, None, None]:
    """Create a KameleonDB instance with PostgreSQL."""
    database = KameleonDB(postgresql_url)
    yield database
    # Cleanup - drop all kdb_ tables
    from sqlalchemy import text

    with database._connection.engine.connect() as conn:
        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'kdb_%'"))
        for row in result:
            conn.execute(text(f'DROP TABLE IF EXISTS "{row[0]}" CASCADE'))
        conn.commit()
    database.close()


@pytest.fixture
def memory_db(postgresql_url: str) -> Generator[KameleonDB, None, None]:
    """Create a KameleonDB instance (alias for db fixture for backward compatibility)."""
    database = KameleonDB(postgresql_url)
    yield database
    # Cleanup - drop all kdb_ tables
    from sqlalchemy import text

    with database._connection.engine.connect() as conn:
        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'kdb_%'"))
        for row in result:
            conn.execute(text(f'DROP TABLE IF EXISTS "{row[0]}" CASCADE'))
        conn.commit()
    database.close()


@pytest.fixture
def pg_db(postgresql_url: str) -> Generator[KameleonDB, None, None]:
    """Create a KameleonDB instance with PostgreSQL (alias for db)."""
    database = KameleonDB(postgresql_url)
    yield database
    # Cleanup - drop all kdb_ tables
    from sqlalchemy import text

    with database._connection.engine.connect() as conn:
        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'kdb_%'"))
        for row in result:
            conn.execute(text(f'DROP TABLE IF EXISTS "{row[0]}" CASCADE'))
        conn.commit()
    database.close()
