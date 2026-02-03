"""Tests for core types."""

from kameleondb.core.types import (
    EntityInfo,
    EntitySpec,
    FieldInfo,
    FieldSpec,
    FieldType,
    QueryResult,
    SchemaInfo,
)


class TestFieldType:
    """Tests for FieldType enum."""

    def test_all_types_exist(self):
        """All documented field types should exist."""
        expected = ["string", "text", "int", "float", "bool", "datetime", "json", "uuid"]
        assert FieldType.values() == expected

    def test_string_values(self):
        """Field types should have correct string values."""
        assert FieldType.STRING.value == "string"
        assert FieldType.INT.value == "int"
        assert FieldType.BOOL.value == "bool"

    def test_from_string(self):
        """Can create FieldType from string."""
        assert FieldType("string") == FieldType.STRING
        assert FieldType("int") == FieldType.INT


class TestFieldSpec:
    """Tests for FieldSpec model."""

    def test_minimal_spec(self):
        """Can create spec with just name."""
        spec = FieldSpec(name="email")
        assert spec.name == "email"
        assert spec.type == FieldType.STRING
        assert spec.required is False
        assert spec.unique is False
        assert spec.indexed is False
        assert spec.default is None

    def test_full_spec(self):
        """Can create spec with all fields."""
        spec = FieldSpec(
            name="email",
            type=FieldType.STRING,
            required=True,
            unique=True,
            indexed=True,
            default="unknown@example.com",
            description="Contact email address",
        )
        assert spec.name == "email"
        assert spec.type == FieldType.STRING
        assert spec.required is True
        assert spec.unique is True
        assert spec.indexed is True
        assert spec.default == "unknown@example.com"
        assert spec.description == "Contact email address"

    def test_from_dict(self):
        """Can create spec from dict (agent-friendly)."""
        data = {"name": "first_name", "type": "string", "required": True}
        spec = FieldSpec(**data)
        assert spec.name == "first_name"
        assert spec.type == FieldType.STRING
        assert spec.required is True


class TestEntitySpec:
    """Tests for EntitySpec model."""

    def test_minimal_spec(self):
        """Can create spec with just name."""
        spec = EntitySpec(name="Contact")
        assert spec.name == "Contact"
        assert spec.fields == []
        assert spec.description is None

    def test_with_fields(self):
        """Can create spec with fields."""
        spec = EntitySpec(
            name="Contact",
            fields=[
                FieldSpec(name="first_name", type=FieldType.STRING, required=True),
                FieldSpec(name="email", type=FieldType.STRING, unique=True),
            ],
            description="Contact information",
        )
        assert spec.name == "Contact"
        assert len(spec.fields) == 2
        assert spec.fields[0].name == "first_name"
        assert spec.fields[1].name == "email"


class TestFieldInfo:
    """Tests for FieldInfo output model."""

    def test_all_fields(self):
        """FieldInfo has all expected fields."""
        info = FieldInfo(
            name="email",
            type="string",
            required=True,
            unique=True,
            indexed=True,
            default=None,
            description="Email address",
        )
        assert info.name == "email"
        assert info.type == "string"
        assert info.required is True


class TestEntityInfo:
    """Tests for EntityInfo output model."""

    def test_all_fields(self):
        """EntityInfo has all expected fields."""
        info = EntityInfo(
            name="Contact",
            table_name="kdb_contact",
            description="Contact info",
            fields=[
                FieldInfo(
                    name="email",
                    type="string",
                    required=False,
                    unique=False,
                    indexed=False,
                    default=None,
                    description=None,
                )
            ],
        )
        assert info.name == "Contact"
        assert info.table_name == "kdb_contact"
        assert len(info.fields) == 1

    def test_model_dump(self):
        """EntityInfo can be serialized to dict."""
        info = EntityInfo(
            name="Contact",
            table_name="kdb_contact",
            description=None,
            fields=[],
        )
        data = info.model_dump()
        assert isinstance(data, dict)
        assert data["name"] == "Contact"


class TestSchemaInfo:
    """Tests for SchemaInfo output model."""

    def test_schema_info(self):
        """SchemaInfo has correct structure."""
        entity_info = EntityInfo(
            name="Contact",
            table_name="kdb_contact",
            description=None,
            fields=[],
        )
        info = SchemaInfo(
            entities={"Contact": entity_info},
            total_entities=1,
            total_fields=0,
        )
        assert info.total_entities == 1
        assert "Contact" in info.entities


class TestQueryResult:
    """Tests for QueryResult model."""

    def test_query_result(self):
        """QueryResult has correct structure."""
        result = QueryResult(
            records=[{"id": "123", "email": "test@example.com"}],
            total_count=1,
            limit=10,
            offset=0,
        )
        assert len(result.records) == 1
        assert result.total_count == 1
        assert result.limit == 10
        assert result.offset == 0
