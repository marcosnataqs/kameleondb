"""Tests for storage-aware schema context generation.

Tests the SchemaContextBuilder's ability to generate correct SQL access
patterns and JOIN hints based on entity storage modes (shared vs dedicated).
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

from kameleondb.query.context import SchemaContextBuilder


def _make_mock_db(dialect: str, schema: dict) -> MagicMock:
    """Create a mock KameleonDB with given dialect and schema."""
    db = MagicMock()
    db._connection = MagicMock()
    type(db._connection).dialect = PropertyMock(return_value=dialect)
    db.describe.return_value = schema
    return db


def _shared_entity(
    name: str,
    entity_id: str = "ent-001",
    fields: list | None = None,
    relationships: list | None = None,
) -> dict:
    """Build a shared entity info dict."""
    return {
        "id": entity_id,
        "name": name,
        "description": f"{name} entity",
        "storage_mode": "shared",
        "dedicated_table_name": None,
        "fields": fields or [],
        "relationships": relationships or [],
        "record_count": 10,
    }


def _dedicated_entity(
    name: str,
    table_name: str,
    entity_id: str = "ent-002",
    fields: list | None = None,
    relationships: list | None = None,
) -> dict:
    """Build a dedicated entity info dict."""
    return {
        "id": entity_id,
        "name": name,
        "description": f"{name} entity",
        "storage_mode": "dedicated",
        "dedicated_table_name": table_name,
        "fields": fields or [],
        "relationships": relationships or [],
        "record_count": 100,
    }


def _field(name: str, field_type: str = "string") -> dict:
    """Build a field info dict."""
    return {
        "name": name,
        "type": field_type,
        "description": None,
        "required": False,
        "unique": False,
        "indexed": False,
    }


def _relationship(
    name: str,
    target: str,
    fk_field: str,
    rel_type: str = "many_to_one",
) -> dict:
    """Build a relationship info dict."""
    return {
        "name": name,
        "target_entity": target,
        "relationship_type": rel_type,
        "foreign_key_field": fk_field,
        "description": None,
    }


class TestEntityContext:
    """Test _build_entity_context for shared and dedicated entities."""

    def test_shared_entity_uses_kdb_records(self) -> None:
        """Shared entities should use kdb_records as table_name."""
        entity = _shared_entity("Contact", fields=[_field("name")])
        db = _make_mock_db("sqlite", {"entities": {"Contact": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder._build_entity_context("Contact", entity)

        assert ctx["table_name"] == "kdb_records"
        assert ctx["storage_mode"] == "shared"

    def test_dedicated_entity_uses_own_table(self) -> None:
        """Dedicated entities should use their dedicated table name."""
        entity = _dedicated_entity("Customer", "ded_customer", fields=[_field("name")])
        db = _make_mock_db("sqlite", {"entities": {"Customer": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder._build_entity_context("Customer", entity)

        assert ctx["table_name"] == "ded_customer"
        assert ctx["storage_mode"] == "dedicated"

    def test_shared_entity_json_access_sqlite(self) -> None:
        """Shared entity fields should use json_extract on SQLite."""
        entity = _shared_entity("Contact", fields=[_field("name"), _field("age", "int")])
        db = _make_mock_db("sqlite", {"entities": {"Contact": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder._build_entity_context("Contact", entity)

        fields_by_name = {f["name"]: f for f in ctx["fields"]}
        assert fields_by_name["name"]["sql_access"] == "json_extract(data, '$.name')"
        assert fields_by_name["age"]["sql_access"] == "CAST(json_extract(data, '$.age') AS INTEGER)"

    def test_shared_entity_json_access_postgresql(self) -> None:
        """Shared entity fields should use JSONB operators on PostgreSQL."""
        entity = _shared_entity("Contact", fields=[_field("name"), _field("age", "int")])
        db = _make_mock_db("postgresql", {"entities": {"Contact": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder._build_entity_context("Contact", entity)

        fields_by_name = {f["name"]: f for f in ctx["fields"]}
        assert fields_by_name["name"]["sql_access"] == "data->>'name'"
        assert fields_by_name["age"]["sql_access"] == "(data->>'age')::int"

    def test_dedicated_entity_direct_column_access(self) -> None:
        """Dedicated entity fields should use direct column names."""
        entity = _dedicated_entity(
            "Customer", "ded_customer", fields=[_field("name"), _field("age", "int")]
        )
        db = _make_mock_db("sqlite", {"entities": {"Customer": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder._build_entity_context("Customer", entity)

        fields_by_name = {f["name"]: f for f in ctx["fields"]}
        assert fields_by_name["name"]["sql_access"] == "name"
        assert fields_by_name["age"]["sql_access"] == "age"

    def test_dedicated_entity_direct_column_access_postgresql(self) -> None:
        """Dedicated entity fields should use direct column names on PostgreSQL too."""
        entity = _dedicated_entity(
            "Customer", "ded_customer", fields=[_field("email"), _field("revenue", "float")]
        )
        db = _make_mock_db("postgresql", {"entities": {"Customer": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder._build_entity_context("Customer", entity)

        fields_by_name = {f["name"]: f for f in ctx["fields"]}
        assert fields_by_name["email"]["sql_access"] == "email"
        assert fields_by_name["revenue"]["sql_access"] == "revenue"

    def test_shared_entity_has_storage_notes(self) -> None:
        """Shared entities should have storage notes mentioning entity_id."""
        entity = _shared_entity("Contact", entity_id="abc-123")
        db = _make_mock_db("sqlite", {"entities": {"Contact": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder._build_entity_context("Contact", entity)

        assert "storage_notes" in ctx
        assert "kdb_records" in ctx["storage_notes"]
        assert "entity_id" in ctx["storage_notes"]

    def test_dedicated_entity_has_storage_notes(self) -> None:
        """Dedicated entities should have storage notes about direct access."""
        entity = _dedicated_entity("Customer", "ded_customer")
        db = _make_mock_db("sqlite", {"entities": {"Customer": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder._build_entity_context("Customer", entity)

        assert "storage_notes" in ctx
        assert "ded_customer" in ctx["storage_notes"]
        assert "no JSON extraction" in ctx["storage_notes"]


class TestJoinHints:
    """Test storage-aware JOIN hint generation."""

    def test_shared_to_shared_sqlite(self) -> None:
        """shared → shared JOIN on SQLite."""
        order = _shared_entity(
            "Order",
            entity_id="ent-order",
            relationships=[_relationship("customer", "Customer", "customer_id")],
        )
        customer = _shared_entity("Customer", entity_id="ent-cust")
        schema = {"entities": {"Order": order, "Customer": customer}}
        db = _make_mock_db("sqlite", schema)
        builder = SchemaContextBuilder(db)

        rels = builder._build_relationships(schema["entities"])

        assert len(rels) == 1
        hint = rels[0]["join_hint"]
        assert "JOIN kdb_records customer" in hint
        assert "json_extract(order.data, '$.customer_id')" in hint
        assert "customer.id" in hint

    def test_shared_to_shared_postgresql(self) -> None:
        """shared → shared JOIN on PostgreSQL."""
        order = _shared_entity(
            "Order",
            entity_id="ent-order",
            relationships=[_relationship("customer", "Customer", "customer_id")],
        )
        customer = _shared_entity("Customer", entity_id="ent-cust")
        schema = {"entities": {"Order": order, "Customer": customer}}
        db = _make_mock_db("postgresql", schema)
        builder = SchemaContextBuilder(db)

        rels = builder._build_relationships(schema["entities"])

        hint = rels[0]["join_hint"]
        assert "JOIN kdb_records customer" in hint
        assert "order.data->>'customer_id'" in hint
        assert "customer.id::text" in hint

    def test_shared_to_dedicated_sqlite(self) -> None:
        """shared → dedicated JOIN on SQLite."""
        order = _shared_entity(
            "Order",
            entity_id="ent-order",
            relationships=[_relationship("customer", "Customer", "customer_id")],
        )
        customer = _dedicated_entity("Customer", "ded_customer", entity_id="ent-cust")
        schema = {"entities": {"Order": order, "Customer": customer}}
        db = _make_mock_db("sqlite", schema)
        builder = SchemaContextBuilder(db)

        rels = builder._build_relationships(schema["entities"])

        hint = rels[0]["join_hint"]
        assert "JOIN ded_customer customer" in hint
        assert "json_extract(order.data, '$.customer_id')" in hint
        assert "storage_note" in rels[0]
        assert "Cross-storage" in rels[0]["storage_note"]

    def test_shared_to_dedicated_postgresql(self) -> None:
        """shared → dedicated JOIN on PostgreSQL."""
        order = _shared_entity(
            "Order",
            entity_id="ent-order",
            relationships=[_relationship("customer", "Customer", "customer_id")],
        )
        customer = _dedicated_entity("Customer", "ded_customer", entity_id="ent-cust")
        schema = {"entities": {"Order": order, "Customer": customer}}
        db = _make_mock_db("postgresql", schema)
        builder = SchemaContextBuilder(db)

        rels = builder._build_relationships(schema["entities"])

        hint = rels[0]["join_hint"]
        assert "JOIN ded_customer customer" in hint
        assert "order.data->>'customer_id'" in hint

    def test_dedicated_to_shared_sqlite(self) -> None:
        """dedicated → shared JOIN on SQLite."""
        order = _dedicated_entity(
            "Order",
            "ded_order",
            entity_id="ent-order",
            relationships=[_relationship("customer", "Customer", "customer_id")],
        )
        customer = _shared_entity("Customer", entity_id="ent-cust")
        schema = {"entities": {"Order": order, "Customer": customer}}
        db = _make_mock_db("sqlite", schema)
        builder = SchemaContextBuilder(db)

        rels = builder._build_relationships(schema["entities"])

        hint = rels[0]["join_hint"]
        assert "JOIN kdb_records customer" in hint
        assert "order.customer_id" in hint
        assert "storage_note" in rels[0]

    def test_dedicated_to_dedicated_sqlite(self) -> None:
        """dedicated → dedicated JOIN on SQLite (standard SQL)."""
        order = _dedicated_entity(
            "Order",
            "ded_order",
            entity_id="ent-order",
            relationships=[_relationship("customer", "Customer", "customer_id")],
        )
        customer = _dedicated_entity("Customer", "ded_customer", entity_id="ent-cust")
        schema = {"entities": {"Order": order, "Customer": customer}}
        db = _make_mock_db("sqlite", schema)
        builder = SchemaContextBuilder(db)

        rels = builder._build_relationships(schema["entities"])

        hint = rels[0]["join_hint"]
        assert "JOIN ded_customer customer" in hint
        assert "order.customer_id" in hint
        # No cross-storage note for same storage mode
        assert "storage_note" not in rels[0]

    def test_dedicated_to_dedicated_postgresql(self) -> None:
        """dedicated → dedicated JOIN on PostgreSQL (standard SQL)."""
        order = _dedicated_entity(
            "Order",
            "ded_order",
            entity_id="ent-order",
            relationships=[_relationship("customer", "Customer", "customer_id")],
        )
        customer = _dedicated_entity("Customer", "ded_customer", entity_id="ent-cust")
        schema = {"entities": {"Order": order, "Customer": customer}}
        db = _make_mock_db("postgresql", schema)
        builder = SchemaContextBuilder(db)

        rels = builder._build_relationships(schema["entities"])

        hint = rels[0]["join_hint"]
        assert "JOIN ded_customer customer" in hint
        assert "order.customer_id" in hint
        assert "storage_note" not in rels[0]

    def test_target_not_in_filtered_set(self) -> None:
        """JOIN should work even if target entity is not in the filtered set."""
        order = _shared_entity(
            "Order",
            entity_id="ent-order",
            relationships=[_relationship("customer", "Customer", "customer_id")],
        )
        # Customer exists in full schema but not in filtered set
        customer = _shared_entity("Customer", entity_id="ent-cust")
        full_schema = {"entities": {"Order": order, "Customer": customer}}
        db = _make_mock_db("sqlite", full_schema)
        builder = SchemaContextBuilder(db)

        # Only pass Order in filtered set
        rels = builder._build_relationships({"Order": order})

        assert len(rels) == 1
        assert rels[0]["join_hint"] is not None
        assert "customer" in rels[0]["join_hint"]


class TestBuildContext:
    """Test the full build_context output."""

    def test_context_includes_storage_modes_info(self) -> None:
        """Full context should document both storage modes."""
        entity = _shared_entity("Contact", fields=[_field("name")])
        db = _make_mock_db("sqlite", {"entities": {"Contact": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder.build_context()

        assert "storage_modes" in ctx["storage_info"]
        assert "shared" in ctx["storage_info"]["storage_modes"]
        assert "dedicated" in ctx["storage_info"]["storage_modes"]

    def test_context_includes_join_patterns(self) -> None:
        """Full context should document all JOIN pattern types."""
        entity = _shared_entity("Contact", fields=[_field("name")])
        db = _make_mock_db("sqlite", {"entities": {"Contact": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder.build_context()

        patterns = ctx["storage_info"]["join_patterns"]
        assert "shared_to_shared" in patterns
        assert "shared_to_dedicated" in patterns
        assert "dedicated_to_shared" in patterns
        assert "dedicated_to_dedicated" in patterns

    def test_guidelines_mention_storage_mode(self) -> None:
        """Guidelines should tell LLMs to check storage_mode."""
        entity = _shared_entity("Contact", fields=[_field("name")])
        db = _make_mock_db("sqlite", {"entities": {"Contact": entity}})
        builder = SchemaContextBuilder(db)

        ctx = builder.build_context()

        guidelines_text = " ".join(ctx["guidelines"])
        assert "storage_mode" in guidelines_text
        assert "dedicated" in guidelines_text.lower()

    def test_mixed_storage_context(self) -> None:
        """Context with both shared and dedicated entities."""
        order = _shared_entity(
            "Order",
            entity_id="ent-order",
            fields=[_field("total", "float"), _field("customer_id")],
            relationships=[_relationship("customer", "Customer", "customer_id")],
        )
        customer = _dedicated_entity(
            "Customer",
            "ded_customer",
            entity_id="ent-cust",
            fields=[_field("name"), _field("email")],
        )
        schema = {"entities": {"Order": order, "Customer": customer}}
        db = _make_mock_db("sqlite", schema)
        builder = SchemaContextBuilder(db)

        ctx = builder.build_context()

        entities_by_name = {e["name"]: e for e in ctx["entities"]}
        # Order should use JSON access
        assert entities_by_name["Order"]["table_name"] == "kdb_records"
        assert "json_extract" in entities_by_name["Order"]["fields"][0]["sql_access"]
        # Customer should use direct columns
        assert entities_by_name["Customer"]["table_name"] == "ded_customer"
        assert entities_by_name["Customer"]["fields"][0]["sql_access"] == "name"
        # Relationship should have cross-storage hint
        assert len(ctx["relationships"]) == 1
        assert "ded_customer" in ctx["relationships"][0]["join_hint"]


class TestHelperMethods:
    """Test helper methods."""

    def test_resolve_table_name_shared(self) -> None:
        """Shared entity resolves to kdb_records."""
        entity = _shared_entity("Contact")
        db = _make_mock_db("sqlite", {"entities": {}})
        builder = SchemaContextBuilder(db)

        assert builder._resolve_table_name(entity) == "kdb_records"

    def test_resolve_table_name_dedicated(self) -> None:
        """Dedicated entity resolves to its dedicated table."""
        entity = _dedicated_entity("Customer", "ded_customer")
        db = _make_mock_db("sqlite", {"entities": {}})
        builder = SchemaContextBuilder(db)

        assert builder._resolve_table_name(entity) == "ded_customer"

    def test_resolve_table_name_dedicated_without_table(self) -> None:
        """Dedicated entity without table name falls back to kdb_records."""
        entity = {
            "storage_mode": "dedicated",
            "dedicated_table_name": None,
        }
        db = _make_mock_db("sqlite", {"entities": {}})
        builder = SchemaContextBuilder(db)

        assert builder._resolve_table_name(entity) == "kdb_records"

    def test_is_dedicated_true(self) -> None:
        """Dedicated entity with table name is detected."""
        entity = _dedicated_entity("Customer", "ded_customer")
        db = _make_mock_db("sqlite", {"entities": {}})
        builder = SchemaContextBuilder(db)

        assert builder._is_dedicated(entity) is True

    def test_is_dedicated_false_shared(self) -> None:
        """Shared entity is not dedicated."""
        entity = _shared_entity("Contact")
        db = _make_mock_db("sqlite", {"entities": {}})
        builder = SchemaContextBuilder(db)

        assert builder._is_dedicated(entity) is False

    def test_is_dedicated_false_no_table(self) -> None:
        """Dedicated entity without table name is not treated as dedicated."""
        entity = {"storage_mode": "dedicated", "dedicated_table_name": None}
        db = _make_mock_db("sqlite", {"entities": {}})
        builder = SchemaContextBuilder(db)

        assert builder._is_dedicated(entity) is False
