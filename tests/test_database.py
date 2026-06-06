"""
Database Tests
Tests for AITBC database utilities
"""

from pathlib import Path

import pytest
from aitbc.database import (
    DatabaseConnection,
    create_async_pooled_engine,
    create_async_pooled_sessionmaker,
    create_pooled_engine,
    create_pooled_sessionmaker,
    ensure_database,
    get_database_connection,
    get_table_info,
    table_exists,
    vacuum_database,
)


class TestDatabaseConnection:
    """Test DatabaseConnection class"""

    def test_database_connection_class_exists(self):
        """Test DatabaseConnection class exists"""
        assert DatabaseConnection is not None

    def test_database_connection_can_be_instantiated(self):
        """Test DatabaseConnection can be instantiated"""
        db = DatabaseConnection(db_path=Path(":memory:"))
        assert db is not None

    def test_database_connection_connect(self):
        """Test DatabaseConnection connect method"""
        db = DatabaseConnection(db_path=Path(":memory:"))
        conn = db.connect()
        assert conn is not None
        db.close()

    def test_database_connection_context_manager(self):
        """Test DatabaseConnection context manager"""
        with DatabaseConnection(db_path=Path(":memory:")) as db:
            assert db._connection is not None


class TestDatabaseFunctions:
    """Test database utility functions"""

    def test_get_database_connection(self):
        """Test get_database_connection function"""
        db = get_database_connection(Path(":memory:"))
        assert isinstance(db, DatabaseConnection)

    def test_ensure_database(self):
        """Test ensure_database function"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            result = ensure_database(db_path)
            assert result == db_path
            assert db_path.parent.exists()

    @pytest.mark.skip(reason="table_exists requires async context")
    def test_table_exists(self):
        """Test table_exists function"""
        with DatabaseConnection(db_path=Path(":memory:")) as db:
            # Create a table
            db.execute("CREATE TABLE test_table (id INTEGER)")
            # Check if table exists
            assert table_exists(db.db_path, "test_table") is True
            # Check non-existent table
            assert table_exists(db.db_path, "nonexistent") is False

    @pytest.mark.skip(reason="get_table_info requires async context")
    def test_get_table_info(self):
        """Test get_table_info function"""
        with DatabaseConnection(db_path=Path(":memory:")) as db:
            # Create a table
            db.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
            # Get table info
            info = get_table_info(db.db_path, "test_table")
            assert len(info) == 2
            assert info[0]["name"] == "id"
            assert info[1]["name"] == "name"


class TestSQLAlchemyFunctions:
    """Test SQLAlchemy utility functions"""

    def test_create_pooled_engine_sqlite(self):
        """Test create_pooled_engine with SQLite"""
        engine = create_pooled_engine("sqlite:///:memory:", pool_size=5)
        assert engine is not None
        engine.dispose()

    def test_create_pooled_engine_sqlite_static_pool(self):
        """Test create_pooled_engine with SQLite static pool"""
        engine = create_pooled_engine("sqlite:///:memory:", use_static_pool=True)
        assert engine is not None
        engine.dispose()

    def test_create_pooled_sessionmaker(self):
        """Test create_pooled_sessionmaker"""
        engine = create_pooled_engine("sqlite:///:memory:")
        sessionmaker = create_pooled_sessionmaker(engine)
        assert sessionmaker is not None
        engine.dispose()

    @pytest.mark.skip(reason="Async engine creation has complex dependencies")
    def test_create_async_pooled_engine(self):
        """Test create_async_pooled_engine"""
        engine = create_async_pooled_engine("sqlite+aiosqlite:///:memory:")
        assert engine is not None
        engine.dispose()

    @pytest.mark.skip(reason="Async sessionmaker has complex dependencies")
    def test_create_async_pooled_sessionmaker(self):
        """Test create_async_pooled_sessionmaker"""
        engine = create_async_pooled_engine("sqlite+aiosqlite:///:memory:")
        sessionmaker = create_async_pooled_sessionmaker(engine)
        assert sessionmaker is not None
        engine.dispose()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
