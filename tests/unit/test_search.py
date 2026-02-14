"""Tests for semantic search functionality."""

import pytest

from kameleondb import KameleonDB


class TestSearchWithoutEmbeddings:
    """Test search behavior when embeddings are not enabled."""

    def test_search_raises_without_embeddings(self, tmp_path):
        """Search should raise RuntimeError if embeddings not enabled."""
        db = KameleonDB(f"sqlite:///{tmp_path}/test.db")
        try:
            with pytest.raises(RuntimeError, match="Search requires embeddings"):
                db.search("test query")
        finally:
            db.close()

    def test_embedding_status_empty_without_embeddings(self, tmp_path):
        """embedding_status should return empty list if embeddings not enabled."""
        db = KameleonDB(f"sqlite:///{tmp_path}/test.db")
        try:
            status = db.embedding_status()
            assert status == []
        finally:
            db.close()


class TestEmbeddingProviderInterface:
    """Test embedding provider interface."""

    def test_get_provider_fastembed_not_installed(self):
        """get_provider should raise ImportError if fastembed not installed."""
        from kameleondb.embeddings import get_provider

        # This will fail if fastembed is installed, which is fine
        # The test is mainly to verify the interface works
        try:
            provider = get_provider("fastembed")
            # If we get here, fastembed is installed
            assert provider.dimensions > 0
            assert provider.model_name is not None
        except ImportError as e:
            assert "fastembed" in str(e).lower()

    def test_get_provider_unknown_raises(self):
        """get_provider should raise ValueError for unknown provider."""
        from kameleondb.embeddings import get_provider

        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_provider("nonexistent_provider")

    def test_embedding_result_dataclass(self):
        """EmbeddingResult should have expected fields."""
        from kameleondb.embeddings import EmbeddingResult

        result = EmbeddingResult(
            text="test",
            embedding=[0.1, 0.2, 0.3],
            model="test-model",
            dimensions=3,
        )
        assert result.text == "test"
        assert len(result.embedding) == 3
        assert result.model == "test-model"
        assert result.dimensions == 3


class TestSearchEngine:
    """Test SearchEngine class."""

    def test_search_engine_creates_tables(self, tmp_path):
        """SearchEngine should create search tables on init."""
        from sqlalchemy import create_engine, text

        from kameleondb.search import SearchEngine

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        SearchEngine(engine, embedding_provider=None)

        # Check tables exist
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='kdb_search'")
            )
            assert result.fetchone() is not None

            # FTS table should also exist
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='kdb_search_fts'")
            )
            assert result.fetchone() is not None

    def test_search_result_dataclass(self):
        """SearchResult should have expected fields."""
        from kameleondb.search import SearchResult

        result = SearchResult(
            entity="Contact",
            id="123",
            score=0.95,
            data={"name": "John"},
            matched_text="name: John",
        )
        assert result.entity == "Contact"
        assert result.id == "123"
        assert result.score == 0.95
        assert result.data == {"name": "John"}
        assert result.matched_text == "name: John"

    def test_index_status_dataclass(self):
        """IndexStatus should have expected fields."""
        from datetime import datetime

        from kameleondb.search import IndexStatus

        now = datetime.now()
        status = IndexStatus(
            entity="Contact",
            indexed=100,
            pending=5,
            last_updated=now,
        )
        assert status.entity == "Contact"
        assert status.indexed == 100
        assert status.pending == 5
        assert status.last_updated == now


class TestSearchEngineBM25Only:
    """Test SearchEngine with BM25 only (no embeddings)."""

    def test_bm25_index_and_status(self, tmp_path):
        """BM25 indexing and status should work without embedding provider."""
        from sqlalchemy import create_engine

        from kameleondb.search import SearchEngine

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        search = SearchEngine(engine, embedding_provider=None)

        # Index some records
        search.index_record("Article", "1", "Python programming tutorial for beginners")
        search.index_record("Article", "2", "Advanced JavaScript patterns")
        search.index_record("Article", "3", "Python data science guide")

        # Check status
        statuses = search.get_status()
        assert len(statuses) == 1
        assert statuses[0].entity == "Article"
        assert statuses[0].indexed == 3

        # Check entity-specific status
        statuses = search.get_status("Article")
        assert len(statuses) == 1
        assert statuses[0].indexed == 3

    def test_delete_record_from_index(self, tmp_path):
        """Deleting should remove from search index."""
        from sqlalchemy import create_engine, text

        from kameleondb.search import SearchEngine

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        search = SearchEngine(engine, embedding_provider=None)

        # Index a record
        search.index_record("Article", "1", "Test content")

        # Verify it's indexed
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM kdb_search WHERE record_id = '1'"))
            assert result.scalar() == 1

        # Delete it
        search.delete_record("Article", "1")

        # Verify it's gone
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM kdb_search WHERE record_id = '1'"))
            assert result.scalar() == 0


class TestSearchEngineSearch:
    """Test actual search execution."""

    def test_bm25_search_returns_matching_records(self, tmp_path):
        """BM25 search should return records matching query keywords."""
        from sqlalchemy import create_engine

        from kameleondb.search import SearchEngine

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        search = SearchEngine(engine, embedding_provider=None)

        # Index records with different content
        search.index_record("Article", "1", "Python programming tutorial for beginners")
        search.index_record("Article", "2", "Advanced JavaScript patterns and best practices")
        search.index_record("Article", "3", "Python data science guide with pandas")
        search.index_record("Article", "4", "Ruby on Rails web development")

        # Search for Python-related articles
        results = search.search("Python programming")

        # Should return Python articles (1 and 3), not JavaScript or Ruby
        assert len(results) > 0
        result_ids = {r.id for r in results}
        assert "1" in result_ids or "3" in result_ids
        # Results should be ordered by relevance (article 1 should score higher)
        assert results[0].id == "1"

    def test_search_respects_limit(self, tmp_path):
        """Search should respect limit parameter."""
        from sqlalchemy import create_engine

        from kameleondb.search import SearchEngine

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        search = SearchEngine(engine, embedding_provider=None)

        # Index 5 articles about Python
        for i in range(1, 6):
            search.index_record("Article", str(i), f"Python tutorial number {i}")

        # Search with limit=2
        results = search.search("Python", limit=2)
        assert len(results) == 2

        # Search with limit=3
        results = search.search("Python", limit=3)
        assert len(results) == 3

    def test_search_filters_by_entity(self, tmp_path):
        """Search should filter results by entity when specified."""
        from sqlalchemy import create_engine

        from kameleondb.search import SearchEngine

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        search = SearchEngine(engine, embedding_provider=None)

        # Index records in different entities
        search.index_record("Article", "a1", "Python programming guide")
        search.index_record("Article", "a2", "Python web development")
        search.index_record("Tutorial", "t1", "Python tutorial for beginners")
        search.index_record("Book", "b1", "Learning Python book")

        # Search only in Article entity
        results = search.search("Python", entities=["Article"])
        assert len(results) == 2
        assert all(r.entity == "Article" for r in results)

        # Search only in Tutorial entity
        results = search.search("Python", entities=["Tutorial"])
        assert len(results) == 1
        assert results[0].entity == "Tutorial"

    def test_search_filters_by_min_score(self, tmp_path):
        """Search should exclude results below min_score threshold."""
        from sqlalchemy import create_engine

        from kameleondb.search import SearchEngine

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        search = SearchEngine(engine, embedding_provider=None)

        # Index one highly relevant and one loosely relevant record
        search.index_record("Article", "1", "Python programming Python Python")
        search.index_record("Article", "2", "introduction to programming")

        # Search with no min_score
        results = search.search("Python programming")
        no_filter_count = len(results)

        # Search with high min_score - should filter out weak matches
        results = search.search("Python programming", min_score=5.0)
        assert len(results) <= no_filter_count
        # All results should have score >= min_score
        assert all(r.score >= 5.0 for r in results)

    def test_search_orders_by_relevance(self, tmp_path):
        """Results should be ordered by relevance score."""
        from sqlalchemy import create_engine

        from kameleondb.search import SearchEngine

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        search = SearchEngine(engine, embedding_provider=None)

        # Index records with varying relevance to query
        search.index_record("Article", "1", "Python programming tutorial")  # high relevance
        search.index_record("Article", "2", "tutorial introduction")  # low relevance
        search.index_record("Article", "3", "Python Python programming")  # higher relevance

        results = search.search("Python programming")

        # Results should be ordered by score (descending)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

        # Most relevant article should be first
        assert results[0].id == "3"  # has "Python" twice

    def test_search_across_multiple_entities(self, tmp_path):
        """Search should work across multiple entities when entities= is provided."""
        from sqlalchemy import create_engine

        from kameleondb.search import SearchEngine

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        search = SearchEngine(engine, embedding_provider=None)

        # Index records in different entities
        search.index_record("Article", "a1", "Python programming")
        search.index_record("Tutorial", "t1", "Python tutorial")
        search.index_record("Book", "b1", "Python book")
        search.index_record("Video", "v1", "JavaScript video")

        # Search across Article and Tutorial only
        results = search.search("Python", entities=["Article", "Tutorial"])
        assert len(results) == 2
        entities = {r.entity for r in results}
        assert entities == {"Article", "Tutorial"}

        # Search across all entities (no filter)
        results = search.search("Python")
        assert len(results) == 3  # Article, Tutorial, Book

    def test_search_returns_empty_list_when_no_matches(self, tmp_path):
        """Search should return empty list when nothing matches."""
        from sqlalchemy import create_engine

        from kameleondb.search import SearchEngine

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        search = SearchEngine(engine, embedding_provider=None)

        # Index some records
        search.index_record("Article", "1", "Python programming")
        search.index_record("Article", "2", "JavaScript development")

        # Search for something unrelated
        results = search.search("Rust quantum computing blockchain")
        assert results == []


class TestKameleonDBSearchIntegration:
    """Test search integration with KameleonDB."""

    def test_build_embed_content(self, tmp_path):
        """_build_embed_content should format fields correctly."""
        db = KameleonDB(f"sqlite:///{tmp_path}/test.db")
        try:
            content = db._build_embed_content(
                {"title": "Hello", "body": "World", "id": "123"},
                ["title", "body"],
            )
            assert content == "title: Hello | body: World"
        finally:
            db.close()

    def test_build_embed_content_skips_none(self, tmp_path):
        """_build_embed_content should skip None values."""
        db = KameleonDB(f"sqlite:///{tmp_path}/test.db")
        try:
            content = db._build_embed_content(
                {"title": "Hello", "body": None},
                ["title", "body"],
            )
            assert content == "title: Hello"
        finally:
            db.close()

    def test_get_embed_fields_returns_text_fields(self, tmp_path):
        """_get_embed_fields should return text/string fields by default."""
        db = KameleonDB(f"sqlite:///{tmp_path}/test.db")
        try:
            db.create_entity(
                "Article",
                fields=[
                    {"name": "title", "type": "string"},
                    {"name": "body", "type": "text"},
                    {"name": "views", "type": "int"},
                    {"name": "published", "type": "bool"},
                ],
            )
            embed_fields = db._get_embed_fields("Article")
            assert "title" in embed_fields
            assert "body" in embed_fields
            assert "views" not in embed_fields
            assert "published" not in embed_fields
        finally:
            db.close()
