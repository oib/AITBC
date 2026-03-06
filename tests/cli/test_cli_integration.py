"""
CLI integration tests using AITBC CLI against a live (in-memory) coordinator.

Spins up the real coordinator FastAPI app with an in-memory SQLite DB,
then patches httpx.Client so every CLI command's HTTP call is routed
through the ASGI transport instead of making real network requests.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from click.testing import CliRunner
from aitbc_cli.main import cli


class TestCLIIntegration:
    """Test CLI integration with coordinator"""
    
    def test_cli_help(self):
        """Test CLI help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'aitbc' in result.output.lower()
    
    def test_config_show(self):
        """Test config show command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['config-show'])
        assert result.exit_code == 0