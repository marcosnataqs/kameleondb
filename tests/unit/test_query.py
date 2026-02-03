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

    def test_insert_and_find(self, contacts):
        """Can insert and find a record."""
        record_id = contacts.insert(
            {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "age": 30,
            }
        )
        assert record_id is not None

        records = contacts.find()
        assert len(records) == 1
        assert records[0]["first_name"] == "John"
        assert records[0]["email"] == "john@example.com"
        assert records[0]["age"] == 30

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

        records = contacts.find()
        assert len(records) == 2

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

    def test_find_with_filter(self, contacts):
        """Can filter records."""
        contacts.insert({"first_name": "John", "email": "john@example.com", "age": 30})
        contacts.insert({"first_name": "Jane", "email": "jane@example.com", "age": 25})

        records = contacts.find(filters={"first_name": "John"})
        assert len(records) == 1
        assert records[0]["first_name"] == "John"

    def test_find_with_multiple_filters(self, contacts):
        """Can filter with multiple conditions."""
        contacts.insert({"first_name": "John", "email": "john@example.com", "age": 30})
        contacts.insert({"first_name": "John", "email": "john2@example.com", "age": 25})

        records = contacts.find(filters={"first_name": "John", "age": 30})
        assert len(records) == 1
        assert records[0]["age"] == 30

    def test_find_with_operators(self, contacts):
        """Can use comparison operators in filters."""
        contacts.insert({"first_name": "John", "email": "john@example.com", "age": 30})
        contacts.insert({"first_name": "Jane", "email": "jane@example.com", "age": 25})
        contacts.insert({"first_name": "Bob", "email": "bob@example.com", "age": 35})

        # Greater than
        records = contacts.find(filters={"age": {"op": "gt", "value": 28}})
        assert len(records) == 2

        # Less than or equal
        records = contacts.find(filters={"age": {"op": "lte", "value": 25}})
        assert len(records) == 1
        assert records[0]["first_name"] == "Jane"

    def test_find_with_ordering(self, contacts):
        """Can order results."""
        contacts.insert({"first_name": "Charlie", "email": "c@example.com", "age": 30})
        contacts.insert({"first_name": "Alice", "email": "a@example.com", "age": 25})
        contacts.insert({"first_name": "Bob", "email": "b@example.com", "age": 35})

        # Order by first_name ascending
        records = contacts.find(order_by="first_name")
        assert records[0]["first_name"] == "Alice"
        assert records[1]["first_name"] == "Bob"
        assert records[2]["first_name"] == "Charlie"

        # Order by age descending
        records = contacts.find(order_by="age", order_desc=True)
        assert records[0]["age"] == 35
        assert records[1]["age"] == 30
        assert records[2]["age"] == 25

    def test_find_with_pagination(self, contacts):
        """Can paginate results."""
        for i in range(10):
            contacts.insert({"first_name": f"Person{i}", "email": f"p{i}@example.com"})

        # First page
        records = contacts.find(limit=3, offset=0)
        assert len(records) == 3

        # Second page
        records = contacts.find(limit=3, offset=3)
        assert len(records) == 3

        # Last page (partial)
        records = contacts.find(limit=3, offset=9)
        assert len(records) == 1

    def test_find_with_count(self, contacts):
        """Can get total count with pagination."""
        for i in range(10):
            contacts.insert({"first_name": f"Person{i}", "email": f"p{i}@example.com"})

        result = contacts.find_with_count(limit=3, offset=0)
        assert len(result.records) == 3
        assert result.total_count == 10
        assert result.limit == 3
        assert result.offset == 0

    def test_find_invalid_field(self, contacts):
        """Filtering by invalid field raises error."""
        contacts.insert({"first_name": "John", "email": "john@example.com"})

        with pytest.raises(FieldNotFoundError) as exc_info:
            contacts.find(filters={"nonexistent": "value"})
        assert "Available fields:" in str(exc_info.value)

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
        assert contacts.count() == 1

        result = contacts.delete(record_id)
        assert result is True
        assert contacts.count() == 0

    def test_delete_not_found(self, contacts):
        """Deleting nonexistent record raises error."""
        with pytest.raises(RecordNotFoundError):
            contacts.delete("nonexistent-id")

    def test_delete_many(self, contacts):
        """Can delete multiple records."""
        contacts.insert({"first_name": "John", "email": "john@example.com", "age": 30})
        contacts.insert({"first_name": "Jane", "email": "jane@example.com", "age": 30})
        contacts.insert({"first_name": "Bob", "email": "bob@example.com", "age": 25})

        deleted = contacts.delete_many(filters={"age": 30})
        assert deleted == 2
        assert contacts.count() == 1

    def test_count(self, contacts):
        """Can count records."""
        assert contacts.count() == 0

        contacts.insert({"first_name": "John", "email": "john@example.com", "age": 30})
        contacts.insert({"first_name": "Jane", "email": "jane@example.com", "age": 25})

        assert contacts.count() == 2
        assert contacts.count(filters={"age": 30}) == 1

    def test_insert_invalid_field(self, contacts):
        """Inserting with invalid field raises error."""
        with pytest.raises(FieldNotFoundError) as exc_info:
            contacts.insert({"nonexistent": "value"})
        assert "Available fields:" in str(exc_info.value)
