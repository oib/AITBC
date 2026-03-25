import sys
from click.testing import CliRunner
from aitbc_cli.commands.node import node
from aitbc_cli.core.config import MultiChainConfig
from unittest.mock import patch, MagicMock
import sys

runner = CliRunner()
with patch('aitbc_cli.commands.node.load_multichain_config') as mock_load:
    with patch('aitbc_cli.commands.node.get_default_node_config') as mock_default:
        with patch('aitbc_cli.commands.node.add_node_config') as mock_add:
            # The function does `from ..core.config import save_multichain_config`
            # This evaluates to `aitbc_cli.core.config` because node.py is in `aitbc_cli.commands`
            with patch('aitbc_cli.core.config.save_multichain_config') as mock_save:
                # The issue with the previous run was not that save_multichain_config wasn't patched correctly.
                # The issue is that click catches exceptions and prints the generic "Error adding node: ...".
                # Wait, "Failed to save configuration" actually implies the unpatched save_multichain_config was CALLED!
                
                # Let's mock at sys.modules level for Python relative imports
                pass

with patch('aitbc_cli.commands.node.load_multichain_config') as mock_load:
    with patch('aitbc_cli.commands.node.get_default_node_config') as mock_default:
        with patch('aitbc_cli.commands.node.add_node_config') as mock_add:
            # the easiest way is to patch it in the exact module it is executed 
            # OR we can just avoid testing the mock_save and let it save to a temp config!
            # Let's check how config is loaded in node.py
            pass
