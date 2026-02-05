"""Tests for database connection."""

import pytest

from kameleondb.core.connection import DatabaseConnection
from kameleondb.exceptions import ConnectionError


class TestDatabaseConnection:
    """Tests for DatabaseConnection class."""

    def test_postgresql_connection(self, postgresql_url: str):
        """Can connect to PostgreSQL."""
        conn = DatabaseConnection(postgresql_url)
        assert conn.test_connection() is True
        assert conn.dialect == "postgresql"
        assert conn.is_postgresql is True
        conn.close()

    def test_engine_created_lazily(self, postgresql_url: str):
        """Engine is not created until accessed."""
        conn = DatabaseConnection(postgresql_url)
        assert conn._engine is None
        _ = conn.engine
        assert conn._engine is not None
        conn.close()

    def test_session_factory(self, postgresql_url: str):
        """Can create sessions."""
        conn = DatabaseConnection(postgresql_url)
        session = conn.get_session()
        assert session is not None
        session.close()
        conn.close()

    def test_context_manager(self, postgresql_url: str):
        """Can use as context manager."""
        with DatabaseConnection(postgresql_url) as conn:
            assert conn.test_connection() is True

    def test_close_disposes_engine(self, postgresql_url: str):
        """Closing disposes engine and session factory."""
        conn = DatabaseConnection(postgresql_url)
        _ = conn.engine  # Create engine
        _ = conn.session_factory  # Create session factory
        conn.close()
        assert conn._engine is None
        assert conn._session_factory is None

    def test_invalid_url(self):
        """Invalid URL raises ConnectionError."""
        conn = DatabaseConnection("invalid://not-a-real-db")
        with pytest.raises(ConnectionError):
            conn.test_connection()

    def test_unsupported_dialect(self):
        """Unsupported dialect raises ConnectionError."""
        # MySQL is not supported (only PostgreSQL and SQLite)
        conn = DatabaseConnection("mysql://user:pass@localhost/db")
        with pytest.raises(ConnectionError) as exc_info:
            _ = conn.engine
        assert "Unsupported database dialect" in str(exc_info.value)

    def test_sqlite_supported(self):
        """SQLite is now a supported dialect."""
        conn = DatabaseConnection("sqlite:///:memory:")
        assert conn.engine is not None
        assert conn.is_sqlite is True
        assert conn.dialect == "sqlite"
        conn.close()
