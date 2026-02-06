"""CLI context management for database connections and shared state."""

import os
from dataclasses import dataclass, field

from kameleondb import KameleonDB


def get_database_url(url: str | None) -> str:
    """Resolve database URL from CLI arg, environment variable, or default.

    Priority:
    1. Explicit URL argument
    2. KAMELEONDB_URL environment variable
    3. Default: sqlite:///./kameleondb.db
    """
    if url:
        return url
    if env_url := os.getenv("KAMELEONDB_URL"):
        return env_url
    return "sqlite:///./kameleondb.db"


@dataclass
class CLIContext:
    """Shared context for CLI commands.

    Manages database connection lifecycle and output preferences.
    """

    database_url: str
    echo: bool
    json_output: bool
    _db: KameleonDB | None = field(default=None, init=False, repr=False)

    def get_db(self) -> KameleonDB:
        """Get or create database connection (lazy initialization).

        Returns:
            KameleonDB instance
        """
        if self._db is None:
            self._db = KameleonDB(self.database_url, echo=self.echo)
        return self._db

    def close(self) -> None:
        """Close database connection if open."""
        if self._db is not None:
            self._db.close()
            self._db = None
