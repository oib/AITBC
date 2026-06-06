"""
Template for testing CLI commands.

Copy this file to tests/cli/test_<command_name>.py and customize for your command.
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
import sys

# Add CLI to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'cli'))


class Test{{CommandName}}:
    """Test suite for {{command_name}} command."""
    
    def test_parser_registration(self):
        """Test that parser is registered in parsers/__init__.py."""
        from parsers import __init__
        # Check that parser is imported
        assert hasattr(__init__, '{{command_name}}')
    
    def test_parser_has_register_function(self):
        """Test that parser has register function."""
        from parsers import {{command_name}}
        assert hasattr({{command_name}}, 'register')
        assert callable({{command_name}}.register)
    
    def test_handler_exists(self):
        """Test that handler module exists."""
        from handlers import {{command_name}}
        assert hasattr({{command_name}}, 'handle_{{command_name}}_action')
    
    def test_handler_signature(self):
        """Test that handler has correct signature."""
        from handlers import {{command_name}}
        import inspect
        
        sig = inspect.signature({{command_name}}.handle_{{command_name}}_action)
        params = list(sig.parameters.keys())
        
        # Should have args and render_mapping
        assert 'args' in params
        assert 'render_mapping' in params
    
    @patch('handlers.{{command_name}}.render_mapping')
    def test_handler_execution(self, mock_render):
        """Test that handler executes successfully."""
        from handlers import {{command_name}}
        from argparse import Namespace
        
        args = Namespace(option="test_value")
        {{command_name}}.handle_{{command_name}}_action(args, mock_render)
        
        # Verify render_mapping was called
        assert mock_render.called
    
    def test_handler_returns_structured_data(self):
        """Test that handler returns structured data."""
        from handlers import {{command_name}}
        from argparse import Namespace
        
        mock_render = Mock()
        args = Namespace(option="test_value")
        
        {{command_name}}.handle_{{command_name}}_action(args, mock_render)
        
        # Verify render_mapping was called with structured data
        call_args = mock_render.call_args
        assert len(call_args[0]) == 2  # label and data
        assert isinstance(call_args[0][1], dict)  # data should be dict
    
    def test_command_help(self):
        """Test that command help works."""
        import subprocess
        result = subprocess.run(
            [sys.executable, '/opt/aitbc/cli/unified_cli.py', '{{command_name}}', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert '{{command_name}}' in result.stdout.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
