"""Tests for LLM-Native Query Generation (ADR-002)."""

from __future__ import annotations

from kameleondb.query.context import (
    POSTGRESQL_ACCESS_PATTERNS,
    POSTGRESQL_EXAMPLE_QUERIES,
    SQLITE_ACCESS_PATTERNS,
    SQLITE_EXAMPLE_QUERIES,
)
from kameleondb.query.validator import (
    ALLOWED_TABLES,
    QueryType,
    QueryValidator,
    ValidationResult,
)


class TestQueryValidator:
    """Test query validation functionality."""

    def test_valid_select_query(self) -> None:
        """Test that a valid SELECT query passes validation."""
        validator = QueryValidator()
        sql = "SELECT id, data FROM kdb_records WHERE entity_id = 'test'"

        result = validator.validate(sql)

        assert result.valid
        assert result.query_type == QueryType.SELECT
        assert "kdb_records" in result.tables_accessed

    def test_invalid_table_access(self) -> None:
        """Test that access to unauthorized tables is blocked."""
        validator = QueryValidator()
        sql = "SELECT * FROM users WHERE id = 1"

        result = validator.validate(sql)

        assert not result.valid
        assert result.error is not None
        assert "Access denied" in result.error
        assert "users" in result.error

    def test_insert_blocked_in_read_only(self) -> None:
        """Test that INSERT is blocked in read-only mode."""
        validator = QueryValidator()
        sql = "INSERT INTO kdb_records (id, data) VALUES ('test', '{}')"

        result = validator.validate(sql, read_only=True)

        assert not result.valid
        assert result.query_type == QueryType.INSERT
        assert result.error is not None
        assert "read-only" in result.error.lower()

    def test_update_blocked_in_read_only(self) -> None:
        """Test that UPDATE is blocked in read-only mode."""
        validator = QueryValidator()
        sql = "UPDATE kdb_records SET data = '{}' WHERE id = 'test'"

        result = validator.validate(sql, read_only=True)

        assert not result.valid
        assert result.query_type == QueryType.UPDATE

    def test_delete_blocked_in_read_only(self) -> None:
        """Test that DELETE is blocked in read-only mode."""
        validator = QueryValidator()
        sql = "DELETE FROM kdb_records WHERE id = 'test'"

        result = validator.validate(sql, read_only=True)

        assert not result.valid
        assert result.query_type == QueryType.DELETE

    def test_sql_injection_patterns_blocked(self) -> None:
        """Test that SQL injection patterns are detected and blocked."""
        validator = QueryValidator()

        # Test various injection patterns
        injection_queries = [
            "SELECT * FROM kdb_records; DROP TABLE users;",
            "SELECT * FROM kdb_records; DELETE FROM users;",
            "SELECT * FROM kdb_records UNION SELECT * FROM users",
            "SELECT * FROM kdb_records WHERE pg_sleep(10)",
        ]

        for sql in injection_queries:
            result = validator.validate(sql)
            assert not result.valid, f"Should have blocked: {sql}"
            assert result.error is not None
            assert "unsafe pattern" in result.error.lower()

    def test_empty_query_rejected(self) -> None:
        """Test that empty queries are rejected."""
        validator = QueryValidator()

        result = validator.validate("")

        assert not result.valid
        assert result.error is not None
        assert "Empty query" in result.error

    def test_whitespace_only_rejected(self) -> None:
        """Test that whitespace-only queries are rejected."""
        validator = QueryValidator()

        result = validator.validate("   \n\t  ")

        assert not result.valid
        assert result.error is not None
        assert "Empty query" in result.error

    def test_warning_for_select_star(self) -> None:
        """Test that SELECT * generates a warning."""
        validator = QueryValidator()
        sql = "SELECT * FROM kdb_records WHERE entity_id = 'test' LIMIT 10"

        result = validator.validate(sql)

        assert result.valid
        assert any("SELECT *" in w for w in result.warnings)

    def test_warning_for_missing_limit(self) -> None:
        """Test that missing LIMIT generates a warning."""
        validator = QueryValidator()
        sql = "SELECT id FROM kdb_records WHERE entity_id = 'test'"

        result = validator.validate(sql)

        assert result.valid
        assert any("LIMIT" in w for w in result.warnings)

    def test_warning_for_missing_entity_id(self) -> None:
        """Test that missing entity_id filter generates a warning."""
        validator = QueryValidator()
        sql = "SELECT id FROM kdb_records WHERE is_deleted = false LIMIT 10"

        result = validator.validate(sql)

        assert result.valid
        assert any("entity_id" in w for w in result.warnings)

    def test_warning_for_missing_is_deleted(self) -> None:
        """Test that missing is_deleted filter generates a warning."""
        validator = QueryValidator()
        sql = "SELECT id FROM kdb_records WHERE entity_id = 'test' LIMIT 10"

        result = validator.validate(sql)

        assert result.valid
        assert any("is_deleted" in w for w in result.warnings)

    def test_all_allowed_tables(self) -> None:
        """Test that all KameleonDB tables are allowed."""
        validator = QueryValidator()

        for table in ALLOWED_TABLES:
            sql = f"SELECT * FROM {table} LIMIT 1"
            result = validator.validate(sql)
            assert result.valid, f"Table {table} should be allowed"

    def test_join_query_validation(self) -> None:
        """Test that JOIN queries are validated correctly."""
        validator = QueryValidator()
        sql = """
            SELECT r.id, e.name
            FROM kdb_records r
            JOIN kdb_entity_definitions e ON r.entity_id = e.id
            WHERE r.is_deleted = false
            LIMIT 10
        """

        result = validator.validate(sql)

        assert result.valid
        assert "kdb_records" in result.tables_accessed
        assert "kdb_entity_definitions" in result.tables_accessed


class TestQueryType:
    """Test query type detection."""

    def test_select_detection(self) -> None:
        """Test SELECT query detection."""
        validator = QueryValidator()

        result = validator.validate("SELECT id FROM kdb_records")
        assert result.query_type == QueryType.SELECT

        result = validator.validate("  select id from kdb_records")
        assert result.query_type == QueryType.SELECT

    def test_insert_detection(self) -> None:
        """Test INSERT query detection."""
        validator = QueryValidator(allow_writes=True)

        result = validator.validate(
            "INSERT INTO kdb_records (id) VALUES ('test')",
            read_only=False,
        )
        assert result.query_type == QueryType.INSERT

    def test_update_detection(self) -> None:
        """Test UPDATE query detection."""
        validator = QueryValidator(allow_writes=True)

        result = validator.validate(
            "UPDATE kdb_records SET data = '{}' WHERE id = 'test'",
            read_only=False,
        )
        assert result.query_type == QueryType.UPDATE

    def test_delete_detection(self) -> None:
        """Test DELETE query detection."""
        validator = QueryValidator(allow_writes=True)

        result = validator.validate(
            "DELETE FROM kdb_records WHERE id = 'test'",
            read_only=False,
        )
        assert result.query_type == QueryType.DELETE


class TestSchemaContextConstants:
    """Test schema context constants and patterns."""

    def test_jsonb_patterns_exist(self) -> None:
        """Test that JSONB access patterns are defined."""
        # PostgreSQL patterns
        assert "text_field" in POSTGRESQL_ACCESS_PATTERNS
        assert "numeric_field" in POSTGRESQL_ACCESS_PATTERNS
        assert "boolean_field" in POSTGRESQL_ACCESS_PATTERNS
        assert "datetime_field" in POSTGRESQL_ACCESS_PATTERNS
        # SQLite patterns
        assert "text_field" in SQLITE_ACCESS_PATTERNS
        assert "numeric_field" in SQLITE_ACCESS_PATTERNS
        assert "boolean_field" in SQLITE_ACCESS_PATTERNS
        assert "datetime_field" in SQLITE_ACCESS_PATTERNS

    def test_example_queries_exist(self) -> None:
        """Test that example queries are defined for both dialects."""
        # PostgreSQL examples
        assert len(POSTGRESQL_EXAMPLE_QUERIES) > 0
        for example in POSTGRESQL_EXAMPLE_QUERIES:
            assert "description" in example
            assert "sql" in example
            assert len(example["sql"]) > 0

        # SQLite examples
        assert len(SQLITE_EXAMPLE_QUERIES) > 0
        for example in SQLITE_EXAMPLE_QUERIES:
            assert "description" in example
            assert "sql" in example
            assert len(example["sql"]) > 0


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_valid_result(self) -> None:
        """Test creating a valid result."""
        result = ValidationResult(
            valid=True,
            sql="SELECT * FROM kdb_records",
            query_type=QueryType.SELECT,
            tables_accessed=["kdb_records"],
        )

        assert result.valid
        assert result.sql == "SELECT * FROM kdb_records"
        assert result.error is None

    def test_invalid_result(self) -> None:
        """Test creating an invalid result."""
        result = ValidationResult(
            valid=False,
            error="Access denied",
            query_type=QueryType.SELECT,
        )

        assert not result.valid
        assert result.error == "Access denied"
        assert result.sql == ""

    def test_default_values(self) -> None:
        """Test default values."""
        result = ValidationResult(valid=True)

        assert result.sql == ""
        assert result.error is None
        assert result.query_type == QueryType.OTHER
        assert result.tables_accessed == []
        assert result.warnings == []
