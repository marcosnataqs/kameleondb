"""Tests for relationship functionality (ADR-001: Hybrid Storage Architecture)."""

from __future__ import annotations

from kameleondb.core.types import (
    OnDeleteActionType,
    RelationshipInfo,
    RelationshipTypeEnum,
    StorageModeType,
)
from kameleondb.exceptions import (
    InvalidOnDeleteActionError,
    InvalidRelationshipTypeError,
    RelationshipAlreadyExistsError,
    RelationshipNotFoundError,
)
from kameleondb.schema.models import (
    EntityDefinition,
    JunctionTable,
    OnDeleteAction,
    RelationshipDefinition,
    RelationshipType,
    StorageMode,
)


class TestStorageModeConstants:
    """Test storage mode constants."""

    def test_storage_mode_values(self):
        """Test StorageMode constants."""
        assert StorageMode.SHARED == "shared"
        assert StorageMode.DEDICATED == "dedicated"

    def test_storage_mode_type_enum(self):
        """Test StorageModeType enum."""
        assert StorageModeType.SHARED.value == "shared"
        assert StorageModeType.DEDICATED.value == "dedicated"
        assert set(StorageModeType.values()) == {"shared", "dedicated"}


class TestRelationshipTypeConstants:
    """Test relationship type constants."""

    def test_relationship_type_values(self):
        """Test RelationshipType constants."""
        assert RelationshipType.MANY_TO_ONE == "many_to_one"
        assert RelationshipType.ONE_TO_MANY == "one_to_many"
        assert RelationshipType.MANY_TO_MANY == "many_to_many"
        assert RelationshipType.ONE_TO_ONE == "one_to_one"

    def test_relationship_type_enum(self):
        """Test RelationshipTypeEnum."""
        assert RelationshipTypeEnum.MANY_TO_ONE.value == "many_to_one"
        assert RelationshipTypeEnum.ONE_TO_MANY.value == "one_to_many"
        assert RelationshipTypeEnum.MANY_TO_MANY.value == "many_to_many"
        assert RelationshipTypeEnum.ONE_TO_ONE.value == "one_to_one"
        assert set(RelationshipTypeEnum.values()) == {
            "many_to_one",
            "one_to_many",
            "many_to_many",
            "one_to_one",
        }


class TestOnDeleteActionConstants:
    """Test on_delete action constants."""

    def test_on_delete_action_values(self):
        """Test OnDeleteAction constants."""
        assert OnDeleteAction.CASCADE == "CASCADE"
        assert OnDeleteAction.SET_NULL == "SET_NULL"
        assert OnDeleteAction.RESTRICT == "RESTRICT"
        assert OnDeleteAction.NO_ACTION == "NO_ACTION"

    def test_on_delete_action_type_enum(self):
        """Test OnDeleteActionType enum."""
        assert OnDeleteActionType.CASCADE.value == "CASCADE"
        assert OnDeleteActionType.SET_NULL.value == "SET_NULL"
        assert OnDeleteActionType.RESTRICT.value == "RESTRICT"
        assert OnDeleteActionType.NO_ACTION.value == "NO_ACTION"
        assert set(OnDeleteActionType.values()) == {
            "CASCADE",
            "SET_NULL",
            "RESTRICT",
            "NO_ACTION",
        }


class TestRelationshipExceptions:
    """Test relationship-related exceptions."""

    def test_relationship_not_found_error_with_available(self):
        """Test RelationshipNotFoundError with available relationships."""
        error = RelationshipNotFoundError("customer", "Order", ["items", "shipping"])
        assert "customer" in str(error)
        assert "Order" in str(error)
        assert "items" in str(error)
        assert "shipping" in str(error)
        assert error.relationship_name == "customer"
        assert error.entity_name == "Order"
        assert error.available_relationships == ["items", "shipping"]

    def test_relationship_not_found_error_no_available(self):
        """Test RelationshipNotFoundError with no available relationships."""
        error = RelationshipNotFoundError("customer", "Order", [])
        assert "customer" in str(error)
        assert "Order" in str(error)
        assert "No relationships defined" in str(error)

    def test_relationship_already_exists_error(self):
        """Test RelationshipAlreadyExistsError."""
        error = RelationshipAlreadyExistsError("customer", "Order")
        assert "customer" in str(error)
        assert "Order" in str(error)
        assert "already exists" in str(error)
        assert error.relationship_name == "customer"
        assert error.entity_name == "Order"

    def test_invalid_relationship_type_error(self):
        """Test InvalidRelationshipTypeError."""
        error = InvalidRelationshipTypeError("invalid_type")
        assert "invalid_type" in str(error)
        assert "many_to_one" in str(error)
        assert error.relationship_type == "invalid_type"
        assert "many_to_one" in error.VALID_TYPES

    def test_invalid_on_delete_action_error(self):
        """Test InvalidOnDeleteActionError."""
        error = InvalidOnDeleteActionError("INVALID")
        assert "INVALID" in str(error)
        assert "CASCADE" in str(error)
        assert error.action == "INVALID"
        assert "CASCADE" in error.VALID_ACTIONS


class TestEntityDefinitionModel:
    """Test EntityDefinition model with storage mode fields."""

    def test_entity_definition_explicit_storage_mode(self):
        """Test that storage mode can be set explicitly."""
        entity = EntityDefinition(
            name="Test", table_name="kdb_test", storage_mode=StorageMode.SHARED
        )
        assert entity.storage_mode == StorageMode.SHARED
        assert entity.dedicated_table_name is None

    def test_entity_definition_to_dict_includes_storage_mode(self):
        """Test that to_dict includes storage mode fields."""
        entity = EntityDefinition(
            id="test-id",
            name="Test",
            table_name="kdb_test",
            storage_mode=StorageMode.DEDICATED,
            dedicated_table_name="kdb_test_dedicated",
        )
        entity.fields = []
        result = entity.to_dict()
        assert result["storage_mode"] == "dedicated"
        assert result["dedicated_table_name"] == "kdb_test_dedicated"


class TestRelationshipDefinitionModel:
    """Test RelationshipDefinition model."""

    def test_relationship_definition_creation(self):
        """Test creating a relationship definition."""
        rel = RelationshipDefinition(
            name="customer",
            source_entity_id="order-entity-id",
            target_entity_id="customer-entity-id",
            relationship_type=RelationshipType.MANY_TO_ONE,
            foreign_key_field="customer_id",
            on_delete=OnDeleteAction.SET_NULL,
            is_active=True,  # Explicit since default only applies at DB level
        )
        assert rel.name == "customer"
        assert rel.relationship_type == "many_to_one"
        assert rel.foreign_key_field == "customer_id"
        assert rel.on_delete == "SET_NULL"
        assert rel.is_active is True

    def test_relationship_definition_to_dict(self):
        """Test relationship to_dict method."""
        rel = RelationshipDefinition(
            id="rel-id",
            name="customer",
            source_entity_id="order-entity-id",
            target_entity_id="customer-entity-id",
            relationship_type=RelationshipType.MANY_TO_ONE,
            foreign_key_field="customer_id",
            inverse_name="orders",
            on_delete=OnDeleteAction.CASCADE,
            on_update=OnDeleteAction.CASCADE,
            description="Order belongs to a customer",
        )
        result = rel.to_dict()
        assert result["id"] == "rel-id"
        assert result["name"] == "customer"
        assert result["relationship_type"] == "many_to_one"
        assert result["foreign_key_field"] == "customer_id"
        assert result["inverse_name"] == "orders"
        assert result["on_delete"] == "CASCADE"
        assert result["description"] == "Order belongs to a customer"


class TestJunctionTableModel:
    """Test JunctionTable model for many-to-many relationships."""

    def test_junction_table_creation(self):
        """Test creating a junction table."""
        junction = JunctionTable(
            relationship_id="rel-id",
            table_name="kdb_product_tag",
            source_fk_column="product_id",
            target_fk_column="tag_id",
        )
        assert junction.table_name == "kdb_product_tag"
        assert junction.source_fk_column == "product_id"
        assert junction.target_fk_column == "tag_id"

    def test_junction_table_to_dict(self):
        """Test junction table to_dict method."""
        junction = JunctionTable(
            id="junction-id",
            relationship_id="rel-id",
            table_name="kdb_product_tag",
            source_fk_column="product_id",
            target_fk_column="tag_id",
        )
        result = junction.to_dict()
        assert result["id"] == "junction-id"
        assert result["table_name"] == "kdb_product_tag"
        assert result["source_fk_column"] == "product_id"
        assert result["target_fk_column"] == "tag_id"


class TestRelationshipInfo:
    """Test RelationshipInfo type."""

    def test_relationship_info_creation(self):
        """Test creating a RelationshipInfo."""
        info = RelationshipInfo(
            name="customer",
            target_entity="Customer",
            relationship_type="many_to_one",
            foreign_key_field="customer_id",
            inverse_name="orders",
            on_delete="SET_NULL",
            on_update="CASCADE",
            description="Order belongs to a customer",
        )
        assert info.name == "customer"
        assert info.target_entity == "Customer"
        assert info.relationship_type == "many_to_one"
        assert info.foreign_key_field == "customer_id"

    def test_relationship_info_model_dump(self):
        """Test RelationshipInfo serialization."""
        info = RelationshipInfo(
            name="customer",
            target_entity="Customer",
            relationship_type="many_to_one",
            on_delete="CASCADE",
            on_update="CASCADE",
        )
        result = info.model_dump()
        assert result["name"] == "customer"
        assert result["target_entity"] == "Customer"
        assert result["on_delete"] == "CASCADE"
