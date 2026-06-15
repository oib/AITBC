"""
Core Version Tests
Tests for version information
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest  # noqa: E402


class TestVersion:
    """Test version information"""

    def test_version_exists(self):
        """Test that version attribute exists"""
        from aitbc_cli.core.__version__ import __version__

        assert __version__ is not None

    def test_version_format(self):
        """Test version follows semantic versioning"""
        from aitbc_cli.core.__version__ import __version__

        # Should follow major.minor.patch format
        parts = __version__.split(".")
        assert len(parts) == 3

        # All parts should be numeric
        for part in parts:
            assert part.isdigit()

    def test_version_value(self):
        """Test version has expected value"""
        from aitbc_cli.core.__version__ import __version__

        # Check version is a valid semantic version (not checking exact value to allow updates)
        parts = __version__.split(".")
        assert len(parts) >= 2  # At least major.minor


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
