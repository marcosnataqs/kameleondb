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


def _normalize_sqlite_url(url: str) -> str:
    """Normalize SQLite URL.

    Supports:
    - sqlite:///path/to/db.sqlite
    - sqlite:///:memory:
    - sqlite+aiosqlite:///... (for async)

    Args:
        url: Database URL

    Returns:
        Normalized URL
    """
    # Already has a driver specified
    if "sqlite+" in url:
        return url

    return url


class DatabaseConnection:
    """Manages database connections for KameleonDB.

    Supports PostgreSQL (with JSONB) and SQLite (with JSON1) databases.
    """

    SUPPORTED_DIALECTS = ("postgresql", "sqlite")

    def __init__(self, url: str | URL, echo: bool = False) -> None:
        """Initialize database connection.

        Args:
            url: Database connection URL
                 PostgreSQL: "postgresql://user:pass@localhost/db"
                 SQLite: "sqlite:///path/to/db.sqlite" or "sqlite:///:memory:"
            echo: Whether to echo SQL statements (for debugging)

        Raises:
            ConnectionError: If connection fails or dialect is not supported
        """
        url_str = str(url)

        # Normalize URL based on dialect
        if url_str.startswith("postgresql"):
            self._url = _normalize_postgresql_url(url_str)
        elif url_str.startswith("sqlite"):
            self._url = _normalize_sqlite_url(url_str)
        else:
            self._url = url_str

        self._echo = echo
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        """Get or create the SQLAlchemy engine."""
        if self._engine is None:
            try:
                # SQLite-specific settings
                connect_args = {}
                if self._url.startswith("sqlite"):
                    # Enable foreign keys for SQLite
                    connect_args["check_same_thread"] = False

                self._engine = create_engine(
                    self._url,
                    echo=self._echo,
                    pool_pre_ping=True,  # Verify connections before use
                    connect_args=connect_args,
                )

                # Execute SQLite-specific pragmas
                if self._engine.dialect.name == "sqlite":
                    with self._engine.connect() as conn:
                        conn.execute(text("PRAGMA foreign_keys = ON"))
                        conn.execute(text("PRAGMA journal_mode = WAL"))
                        conn.commit()

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
    def dialect(self) -> Literal["postgresql", "sqlite"]:
        """Get the database dialect name."""
        name = self.engine.dialect.name
        if name not in self.SUPPORTED_DIALECTS:
            raise ConnectionError(f"Unsupported dialect: {name}")
        return name  # type: ignore[return-value]

    @property
    def is_postgresql(self) -> bool:
        """Check if connected to PostgreSQL."""
        return self.dialect == "postgresql"

    @property
    def is_sqlite(self) -> bool:
        """Check if connected to SQLite."""
        return self.dialect == "sqlite"

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
