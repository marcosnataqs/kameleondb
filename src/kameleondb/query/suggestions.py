"""Suggestion engine for materialization recommendations.

Analyzes query metrics and generates actionable suggestions for agents.
"""

from __future__ import annotations

from kameleondb.core.types import (
    EntityStats,
    MaterializationPolicy,
    MaterializationSuggestion,
    QueryMetrics,
)


class SuggestionEngine:
    """Generates materialization suggestions based on query metrics.

    Analyzes both immediate query performance and historical patterns
    to provide intelligent recommendations.
    """

    def __init__(self, policy: MaterializationPolicy | None = None) -> None:
        """Initialize the suggestion engine.

        Args:
            policy: Materialization policy (uses defaults if not provided)
        """
        self._policy = policy or MaterializationPolicy()

    def evaluate_query(
        self,
        entity_name: str,
        metrics: QueryMetrics,
        storage_mode: str = "shared",
    ) -> list[MaterializationSuggestion]:
        """Evaluate a query and generate immediate suggestions.

        Checks against per-query thresholds.

        Args:
            entity_name: Primary entity accessed
            metrics: Query execution metrics
            storage_mode: Current storage mode of the entity

        Returns:
            List of suggestions (may be empty)
        """
        if not self._policy.enabled or storage_mode == "dedicated":
            return []

        suggestions: list[MaterializationSuggestion] = []

        # Check execution time threshold
        if metrics.execution_time_ms > self._policy.execution_time_threshold_ms:
            suggestions.append(
                MaterializationSuggestion(
                    entity_name=entity_name,
                    reason=(
                        f"Query took {metrics.execution_time_ms:.0f}ms "
                        f"(threshold: {self._policy.execution_time_threshold_ms:.0f}ms)"
                    ),
                    evidence={
                        "execution_time_ms": metrics.execution_time_ms,
                        "threshold_ms": self._policy.execution_time_threshold_ms,
                    },
                    action=f"db.materialize_entity('{entity_name}')",
                    priority="high",
                )
            )

        # Check row count threshold
        if metrics.row_count > self._policy.row_count_threshold:
            suggestions.append(
                MaterializationSuggestion(
                    entity_name=entity_name,
                    reason=(
                        f"Query returned {metrics.row_count} rows "
                        f"(threshold: {self._policy.row_count_threshold})"
                    ),
                    evidence={
                        "row_count": metrics.row_count,
                        "threshold": self._policy.row_count_threshold,
                    },
                    action=f"db.materialize_entity('{entity_name}')",
                    priority="medium",
                )
            )

        # Check for joins on shared tables
        if metrics.has_join and storage_mode == "shared":
            suggestions.append(
                MaterializationSuggestion(
                    entity_name=entity_name,
                    reason="Query uses JOIN on shared table (may benefit from FK constraints)",
                    evidence={
                        "has_join": True,
                        "storage_mode": storage_mode,
                    },
                    action=f"db.materialize_entity('{entity_name}')",
                    priority="medium",
                )
            )

        return suggestions

    def evaluate_entity(
        self,
        stats: EntityStats,
    ) -> list[MaterializationSuggestion]:
        """Evaluate historical patterns and generate suggestions.

        Checks against aggregated/historical thresholds.

        Args:
            stats: Entity statistics

        Returns:
            List of suggestions (may be empty)
        """
        if not self._policy.enabled or stats.storage_mode == "dedicated":
            return []

        suggestions: list[MaterializationSuggestion] = []

        # Check join frequency
        if stats.join_count_24h > self._policy.join_frequency_threshold:
            suggestions.append(
                MaterializationSuggestion(
                    entity_name=stats.entity_name,
                    reason=(
                        f"Entity joined {stats.join_count_24h} times in last 24h "
                        f"(threshold: {self._policy.join_frequency_threshold})"
                    ),
                    evidence={
                        "join_count_24h": stats.join_count_24h,
                        "threshold": self._policy.join_frequency_threshold,
                    },
                    action=f"db.materialize_entity('{stats.entity_name}')",
                    priority="high",
                )
            )

        # Check average execution time
        if stats.avg_execution_time_ms > self._policy.execution_time_threshold_ms:
            suggestions.append(
                MaterializationSuggestion(
                    entity_name=stats.entity_name,
                    reason=(
                        f"Average query time is {stats.avg_execution_time_ms:.0f}ms "
                        f"(threshold: {self._policy.execution_time_threshold_ms:.0f}ms)"
                    ),
                    evidence={
                        "avg_execution_time_ms": stats.avg_execution_time_ms,
                        "threshold_ms": self._policy.execution_time_threshold_ms,
                    },
                    action=f"db.materialize_entity('{stats.entity_name}')",
                    priority="medium",
                )
            )

        return suggestions

    def generate_suggestions(
        self,
        entity_name: str,
        metrics: QueryMetrics,
        stats: EntityStats | None = None,
        storage_mode: str = "shared",
    ) -> list[MaterializationSuggestion]:
        """Generate all applicable suggestions.

        Combines immediate query evaluation with historical patterns.

        Args:
            entity_name: Primary entity accessed
            metrics: Query execution metrics
            stats: Optional entity statistics for historical analysis
            storage_mode: Current storage mode

        Returns:
            List of deduplicated suggestions
        """
        suggestions = self.evaluate_query(entity_name, metrics, storage_mode)

        if stats:
            historical = self.evaluate_entity(stats)
            # Deduplicate by keeping unique entity+reason combinations
            seen = {(s.entity_name, s.reason) for s in suggestions}
            for s in historical:
                if (s.entity_name, s.reason) not in seen:
                    suggestions.append(s)
                    seen.add((s.entity_name, s.reason))

        return suggestions
