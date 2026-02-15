"""Integration tests for search functionality."""

import pytest

from kameleondb import KameleonDB


class TestSearchIntegration:
    """Test actual search execution with full KameleonDB."""

    def test_bm25_search_returns_matching_records(self, tmp_path):
        """BM25 search should return records matching query keywords."""
        db = KameleonDB(
            f"sqlite:///{tmp_path}/test.db",
            embeddings=True,
            embedding_provider=None,
        )

        try:
            # Create entity and insert records with different content
            articles = db.create_entity(
                "Article",
                fields=[
                    {"name": "title", "type": "string"},
                    {"name": "body", "type": "text"},
                ],
            )

            articles.insert(
                {
                    "title": "Python Programming Tutorial",
                    "body": "Learn Python programming from scratch for beginners",
                }
            )
            articles.insert(
                {
                    "title": "Advanced JavaScript Patterns",
                    "body": "Best practices and design patterns in JavaScript development",
                }
            )
            articles.insert(
                {
                    "title": "Python Data Science",
                    "body": "Comprehensive guide to data science with pandas and Python",
                }
            )
            articles.insert(
                {
                    "title": "Ruby on Rails",
                    "body": "Web development with Ruby framework",
                }
            )

            # Search for Python-related articles
            results = db.search("Python programming")

            # Should return Python articles, not JavaScript or Ruby
            assert len(results) > 0
            result_bodies = {r["data"].get("body", "") for r in results}
            assert any("Python" in body for body in result_bodies)

            # Most relevant result should be first
            assert "Python" in results[0]["data"].get("title", "")

        finally:
            db.close()

    def test_search_respects_limit(self, tmp_path):
        """Search should respect limit parameter."""
        db = KameleonDB(
            f"sqlite:///{tmp_path}/test.db",
            embeddings=True,
            embedding_provider=None,
        )

        try:
            articles = db.create_entity(
                "Article",
                fields=[{"name": "content", "type": "text"}],
            )

            # Insert 5 articles about Python
            for i in range(1, 6):
                articles.insert({"content": f"Python tutorial number {i}"})

            # Search with limit=2
            results = db.search("Python", limit=2)
            assert len(results) == 2

            # Search with limit=3
            results = db.search("Python", limit=3)
            assert len(results) == 3

        finally:
            db.close()

    def test_search_filters_by_entity(self, tmp_path):
        """Search should filter results by entity when specified."""
        db = KameleonDB(
            f"sqlite:///{tmp_path}/test.db",
            embeddings=True,
            embedding_provider=None,
        )

        try:
            # Create multiple entities
            articles = db.create_entity(
                "Article",
                fields=[{"name": "title", "type": "string"}],
            )
            tutorials = db.create_entity(
                "Tutorial",
                fields=[{"name": "title", "type": "string"}],
            )
            books = db.create_entity(
                "Book",
                fields=[{"name": "title", "type": "string"}],
            )

            # Insert records in different entities
            articles.insert({"title": "Python programming guide"})
            articles.insert({"title": "Python web development"})
            tutorials.insert({"title": "Python tutorial for beginners"})
            books.insert({"title": "Learning Python book"})

            # Search only in Article entity
            results = db.search("Python", entities=["Article"])
            assert len(results) == 2
            assert all(r["entity"] == "Article" for r in results)

            # Search only in Tutorial entity
            results = db.search("Python", entities=["Tutorial"])
            assert len(results) == 1
            assert results[0]["entity"] == "Tutorial"

        finally:
            db.close()

    def test_search_filters_by_min_score(self, tmp_path):
        """Search should exclude results below min_score threshold."""
        db = KameleonDB(
            f"sqlite:///{tmp_path}/test.db",
            embeddings=True,
            embedding_provider=None,
        )

        try:
            articles = db.create_entity(
                "Article",
                fields=[{"name": "content", "type": "text"}],
            )

            # Insert one highly relevant and one loosely relevant record
            articles.insert({"content": "Python programming Python Python tutorial"})
            articles.insert({"content": "introduction to programming basics"})

            # Search with no min_score
            results = db.search("Python programming")
            no_filter_count = len(results)

            # Search with high min_score - should filter out weak matches
            results = db.search("Python programming", min_score=5.0)
            assert len(results) <= no_filter_count
            # All results should have score >= min_score
            assert all(r["score"] >= 5.0 for r in results)

        finally:
            db.close()

    def test_search_orders_by_relevance(self, tmp_path):
        """Results should be ordered by relevance score."""
        db = KameleonDB(
            f"sqlite:///{tmp_path}/test.db",
            embeddings=True,
            embedding_provider=None,
        )

        try:
            articles = db.create_entity(
                "Article",
                fields=[{"name": "content", "type": "text"}],
            )

            # Insert records with varying relevance to query
            articles.insert({"content": "Python programming tutorial"})  # medium relevance
            articles.insert({"content": "tutorial introduction"})  # low relevance
            id3 = articles.insert({"content": "Python Python programming"})  # high relevance

            results = db.search("Python programming")

            # Results should be ordered by score (descending)
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)

            # Most relevant article (id3 with "Python" twice) should be first
            assert results[0]["id"] == id3

        finally:
            db.close()

    def test_search_across_multiple_entities(self, tmp_path):
        """Search should work across multiple entities when entities= is provided."""
        db = KameleonDB(
            f"sqlite:///{tmp_path}/test.db",
            embeddings=True,
            embedding_provider=None,
        )

        try:
            articles = db.create_entity(
                "Article",
                fields=[{"name": "title", "type": "string"}],
            )
            tutorials = db.create_entity(
                "Tutorial",
                fields=[{"name": "title", "type": "string"}],
            )
            books = db.create_entity(
                "Book",
                fields=[{"name": "title", "type": "string"}],
            )
            videos = db.create_entity(
                "Video",
                fields=[{"name": "title", "type": "string"}],
            )

            # Insert records in different entities
            articles.insert({"title": "Python programming"})
            tutorials.insert({"title": "Python tutorial"})
            books.insert({"title": "Python book"})
            videos.insert({"title": "JavaScript video"})

            # Search across Article and Tutorial only
            results = db.search("Python", entities=["Article", "Tutorial"])
            assert len(results) == 2
            entities = {r["entity"] for r in results}
            assert entities == {"Article", "Tutorial"}

            # Search across all entities (no filter)
            results = db.search("Python")
            assert len(results) == 3  # Article, Tutorial, Book

        finally:
            db.close()

    def test_search_returns_empty_list_when_no_matches(self, tmp_path):
        """Search should return empty list when nothing matches."""
        db = KameleonDB(
            f"sqlite:///{tmp_path}/test.db",
            embeddings=True,
            embedding_provider=None,
        )

        try:
            articles = db.create_entity(
                "Article",
                fields=[{"name": "content", "type": "text"}],
            )

            # Insert some records
            articles.insert({"content": "Python programming"})
            articles.insert({"content": "JavaScript development"})

            # Search for something unrelated
            results = db.search("Rust quantum computing blockchain")
            assert results == []

        finally:
            db.close()

    def test_search_with_materialized_storage(self, tmp_path):
        """Search should work with entities using materialized (dedicated table) storage."""
        db = KameleonDB(
            f"sqlite:///{tmp_path}/test.db",
            embeddings=True,
            embedding_provider=None,
        )

        try:
            # Create entity in shared mode first
            articles = db.create_entity(
                "Article",
                fields=[
                    {"name": "title", "type": "string"},
                    {"name": "content", "type": "text"},
                ],
            )

            # Insert records (in shared mode)
            id1 = articles.insert(
                {
                    "title": "Python Guide",
                    "content": "Complete Python programming guide",
                }
            )
            articles.insert(
                {
                    "title": "JavaScript Patterns",
                    "content": "Modern JavaScript development patterns",
                }
            )

            # Materialize to dedicated storage
            db.materialize_entity("Article")

            # Search should still work after materialization
            results = db.search("Python programming")
            assert len(results) > 0
            assert results[0]["id"] == id1
            assert "Python" in results[0]["data"].get("title", "")

        finally:
            db.close()


@pytest.mark.integration
class TestSearchPostgreSQL:
    """Test search with PostgreSQL backend."""

    def test_search_postgresql(self, postgresql_url: str):
        """Search should work with PostgreSQL backend."""
        from sqlalchemy import text

        db = KameleonDB(postgresql_url, embeddings=True, embedding_provider=None)
        try:
            # Create entity and insert records
            articles = db.create_entity(
                "Article",
                fields=[
                    {"name": "title", "type": "string"},
                    {"name": "body", "type": "text"},
                ],
            )

            articles.insert(
                {
                    "title": "Python Tutorial",
                    "body": "Learn Python programming",
                }
            )
            articles.insert(
                {
                    "title": "Ruby Guide",
                    "body": "Ruby programming guide",
                }
            )

            # Search should work
            results = db.search("Python programming")
            assert len(results) > 0
            assert any("Python" in r["data"].get("title", "") for r in results)
        finally:
            # Cleanup
            with db._connection.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'kdb_%'")
                )
                for row in result:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{row[0]}" CASCADE'))
                conn.commit()
            db.close()
