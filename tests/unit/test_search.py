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
        search = SearchEngine(engine, embedding_provider=None)

        # Check tables exist
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='kdb_search'")
            )
            assert result.fetchone() is not None

            # FTS table should also exist
            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='kdb_search_fts'"
                )
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
            result = conn.execute(
                text("SELECT COUNT(*) FROM kdb_search WHERE record_id = '1'")
            )
            assert result.scalar() == 1

        # Delete it
        search.delete_record("Article", "1")

        # Verify it's gone
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM kdb_search WHERE record_id = '1'")
            )
            assert result.scalar() == 0


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
