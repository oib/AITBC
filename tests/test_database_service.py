"""
Database Service Tests
Tests for AITBC database service layer
"""

import tempfile
from pathlib import Path

import pytest

from aitbc.database_service import (
    DatabaseService,
    DatabaseServiceFactory,
    SQLiteDatabaseService,
)


class TestDatabaseService:
    """Test DatabaseService abstract class"""

    def test_database_service_is_abstract(self):
        """Test DatabaseService cannot be instantiated directly"""
        with pytest.raises(TypeError):
            DatabaseService()

    def test_database_service_has_abstract_methods(self):
        """Test DatabaseService defines required abstract methods"""
        assert hasattr(DatabaseService, "execute_query")
        assert hasattr(DatabaseService, "execute_update")
        assert hasattr(DatabaseService, "execute_transaction")


class TestSQLiteDatabaseService:
    """Test SQLiteDatabaseService class"""

    def test_initialization(self):
        """Test SQLiteDatabaseService initialization"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path, pool_size=5)

            assert service.db_path == db_path
            assert service.pool_size == 5
            assert service._connections == []
            assert db_path.exists()

    def test_initialization_creates_directory(self):
        """Test initialization creates parent directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "subdir" / "test.db"
            SQLiteDatabaseService(db_path)

            assert db_path.parent.exists()
            assert db_path.exists()

    def test_get_connection(self):
        """Test get_connection creates new connection"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            with service.get_connection() as conn:
                assert conn is not None

    def test_get_connection_commits_on_success(self):
        """Test get_connection commits on success"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            with service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE test (id INTEGER)")

            # Verify table exists
            with service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test'")
                result = cursor.fetchone()
                assert result is not None

    def test_get_connection_rolls_back_on_error(self):
        """Test get_connection rolls back on error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            # Create table first (DDL is auto-committed in SQLite)
            with service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE test (id INTEGER)")

            with pytest.raises(Exception):
                with service.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO test (id) VALUES (1)")
                    raise Exception("Test error")

            # Verify insert was rolled back
            with service.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM test")
                result = cursor.fetchone()
                assert result is None

    def test_execute_query(self):
        """Test execute_query method"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            # Create table and insert data
            service.execute_update("CREATE TABLE test (id INTEGER, name TEXT)")
            service.execute_update("INSERT INTO test (id, name) VALUES (?, ?)", (1, "Alice"))
            service.execute_update("INSERT INTO test (id, name) VALUES (?, ?)", (2, "Bob"))

            # Query data
            results = service.execute_query("SELECT * FROM test")

            assert len(results) == 2
            assert results[0]["id"] == 1
            assert results[0]["name"] == "Alice"
            assert results[1]["id"] == 2
            assert results[1]["name"] == "Bob"

    def test_execute_query_with_params(self):
        """Test execute_query with parameters"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            service.execute_update("CREATE TABLE test (id INTEGER, name TEXT)")
            service.execute_update("INSERT INTO test (id, name) VALUES (?, ?)", (1, "Alice"))
            service.execute_update("INSERT INTO test (id, name) VALUES (?, ?)", (2, "Bob"))

            results = service.execute_query("SELECT * FROM test WHERE id = ?", (1,))

            assert len(results) == 1
            assert results[0]["name"] == "Alice"

    def test_execute_query_empty_result(self):
        """Test execute_query with empty result"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            service.execute_update("CREATE TABLE test (id INTEGER)")

            results = service.execute_query("SELECT * FROM test")
            assert results == []

    def test_execute_update(self):
        """Test execute_update method"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            service.execute_update("CREATE TABLE test (id INTEGER, name TEXT)")

            rowcount = service.execute_update("INSERT INTO test (id, name) VALUES (?, ?)", (1, "Alice"))
            assert rowcount == 1

    def test_execute_update_multiple_rows(self):
        """Test execute_update affects multiple rows"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            service.execute_update("CREATE TABLE test (id INTEGER, active INTEGER)")
            service.execute_update("INSERT INTO test (id, active) VALUES (?, ?)", (1, 1))
            service.execute_update("INSERT INTO test (id, active) VALUES (?, ?)", (2, 1))
            service.execute_update("INSERT INTO test (id, active) VALUES (?, ?)", (3, 0))

            rowcount = service.execute_update("UPDATE test SET active = 0 WHERE active = 1")
            assert rowcount == 2

    def test_execute_transaction(self):
        """Test execute_transaction method"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            service.execute_update("CREATE TABLE test (id INTEGER, name TEXT)")

            queries = [
                ("INSERT INTO test (id, name) VALUES (?, ?)", (1, "Alice")),
                ("INSERT INTO test (id, name) VALUES (?, ?)", (2, "Bob")),
                ("INSERT INTO test (id, name) VALUES (?, ?)", (3, "Charlie")),
            ]

            result = service.execute_transaction(queries)
            assert result is True

            # Verify all rows inserted
            results = service.execute_query("SELECT * FROM test")
            assert len(results) == 3

    def test_execute_transaction_rollback_on_error(self):
        """Test execute_transaction rolls back on error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            service.execute_update("CREATE TABLE test (id INTEGER, name TEXT)")

            queries = [
                ("INSERT INTO test (id, name) VALUES (?, ?)", (1, "Alice")),
                ("INSERT INTO test (id, name) VALUES (?, ?)", (2, "Bob")),
                ("INSERT INTO test (id, name, invalid) VALUES (?, ?, ?)", (3, "Charlie", "error")),  # Invalid
            ]

            with pytest.raises(Exception):
                service.execute_transaction(queries)

            # Verify no rows inserted
            results = service.execute_query("SELECT * FROM test")
            assert len(results) == 0

    def test_connection_pooling(self):
        """Test connection pooling"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path, pool_size=3)

            # Get multiple connections
            service._get_connection()
            service._get_connection()
            service._get_connection()

            assert len(service._connections) == 3

            # Should reuse connections
            service._get_connection()
            assert len(service._connections) == 3

    def test_close(self):
        """Test close method"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = SQLiteDatabaseService(db_path)

            # Create some connections
            service._get_connection()
            service._get_connection()

            assert len(service._connections) == 2

            service.close()

            assert len(service._connections) == 0


class TestDatabaseServiceFactory:
    """Test DatabaseServiceFactory class"""

    def test_create_sqlite_service(self):
        """Test create_sqlite_service method"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = DatabaseServiceFactory.create_sqlite_service(db_path, pool_size=5)

            assert isinstance(service, SQLiteDatabaseService)
            assert service.db_path == db_path
            assert service.pool_size == 5

    def test_create_service_sqlite(self):
        """Test create_service with sqlite type"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            service = DatabaseServiceFactory.create_service("sqlite", db_path=db_path, pool_size=3)

            assert isinstance(service, SQLiteDatabaseService)

    def test_create_service_unknown_type(self):
        """Test create_service with unknown type raises error"""
        with pytest.raises(ValueError) as exc_info:
            DatabaseServiceFactory.create_service("unknown_type")

        assert "Unknown database type" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
