"""Tests for Spec 007: Many-to-Many Relationships.

Tests junction table creation and link/unlink operations.
"""

import pytest

from kameleondb import KameleonDB


@pytest.fixture
def db():
    """Create a test database."""
    db = KameleonDB("sqlite:///:memory:")
    yield db
    db.close()


@pytest.fixture
def db_with_entities(db):
    """Set up Product and Tag entities for many-to-many testing."""
    db.create_entity(
        "Product",
        fields=[
            {"name": "name", "type": "string"},
            {"name": "price", "type": "float"},
        ],
    )
    db.create_entity(
        "Tag",
        fields=[
            {"name": "name", "type": "string"},
        ],
    )
    return db


class TestJunctionTableCreation:
    """Test junction table auto-creation."""

    def test_many_to_many_creates_junction_table(self, db_with_entities):
        """Creating many-to-many relationship creates junction table."""
        db = db_with_entities

        # Create many-to-many relationship
        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
            on_delete="CASCADE",
        )

        # Verify junction table exists
        from kameleondb.storage.dedicated import DedicatedTableManager

        manager = DedicatedTableManager(db._connection.engine)
        assert manager.table_exists("kdb_product_tag")

    def test_junction_table_has_correct_structure(self, db_with_entities):
        """Junction table has correct columns."""
        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
        )

        # Query junction table columns
        from sqlalchemy import text

        with db._connection.engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(kdb_product_tag)"))
            columns = {row[1] for row in result.fetchall()}

        assert "id" in columns
        assert "product_id" in columns
        assert "tag_id" in columns
        assert "created_at" in columns


class TestLinkOperations:
    """Test link/unlink operations."""

    def test_link_creates_junction_entry(self, db_with_entities):
        """link() creates entry in junction table."""
        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
        )

        product = db.entity("Product")
        tag = db.entity("Tag")

        product_id = product.insert({"name": "Widget", "price": 9.99})
        tag_id = tag.insert({"name": "Featured"})

        # Link product to tag
        result = product.link("tags", product_id, tag_id)
        assert result is True

        # Verify junction entry exists
        linked = product.get_linked("tags", product_id)
        assert tag_id in linked

    def test_link_is_idempotent(self, db_with_entities):
        """Duplicate link returns False (already exists)."""
        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
        )

        product = db.entity("Product")
        tag = db.entity("Tag")

        product_id = product.insert({"name": "Widget", "price": 9.99})
        tag_id = tag.insert({"name": "Featured"})

        # First link succeeds
        assert product.link("tags", product_id, tag_id) is True

        # Second link returns False (already exists)
        assert product.link("tags", product_id, tag_id) is False

        # Only one link exists
        assert len(product.get_linked("tags", product_id)) == 1

    def test_unlink_removes_junction_entry(self, db_with_entities):
        """unlink() removes entry from junction table."""
        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
        )

        product = db.entity("Product")
        tag = db.entity("Tag")

        product_id = product.insert({"name": "Widget", "price": 9.99})
        tag_id = tag.insert({"name": "Featured"})

        product.link("tags", product_id, tag_id)
        assert len(product.get_linked("tags", product_id)) == 1

        # Unlink
        result = product.unlink("tags", product_id, tag_id)
        assert result is True

        # Link is gone
        assert len(product.get_linked("tags", product_id)) == 0

    def test_unlink_nonexistent_returns_false(self, db_with_entities):
        """unlink() returns False when link doesn't exist."""
        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
        )

        product = db.entity("Product")
        tag = db.entity("Tag")

        product_id = product.insert({"name": "Widget", "price": 9.99})
        tag_id = tag.insert({"name": "Featured"})

        # Try to unlink without linking first
        result = product.unlink("tags", product_id, tag_id)
        assert result is False

    def test_unlink_all_removes_all_links(self, db_with_entities):
        """unlink_all() removes all links for a record."""
        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
        )

        product = db.entity("Product")
        tag = db.entity("Tag")

        product_id = product.insert({"name": "Widget", "price": 9.99})
        tag1_id = tag.insert({"name": "Featured"})
        tag2_id = tag.insert({"name": "Sale"})
        tag3_id = tag.insert({"name": "New"})

        # Link to all tags
        product.link("tags", product_id, tag1_id)
        product.link("tags", product_id, tag2_id)
        product.link("tags", product_id, tag3_id)
        assert len(product.get_linked("tags", product_id)) == 3

        # Unlink all
        count = product.unlink_all("tags", product_id)
        assert count == 3
        assert len(product.get_linked("tags", product_id)) == 0


class TestBulkOperations:
    """Test bulk link/unlink operations."""

    def test_link_many(self, db_with_entities):
        """link_many() creates multiple links."""
        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
        )

        product = db.entity("Product")
        tag = db.entity("Tag")

        product_id = product.insert({"name": "Widget", "price": 9.99})
        tag_ids = [
            tag.insert({"name": "Featured"}),
            tag.insert({"name": "Sale"}),
            tag.insert({"name": "New"}),
        ]

        # Bulk link
        count = product.link_many("tags", product_id, tag_ids)
        assert count == 3
        assert len(product.get_linked("tags", product_id)) == 3

    def test_unlink_many(self, db_with_entities):
        """unlink_many() removes multiple links."""
        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
        )

        product = db.entity("Product")
        tag = db.entity("Tag")

        product_id = product.insert({"name": "Widget", "price": 9.99})
        tag_ids = [
            tag.insert({"name": "Featured"}),
            tag.insert({"name": "Sale"}),
            tag.insert({"name": "New"}),
        ]

        product.link_many("tags", product_id, tag_ids)
        assert len(product.get_linked("tags", product_id)) == 3

        # Bulk unlink first two
        count = product.unlink_many("tags", product_id, tag_ids[:2])
        assert count == 2
        assert len(product.get_linked("tags", product_id)) == 1


class TestCascadeDelete:
    """Test cascade behavior for many-to-many."""

    def test_delete_source_removes_junction_entries(self, db_with_entities):
        """Deleting source record removes its junction entries."""
        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
            on_delete="CASCADE",
        )

        product = db.entity("Product")
        tag = db.entity("Tag")

        product_id = product.insert({"name": "Widget", "price": 9.99})
        tag1_id = tag.insert({"name": "Featured"})
        tag2_id = tag.insert({"name": "Sale"})

        product.link("tags", product_id, tag1_id)
        product.link("tags", product_id, tag2_id)
        assert len(product.get_linked("tags", product_id)) == 2

        # Verify junction entries exist before delete
        from sqlalchemy import text

        with db._connection.engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM kdb_product_tag WHERE product_id = :pid"),
                {"pid": product_id},
            )
            assert result.scalar() == 2

        # Delete product
        product.delete(product_id)

        # Tags still exist
        assert tag.find_by_id(tag1_id) is not None
        assert tag.find_by_id(tag2_id) is not None

        # Junction entries are gone (this was the bug!)
        with db._connection.engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM kdb_product_tag WHERE product_id = :pid"),
                {"pid": product_id},
            )
            assert result.scalar() == 0

    def test_delete_target_removes_junction_entries(self, db_with_entities):
        """Deleting target record removes junction entries pointing to it."""
        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
            on_delete="CASCADE",
        )

        product = db.entity("Product")
        tag = db.entity("Tag")

        product_id = product.insert({"name": "Widget", "price": 9.99})
        tag_id = tag.insert({"name": "Featured"})

        product.link("tags", product_id, tag_id)
        assert len(product.get_linked("tags", product_id)) == 1

        # Delete tag
        tag.delete(tag_id)

        # Product still exists
        assert product.find_by_id(product_id) is not None

        # Junction entry is gone
        assert len(product.get_linked("tags", product_id)) == 0


class TestInvalidOperations:
    """Test error handling."""

    def test_link_non_many_to_many_raises(self, db_with_entities):
        """link() on non-many-to-many relationship raises ValueError."""
        db = db_with_entities

        # Create a many-to-one relationship
        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="category",
            target_entity_name="Tag",  # Using Tag as category for simplicity
            relationship_type="many_to_one",
        )

        product = db.entity("Product")
        product_id = product.insert({"name": "Widget", "price": 9.99})

        with pytest.raises(ValueError) as exc_info:
            product.link("category", product_id, "some-id")

        assert "not a many-to-many relationship" in str(exc_info.value)

    def test_link_nonexistent_relationship_raises(self, db_with_entities):
        """link() on nonexistent relationship raises ValueError."""
        db = db_with_entities

        product = db.entity("Product")
        product_id = product.insert({"name": "Widget", "price": 9.99})

        with pytest.raises(ValueError) as exc_info:
            product.link("nonexistent", product_id, "some-id")

        assert "not found" in str(exc_info.value)

    def test_link_nonexistent_source_raises(self, db_with_entities):
        """link() with nonexistent source record raises RecordNotFoundError."""
        from kameleondb.exceptions import RecordNotFoundError

        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
        )

        product = db.entity("Product")
        tag = db.entity("Tag")
        tag_id = tag.insert({"name": "Featured"})

        with pytest.raises(RecordNotFoundError):
            product.link("tags", "nonexistent-product-id", tag_id)

    def test_link_nonexistent_target_raises(self, db_with_entities):
        """link() with nonexistent target record raises RecordNotFoundError."""
        from kameleondb.exceptions import RecordNotFoundError

        db = db_with_entities

        db._schema_engine.add_relationship(
            source_entity_name="Product",
            name="tags",
            target_entity_name="Tag",
            relationship_type="many_to_many",
        )

        product = db.entity("Product")
        product_id = product.insert({"name": "Widget", "price": 9.99})

        with pytest.raises(RecordNotFoundError):
            product.link("tags", product_id, "nonexistent-tag-id")
