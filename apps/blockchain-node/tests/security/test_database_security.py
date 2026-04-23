"""
Security tests for database access restrictions.

Tests that database manipulation is not possible without detection.
import sys
"""

import os
import stat
import pytest
from pathlib import Path

from aitbc_chain.database import DatabaseOperationValidator, init_db
from aitbc_chain.config import settings


class TestDatabaseSecurity:
    """Test database security measures."""
    
    def test_database_file_permissions(self):
        """Test that database file has restrictive permissions."""
        # Initialize database
        init_db()
        
        # Check file permissions
        db_path = settings.db_path
        if db_path.exists():
            file_stat = os.stat(db_path)
            mode = file_stat.st_mode
            
            # Check that file is readable/writable only by owner (600)
            assert mode & stat.S_IRUSR  # Owner can read
            assert mode & stat.S_IWUSR  # Owner can write
            assert not (mode & stat.S_IRGRP)  # Group cannot read
            assert not (mode & stat.S_IWGRP)  # Group cannot write
            assert not (mode & stat.S_IROTH)  # Others cannot read
            assert not (mode & stat.S_IWOTH)  # Others cannot write
    
    def test_operation_validator_allowed_operations(self):
        """Test that operation validator allows valid operations."""
        validator = DatabaseOperationValidator()
        
        assert validator.validate_operation('select')
        assert validator.validate_operation('insert')
        assert validator.validate_operation('update')
        assert validator.validate_operation('delete')
        assert not validator.validate_operation('drop')
        assert not validator.validate_operation('truncate')
    
    def test_operation_validator_dangerous_queries(self):
        """Test that operation validator blocks dangerous queries."""
        validator = DatabaseOperationValidator()
        
        # Dangerous patterns should be blocked
        assert not validator.validate_query('DROP TABLE account')
        assert not validator.validate_query('DROP DATABASE')
        assert not validator.validate_query('TRUNCATE account')
        assert not validator.validate_query('ALTER TABLE account')
        assert not validator.validate_query('DELETE FROM account')
        assert not validator.validate_query('UPDATE account SET balance')
        
        # Safe queries should pass
        assert validator.validate_query('SELECT * FROM account')
        assert validator.validate_query('INSERT INTO transaction VALUES')
        assert validator.validate_query('UPDATE block SET height = 1')
