"""Query metrics collection and storage for KameleonDB.

Provides metrics tracking for query intelligence and materialization suggestions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.orm import Session

from kameleondb.core.types import EntityStats, MaterializationPolicy, QueryMetrics
from kameleondb.schema.models import QueryMetric

if TYPE_CHECKING:
    from sqlalchemy import Engine


class MetricsCollector:
    """Collects and manages query execution metrics.

    Tracks query performance and patterns to enable intelligent
    suggestions for entity materialization.
    """

    def __init__(
        self,
        engine: Engine,
        policy: MaterializationPolicy | None = None,
    ) -> None:
        """Initialize the metrics collector.

        Args:
            engine: SQLAlchemy engine
            policy: Materialization policy (uses defaults if not provided)
        """
        self._engine = engine
        self._policy = policy or MaterializationPolicy()

    @property
    def enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        return self._policy.enabled

    def record_query(
        self,
        metrics: QueryMetrics,
        entity_name: str | None = None,
        tables_accessed: list[str] | None = None,
        created_by: str | None = None,
    ) -> str | None:
        """Record query execution metrics.

        Args:
            metrics: Query metrics from execution
            entity_name: Primary entity accessed (if known)
            tables_accessed: List of tables accessed
            created_by: Agent/user identifier

        Returns:
            Metric ID if recorded, None if disabled
        """
        if not self._policy.enabled:
            return None

        with Session(self._engine) as session:
            metric = QueryMetric(
                entity_name=entity_name,
                query_type=metrics.query_type,
                execution_time_ms=metrics.execution_time_ms,
                row_count=metrics.row_count,
                has_join=metrics.has_join,
                tables_accessed=tables_accessed,
                created_by=created_by,
            )
            session.add(metric)
            session.commit()
            return metric.id

    def get_entity_stats(
        self,
        entity_name: str,
        storage_mode: str = "shared",
        record_count: int = 0,
    ) -> EntityStats:
        """Get aggregated statistics for an entity.

        Args:
            entity_name: Entity to get stats for
            storage_mode: Current storage mode of the entity
            record_count: Current record count for the entity

        Returns:
            EntityStats with aggregated metrics
        """
        with Session(self._engine) as session:
            # Get aggregate stats
            result = session.execute(
                text(
                    """
                SELECT
                    COUNT(*) as total_queries,
                    COALESCE(AVG(execution_time_ms), 0) as avg_time,
                    COALESCE(MAX(execution_time_ms), 0) as max_time,
                    COALESCE(SUM(row_count), 0) as total_rows
                FROM kdb_query_metrics
                WHERE entity_name = :entity_name
            """
                ),
                {"entity_name": entity_name},
            )
            row = result.fetchone()

            total_queries = row[0] if row else 0
            avg_time = float(row[1]) if row else 0.0
            max_time = float(row[2]) if row else 0.0
            total_rows = int(row[3]) if row else 0

            # Get join count in last 24 hours
            cutoff = datetime.now(UTC) - timedelta(hours=24)
            result = session.execute(
                text(
                    """
                SELECT COUNT(*) FROM kdb_query_metrics
                WHERE entity_name = :entity_name
                  AND has_join = true
                  AND timestamp > :cutoff
            """
                ),
                {"entity_name": entity_name, "cutoff": cutoff},
            )
            join_count = result.scalar() or 0

        # Generate suggestion based on stats
        suggestion = None
        if join_count > self._policy.join_frequency_threshold:
            suggestion = "Consider materialization - high join frequency"
        elif avg_time > self._policy.execution_time_threshold_ms:
            suggestion = "Consider materialization - slow average query time"
        elif total_rows > self._policy.row_count_threshold * total_queries:
            suggestion = "Consider materialization - large result sets"

        return EntityStats(
            entity_name=entity_name,
            total_queries=total_queries,
            avg_execution_time_ms=avg_time,
            max_execution_time_ms=max_time,
            total_rows_returned=total_rows,
            join_count_24h=join_count,
            storage_mode=storage_mode,
            record_count=record_count,
            suggestion=suggestion,
        )

    def cleanup_old_metrics(self) -> int:
        """Remove metrics older than retention period.

        Returns:
            Number of metrics deleted
        """
        cutoff = datetime.now(UTC) - timedelta(days=self._policy.retention_days)

        with Session(self._engine) as session:
            result = session.execute(
                text(
                    """
                DELETE FROM kdb_query_metrics
                WHERE timestamp < :cutoff
            """
                ),
                {"cutoff": cutoff},
            )
            session.commit()
            return result.rowcount or 0

    def get_metrics_count(self, entity_name: str | None = None) -> int:
        """Get the count of stored metrics.

        Args:
            entity_name: Optional filter by entity name

        Returns:
            Number of metrics stored
        """
        with Session(self._engine) as session:
            if entity_name:
                result = session.execute(
                    text("SELECT COUNT(*) FROM kdb_query_metrics WHERE entity_name = :name"),
                    {"name": entity_name},
                )
            else:
                result = session.execute(text("SELECT COUNT(*) FROM kdb_query_metrics"))
            return result.scalar() or 0
