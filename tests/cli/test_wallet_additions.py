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
        "public_key": "test_pub",
        "transactions": [],
        "balance": 0.0
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
        
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'backup', 'test_wallet', '--destination', str(backup_path)
        ], catch_exceptions=False)
        
        assert result.exit_code == 0
        assert os.path.exists(backup_path)
        
    def test_backup_wallet_not_found(self, runner, mock_wallet_dir):
        """Test backing up non-existent wallet"""
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'backup', 'non_existent_wallet'
        ])
        
        assert "does not exist" in result.output.lower()
        
    def test_delete_wallet_success(self, runner, mock_wallet_dir):
        """Test successful wallet deletion"""
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'delete', 'test_wallet', '--confirm'
        ])
        
        assert result.exit_code == 0
        assert not os.path.exists(mock_wallet_dir / "test_wallet.json")
        
    def test_delete_wallet_not_found(self, runner, mock_wallet_dir):
        """Test deleting non-existent wallet"""
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'delete', 'non_existent', '--confirm'
        ])
        
        assert "does not exist" in result.output.lower()

    
    @patch('aitbc_cli.commands.wallet._save_wallet')
    def test_earn_success(self, mock_save, runner, mock_wallet_dir):
        """Test successful wallet earning"""
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'earn', '10.5', 'job_123'
        ])
        
        assert result.exit_code == 0
        assert "earnings added" in result.output.lower()
        mock_save.assert_called_once()
        
    def test_earn_wallet_not_found(self, runner, mock_wallet_dir):
        """Test earning to non-existent wallet"""
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "non_existent.json"),
            'earn', '10.5', 'job_123'
        ])
        
        assert "not found" in result.output.lower()

    
    def test_restore_wallet_success(self, runner, mock_wallet_dir, tmp_path):
        """Test successful wallet restore"""
        # Create a backup file to restore from
        backup_file = tmp_path / "backup.json"
        with open(backup_file, "w") as f:
            json.dump({"address": "restored", "transactions": []}, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "new_wallet.json"),
            'restore', str(backup_file), 'new_wallet'
        ])
        
        assert result.exit_code == 0
        assert os.path.exists(mock_wallet_dir / "new_wallet.json")
        with open(mock_wallet_dir / "new_wallet.json", "r") as f:
            data = json.load(f)
            assert data["address"] == "restored"
            
    def test_restore_wallet_exists(self, runner, mock_wallet_dir, tmp_path):
        """Test restoring to an existing wallet without force"""
        backup_file = tmp_path / "backup.json"
        with open(backup_file, "w") as f:
            json.dump({"address": "restored", "transactions": []}, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'restore', str(backup_file), 'test_wallet'
        ])
        
        assert "already exists" in result.output.lower()

    def test_restore_wallet_force(self, runner, mock_wallet_dir, tmp_path):
        """Test restoring to an existing wallet with force"""
        backup_file = tmp_path / "backup.json"
        with open(backup_file, "w") as f:
            json.dump({"address": "restored", "transactions": []}, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'restore', str(backup_file), 'test_wallet', '--force'
        ])
        
        assert result.exit_code == 0
        with open(mock_wallet_dir / "test_wallet.json", "r") as f:
            data = json.load(f)
            assert data["address"] == "restored"

