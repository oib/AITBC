"""Tests for wallet commands using AITBC CLI"""

import pytest
import json
import re
import tempfile
import os
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.main import cli


def extract_json_from_output(output):
    """Extract JSON from CLI output"""
    try:
        # Look for JSON blocks in output
        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return None
    except json.JSONDecodeError:
        return None


class TestWalletCommands:
    """Test suite for wallet commands"""
    
    def test_wallet_help(self):
        """Test wallet help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['wallet', '--help'])
        assert result.exit_code == 0
        assert 'wallet' in result.output.lower()
    
    def test_wallet_create(self):
        """Test wallet creation"""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set wallet directory in environment
            env = {'WALLET_DIR': temp_dir}
            # Use unique wallet name with timestamp
            import time
            wallet_name = f"test-wallet-{int(time.time())}"
            result = runner.invoke(cli, ['wallet', 'create', wallet_name], env=env)
            print(f"Exit code: {result.exit_code}")
            print(f"Output: {result.output}")
            print(f"Temp dir contents: {list(Path(temp_dir).iterdir())}")
            assert result.exit_code == 0
            # Check if wallet was created successfully
            assert 'created' in result.output.lower() or 'wallet' in result.output.lower()
    
    def test_wallet_balance(self):
        """Test wallet balance command"""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set wallet directory in environment
            env = {'WALLET_DIR': temp_dir}
            # Use unique wallet name
            import time
            wallet_name = f"test-wallet-balance-{int(time.time())}"
            # Create wallet first
            create_result = runner.invoke(cli, ['wallet', 'create', wallet_name], env=env)
            assert create_result.exit_code == 0
            
            # Switch to the created wallet
            switch_result = runner.invoke(cli, ['wallet', 'switch', wallet_name], env=env)
            assert switch_result.exit_code == 0
            
            # Check balance (uses current active wallet)
            result = runner.invoke(cli, ['wallet', 'balance'], env=env)
            print(f"Balance exit code: {result.exit_code}")
            print(f"Balance output: {result.output}")
            assert result.exit_code == 0
            # Should contain balance information
            assert 'balance' in result.output.lower() or 'aitbc' in result.output.lower()
   