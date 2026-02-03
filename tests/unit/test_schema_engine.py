"""Tests for schema engine."""

import pytest

from kameleondb import KameleonDB
from kameleondb.core.types import FieldType
from kameleondb.exceptions import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    FieldAlreadyExistsError,
    InvalidFieldTypeError,
)


class TestSchemaEngine:
    """Tests for SchemaEngine class."""

    def test_initialize_creates_meta_tables(self, memory_db: KameleonDB):
        """Initializing creates meta-tables."""
        # Meta-tables should exist after initialization
        from sqlalchemy import inspect

        inspector = inspect(memory_db._connection.engine)
        tables = inspector.get_table_names()
        assert "kdb_entity_definitions" in tables
        assert "kdb_field_definitions" in tables
        assert "kdb_schema_changelog" in tables

    def test_list_entities_empty(self, memory_db: KameleonDB):
        """List entities returns empty when no entities."""
        entities = memory_db.list_entities()
        assert entities == []

    def test_create_entity_basic(self, memory_db: KameleonDB):
        """Can create a basic entity."""
        entity = memory_db.create_entity("Contact")
        assert entity.name == "Contact"
        assert memory_db.list_entities() == ["Contact"]

    def test_create_entity_with_fields(self, memory_db: KameleonDB):
        """Can create entity with fields."""
        entity = memory_db.create_entity(
            name="Contact",
            fields=[
                {"name": "first_name", "type": "string", "required": True},
                {"name": "email", "type": "string", "unique": True},
            ],
            description="Contact information",
            created_by="test",
        )
        assert entity.name == "Contact"

        info = memory_db.describe_entity("Contact")
        assert len(info.fields) == 2
        assert info.fields[0].name == "first_name"
        assert info.fields[0].required is True
        assert info.fields[1].name == "email"
        assert info.fields[1].unique is True

    def test_create_entity_already_exists(self, memory_db: KameleonDB):
        """Creating existing entity raises error."""
        memory_db.create_entity("Contact")
        with pytest.raises(EntityAlreadyExistsError) as exc_info:
            memory_db.create_entity("Contact")
        assert "already exists" in str(exc_info.value)
        assert "if_not_exists=True" in str(exc_info.value)

    def test_create_entity_if_not_exists(self, memory_db: KameleonDB):
        """Creating with if_not_exists=True is idempotent."""
        entity1 = memory_db.create_entity("Contact", if_not_exists=True)
        entity2 = memory_db.create_entity("Contact", if_not_exists=True)
        # Should return same entity without error
        assert entity1.name == entity2.name

    def test_entity_not_found_shows_available(self, memory_db: KameleonDB):
        """EntityNotFoundError shows available entities."""
        memory_db.create_entity("Contact")
        memory_db.create_entity("Deal")
        with pytest.raises(EntityNotFoundError) as exc_info:
            memory_db.describe_entity("NonExistent")
        assert "Available entities: Contact, Deal" in str(exc_info.value)

    def test_add_field(self, memory_db: KameleonDB):
        """Can add a field to an entity."""
        entity = memory_db.create_entity("Contact")
        entity.add_field(
            name="phone",
            field_type="string",
            description="Phone number",
            created_by="test-agent",
            reason="Need to store phone numbers",
        )

        info = memory_db.describe_entity("Contact")
        assert len(info.fields) == 1
        assert info.fields[0].name == "phone"
        assert info.fields[0].type == "string"

    def test_add_field_all_types(self, memory_db: KameleonDB):
        """Can add fields of all types."""
        entity = memory_db.create_entity("TestEntity")

        for field_type in FieldType.values():
            entity.add_field(
                name=f"field_{field_type}",
                field_type=field_type,
                if_not_exists=True,
            )

        info = memory_db.describe_entity("TestEntity")
        assert len(info.fields) == len(FieldType.values())

    def test_add_field_invalid_type(self, memory_db: KameleonDB):
        """Adding invalid field type raises error."""
        entity = memory_db.create_entity("Contact")
        with pytest.raises(InvalidFieldTypeError) as exc_info:
            entity.add_field(name="bad", field_type="not_a_type")
        assert "Valid types:" in str(exc_info.value)

    def test_add_field_already_exists(self, memory_db: KameleonDB):
        """Adding existing field raises error."""
        entity = memory_db.create_entity("Contact")
        entity.add_field(name="email", field_type="string")
        with pytest.raises(FieldAlreadyExistsError) as exc_info:
            entity.add_field(name="email", field_type="string")
        assert "already exists" in str(exc_info.value)

    def test_add_field_if_not_exists(self, memory_db: KameleonDB):
        """Adding with if_not_exists=True is idempotent."""
        entity = memory_db.create_entity("Contact")
        entity.add_field(name="email", field_type="string", if_not_exists=True)
        entity.add_field(name="email", field_type="string", if_not_exists=True)
        # Should not raise

        info = memory_db.describe_entity("Contact")
        assert len(info.fields) == 1

    def test_describe_schema(self, memory_db: KameleonDB):
        """Can describe full schema."""
        memory_db.create_entity(
            "Contact",
            fields=[{"name": "email", "type": "string"}],
        )
        memory_db.create_entity(
            "Deal",
            fields=[
                {"name": "name", "type": "string"},
                {"name": "value", "type": "float"},
            ],
        )

        schema = memory_db.describe()
        assert schema["total_entities"] == 2
        assert schema["total_fields"] == 3
        assert "Contact" in schema["entities"]
        assert "Deal" in schema["entities"]

    def test_table_name_generation(self, memory_db: KameleonDB):
        """Entity names are converted to proper table names."""
        memory_db.create_entity("ContactPerson")
        info = memory_db.describe_entity("ContactPerson")
        assert info.table_name == "kdb_contact_person"

    def test_changelog_tracked(self, memory_db: KameleonDB):
        """Schema changes are logged."""
        entity = memory_db.create_entity("Contact", created_by="test-agent")
        entity.add_field(
            name="email",
            field_type="string",
            created_by="test-agent",
            reason="Need email for contacts",
        )

        changelog = memory_db.get_changelog()
        assert len(changelog) == 2
        assert changelog[0]["operation"] == "add_field"
        assert changelog[0]["reason"] == "Need email for contacts"
        assert changelog[1]["operation"] == "create_entity"

    def test_changelog_filtered_by_entity(self, memory_db: KameleonDB):
        """Can filter changelog by entity."""
        memory_db.create_entity("Contact")
        memory_db.create_entity("Deal")

        changelog = memory_db.get_changelog(entity_name="Contact")
        assert len(changelog) == 1
        assert changelog[0]["entity_name"] == "Contact"

    def test_drop_entity(self, memory_db: KameleonDB):
        """Can drop an entity (soft delete)."""
        memory_db.create_entity("Contact")
        assert "Contact" in memory_db.list_entities()

        memory_db.drop_entity("Contact", reason="No longer needed")
        assert "Contact" not in memory_db.list_entities()

        # Should be in changelog
        changelog = memory_db.get_changelog(entity_name="Contact")
        assert any(c["operation"] == "drop_entity" for c in changelog)

    def test_rename_field(self, memory_db: KameleonDB):
        """Can rename a field (logical name changes, column stays)."""
        entity = memory_db.create_entity("Contact")
        entity.add_field(name="phone", field_type="string")

        # Insert data with old name
        record_id = entity.insert({"phone": "123-456"})

        # Rename the field
        entity.rename_field(
            old_name="phone",
            new_name="phone_number",
            reason="Standardizing field names",
        )

        # Field should be renamed in schema
        info = memory_db.describe_entity("Contact")
        field_names = [f.name for f in info.fields]
        assert "phone_number" in field_names
        assert "phone" not in field_names

        # Should be able to query with new name
        record = entity.find_by_id(record_id)
        assert record["phone_number"] == "123-456"

        # Should be in changelog
        changelog = memory_db.get_changelog(entity_name="Contact")
        assert any(c["operation"] == "rename_field" for c in changelog)

    def test_rename_field_to_existing_raises_error(self, memory_db: KameleonDB):
        """Renaming to existing field name raises error."""
        entity = memory_db.create_entity("Contact")
        entity.add_field(name="phone", field_type="string")
        entity.add_field(name="email", field_type="string")

        with pytest.raises(FieldAlreadyExistsError):
            entity.rename_field(old_name="phone", new_name="email")

    def test_drop_field(self, memory_db: KameleonDB):
        """Can drop a field (soft delete)."""
        entity = memory_db.create_entity("Contact")
        entity.add_field(name="phone", field_type="string")
        entity.add_field(name="email", field_type="string")

        # Drop phone field
        entity.drop_field(name="phone", reason="No longer needed")

        # Phone should not appear in schema
        info = memory_db.describe_entity("Contact")
        field_names = [f.name for f in info.fields]
        assert "phone" not in field_names
        assert "email" in field_names

        # Should be in changelog
        changelog = memory_db.get_changelog(entity_name="Contact")
        assert any(c["operation"] == "drop_field" for c in changelog)

    def test_modify_field(self, memory_db: KameleonDB):
        """Can modify field properties."""
        entity = memory_db.create_entity("Contact")
        entity.add_field(name="email", field_type="string", indexed=False)

        # Modify to add index and description
        entity.modify_field(
            name="email",
            indexed=True,
            description="Primary email address",
            reason="Adding index for performance",
        )

        info = memory_db.describe_entity("Contact")
        email_field = next(f for f in info.fields if f.name == "email")
        assert email_field.indexed is True
        assert email_field.description == "Primary email address"

        # Should be in changelog
        changelog = memory_db.get_changelog(entity_name="Contact")
        assert any(c["operation"] == "modify_field" for c in changelog)

    def test_alter_unified_api(self, memory_db: KameleonDB):
        """Can use unified alter() API for multiple changes."""
        entity = memory_db.create_entity(
            "Contact",
            fields=[
                {"name": "old_field", "type": "string"},
                {"name": "to_rename", "type": "string"},
                {"name": "to_drop", "type": "string"},
            ],
        )

        # Apply multiple changes at once
        info = entity.alter(
            add_fields=[{"name": "new_field", "type": "string", "indexed": True}],
            rename_fields={"to_rename": "renamed_field"},
            drop_fields=["to_drop"],
            reason="Batch schema update",
        )

        field_names = [f.name for f in info.fields]
        assert "new_field" in field_names
        assert "renamed_field" in field_names
        assert "to_rename" not in field_names
        assert "to_drop" not in field_names
        assert "old_field" in field_names

    def test_data_access_after_rename(self, memory_db: KameleonDB):
        """Data remains accessible after field rename."""
        entity = memory_db.create_entity("Contact")
        entity.add_field(name="phone", field_type="string")
        entity.add_field(name="email", field_type="string")

        # Insert data
        id1 = entity.insert({"phone": "111-111", "email": "a@a.com"})
        entity.insert({"phone": "222-222", "email": "b@b.com"})

        # Rename field
        entity.rename_field(old_name="phone", new_name="phone_number")

        # Query with new name should work
        records = entity.find(filters={"phone_number": "111-111"})
        assert len(records) == 1
        assert records[0]["phone_number"] == "111-111"
        assert records[0]["email"] == "a@a.com"

        # Insert with new name should work
        id3 = entity.insert({"phone_number": "333-333", "email": "c@c.com"})
        record = entity.find_by_id(id3)
        assert record["phone_number"] == "333-333"

        # Update with new name should work
        entity.update(id1, {"phone_number": "111-updated"})
        record = entity.find_by_id(id1)
        assert record["phone_number"] == "111-updated"

    def test_order_by_renamed_field(self, memory_db: KameleonDB):
        """Can order by renamed field."""
        entity = memory_db.create_entity("Contact")
        entity.add_field(name="name", field_type="string")

        entity.insert({"name": "Zoe"})
        entity.insert({"name": "Alice"})
        entity.insert({"name": "Bob"})

        # Rename field
        entity.rename_field(old_name="name", new_name="full_name")

        # Order by new name
        records = entity.find(order_by="full_name")
        assert records[0]["full_name"] == "Alice"
        assert records[1]["full_name"] == "Bob"
        assert records[2]["full_name"] == "Zoe"
