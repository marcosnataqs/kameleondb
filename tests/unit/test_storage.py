"""Tests for hybrid storage functionality (ADR-001 Phase 2)."""

from __future__ import annotations

import pytest

from kameleondb import KameleonDB
from kameleondb.schema.models import StorageMode
from kameleondb.storage.dedicated import DedicatedTableManager
from kameleondb.storage.migration import MigrationProgress, StorageMigration


class TestDedicatedTableManager:
    """Test DedicatedTableManager functionality."""

    def test_generate_table_name(self, memory_db: KameleonDB) -> None:
        """Test table name generation."""
        manager = DedicatedTableManager(memory_db._connection.engine)

        assert manager.generate_table_name("Contact") == "kdb_contact"
        assert manager.generate_table_name("CustomerOrder") == "kdb_customer_order"
        assert manager.generate_table_name("User Profile") == "kdb_user_profile"

    def test_create_dedicated_table(self, memory_db: KameleonDB) -> None:
        """Test creating a dedicated table."""
        # Create entity in shared mode
        memory_db.create_entity(
            "TestEntity",
            fields=[
                {"name": "name", "type": "string", "required": True},
                {"name": "count", "type": "int"},
                {"name": "active", "type": "bool"},
            ],
        )

        # Get entity definition
        entity_def = memory_db._schema_engine.get_entity("TestEntity")
        fields = memory_db._schema_engine.get_fields("TestEntity")

        manager = DedicatedTableManager(memory_db._connection.engine)

        # Create dedicated table
        table_name = manager.create_dedicated_table(entity_def, fields)

        assert table_name == "kdb_test_entity"
        assert manager.table_exists(table_name)

    def test_create_dedicated_table_fails_if_already_dedicated(self, memory_db: KameleonDB) -> None:
        """Test that creating a dedicated table fails if entity is already dedicated."""
        memory_db.create_entity("TestEntity", fields=[{"name": "name", "type": "string"}])

        entity_def = memory_db._schema_engine.get_entity("TestEntity")
        fields = memory_db._schema_engine.get_fields("TestEntity")

        # Manually set to dedicated mode
        entity_def.storage_mode = StorageMode.DEDICATED

        manager = DedicatedTableManager(memory_db._connection.engine)

        with pytest.raises(ValueError, match="already in dedicated mode"):
            manager.create_dedicated_table(entity_def, fields)

    def test_drop_dedicated_table(self, memory_db: KameleonDB) -> None:
        """Test dropping a dedicated table."""
        memory_db.create_entity("TestEntity", fields=[{"name": "name", "type": "string"}])

        entity_def = memory_db._schema_engine.get_entity("TestEntity")
        fields = memory_db._schema_engine.get_fields("TestEntity")

        manager = DedicatedTableManager(memory_db._connection.engine)
        table_name = manager.create_dedicated_table(entity_def, fields)

        assert manager.table_exists(table_name)

        manager.drop_dedicated_table(table_name)

        assert not manager.table_exists(table_name)


class TestStorageMigration:
    """Test StorageMigration functionality."""

    def test_migrate_to_dedicated_empty_entity(self, memory_db: KameleonDB) -> None:
        """Test migrating an empty entity to dedicated storage."""
        memory_db.create_entity(
            "TestEntity",
            fields=[{"name": "name", "type": "string"}],
        )

        entity_def = memory_db._schema_engine.get_entity("TestEntity")
        fields = memory_db._schema_engine.get_fields("TestEntity")

        migration = StorageMigration(memory_db._connection.engine)
        result = migration.migrate_to_dedicated(entity_def, fields)

        assert result.success
        assert result.records_migrated == 0
        assert result.table_name == "kdb_test_entity"

    def test_migrate_to_dedicated_with_data(self, memory_db: KameleonDB) -> None:
        """Test migrating an entity with data to dedicated storage."""
        entity = memory_db.create_entity(
            "TestEntity",
            fields=[
                {"name": "name", "type": "string"},
                {"name": "value", "type": "int"},
            ],
        )

        # Insert some records
        entity.insert({"name": "Record 1", "value": 100})
        entity.insert({"name": "Record 2", "value": 200})
        entity.insert({"name": "Record 3", "value": 300})

        entity_def = memory_db._schema_engine.get_entity("TestEntity")
        fields = memory_db._schema_engine.get_fields("TestEntity")

        migration = StorageMigration(memory_db._connection.engine)
        result = migration.migrate_to_dedicated(entity_def, fields)

        assert result.success
        assert result.records_migrated == 3
        assert result.table_name == "kdb_test_entity"

    def test_migrate_to_dedicated_with_progress(self, memory_db: KameleonDB) -> None:
        """Test migration with progress callback."""
        entity = memory_db.create_entity(
            "TestEntity",
            fields=[{"name": "name", "type": "string"}],
        )

        # Insert records
        for i in range(5):
            entity.insert({"name": f"Record {i}"})

        entity_def = memory_db._schema_engine.get_entity("TestEntity")
        fields = memory_db._schema_engine.get_fields("TestEntity")

        progress_updates: list[MigrationProgress] = []

        def on_progress(progress: MigrationProgress) -> None:
            progress_updates.append(progress)

        migration = StorageMigration(memory_db._connection.engine)
        result = migration.migrate_to_dedicated(
            entity_def, fields, batch_size=2, on_progress=on_progress
        )

        assert result.success
        assert result.records_migrated == 5
        assert len(progress_updates) > 0
        assert progress_updates[-1].percentage == 100.0

    def test_migrate_to_shared(self, memory_db: KameleonDB) -> None:
        """Test migrating from dedicated back to shared storage."""
        entity = memory_db.create_entity(
            "TestEntity",
            fields=[{"name": "name", "type": "string"}],
        )

        # Insert records
        entity.insert({"name": "Record 1"})
        entity.insert({"name": "Record 2"})

        entity_def = memory_db._schema_engine.get_entity("TestEntity")
        fields = memory_db._schema_engine.get_fields("TestEntity")

        migration = StorageMigration(memory_db._connection.engine)

        # First, migrate to dedicated
        result1 = migration.migrate_to_dedicated(entity_def, fields)
        assert result1.success

        # Refresh entity definition (storage_mode changed)
        entity_def = memory_db._schema_engine.get_entity("TestEntity")
        assert entity_def.storage_mode == StorageMode.DEDICATED

        # Now migrate back to shared
        result2 = migration.migrate_to_shared(entity_def, fields)
        assert result2.success
        assert result2.records_migrated == 2

    def test_migrate_to_shared_fails_if_not_dedicated(self, memory_db: KameleonDB) -> None:
        """Test that migrating to shared fails if entity is not dedicated."""
        memory_db.create_entity(
            "TestEntity",
            fields=[{"name": "name", "type": "string"}],
        )

        entity_def = memory_db._schema_engine.get_entity("TestEntity")
        fields = memory_db._schema_engine.get_fields("TestEntity")

        migration = StorageMigration(memory_db._connection.engine)
        result = migration.migrate_to_shared(entity_def, fields)

        assert not result.success
        assert "not in dedicated mode" in result.error


class TestKameleonDBMaterialization:
    """Test KameleonDB materialize/dematerialize methods."""

    def test_materialize_entity(self, memory_db: KameleonDB) -> None:
        """Test materializing an entity through the main API."""
        entity = memory_db.create_entity(
            "Contact",
            fields=[
                {"name": "email", "type": "string"},
                {"name": "name", "type": "string"},
            ],
        )

        # Insert some data
        entity.insert({"email": "test@example.com", "name": "Test User"})

        result = memory_db.materialize_entity(
            "Contact",
            reason="Enable foreign keys",
        )

        assert result["success"]
        assert result["records_migrated"] == 1
        assert result["table_name"] == "kdb_contact"

        # Verify entity info updated
        info = memory_db.describe_entity("Contact")
        assert info.storage_mode == StorageMode.DEDICATED
        assert info.dedicated_table_name == "kdb_contact"

    def test_dematerialize_entity(self, memory_db: KameleonDB) -> None:
        """Test dematerializing an entity through the main API."""
        entity = memory_db.create_entity(
            "Contact",
            fields=[{"name": "email", "type": "string"}],
        )

        entity.insert({"email": "test@example.com"})

        # First materialize
        memory_db.materialize_entity("Contact")

        # Then dematerialize
        result = memory_db.dematerialize_entity(
            "Contact",
            reason="Removing FK constraints",
        )

        assert result["success"]
        assert result["records_migrated"] == 1

        # Verify entity info updated
        info = memory_db.describe_entity("Contact")
        assert info.storage_mode == StorageMode.SHARED
        assert info.dedicated_table_name is None

    def test_materialize_logs_to_changelog(self, memory_db: KameleonDB) -> None:
        """Test that materialization is logged to changelog."""
        memory_db.create_entity(
            "Contact",
            fields=[{"name": "email", "type": "string"}],
        )

        memory_db.materialize_entity(
            "Contact",
            created_by="test_agent",
            reason="Enable foreign keys",
        )

        changelog = memory_db.get_changelog(entity_name="Contact", limit=10)

        # Find the materialize entry
        materialize_entries = [e for e in changelog if e["operation"] == "materialize"]
        assert len(materialize_entries) == 1
        assert materialize_entries[0]["created_by"] == "test_agent"
        assert materialize_entries[0]["reason"] == "Enable foreign keys"
