"""Tests for query operations."""

import pytest

from kameleondb import KameleonDB
from kameleondb.exceptions import FieldNotFoundError, RecordNotFoundError


class TestQueryOperations:
    """Tests for data CRUD operations."""

    @pytest.fixture
    def contacts(self, memory_db: KameleonDB):
        """Create a Contact entity for testing."""
        return memory_db.create_entity(
            "Contact",
            fields=[
                {"name": "first_name", "type": "string", "required": True},
                {"name": "last_name", "type": "string"},
                {"name": "email", "type": "string", "unique": True},
                {"name": "age", "type": "int"},
            ],
        )

    def test_insert_and_find_by_id(self, contacts):
        """Can insert and find a record by ID."""
        record_id = contacts.insert(
            {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "age": 30,
            }
        )
        assert record_id is not None

        record = contacts.find_by_id(record_id)
        assert record is not None
        assert record["first_name"] == "John"
        assert record["email"] == "john@example.com"
        assert record["age"] == 30

    def test_insert_with_created_by(self, contacts):
        """Insert tracks created_by."""
        record_id = contacts.insert(
            {"first_name": "John", "email": "john@example.com"},
            created_by="test-agent",
        )

        record = contacts.find_by_id(record_id)
        assert record is not None
        assert record["created_by"] == "test-agent"

    def test_insert_many(self, contacts):
        """Can insert multiple records."""
        ids = contacts.insert_many(
            [
                {"first_name": "John", "email": "john@example.com"},
                {"first_name": "Jane", "email": "jane@example.com"},
            ]
        )
        assert len(ids) == 2

        # Verify both records exist
        for record_id in ids:
            record = contacts.find_by_id(record_id)
            assert record is not None

    def test_find_by_id(self, contacts):
        """Can find record by ID."""
        record_id = contacts.insert({"first_name": "John", "email": "john@example.com"})

        record = contacts.find_by_id(record_id)
        assert record is not None
        assert record["id"] == record_id
        assert record["first_name"] == "John"

    def test_find_by_id_not_found(self, contacts):
        """Find by ID returns None for missing record."""
        record = contacts.find_by_id("nonexistent-id")
        assert record is None

    def test_update(self, contacts):
        """Can update a record."""
        record_id = contacts.insert({"first_name": "John", "email": "john@example.com"})

        updated = contacts.update(record_id, {"first_name": "Johnny"})
        assert updated["first_name"] == "Johnny"
        assert updated["email"] == "john@example.com"

        # Verify persistence
        record = contacts.find_by_id(record_id)
        assert record is not None
        assert record["first_name"] == "Johnny"

    def test_update_not_found(self, contacts):
        """Updating nonexistent record raises error."""
        with pytest.raises(RecordNotFoundError) as exc_info:
            contacts.update("nonexistent-id", {"first_name": "John"})
        assert "not found" in str(exc_info.value)

    def test_update_invalid_field(self, contacts):
        """Updating with invalid field raises error."""
        record_id = contacts.insert({"first_name": "John", "email": "john@example.com"})

        with pytest.raises(FieldNotFoundError):
            contacts.update(record_id, {"nonexistent": "value"})

    def test_delete(self, contacts):
        """Can delete a record."""
        record_id = contacts.insert({"first_name": "John", "email": "john@example.com"})

        # Verify record exists
        record = contacts.find_by_id(record_id)
        assert record is not None

        result = contacts.delete(record_id)
        assert result is True

        # Verify record is deleted (soft delete - returns None)
        record = contacts.find_by_id(record_id)
        assert record is None

    def test_delete_not_found(self, contacts):
        """Deleting nonexistent record raises error."""
        with pytest.raises(RecordNotFoundError):
            contacts.delete("nonexistent-id")

    def test_insert_invalid_field(self, contacts):
        """Inserting with invalid field raises error."""
        with pytest.raises(FieldNotFoundError) as exc_info:
            contacts.insert({"nonexistent": "value"})
        assert "Available fields:" in str(exc_info.value)
