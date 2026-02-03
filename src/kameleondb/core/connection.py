"""Database connection management for KameleonDB."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from kameleondb.exceptions import ConnectionError

if TYPE_CHECKING:
    from sqlalchemy.engine.url import URL


def _normalize_postgresql_url(url: str) -> str:
    """Normalize PostgreSQL URL to use psycopg3 driver.

    SQLAlchemy defaults to psycopg2 for 'postgresql://' URLs.
    This converts to 'postgresql+psycopg://' to use psycopg3.

    Args:
        url: Database URL

    Returns:
        Normalized URL using psycopg3 driver
    """
    # Already using psycopg3 or another driver
    if "postgresql+" in url:
        return url

    # Convert postgresql:// to postgresql+psycopg://
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


class DatabaseConnection:
    """Manages PostgreSQL database connections.

    Supports PostgreSQL databases only (with JSONB).
    Uses psycopg3 as the database driver.
    """

    SUPPORTED_DIALECTS = ("postgresql",)

    def __init__(self, url: str | URL, echo: bool = False) -> None:
        """Initialize PostgreSQL database connection.

        Args:
            url: PostgreSQL connection URL (e.g., "postgresql://user:pass@localhost/db")
                 Automatically uses psycopg3 driver.
            echo: Whether to echo SQL statements (for debugging)

        Raises:
            ConnectionError: If connection fails or dialect is not PostgreSQL
        """
        self._url = _normalize_postgresql_url(str(url))
        self._echo = echo
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        """Get or create the SQLAlchemy engine."""
        if self._engine is None:
            try:
                self._engine = create_engine(self._url, echo=self._echo)
                # Validate dialect
                if self._engine.dialect.name not in self.SUPPORTED_DIALECTS:
                    raise ConnectionError(
                        f"Unsupported database dialect: {self._engine.dialect.name}. "
                        f"Supported: {', '.join(self.SUPPORTED_DIALECTS)}"
                    )
            except Exception as e:
                if isinstance(e, ConnectionError):
                    raise
                raise ConnectionError(f"Failed to create database engine: {e}") from e
        return self._engine

    @property
    def dialect(self) -> Literal["postgresql"]:
        """Get the database dialect name."""
        name = self.engine.dialect.name
        if name != "postgresql":
            raise ConnectionError(f"Unsupported dialect: {name}")
        return name  # type: ignore[return-value]

    @property
    def is_postgresql(self) -> bool:
        """Check if connected to PostgreSQL."""
        return self.dialect == "postgresql"

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """Get the session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.engine)
        return self._session_factory

    def get_session(self) -> Session:
        """Create a new database session."""
        return self.session_factory()

    def test_connection(self) -> bool:
        """Test if the database connection works.

        Returns:
            True if connection is successful

        Raises:
            ConnectionError: If connection test fails
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            raise ConnectionError(f"Database connection test failed: {e}") from e

    def close(self) -> None:
        """Close the database connection and dispose of the engine."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None

    def __enter__(self) -> DatabaseConnection:
        """Context manager entry."""
        self.test_connection()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()
