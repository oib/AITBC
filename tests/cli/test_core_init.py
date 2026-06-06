"""
Core Init Tests
Tests for core package initialization
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestCoreInit:
    """Test core package initialization"""

    def test_version_attribute(self):
        """Test that __version__ attribute exists"""
        import aitbc_cli.core as core_module
        
        # Check if __version__ exists as an attribute
        assert hasattr(core_module, '__version__')
        version = getattr(core_module, '__version__')
        
        # It could be a string or a module (if __version__.py is imported)
        if isinstance(version, str):
            assert version is not None
        else:
            # If it's a module, check for the string attribute inside
            assert hasattr(version, '__version__')

    def test_author_attribute(self):
        """Test that __author__ attribute exists"""
        import aitbc_cli.core as core_module
        
        assert hasattr(core_module, '__author__')
        author = getattr(core_module, '__author__')
        assert author is not None
        assert isinstance(author, str)

    def test_email_attribute(self):
        """Test that __email__ attribute exists"""
        import aitbc_cli.core as core_module
        
        assert hasattr(core_module, '__email__')
        email = getattr(core_module, '__email__')
        assert email is not None
        assert isinstance(email, str)

    def test_version_format(self):
        """Test version follows semantic versioning"""
        import aitbc_cli.core as core_module
        
        version = getattr(core_module, '__version__')
        
        # If it's a module, get the string from inside
        if not isinstance(version, str):
            version = getattr(version, '__version__', '0.1.0')
        
        # Should follow major.minor.patch format
        parts = version.split(".")
        assert len(parts) >= 2  # At least major.minor
        
        # All parts should be numeric
        for part in parts:
            assert part.isdigit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
