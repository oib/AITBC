"""Additional tests for wallet CLI commands"""

import os
import json
import pytest
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.commands.wallet import wallet

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def mock_wallet_dir(tmp_path):
    wallet_dir = tmp_path / "wallets"
    wallet_dir.mkdir()
    
    # Create a dummy wallet file
    wallet_file = wallet_dir / "test_wallet.json"
    wallet_data = {
        "address": "aitbc1test",
        "private_key": "test_key",
        "public_key": "test_pub"
    }
    with open(wallet_file, "w") as f:
        json.dump(wallet_data, f)
        
    return wallet_dir

class TestWalletAdditionalCommands:
    
    def test_backup_wallet_success(self, runner, mock_wallet_dir, tmp_path):
        """Test successful wallet backup"""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        backup_path = backup_dir / "backup.json"
        
        # We need to test the backup command properly.
        # click might suppress exception output if not configured otherwise.
        result = runner.invoke(wallet, [
            'backup', 'test_wallet', '--destination', str(backup_path)
        ], obj={"wallet_dir": mock_wallet_dir, "output_format": "json"}, catch_exceptions=False)
        
        assert result.exit_code == 0
        assert os.path.exists(backup_path)
        
    def test_backup_wallet_not_found(self, runner, mock_wallet_dir):
        """Test backing up non-existent wallet"""
        # We handle raise click.Abort()
        result = runner.invoke(wallet, [
            'backup', 'non_existent_wallet'
        ], obj={"wallet_dir": mock_wallet_dir, "output_format": "json"})
        
        assert result.exit_code != 0
        
    def test_delete_wallet_success(self, runner, mock_wallet_dir):
        """Test successful wallet deletion"""
        result = runner.invoke(wallet, [
            'delete', 'test_wallet', '--confirm'
        ], obj={"wallet_dir": mock_wallet_dir, "output_format": "json"})
        
        assert result.exit_code == 0
        assert not os.path.exists(mock_wallet_dir / "test_wallet.json")
        
    def test_delete_wallet_not_found(self, runner, mock_wallet_dir):
        """Test deleting non-existent wallet"""
        result = runner.invoke(wallet, [
            'delete', 'non_existent', '--confirm'
        ], obj={"wallet_dir": mock_wallet_dir, "output_format": "json"})
        
        assert result.exit_code != 0

