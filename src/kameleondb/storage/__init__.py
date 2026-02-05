"""Storage management for KameleonDB.

This module provides hybrid storage support:
- Shared storage: All records in kdb_records table (default)
- Dedicated storage: Entity-specific tables with foreign keys
"""

from kameleondb.storage.dedicated import DedicatedTableManager
from kameleondb.storage.migration import StorageMigration

__all__ = ["DedicatedTableManager", "StorageMigration"]
