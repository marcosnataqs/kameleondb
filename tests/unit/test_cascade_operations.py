"""Tests for Spec 006: Cascading Operations.

Tests cascade behavior for on_delete actions (CASCADE, SET_NULL, RESTRICT).
"""

import pytest

from kameleondb import KameleonDB
from kameleondb.exceptions import RestrictDeleteError


@pytest.fixture
def db():
    """Create a test database with relationships."""
    db = KameleonDB("sqlite:///:memory:")
    yield db
    db.close()


@pytest.fixture
def db_with_relationships(db):
    """Set up Customer -> Order relationship."""
    # Create Customer entity
    db.create_entity(
        "Customer",
        fields=[
            {"name": "name", "type": "string"},
            {"name": "email", "type": "string"},
        ],
    )

    # Create Order entity with FK to Customer
    db.create_entity(
        "Order",
        fields=[
            {"name": "total", "type": "float"},
            {"name": "status", "type": "string"},
        ],
    )

    return db


class TestRestrictDeleteError:
    """Test RestrictDeleteError exception."""

    def test_error_message(self):
        """Test error message is actionable."""
        error = RestrictDeleteError("Customer", "Order", 5)
        assert "Cannot delete Customer" in str(error)
        assert "5 related Order" in str(error)
        assert "Delete related records first" in str(error)

    def test_error_context(self):
        """Test error context includes useful info."""
        error = RestrictDeleteError("Customer", "Order", 5)
        assert error.context["entity_name"] == "Customer"
        assert error.context["related_entity"] == "Order"
        assert error.context["related_count"] == 5
        assert "suggestion" in error.context


class TestCascadeDelete:
    """Test CASCADE on_delete behavior."""

    def test_cascade_deletes_related_records(self, db_with_relationships):
        """When parent is deleted, CASCADE deletes children."""
        db = db_with_relationships

        # Add relationship with CASCADE
        db._schema_engine.add_relationship(
            source_entity_name="Order",
            name="customer",
            target_entity_name="Customer",
            relationship_type="many_to_one",
            on_delete="CASCADE",
        )

        # Create customer and orders
        customer = db.entity("Customer")
        order = db.entity("Order")

        customer_id = customer.insert({"name": "John", "email": "john@test.com"})
        order1_id = order.insert({"total": 100.0, "status": "pending", "customer_id": customer_id})
        order2_id = order.insert({"total": 200.0, "status": "shipped", "customer_id": customer_id})

        # Verify orders exist
        assert order.find_by_id(order1_id) is not None
        assert order.find_by_id(order2_id) is not None

        # Delete customer - should cascade to orders
        result = customer.delete(customer_id)
        assert result is True

        # Orders should be deleted (soft delete)
        assert order.find_by_id(order1_id) is None
        assert order.find_by_id(order2_id) is None

    def test_cascade_without_related_records(self, db_with_relationships):
        """Delete works fine when no related records exist."""
        db = db_with_relationships

        # Add relationship with CASCADE
        db._schema_engine.add_relationship(
            source_entity_name="Order",
            name="customer",
            target_entity_name="Customer",
            relationship_type="many_to_one",
            on_delete="CASCADE",
        )

        # Create customer with no orders
        customer = db.entity("Customer")
        customer_id = customer.insert({"name": "Jane", "email": "jane@test.com"})

        # Delete should succeed
        result = customer.delete(customer_id)
        assert result is True
        assert customer.find_by_id(customer_id) is None


class TestSetNullDelete:
    """Test SET_NULL on_delete behavior."""

    def test_set_null_clears_fk_field(self, db_with_relationships):
        """When parent is deleted, SET_NULL clears FK on children."""
        db = db_with_relationships

        # Add relationship with SET_NULL
        db._schema_engine.add_relationship(
            source_entity_name="Order",
            name="customer",
            target_entity_name="Customer",
            relationship_type="many_to_one",
            on_delete="SET_NULL",
        )

        # Create customer and orders
        customer = db.entity("Customer")
        order = db.entity("Order")

        customer_id = customer.insert({"name": "John", "email": "john@test.com"})
        order_id = order.insert({"total": 100.0, "status": "pending", "customer_id": customer_id})

        # Verify order has customer_id
        order_data = order.find_by_id(order_id)
        assert order_data["customer_id"] == customer_id

        # Delete customer - should set FK to null
        customer.delete(customer_id)

        # Order should still exist but with null customer_id
        order_data = order.find_by_id(order_id)
        assert order_data is not None
        # FK field should be removed/null
        assert order_data.get("customer_id") is None


class TestRestrictDelete:
    """Test RESTRICT on_delete behavior."""

    def test_restrict_blocks_delete_with_related(self, db_with_relationships):
        """RESTRICT prevents deletion when related records exist."""
        db = db_with_relationships

        # Add relationship with RESTRICT
        db._schema_engine.add_relationship(
            source_entity_name="Order",
            name="customer",
            target_entity_name="Customer",
            relationship_type="many_to_one",
            on_delete="RESTRICT",
        )

        # Create customer and order
        customer = db.entity("Customer")
        order = db.entity("Order")

        customer_id = customer.insert({"name": "John", "email": "john@test.com"})
        order.insert({"total": 100.0, "status": "pending", "customer_id": customer_id})

        # Delete should raise RestrictDeleteError
        with pytest.raises(RestrictDeleteError) as exc_info:
            customer.delete(customer_id)

        assert exc_info.value.entity_name == "Customer"
        assert exc_info.value.related_entity == "Order"
        assert exc_info.value.count == 1

    def test_restrict_allows_delete_without_related(self, db_with_relationships):
        """RESTRICT allows deletion when no related records exist."""
        db = db_with_relationships

        # Add relationship with RESTRICT
        db._schema_engine.add_relationship(
            source_entity_name="Order",
            name="customer",
            target_entity_name="Customer",
            relationship_type="many_to_one",
            on_delete="RESTRICT",
        )

        # Create customer with no orders
        customer = db.entity("Customer")
        customer_id = customer.insert({"name": "Jane", "email": "jane@test.com"})

        # Delete should succeed
        result = customer.delete(customer_id)
        assert result is True

    def test_force_bypasses_restrict(self, db_with_relationships):
        """force=True bypasses RESTRICT check."""
        db = db_with_relationships

        # Add relationship with RESTRICT
        db._schema_engine.add_relationship(
            source_entity_name="Order",
            name="customer",
            target_entity_name="Customer",
            relationship_type="many_to_one",
            on_delete="RESTRICT",
        )

        # Create customer and order
        customer = db.entity("Customer")
        order = db.entity("Order")

        customer_id = customer.insert({"name": "John", "email": "john@test.com"})
        order.insert({"total": 100.0, "status": "pending", "customer_id": customer_id})

        # Delete with force=True should succeed
        result = customer.delete(customer_id, force=True)
        assert result is True


class TestCascadeDisabled:
    """Test cascade=False to skip cascade logic."""

    def test_cascade_false_skips_cascade(self, db_with_relationships):
        """cascade=False skips all cascade logic."""
        db = db_with_relationships

        # Add relationship with CASCADE
        db._schema_engine.add_relationship(
            source_entity_name="Order",
            name="customer",
            target_entity_name="Customer",
            relationship_type="many_to_one",
            on_delete="CASCADE",
        )

        # Create customer and order
        customer = db.entity("Customer")
        order = db.entity("Order")

        customer_id = customer.insert({"name": "John", "email": "john@test.com"})
        order_id = order.insert({"total": 100.0, "status": "pending", "customer_id": customer_id})

        # Delete with cascade=False - order should remain
        customer.delete(customer_id, cascade=False)

        # Order should still exist
        assert order.find_by_id(order_id) is not None


class TestGetIncomingRelationships:
    """Test SchemaEngine.get_incoming_relationships()."""

    def test_get_incoming_relationships(self, db_with_relationships):
        """Test retrieving incoming relationships."""
        db = db_with_relationships

        # Add relationship
        db._schema_engine.add_relationship(
            source_entity_name="Order",
            name="customer",
            target_entity_name="Customer",
            relationship_type="many_to_one",
            on_delete="CASCADE",
        )

        # Get incoming relationships for Customer
        incoming = db._schema_engine.get_incoming_relationships("Customer")

        assert len(incoming) == 1
        assert incoming[0]["source_entity"] == "Order"
        assert incoming[0]["target_entity"] == "Customer"
        assert incoming[0]["foreign_key_field"] == "customer_id"
        assert incoming[0]["on_delete"] == "CASCADE"

    def test_get_incoming_relationships_empty(self, db_with_relationships):
        """Test entity with no incoming relationships."""
        db = db_with_relationships

        # Customer has no incoming relationships by default
        incoming = db._schema_engine.get_incoming_relationships("Order")
        assert len(incoming) == 0
