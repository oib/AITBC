"""
Security Init Tests
Tests for security module initialization
"""

import sys
from pathlib import Path

# Add CLI path for imports
cli_path = Path("/opt/aitbc/cli")
if str(cli_path) not in sys.path:
    sys.path.insert(0, str(cli_path))

import pytest


class TestSecurityInit:
    """Test security module initialization"""

    def test_security_module_imports(self):
        """Test that security module exports expected items"""
        from security import (
            CLITranslationSecurityManager,
            SecurityLevel,
            TranslationMode,
            cli_translation_security,
            secure_translation,
            configure_translation_security,
            get_translation_security_report
        )
        
        assert CLITranslationSecurityManager is not None
        assert SecurityLevel is not None
        assert TranslationMode is not None
        assert cli_translation_security is not None
        assert secure_translation is not None
        assert configure_translation_security is not None
        assert get_translation_security_report is not None

    def test_security_all_exports(self):
        """Test __all__ contains expected exports"""
        import security
        
        expected_exports = [
            "CLITranslationSecurityManager",
            "SecurityLevel",
            "TranslationMode",
            "cli_translation_security",
            "secure_translation",
            "configure_translation_security",
            "get_translation_security_report"
        ]
        
        for export in expected_exports:
            assert export in security.__all__


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
