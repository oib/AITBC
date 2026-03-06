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

    def test_wallet_history_success(self, runner, mock_wallet_dir):
        """Test successful wallet history display"""
        # Add transactions to wallet
        wallet_data = {
            "address": "test_address",
            "transactions": [
                {"type": "earn", "amount": 10.5, "description": "Job 1", "timestamp": "2023-01-01T10:00:00"},
                {"type": "spend", "amount": -2.0, "description": "Purchase", "timestamp": "2023-01-02T15:30:00"},
                {"type": "earn", "amount": 5.0, "description": "Job 2", "timestamp": "2023-01-03T09:15:00"},
            ]
        }
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'history', '--limit', '2'
        ])
        
        assert result.exit_code == 0
        assert "transactions" in result.output.lower()
        
    def test_wallet_history_empty(self, runner, mock_wallet_dir):
        """Test wallet history with no transactions"""
        wallet_data = {"address": "test_address", "transactions": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'history'
        ])
        
        assert result.exit_code == 0
        
    def test_wallet_history_not_found(self, runner, mock_wallet_dir):
        """Test wallet history for non-existent wallet"""
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "non_existent.json"),
            'history'
        ])
        
        assert "not found" in result.output.lower()

    def test_wallet_info_success(self, runner, mock_wallet_dir):
        """Test successful wallet info display"""
        wallet_data = {
            "wallet_id": "test_wallet",
            "type": "hd",
            "address": "aitbc1test123",
            "public_key": "0xtestpub",
            "created_at": "2023-01-01T00:00:00Z",
            "balance": 15.5
        }
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'info'
        ])
        
        assert result.exit_code == 0
        assert "test_wallet" in result.output
        assert "aitbc1test123" in result.output
        
    def test_wallet_info_not_found(self, runner, mock_wallet_dir):
        """Test wallet info for non-existent wallet"""
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "non_existent.json"),
            'info'
        ])
        
        assert "not found" in result.output.lower()

    def test_liquidity_stake_success(self, runner, mock_wallet_dir):
        """Test successful liquidity stake"""
        wallet_data = {"address": "test_address", "balance": 100.0, "transactions": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        with patch('aitbc_cli.commands.wallet._save_wallet') as mock_save:
            result = runner.invoke(wallet, [
                '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
                'liquidity-stake', '50.0', '--pool', 'main', '--lock-days', '30'
            ])
            
            assert result.exit_code == 0
            assert "staked" in result.output.lower()
            assert "gold" in result.output.lower()  # 30-day lock = gold tier
            mock_save.assert_called_once()
            
    def test_liquidity_stake_insufficient_balance(self, runner, mock_wallet_dir):
        """Test liquidity stake with insufficient balance"""
        wallet_data = {"address": "test_address", "balance": 10.0, "transactions": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'liquidity-stake', '50.0'
        ])
        
        assert "insufficient balance" in result.output.lower()

    def test_send_success_local(self, runner, mock_wallet_dir):
        """Test successful send transaction (local fallback)"""
        wallet_data = {"address": "aitbc1sender", "balance": 100.0, "transactions": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        with patch('aitbc_cli.commands.wallet._save_wallet') as mock_save:
            result = runner.invoke(wallet, [
                '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
                'send', 'aitbc1recipient', '25.0',
                '--description', 'Test payment'
            ])
            
            assert result.exit_code == 0
            assert "recorded locally" in result.output.lower()
            mock_save.assert_called_once()
            
    def test_send_insufficient_balance(self, runner, mock_wallet_dir):
        """Test send with insufficient balance"""
        wallet_data = {"address": "aitbc1sender", "balance": 10.0, "transactions": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'send', 'aitbc1recipient', '25.0'
        ])
        
        assert "insufficient balance" in result.output.lower()
        
    def test_spend_success(self, runner, mock_wallet_dir):
        """Test successful spend transaction"""
        wallet_data = {"address": "test_address", "balance": 100.0, "transactions": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        with patch('aitbc_cli.commands.wallet._save_wallet') as mock_save:
            result = runner.invoke(wallet, [
                '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
                'spend', '25.0', 'Test purchase'
            ])
            
            assert result.exit_code == 0
            assert "spent" in result.output.lower()
            mock_save.assert_called_once()
            
    def test_spend_insufficient_balance(self, runner, mock_wallet_dir):
        """Test spend with insufficient balance"""
        wallet_data = {"address": "test_address", "balance": 10.0, "transactions": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'spend', '25.0', 'Test purchase'
        ])
        
        assert "insufficient balance" in result.output.lower()

    def test_stake_success(self, runner, mock_wallet_dir):
        """Test successful staking"""
        wallet_data = {"address": "test_address", "balance": 100.0, "transactions": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        with patch('aitbc_cli.commands.wallet._save_wallet') as mock_save:
            result = runner.invoke(wallet, [
                '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
                'stake', '50.0', '--duration', '30'
            ])
            
            assert result.exit_code == 0
            assert "staked" in result.output.lower()
            mock_save.assert_called_once()
            
    def test_stake_insufficient_balance(self, runner, mock_wallet_dir):
        """Test stake with insufficient balance"""
        wallet_data = {"address": "test_address", "balance": 10.0, "transactions": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'stake', '50.0'
        ])
        
        assert "insufficient balance" in result.output.lower()

    def test_staking_info_success(self, runner, mock_wallet_dir):
        """Test successful staking info display"""
        import datetime
        start_date = (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat()
        
        wallet_data = {
            "address": "test_address",
            "staking": [{
                "stake_id": "stake_123",
                "amount": 50.0,
                "apy": 5.0,
                "duration_days": 30,
                "start_date": start_date,
                "status": "active"
            }, {
                "stake_id": "stake_456",
                "amount": 25.0,
                "apy": 5.0,
                "duration_days": 30,
                "start_date": start_date,
                "rewards": 1.5,
                "status": "completed"
            }]
        }
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'staking-info'
        ])
        
        assert result.exit_code == 0
        assert "active" in result.output.lower()
        assert "completed" in result.output.lower()
        
    def test_staking_info_empty(self, runner, mock_wallet_dir):
        """Test staking info with no stakes"""
        wallet_data = {"address": "test_address", "staking": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'staking-info'
        ])
        
        assert result.exit_code == 0
        assert "0" in result.output  # Should show zero active stakes

    def test_stats_success(self, runner, mock_wallet_dir):
        """Test successful wallet stats display"""
        wallet_data = {
            "address": "test_address",
            "balance": 150.0,
            "created_at": "2023-01-01T00:00:00Z",
            "transactions": [
                {"type": "earn", "amount": 100.0, "timestamp": "2023-01-01T10:00:00"},
                {"type": "earn", "amount": 75.0, "timestamp": "2023-01-02T15:30:00"},
                {"type": "spend", "amount": -25.0, "timestamp": "2023-01-03T09:15:00"}
            ]
        }
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'stats'
        ])
        
        assert result.exit_code == 0
        assert "175.0" in result.output  # Total earned
        assert "25.0" in result.output   # Total spent
        assert "2" in result.output      # Jobs completed
        
    def test_stats_empty(self, runner, mock_wallet_dir):
        """Test wallet stats with no transactions"""
        wallet_data = {
            "address": "test_address",
            "balance": 0.0,
            "created_at": "2023-01-01T00:00:00Z",
            "transactions": []
        }
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'stats'
        ])
        
        assert result.exit_code == 0
        assert "0" in result.output  # Should show zero for all metrics

    def test_unstake_success(self, runner, mock_wallet_dir):
        """Test successful unstaking"""
        import datetime
        start_date = (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat()
        
        wallet_data = {
            "address": "test_address",
            "balance": 50.0,
            "transactions": [],
            "staking": [{
                "stake_id": "stake_123",
                "amount": 50.0,
                "apy": 5.0,
                "start_date": start_date,
                "status": "active"
            }]
        }
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        with patch('aitbc_cli.commands.wallet._save_wallet') as mock_save:
            result = runner.invoke(wallet, [
                '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
                'unstake', 'stake_123'
            ])
            
            assert result.exit_code == 0
            assert "unstaked" in result.output.lower()
            assert "rewards" in result.output.lower()
            mock_save.assert_called_once()
            
    def test_unstake_not_found(self, runner, mock_wallet_dir):
        """Test unstake for non-existent stake"""
        wallet_data = {"address": "test_address", "staking": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'unstake', 'non_existent'
        ])
        
        assert "not found" in result.output.lower()

