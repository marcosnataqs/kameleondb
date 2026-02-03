"""LLM-Native Query Generation for KameleonDB.

This module provides the infrastructure for LLM-powered SQL query generation,
including schema context building, query validation, and execution.

Architecture (ADR-002):
    1. Schema Context Builder - Generates rich context for LLM SQL generation
    2. Query Validator - Validates and sanitizes LLM-generated SQL
    3. Query Executor - Executes validated SQL with result transformation

Example:
    # Natural language query (future)
    results = db.query("Find premium customers who spent over $1000 last month")

    # Schema context for agents to generate SQL themselves
    context = db.get_schema_context(entities=["Customer", "Order"])
"""

from kameleondb.query.context import SchemaContextBuilder, get_schema_context
from kameleondb.query.validator import QueryValidator, ValidationResult

__all__ = [
    "SchemaContextBuilder",
    "get_schema_context",
    "QueryValidator",
    "ValidationResult",
]
