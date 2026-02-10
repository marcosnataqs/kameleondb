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

    def test_query_dedicated_table_after_materialization(self, memory_db: KameleonDB) -> None:
        """Test that SQL queries work on dedicated tables after materialization."""
        # Create entity and add data
        entity = memory_db.create_entity(
            "Product",
            fields=[
                {"name": "name", "type": "string"},
                {"name": "price", "type": "float"},
            ],
        )
        entity.insert({"name": "Widget", "price": 19.99})
        entity.insert({"name": "Gadget", "price": 5.99})

        # Materialize to dedicated table
        memory_db.materialize_entity("Product")

        # Execute SQL query on dedicated table (use typed columns)
        result = memory_db.execute_sql("SELECT * FROM kdb_product WHERE price > 10.0")

        assert len(result.rows) == 1
        # Access typed columns directly
        assert result.rows[0]["name"] == "Widget"
        assert result.rows[0]["price"] == 19.99

    def test_migration_counter_excludes_deleted_records(self, memory_db: KameleonDB) -> None:
        """Test that migration counter only counts non-deleted records."""
        # Create entity with 5 records
        entity = memory_db.create_entity(
            "Contact",
            fields=[
                {"name": "name", "type": "string"},
            ],
        )
        ids = []
        for i in range(5):
            record_id = entity.insert({"name": f"Contact {i}"})
            ids.append(record_id)

        # Soft-delete one record BEFORE materialization
        entity.delete(ids[0])

        # Materialize to dedicated (should migrate only 4 non-deleted records)
        report = memory_db.materialize_entity("Contact")

        # Report should show 4 migrated (not 5)
        assert report["records_migrated"] == 4
        assert report["success"]

        # Now dematerialize back and verify counter again
        report2 = memory_db.dematerialize_entity("Contact")
        assert report2["records_migrated"] == 4
        assert report2["success"]

    def test_cross_storage_join(self, memory_db: KameleonDB) -> None:
        """Test JOINs between shared and dedicated tables."""
        # Create two related entities
        property_entity = memory_db.create_entity(
            "Property",
            fields=[
                {"name": "address", "type": "string"},
            ],
        )
        transaction_entity = memory_db.create_entity(
            "Transaction",
            fields=[
                {"name": "property_id", "type": "string"},
                {"name": "amount", "type": "float"},
            ],
        )

        # Insert property
        prop_id = property_entity.insert({"address": "123 Main St"})

        # Insert transaction referencing property
        transaction_entity.insert(
            {
                "property_id": prop_id,
                "amount": 500000.0,
            }
        )

        # Materialize Property to dedicated table
        memory_db.materialize_entity("Property")

        # Get entity IDs for query
        txn_entity_id = memory_db._schema_engine.get_entity("Transaction").id

        # Execute cross-storage JOIN
        # Transaction stays in shared (kdb_records with JSON data)
        # Property moves to dedicated (kdb_property with typed columns)
        result = memory_db.execute_sql(
            f"""
            SELECT
              t.id as transaction_id,
              p.address as property_address
            FROM kdb_records t
            JOIN kdb_property p ON json_extract(t.data, '$.property_id') = p.id
            WHERE t.entity_id = '{txn_entity_id}'
        """
        )

        assert len(result.rows) == 1
        assert result.rows[0]["property_address"] == "123 Main St"

    def test_reserved_field_names_rejected_on_create(self, memory_db: KameleonDB) -> None:
        """Test that reserved system column names are rejected when creating entities.

        Regression test for GitHub issue #27: Users should not be able to create
        fields with names like 'created_at', 'updated_at', 'is_deleted', etc.
        as these conflict with internal system columns.
        """
        from kameleondb.exceptions import ReservedFieldNameError

        # Try to create entity with reserved field name 'created_at'
        with pytest.raises(ReservedFieldNameError) as exc_info:
            memory_db.create_entity(
                "EventLog",
                fields=[
                    {"name": "event_type", "type": "string", "required": True},
                    {"name": "created_at", "type": "datetime"},  # Reserved!
                ],
            )

        assert "created_at" in str(exc_info.value)
        assert "reserved" in str(exc_info.value).lower()

    def test_reserved_field_names_rejected_on_add_field(self, memory_db: KameleonDB) -> None:
        """Test that reserved names are also rejected when adding fields later."""
        from kameleondb.exceptions import ReservedFieldNameError

        # Create entity without reserved fields
        entity = memory_db.create_entity(
            "EventLog",
            fields=[{"name": "event_type", "type": "string"}],
        )

        # Try to add a field with reserved name
        with pytest.raises(ReservedFieldNameError) as exc_info:
            entity.add_field("updated_at", field_type="datetime")

        assert "updated_at" in str(exc_info.value)
        assert "reserved" in str(exc_info.value).lower()

        # Also test 'is_deleted'
        with pytest.raises(ReservedFieldNameError):
            entity.add_field("is_deleted", field_type="bool")
