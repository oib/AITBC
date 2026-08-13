"""Security tests for database access restrictions.

Tests that database manipulation is not possible without detection.
"""

from aitbc_chain.database import DatabaseOperationValidator


class TestDatabaseSecurity:
    """Test database security measures."""

    def test_operation_validator_allowed_operations(self):
        """Test that operation validator allows valid operations."""
        validator = DatabaseOperationValidator()

        assert validator.validate_operation("select")
        assert validator.validate_operation("insert")
        assert validator.validate_operation("update")
        assert validator.validate_operation("delete")
        assert not validator.validate_operation("drop")
        assert not validator.validate_operation("truncate")

    def test_operation_validator_dangerous_queries(self):
        """Test that operation validator blocks dangerous queries."""
        validator = DatabaseOperationValidator()

        # Dangerous patterns should be blocked
        assert not validator.validate_query("DROP TABLE account")
        assert not validator.validate_query("DROP DATABASE")
        assert not validator.validate_query("TRUNCATE account")
        assert not validator.validate_query("ALTER TABLE account")
        assert not validator.validate_query("DELETE FROM account")
        assert not validator.validate_query("UPDATE account SET balance")

        # Safe queries should pass
        assert validator.validate_query("SELECT * FROM account")
        assert validator.validate_query("INSERT INTO transaction VALUES")
        assert validator.validate_query("UPDATE block SET height = 1")
