"""Tests for Query Intelligence (ADR-002 Phase 1)."""

from __future__ import annotations

from kameleondb import KameleonDB
from kameleondb.core.types import (
    EntityStats,
    MaterializationPolicy,
    QueryMetrics,
)
from kameleondb.query.metrics import MetricsCollector
from kameleondb.query.suggestions import SuggestionEngine


class TestMaterializationPolicy:
    """Test MaterializationPolicy configuration."""

    def test_default_values(self) -> None:
        """Test default policy values."""
        policy = MaterializationPolicy()

        assert policy.execution_time_threshold_ms == 100.0
        assert policy.row_count_threshold == 1000
        assert policy.join_frequency_threshold == 10
        assert policy.enabled is True
        assert policy.retention_days == 7

    def test_custom_values(self) -> None:
        """Test custom policy values."""
        policy = MaterializationPolicy(
            execution_time_threshold_ms=50.0,
            row_count_threshold=500,
            enabled=False,
        )

        assert policy.execution_time_threshold_ms == 50.0
        assert policy.row_count_threshold == 500
        assert policy.enabled is False


class TestQueryMetrics:
    """Test QueryMetrics dataclass."""

    def test_basic_metrics(self) -> None:
        """Test basic metrics creation."""
        metrics = QueryMetrics(
            execution_time_ms=150.5,
            row_count=100,
            query_type="SELECT",
        )

        assert metrics.execution_time_ms == 150.5
        assert metrics.row_count == 100
        assert metrics.query_type == "SELECT"
        assert metrics.has_join is False
        assert metrics.entities_accessed == []


class TestSuggestionEngine:
    """Test SuggestionEngine functionality."""

    def test_slow_query_suggestion(self) -> None:
        """Test suggestion for slow queries."""
        engine = SuggestionEngine(MaterializationPolicy(execution_time_threshold_ms=100.0))
        metrics = QueryMetrics(
            execution_time_ms=250.0,
            row_count=50,
            query_type="SELECT",
        )

        suggestions = engine.evaluate_query("Contact", metrics)

        assert len(suggestions) >= 1
        assert any(s.priority == "high" for s in suggestions)
        assert any("250ms" in s.reason for s in suggestions)

    def test_large_result_suggestion(self) -> None:
        """Test suggestion for large result sets."""
        engine = SuggestionEngine(MaterializationPolicy(row_count_threshold=100))
        metrics = QueryMetrics(
            execution_time_ms=50.0,
            row_count=500,
            query_type="SELECT",
        )

        suggestions = engine.evaluate_query("Contact", metrics)

        assert len(suggestions) >= 1
        assert any("500 rows" in s.reason for s in suggestions)

    def test_join_suggestion(self) -> None:
        """Test suggestion for joins on shared tables."""
        engine = SuggestionEngine()
        metrics = QueryMetrics(
            execution_time_ms=50.0,
            row_count=50,
            query_type="SELECT",
            has_join=True,
        )

        suggestions = engine.evaluate_query("Contact", metrics, storage_mode="shared")

        assert len(suggestions) >= 1
        assert any("JOIN" in s.reason for s in suggestions)

    def test_no_suggestion_for_dedicated(self) -> None:
        """Test no suggestions for already dedicated entities."""
        engine = SuggestionEngine()
        metrics = QueryMetrics(
            execution_time_ms=500.0,  # Very slow
            row_count=5000,  # Many rows
            query_type="SELECT",
            has_join=True,
        )

        suggestions = engine.evaluate_query("Contact", metrics, storage_mode="dedicated")

        assert len(suggestions) == 0

    def test_no_suggestion_when_disabled(self) -> None:
        """Test no suggestions when disabled."""
        engine = SuggestionEngine(MaterializationPolicy(enabled=False))
        metrics = QueryMetrics(
            execution_time_ms=500.0,
            row_count=5000,
            query_type="SELECT",
        )

        suggestions = engine.evaluate_query("Contact", metrics)

        assert len(suggestions) == 0

    def test_evaluate_entity_historical(self) -> None:
        """Test suggestions from historical patterns."""
        engine = SuggestionEngine(MaterializationPolicy(join_frequency_threshold=5))
        stats = EntityStats(
            entity_name="Contact",
            total_queries=100,
            avg_execution_time_ms=50.0,
            join_count_24h=20,
            storage_mode="shared",
        )

        suggestions = engine.evaluate_entity(stats)

        assert len(suggestions) >= 1
        assert any("20 times" in s.reason for s in suggestions)


class TestMetricsCollector:
    """Test MetricsCollector functionality."""

    def test_record_query(self, memory_db: KameleonDB) -> None:
        """Test recording query metrics."""
        collector = MetricsCollector(memory_db._connection.engine)
        metrics = QueryMetrics(
            execution_time_ms=100.0,
            row_count=50,
            query_type="SELECT",
            has_join=False,
        )

        metric_id = collector.record_query(
            metrics=metrics,
            entity_name="TestEntity",
            created_by="test_agent",
        )

        assert metric_id is not None

    def test_record_query_disabled(self, memory_db: KameleonDB) -> None:
        """Test that recording is skipped when disabled."""
        collector = MetricsCollector(
            memory_db._connection.engine,
            MaterializationPolicy(enabled=False),
        )
        metrics = QueryMetrics(
            execution_time_ms=100.0,
            row_count=50,
            query_type="SELECT",
        )

        metric_id = collector.record_query(metrics=metrics, entity_name="TestEntity")

        assert metric_id is None

    def test_get_entity_stats(self, memory_db: KameleonDB) -> None:
        """Test getting entity statistics."""
        collector = MetricsCollector(memory_db._connection.engine)

        # Record some metrics
        for i in range(5):
            metrics = QueryMetrics(
                execution_time_ms=100.0 + i * 10,
                row_count=50 + i,
                query_type="SELECT",
            )
            collector.record_query(metrics=metrics, entity_name="TestEntity")

        stats = collector.get_entity_stats("TestEntity")

        assert stats.entity_name == "TestEntity"
        assert stats.total_queries == 5

    def test_get_metrics_count(self, memory_db: KameleonDB) -> None:
        """Test getting metrics count."""
        collector = MetricsCollector(memory_db._connection.engine)

        # Record some metrics
        for _ in range(3):
            metrics = QueryMetrics(
                execution_time_ms=100.0,
                row_count=50,
                query_type="SELECT",
            )
            collector.record_query(metrics=metrics, entity_name="TestEntity")

        count = collector.get_metrics_count("TestEntity")
        assert count == 3

        total_count = collector.get_metrics_count()
        assert total_count >= 3


class TestKameleonDBQueryIntelligence:
    """Test KameleonDB query intelligence integration."""

    def test_execute_sql_returns_metrics_and_hints(self, memory_db: KameleonDB) -> None:
        """Test executing SQL with metrics and hints (agent-first pattern)."""
        # Create entity and insert data
        entity = memory_db.create_entity("TestEntity", fields=[{"name": "name", "type": "string"}])
        entity.insert({"name": "Test 1"})
        entity.insert({"name": "Test 2"})

        # Get entity_id for query
        entity_def = memory_db._schema_engine.get_entity("TestEntity")

        # execute_sql now always returns QueryExecutionResult with metrics
        result = memory_db.execute_sql(
            f"SELECT * FROM kdb_records WHERE entity_id = '{entity_def.id}'",
            entity_name="TestEntity",
            created_by="test",
        )

        assert len(result.rows) == 2
        assert result.metrics.row_count == 2
        assert result.metrics.execution_time_ms > 0
        assert result.metrics.query_type == "SELECT"

        # Result should have suggestions list (may be empty)
        assert isinstance(result.suggestions, list)

    def test_get_entity_stats(self, memory_db: KameleonDB) -> None:
        """Test getting entity stats through main API."""
        memory_db.create_entity("TestEntity", fields=[{"name": "name", "type": "string"}])

        stats = memory_db.get_entity_stats("TestEntity")

        assert stats.entity_name == "TestEntity"
        assert stats.storage_mode == "shared"

    def test_custom_materialization_policy(self) -> None:
        """Test initializing with custom policy."""
        policy = MaterializationPolicy(
            execution_time_threshold_ms=50.0,
            enabled=True,
        )
        db = KameleonDB("sqlite:///:memory:", materialization_policy=policy)

        assert db._materialization_policy.execution_time_threshold_ms == 50.0
        db.close()
