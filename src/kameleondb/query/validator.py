"""SQL Query Validator for LLM-generated queries.

Validates and sanitizes SQL queries before execution to ensure:
- Only SELECT statements are allowed (by default)
- Table access is limited to KameleonDB tables
- No SQL injection patterns are present
- Row-level security policies are applied
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kameleondb import KameleonDB


class QueryType(StrEnum):
    """Types of SQL queries."""

    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    OTHER = "OTHER"


# Allowed tables for KameleonDB queries
ALLOWED_TABLES = {
    "kdb_records",
    "kdb_entity_definitions",
    "kdb_field_definitions",
    "kdb_relationship_definitions",
    "kdb_schema_changelog",
}

# Dangerous SQL patterns to block
INJECTION_PATTERNS = [
    r";\s*DROP\s+",
    r";\s*DELETE\s+",
    r";\s*TRUNCATE\s+",
    r";\s*ALTER\s+",
    r";\s*CREATE\s+",
    r"--\s*$",  # SQL comments at end of line
    r"/\*.*\*/",  # Block comments
    r"UNION\s+ALL\s+SELECT",  # Union-based injection
    r"UNION\s+SELECT",
    r"INTO\s+OUTFILE",
    r"INTO\s+DUMPFILE",
    r"LOAD_FILE\s*\(",
    r"BENCHMARK\s*\(",
    r"SLEEP\s*\(",
    r"WAITFOR\s+DELAY",
    r"xp_cmdshell",
    r"sp_executesql",
    r"EXECUTE\s+IMMEDIATE",
    r"pg_sleep\s*\(",
    r"pg_read_file\s*\(",
    r"pg_ls_dir\s*\(",
]


@dataclass
class ValidationResult:
    """Result of query validation."""

    valid: bool
    """Whether the query passed validation."""

    sql: str = ""
    """The validated (possibly modified) SQL query."""

    error: str | None = None
    """Error message if validation failed."""

    query_type: QueryType = QueryType.OTHER
    """Detected query type."""

    tables_accessed: list[str] = field(default_factory=list)
    """List of tables referenced in the query."""

    warnings: list[str] = field(default_factory=list)
    """Non-fatal warnings about the query."""


class QueryValidator:
    """Validates LLM-generated SQL queries before execution.

    Provides multiple layers of protection:
    1. Statement type validation (SELECT only by default)
    2. Table access control
    3. SQL injection pattern detection
    4. Optional row-level security policy injection
    """

    def __init__(
        self,
        db: KameleonDB | None = None,
        allowed_tables: set[str] | None = None,
        allow_writes: bool = False,
    ) -> None:
        """Initialize the validator.

        Args:
            db: Optional KameleonDB instance for schema-aware validation
            allowed_tables: Set of allowed table names (defaults to KameleonDB tables)
            allow_writes: Whether to allow INSERT/UPDATE/DELETE (default False)
        """
        self._db = db
        self._allowed_tables = allowed_tables or ALLOWED_TABLES
        self._allow_writes = allow_writes

    def validate(
        self,
        sql: str,
        read_only: bool = True,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate an SQL query.

        Args:
            sql: SQL query string to validate
            read_only: If True, only SELECT statements are allowed
            context: Optional schema context for additional validation

        Returns:
            ValidationResult with validation status and details
        """
        # Clean up the SQL
        cleaned_sql = self._clean_sql(sql)

        if not cleaned_sql:
            return ValidationResult(
                valid=False,
                error="Empty query",
            )

        # Detect query type
        query_type = self._detect_query_type(cleaned_sql)

        # Check if query type is allowed
        if read_only and query_type != QueryType.SELECT:
            return ValidationResult(
                valid=False,
                error=f"Only SELECT statements allowed in read-only mode. Got: {query_type.value}",
                query_type=query_type,
            )

        if not self._allow_writes and query_type in (
            QueryType.INSERT,
            QueryType.UPDATE,
            QueryType.DELETE,
        ):
            return ValidationResult(
                valid=False,
                error=f"Write operations not allowed. Got: {query_type.value}",
                query_type=query_type,
            )

        # Check for injection patterns
        injection_check = self._check_injection_patterns(cleaned_sql)
        if injection_check:
            return ValidationResult(
                valid=False,
                error=f"Query contains potentially unsafe pattern: {injection_check}",
                query_type=query_type,
            )

        # Extract and validate table references
        tables = self._extract_tables(cleaned_sql)
        unauthorized = tables - self._allowed_tables

        if unauthorized:
            return ValidationResult(
                valid=False,
                error=f"Access denied to tables: {', '.join(sorted(unauthorized))}. "
                f"Allowed tables: {', '.join(sorted(self._allowed_tables))}",
                query_type=query_type,
                tables_accessed=list(tables),
            )

        # Build warnings
        warnings = self._check_warnings(cleaned_sql, query_type)

        # Apply row-level security if context provides entity filtering
        final_sql = self._apply_rls(cleaned_sql, context)

        return ValidationResult(
            valid=True,
            sql=final_sql,
            query_type=query_type,
            tables_accessed=list(tables),
            warnings=warnings,
        )

    def _clean_sql(self, sql: str) -> str:
        """Clean and normalize SQL query.

        Args:
            sql: Raw SQL string

        Returns:
            Cleaned SQL string
        """
        # Remove leading/trailing whitespace
        cleaned = sql.strip()

        # Remove multiple consecutive whitespaces
        cleaned = re.sub(r"\s+", " ", cleaned)

        # Remove trailing semicolons (we'll add one if needed)
        cleaned = cleaned.rstrip(";")

        return cleaned

    def _detect_query_type(self, sql: str) -> QueryType:
        """Detect the type of SQL query.

        Args:
            sql: Cleaned SQL string

        Returns:
            QueryType enum value
        """
        upper_sql = sql.upper().lstrip()

        if upper_sql.startswith("SELECT"):
            return QueryType.SELECT
        elif upper_sql.startswith("INSERT"):
            return QueryType.INSERT
        elif upper_sql.startswith("UPDATE"):
            return QueryType.UPDATE
        elif upper_sql.startswith("DELETE"):
            return QueryType.DELETE
        else:
            return QueryType.OTHER

    def _check_injection_patterns(self, sql: str) -> str | None:
        """Check for SQL injection patterns.

        Args:
            sql: SQL string to check

        Returns:
            Description of detected pattern, or None if clean
        """
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                return pattern
        return None

    def _extract_tables(self, sql: str) -> set[str]:
        """Extract table names from SQL query.

        Args:
            sql: SQL string

        Returns:
            Set of table names
        """
        tables: set[str] = set()

        # Pattern for FROM clause
        from_pattern = r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        for match in re.finditer(from_pattern, sql, re.IGNORECASE):
            tables.add(match.group(1).lower())

        # Pattern for JOIN clauses
        join_pattern = r"\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        for match in re.finditer(join_pattern, sql, re.IGNORECASE):
            tables.add(match.group(1).lower())

        # Pattern for INSERT INTO
        insert_pattern = r"\bINSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        for match in re.finditer(insert_pattern, sql, re.IGNORECASE):
            tables.add(match.group(1).lower())

        # Pattern for UPDATE
        update_pattern = r"\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        for match in re.finditer(update_pattern, sql, re.IGNORECASE):
            tables.add(match.group(1).lower())

        # Pattern for DELETE FROM
        delete_pattern = r"\bDELETE\s+FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        for match in re.finditer(delete_pattern, sql, re.IGNORECASE):
            tables.add(match.group(1).lower())

        return tables

    def _check_warnings(self, sql: str, query_type: QueryType) -> list[str]:
        """Generate warnings for potentially problematic queries.

        Args:
            sql: SQL string
            query_type: Detected query type

        Returns:
            List of warning messages
        """
        warnings = []

        # Check for SELECT *
        if re.search(r"\bSELECT\s+\*", sql, re.IGNORECASE):
            warnings.append(
                "Using SELECT * may return more data than needed. "
                "Consider selecting specific columns."
            )

        # Check for missing LIMIT
        if query_type == QueryType.SELECT and not re.search(r"\bLIMIT\s+\d+", sql, re.IGNORECASE):
            warnings.append(
                "No LIMIT clause found. Consider adding one to prevent returning too many rows."
            )

        # Check for missing WHERE on kdb_records
        if "kdb_records" in sql.lower():
            if not re.search(r"\bWHERE\b", sql, re.IGNORECASE):
                warnings.append(
                    "Query on kdb_records without WHERE clause may return "
                    "all records across all entities."
                )
            elif not re.search(r"\bentity_id\b", sql, re.IGNORECASE):
                warnings.append(
                    "Query on kdb_records without entity_id filter may return "
                    "records from multiple entity types."
                )

        # Check for missing is_deleted filter
        if "kdb_records" in sql.lower() and not re.search(r"\bis_deleted\b", sql, re.IGNORECASE):
            warnings.append(
                "Query on kdb_records without is_deleted filter may include soft-deleted records."
            )

        return warnings

    def _apply_rls(self, sql: str, _context: dict[str, Any] | None) -> str:
        """Apply row-level security policies to the query.

        This is a placeholder for future RLS implementation.
        Currently returns the query unchanged.

        Args:
            sql: SQL query
            _context: Schema context with potential RLS info (unused for now)

        Returns:
            SQL with RLS policies applied
        """
        # TODO: Implement RLS policy injection based on context
        # For now, just return the original SQL
        return sql


def validate_query(
    sql: str,
    db: KameleonDB | None = None,
    read_only: bool = True,
) -> ValidationResult:
    """Convenience function to validate a query.

    Args:
        sql: SQL query to validate
        db: Optional KameleonDB instance
        read_only: If True, only SELECT statements allowed

    Returns:
        ValidationResult
    """
    validator = QueryValidator(db=db)
    return validator.validate(sql, read_only=read_only)
