"""Shared test fixtures for KameleonDB."""

import os
from collections.abc import Generator

import pytest

from kameleondb import KameleonDB


def _psycopg_available() -> bool:
    """Check if psycopg is installed."""
    try:
        import psycopg  # noqa: F401

        return True
    except ImportError:
        return False


def _postgresql_connectable(url: str) -> bool:
    """Check if we can connect to PostgreSQL."""
    if not _psycopg_available():
        return False
    try:
        from kameleondb.core.connection import DatabaseConnection

        conn = DatabaseConnection(url)
        result = conn.test_connection()
        conn.close()
        return result
    except Exception:
        return False


# Skip marker for tests requiring PostgreSQL
requires_postgresql = pytest.mark.skipif(
    not _psycopg_available(),
    reason="psycopg not installed (install with: pip install kameleondb[postgresql])",
)


@pytest.fixture
def postgresql_url() -> str:
    """Get PostgreSQL URL from environment or use default.

    Tests using this fixture should also use @requires_postgresql marker.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        # Default to local PostgreSQL
        url = "postgresql://localhost/kameleondb_test"

    # Skip if psycopg not available
    if not _psycopg_available():
        pytest.skip("psycopg not installed")

    # Skip if can't connect (no PostgreSQL server)
    if not _postgresql_connectable(url):
        pytest.skip(f"Cannot connect to PostgreSQL at {url}")

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
def memory_db() -> Generator[KameleonDB, None, None]:
    """Create a KameleonDB instance with SQLite in-memory.

    This is faster for unit tests that don't need PostgreSQL-specific features.
    """
    database = KameleonDB("sqlite:///:memory:")
    yield database
    database.close()


@pytest.fixture
def sqlite_db() -> Generator[KameleonDB, None, None]:
    """Create a KameleonDB instance with SQLite in-memory."""
    database = KameleonDB("sqlite:///:memory:")
    yield database
    database.close()


@pytest.fixture
def pg_db(postgresql_url: str) -> Generator[KameleonDB, None, None]:
    """Create a KameleonDB instance with PostgreSQL.

    Use this for integration tests that need PostgreSQL-specific features.
    The postgresql_url fixture handles skipping when PostgreSQL isn't available.
    """
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


# Re-export for use in test files
__all__ = ["requires_postgresql"]
