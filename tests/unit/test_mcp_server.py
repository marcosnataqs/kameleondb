"""Unit tests for KameleonDB MCP server integration.

Tests all 22 MCP tools exposed via src/kameleondb/integrations/mcp/server.py.
See GitHub issue #66.

Note: FastMCP tools take typed Python objects directly (not JSON strings).
The MCP framework handles JSON serialization at the transport layer.
"""

from __future__ import annotations

import json
from collections.abc import Generator

import pytest

# Skip entire module if mcp is not installed (optional dependency)
pytest.importorskip("mcp", reason="mcp not installed (install with: pip install kameleondb[mcp])")

from kameleondb import KameleonDB  # noqa: E402
from kameleondb.integrations.mcp import server as mcp_server  # noqa: E402


@pytest.fixture
def db() -> Generator[KameleonDB, None, None]:
    """In-memory SQLite DB for MCP tests."""
    database = KameleonDB("sqlite:///:memory:")
    yield database
    database.close()


@pytest.fixture(autouse=True)
def set_mcp_db(db: KameleonDB) -> Generator[None, None, None]:
    """Inject db into the MCP server global before each test."""
    mcp_server._db = db
    yield
    mcp_server._db = None


# === Helpers ===


def _ok(result: str) -> dict:
    """Parse result and assert no error (None error values are OK)."""
    data = json.loads(result)
    if "error" in data:
        assert data["error"] is None, f"Unexpected error: {data['error']}"
    return data


def _err(result: str) -> dict:
    """Parse result and assert a non-None error is present."""
    data = json.loads(result)
    assert "error" in data and data["error"] is not None, f"Expected error, got: {data}"
    return data


def _create(db: KameleonDB, name: str, fields: list[dict] | None = None) -> None:
    """Helper to create entity with proper field spec."""
    db.create_entity(name, fields=fields)


def _insert(db: KameleonDB, entity: str, data: dict) -> str:
    """Helper to insert and return record id."""
    return db.entity(entity).insert(data)


# === Schema Discovery ===


class TestDescribeTools:
    def test_describe_empty_db(self) -> None:
        result = json.loads(mcp_server.kameleondb_describe())
        assert isinstance(result, dict)

    def test_list_entities_empty(self) -> None:
        result = json.loads(mcp_server.kameleondb_list_entities())
        assert result == []

    def test_describe_entity_not_found(self) -> None:
        _err(mcp_server.kameleondb_describe_entity("NonExistent"))

    def test_describe_entity_exists(self, db: KameleonDB) -> None:
        _create(db, "Product", [{"name": "title", "type": "string"}])
        result = json.loads(mcp_server.kameleondb_describe_entity("Product"))
        assert result.get("name") == "Product"

    def test_list_entities_after_create(self, db: KameleonDB) -> None:
        _create(db, "Product")
        result = json.loads(mcp_server.kameleondb_list_entities())
        assert "Product" in result


# === Entity Management ===


class TestEntityManagement:
    def test_create_entity_with_fields(self) -> None:
        result = mcp_server.kameleondb_create_entity(
            name="Order",
            fields=[
                {"name": "total", "type": "float"},
                {"name": "status", "type": "string"},
            ],
        )
        _ok(result)

    def test_create_entity_minimal(self) -> None:
        _ok(mcp_server.kameleondb_create_entity(name="Tag"))

    def test_drop_entity(self, db: KameleonDB) -> None:
        _create(db, "Temp")
        _ok(mcp_server.kameleondb_drop_entity("Temp"))
        entities = json.loads(mcp_server.kameleondb_list_entities())
        assert "Temp" not in entities

    def test_drop_entity_not_found(self) -> None:
        _err(mcp_server.kameleondb_drop_entity("Ghost"))

    def test_alter_entity_add_field(self, db: KameleonDB) -> None:
        _create(db, "Item", [{"name": "name", "type": "string"}])
        result = mcp_server.kameleondb_alter_entity(
            entity_name="Item",
            add_fields=[{"name": "color", "type": "string"}],
        )
        _ok(result)

    def test_alter_entity_drop_field(self, db: KameleonDB) -> None:
        _create(
            db, "Widget", [{"name": "name", "type": "string"}, {"name": "legacy", "type": "string"}]
        )
        _ok(mcp_server.kameleondb_alter_entity(entity_name="Widget", drop_fields=["legacy"]))


# === CRUD Operations ===


class TestCRUD:
    def test_insert_returns_id(self, db: KameleonDB) -> None:
        _create(db, "Note", [{"name": "title", "type": "string"}])
        result = json.loads(mcp_server.kameleondb_insert("Note", {"title": "Hello"}))
        assert "error" not in result
        assert "id" in result

    def test_find_by_id(self, db: KameleonDB) -> None:
        _create(db, "Note", [{"name": "title", "type": "string"}])
        record_id = _insert(db, "Note", {"title": "test"})
        result = json.loads(mcp_server.kameleondb_find_by_id("Note", record_id))
        assert "error" not in result

    def test_find_by_id_not_found(self, db: KameleonDB) -> None:
        _create(db, "Note", [{"name": "title", "type": "string"}])
        result = json.loads(mcp_server.kameleondb_find_by_id("Note", "99999"))
        # Should return error or null — not crash
        assert result is None or "error" in result

    def test_insert_many(self, db: KameleonDB) -> None:
        _create(db, "Tag", [{"name": "label", "type": "string"}])
        result = json.loads(
            mcp_server.kameleondb_insert_many(
                "Tag", [{"label": "a"}, {"label": "b"}, {"label": "c"}]
            )
        )
        assert "error" not in result

    def test_update(self, db: KameleonDB) -> None:
        _create(db, "Note", [{"name": "title", "type": "string"}])
        record_id = _insert(db, "Note", {"title": "old"})
        result = json.loads(mcp_server.kameleondb_update("Note", record_id, {"title": "new"}))
        assert "error" not in result

    def test_delete(self, db: KameleonDB) -> None:
        _create(db, "Note", [{"name": "title", "type": "string"}])
        record_id = _insert(db, "Note", {"title": "bye"})
        _ok(mcp_server.kameleondb_delete("Note", record_id))

    def test_delete_not_found(self, db: KameleonDB) -> None:
        _create(db, "Note", [{"name": "title", "type": "string"}])
        _err(mcp_server.kameleondb_delete("Note", "99999"))


# === Relationships ===


class TestRelationships:
    def test_add_and_list_relationship(self, db: KameleonDB) -> None:
        _create(db, "Author", [{"name": "name", "type": "string"}])
        _create(db, "Book", [{"name": "title", "type": "string"}])
        _ok(
            mcp_server.kameleondb_add_relationship(
                source_entity="Author",
                name="books",
                target_entity="Book",
                relationship_type="one_to_many",
            )
        )
        rels = json.loads(mcp_server.kameleondb_list_relationships("Author"))
        assert isinstance(rels, list)
        assert any(r.get("name") == "books" for r in rels)

    def test_remove_relationship(self, db: KameleonDB) -> None:
        _create(db, "Author", [{"name": "name", "type": "string"}])
        _create(db, "Book", [{"name": "title", "type": "string"}])
        # Use the MCP tool to add relationship (mirrors real usage)
        mcp_server.kameleondb_add_relationship(
            source_entity="Author",
            name="books",
            target_entity="Book",
            relationship_type="one_to_many",
        )
        _ok(mcp_server.kameleondb_remove_relationship("Author", "books"))

    def test_link_and_unlink(self, db: KameleonDB) -> None:
        _create(db, "Author", [{"name": "name", "type": "string"}])
        _create(db, "Book", [{"name": "title", "type": "string"}])
        mcp_server.kameleondb_add_relationship(
            source_entity="Author",
            name="books",
            target_entity="Book",
            relationship_type="many_to_many",
        )
        a_id = _insert(db, "Author", {"name": "Alice"})
        b_id = _insert(db, "Book", {"title": "KameleonDB Guide"})

        _ok(mcp_server.kameleondb_link("Author", a_id, "books", [b_id]))
        _ok(mcp_server.kameleondb_unlink("Author", a_id, "books", [b_id]))


# === Query & Utility ===


class TestQueryAndUtility:
    def test_execute_sql_select(self) -> None:
        data = _ok(mcp_server.kameleondb_execute_sql("SELECT 1 AS val"))
        # Result may be a list directly or wrapped in a dict with "rows"
        rows = data.get("rows", data) if isinstance(data, dict) else data
        assert isinstance(rows, list)

    def test_execute_sql_invalid(self) -> None:
        result = json.loads(mcp_server.kameleondb_execute_sql("INVALID SQL !!!"))
        assert "error" in result

    def test_get_entity_stats(self, db: KameleonDB) -> None:
        _create(db, "Log", [{"name": "msg", "type": "string"}])
        _insert(db, "Log", {"msg": "hello"})
        _ok(mcp_server.kameleondb_get_entity_stats("Log"))

    def test_get_schema_context(self, db: KameleonDB) -> None:
        _create(db, "Event", [{"name": "name", "type": "string"}])
        result = mcp_server.kameleondb_get_schema_context()
        # Should return valid JSON
        parsed = json.loads(result)
        assert parsed is not None

    def test_get_changelog_all(self, db: KameleonDB) -> None:
        _create(db, "Thing", [{"name": "val", "type": "string"}])
        result = json.loads(mcp_server.kameleondb_get_changelog())
        assert isinstance(result, list)

    def test_get_changelog_filtered(self, db: KameleonDB) -> None:
        _create(db, "Thing", [{"name": "val", "type": "string"}])
        result = json.loads(mcp_server.kameleondb_get_changelog(entity_name="Thing"))
        assert isinstance(result, list)


# === Materialization ===


class TestMaterialization:
    def test_materialize_and_dematerialize(self, db: KameleonDB) -> None:
        _create(
            db, "Cache", [{"name": "key", "type": "string"}, {"name": "value", "type": "string"}]
        )
        _ok(mcp_server.kameleondb_materialize_entity("Cache"))
        _ok(mcp_server.kameleondb_dematerialize_entity("Cache"))

    def test_materialize_not_found(self) -> None:
        _err(mcp_server.kameleondb_materialize_entity("Ghost"))


# === Error Handling ===


class TestErrorHandling:
    def test_no_db_raises(self) -> None:
        mcp_server._db = None
        with pytest.raises(RuntimeError, match="Database not initialized"):
            mcp_server.kameleondb_describe()

    def test_insert_invalid_entity(self) -> None:
        _err(mcp_server.kameleondb_insert("NoSuchEntity", {"x": 1}))

    def test_update_invalid_entity(self) -> None:
        _err(mcp_server.kameleondb_update("NoSuchEntity", "1", {"x": 1}))
