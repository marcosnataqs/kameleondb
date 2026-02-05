"""Integration tests for full KameleonDB workflow."""

import pytest

from kameleondb import KameleonDB


class TestFullWorkflow:
    """End-to-end tests for KameleonDB."""

    def test_complete_crud_workflow(self, memory_db: KameleonDB):
        """Test complete CRUD workflow as an agent would use it."""
        # 1. Discover schema (agent's first action)
        schema = memory_db.describe()
        assert schema["total_entities"] == 0

        # 2. Create an entity with fields
        contacts = memory_db.create_entity(
            name="Contact",
            fields=[
                {"name": "first_name", "type": "string", "required": True},
                {"name": "email", "type": "string", "unique": True},
                {"name": "age", "type": "int"},
            ],
            created_by="discovery-agent",
            if_not_exists=True,
        )

        # 3. Verify entity was created
        schema = memory_db.describe()
        assert schema["total_entities"] == 1
        assert "Contact" in schema["entities"]

        # 4. Get entity details
        entity_info = memory_db.describe_entity("Contact")
        assert entity_info.name == "Contact"
        assert len(entity_info.fields) == 3

        # 5. Insert records
        id1 = contacts.insert(
            {"first_name": "John", "email": "john@example.com", "age": 30},
            created_by="data-agent",
        )
        id2 = contacts.insert(
            {"first_name": "Jane", "email": "jane@example.com", "age": 25},
            created_by="data-agent",
        )

        # 6. Query records by ID
        john = contacts.find_by_id(id1)
        assert john is not None
        assert john["email"] == "john@example.com"

        jane = contacts.find_by_id(id2)
        assert jane is not None
        assert jane["email"] == "jane@example.com"

        # 7. Update a record
        updated = contacts.update(id1, {"age": 31})
        assert updated["age"] == 31

        # 8. Evolve schema (add a field)
        contacts.add_field(
            name="linkedin_url",
            field_type="string",
            created_by="enrichment-agent",
            reason="Found LinkedIn profiles in documents",
            if_not_exists=True,
        )

        # 9. Verify new field exists
        entity_info = memory_db.describe_entity("Contact")
        field_names = [f.name for f in entity_info.fields]
        assert "linkedin_url" in field_names

        # 10. Use new field
        contacts.update(id1, {"linkedin_url": "https://linkedin.com/in/johndoe"})
        john = contacts.find_by_id(id1)
        assert john is not None
        assert john["linkedin_url"] == "https://linkedin.com/in/johndoe"

        # 11. Delete a record
        contacts.delete(id2)

        # Verify deletion (soft delete - record not found)
        jane = contacts.find_by_id(id2)
        assert jane is None

        # John should still exist
        john = contacts.find_by_id(id1)
        assert john is not None

        # 12. Check changelog
        changelog = memory_db.get_changelog(entity_name="Contact")
        assert len(changelog) >= 2  # At least create_entity and add_field

    def test_idempotent_operations(self, memory_db: KameleonDB):
        """Test that idempotent operations work correctly for agents."""
        # Agents may call operations multiple times
        # These should not fail with if_not_exists=True

        # Create entity multiple times
        for _ in range(3):
            entity = memory_db.create_entity(
                name="Contact",
                fields=[{"name": "email", "type": "string"}],
                if_not_exists=True,
            )
            assert entity.name == "Contact"

        # Add field multiple times
        for _ in range(3):
            entity.add_field(
                name="phone",
                field_type="string",
                if_not_exists=True,
            )

        # Should only have one entity with expected fields
        schema = memory_db.describe()
        assert schema["total_entities"] == 1
        assert schema["total_fields"] == 2  # email + phone

    def test_multiple_entities(self, memory_db: KameleonDB):
        """Test working with multiple entities."""
        # Create multiple entities
        contacts = memory_db.create_entity(
            "Contact",
            fields=[{"name": "email", "type": "string"}],
        )
        deals = memory_db.create_entity(
            "Deal",
            fields=[
                {"name": "name", "type": "string"},
                {"name": "value", "type": "float"},
            ],
        )
        companies = memory_db.create_entity(
            "Company",
            fields=[{"name": "name", "type": "string"}],
        )

        # All should be accessible
        assert memory_db.list_entities() == ["Contact", "Deal", "Company"]

        # Can use each independently
        contact_id = contacts.insert({"email": "test@example.com"})
        deal_id = deals.insert({"name": "Big Deal", "value": 10000.0})
        company_id = companies.insert({"name": "ACME Corp"})

        # Verify records exist
        assert contacts.find_by_id(contact_id) is not None
        assert deals.find_by_id(deal_id) is not None
        assert companies.find_by_id(company_id) is not None

    def test_error_messages_are_actionable(self, memory_db: KameleonDB):
        """Test that error messages help agents fix issues."""
        # Create an entity
        memory_db.create_entity(
            "Contact",
            fields=[{"name": "email", "type": "string"}],
        )

        # Try to access non-existent entity
        try:
            memory_db.describe_entity("NonExistent")
        except Exception as e:
            # Error should list available entities
            assert "Contact" in str(e)
            assert "Available entities:" in str(e)

        # Note: filter-based queries are now done via SQL generation
        # Use get_schema_context() + execute_sql() for complex queries

    def test_tools_are_functional(self, memory_db: KameleonDB):
        """Test that exported tools are actually callable."""
        tools = memory_db.get_tools()

        # Find describe tool
        describe_tool = next(t for t in tools if t.name == "kameleondb_describe")
        assert describe_tool.function is not None

        # Call it
        result = describe_tool.function()
        assert isinstance(result, dict)
        assert "total_entities" in result

        # Find list_entities tool
        list_tool = next(t for t in tools if t.name == "kameleondb_list_entities")
        result = list_tool.function()
        assert isinstance(result, list)


@pytest.mark.integration
class TestPostgreSQLIntegration:
    """Integration tests for PostgreSQL."""

    def test_basic_workflow_postgresql(self, pg_db: KameleonDB):
        """Test basic workflow with PostgreSQL."""
        # Create entity
        contacts = pg_db.create_entity(
            "Contact",
            fields=[
                {"name": "email", "type": "string", "unique": True},
                {"name": "data", "type": "json"},
            ],
        )

        # Insert with JSON field
        id1 = contacts.insert(
            {
                "email": "test@example.com",
                "data": {"tags": ["customer", "premium"]},
            }
        )

        # Query
        record = contacts.find_by_id(id1)
        assert record is not None
        assert record["email"] == "test@example.com"
        # JSONB should work
        assert record["data"] is not None

    def test_all_field_types_postgresql(self, pg_db: KameleonDB):
        """Test all field types work with PostgreSQL."""
        from kameleondb.core.types import FieldType

        entity = pg_db.create_entity("TypeTest")

        for field_type in FieldType.values():
            entity.add_field(
                name=f"field_{field_type}",
                field_type=field_type,
                if_not_exists=True,
            )

        info = pg_db.describe_entity("TypeTest")
        assert len(info.fields) == len(FieldType.values())
