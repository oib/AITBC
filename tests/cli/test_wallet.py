"""Tests for wallet CLI commands"""

import pytest
import json
import re
import tempfile
import os
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import Mock, patch
from aitbc_cli.commands.wallet import wallet


def extract_json_from_output(output):
    """Extract JSON from CLI output that may contain Rich panel markup"""
    clean = re.sub(r'\x1b\[[0-9;]*m', '', output)
    lines = clean.strip().split('\n')
    json_lines = []
    in_json = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('{'):
            in_json = True
            json_lines.append(stripped)
        elif in_json:
            json_lines.append(stripped)
            if stripped.startswith('}'):
                break
    return json.loads('\n'.join(json_lines))


@pytest.fixture
def runner():
    """Create CLI runner"""
    return CliRunner()


@pytest.fixture
def temp_wallet():
    """Create temporary wallet file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        wallet_data = {
            "address": "aitbc1test",
            "balance": 100.0,
            "transactions": [
                {
                    "type": "earn",
                    "amount": 50.0,
                    "description": "Test job",
                    "timestamp": "2024-01-01T00:00:00"
                }
            ],
            "created_at": "2024-01-01T00:00:00"
        }
        json.dump(wallet_data, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def mock_config():
    """Mock configuration"""
    config = Mock()
    config.coordinator_url = "http://test:8000"
    config.api_key = "test_key"
    return config


class TestWalletCommands:
    """Test wallet command group"""
    
    def test_balance_command(self, runner, temp_wallet, mock_config):
        """Test wallet balance command"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'balance'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['balance'] == 100.0
        assert data['address'] == 'aitbc1test'
    
    def test_balance_new_wallet(self, runner, mock_config, tmp_path):
        """Test balance with new wallet (auto-creation)"""
        wallet_path = tmp_path / "new_wallet.json"
        
        result = runner.invoke(wallet, [
            '--wallet-path', str(wallet_path),
            'balance'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert wallet_path.exists()
        
        data = json.loads(result.output)
        assert data['balance'] == 0.0
        assert 'address' in data
    
    def test_earn_command(self, runner, temp_wallet, mock_config):
        """Test earning command"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'earn',
            '25.5',
            'job_456',
            '--desc', 'Another test job'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = extract_json_from_output(result.output)
        assert data['new_balance'] == 125.5  # 100 + 25.5
        assert data['job_id'] == 'job_456'
        
        # Verify wallet file updated
        with open(temp_wallet) as f:
            wallet_data = json.load(f)
        assert wallet_data['balance'] == 125.5
        assert len(wallet_data['transactions']) == 2
    
    def test_spend_command_success(self, runner, temp_wallet, mock_config):
        """Test successful spend command"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'spend',
            '30.0',
            'GPU rental'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = extract_json_from_output(result.output)
        assert data['new_balance'] == 70.0  # 100 - 30
        assert data['description'] == 'GPU rental'
    
    def test_spend_insufficient_balance(self, runner, temp_wallet, mock_config):
        """Test spend with insufficient balance"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'spend',
            '200.0',
            'Too much'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code != 0
        assert 'Insufficient balance' in result.output
    
    def test_history_command(self, runner, temp_wallet, mock_config):
        """Test transaction history"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'history',
            '--limit', '5'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'transactions' in data
        assert len(data['transactions']) == 1
        assert data['transactions'][0]['amount'] == 50.0
    
    def test_address_command(self, runner, temp_wallet, mock_config):
        """Test address command"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'address'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['address'] == 'aitbc1test'
    
    def test_stats_command(self, runner, temp_wallet, mock_config):
        """Test wallet statistics"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'stats'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['current_balance'] == 100.0
        assert data['total_earned'] == 50.0
        assert data['total_spent'] == 0.0
        assert data['jobs_completed'] == 1
        assert data['transaction_count'] == 1
    
    @patch('aitbc_cli.commands.wallet.httpx.Client')
    def test_send_command_success(self, mock_client_class, runner, temp_wallet, mock_config):
        """Test successful send command"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"hash": "0xabc123"}
        mock_client.post.return_value = mock_response
        
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'send',
            'aitbc1recipient',
            '25.0',
            '--description', 'Payment'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = extract_json_from_output(result.output)
        assert data['new_balance'] == 75.0  # 100 - 25
        assert data['tx_hash'] == '0xabc123'
        
        # Verify API call
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert '/transactions' in call_args[0][0]
        assert call_args[1]['json']['amount'] == 25.0
        assert call_args[1]['json']['to'] == 'aitbc1recipient'
    
    def test_request_payment_command(self, runner, temp_wallet, mock_config):
        """Test payment request command"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'request-payment',
            'aitbc1payer',
            '50.0',
            '--description', 'Service payment'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'payment_request' in data
        assert data['payment_request']['from_address'] == 'aitbc1payer'
        assert data['payment_request']['to_address'] == 'aitbc1test'
        assert data['payment_request']['amount'] == 50.0
    
    @patch('aitbc_cli.commands.wallet.httpx.Client')
    def test_send_insufficient_balance(self, mock_client_class, runner, temp_wallet, mock_config):
        """Test send with insufficient balance"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'send',
            'aitbc1recipient',
            '200.0'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code != 0
        assert 'Insufficient balance' in result.output
    
    def test_wallet_file_creation(self, runner, mock_config, tmp_path):
        """Test wallet file is created in correct directory"""
        wallet_dir = tmp_path / "wallets"
        wallet_path = wallet_dir / "test_wallet.json"
        
        result = runner.invoke(wallet, [
            '--wallet-path', str(wallet_path),
            'balance'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        assert wallet_path.exists()
        assert wallet_path.parent.exists()
    
    def test_stake_command(self, runner, temp_wallet, mock_config):
        """Test staking tokens"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'stake',
            '50.0',
            '--duration', '30'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = extract_json_from_output(result.output)
        assert data['amount'] == 50.0
        assert data['duration_days'] == 30
        assert data['new_balance'] == 50.0  # 100 - 50
        assert 'stake_id' in data
        assert 'apy' in data
        
        # Verify wallet file updated
        with open(temp_wallet) as f:
            wallet_data = json.load(f)
        assert wallet_data['balance'] == 50.0
        assert len(wallet_data['staking']) == 1
        assert wallet_data['staking'][0]['status'] == 'active'
    
    def test_stake_insufficient_balance(self, runner, temp_wallet, mock_config):
        """Test staking with insufficient balance"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'stake',
            '200.0'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code != 0
        assert 'Insufficient balance' in result.output
    
    def test_unstake_command(self, runner, temp_wallet, mock_config):
        """Test unstaking tokens"""
        # First stake
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'stake',
            '50.0',
            '--duration', '30'
        ], obj={'config': mock_config, 'output_format': 'json'})
        assert result.exit_code == 0
        stake_data = extract_json_from_output(result.output)
        stake_id = stake_data['stake_id']
        
        # Then unstake
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'unstake',
            stake_id
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = extract_json_from_output(result.output)
        assert data['stake_id'] == stake_id
        assert data['principal'] == 50.0
        assert 'rewards' in data
        assert data['total_returned'] >= 50.0
        assert data['new_balance'] >= 100.0  # Got back principal + rewards
    
    def test_unstake_invalid_id(self, runner, temp_wallet, mock_config):
        """Test unstaking with invalid stake ID"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'unstake',
            'nonexistent_stake'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code != 0
        assert 'not found' in result.output
    
    def test_staking_info_command(self, runner, temp_wallet, mock_config):
        """Test staking info command"""
        # Stake first
        runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'stake', '30.0', '--duration', '60'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        # Check staking info
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'staking-info'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['total_staked'] == 30.0
        assert data['active_stakes'] == 1
        assert len(data['stakes']) == 1
    
    def test_liquidity_stake_command(self, runner, temp_wallet, mock_config):
        """Test liquidity pool staking"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'liquidity-stake', '40.0',
            '--pool', 'main',
            '--lock-days', '0'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = extract_json_from_output(result.output)
        assert data['amount'] == 40.0
        assert data['pool'] == 'main'
        assert data['tier'] == 'bronze'
        assert data['apy'] == 3.0
        assert data['new_balance'] == 60.0
        assert 'stake_id' in data
    
    def test_liquidity_stake_gold_tier(self, runner, temp_wallet, mock_config):
        """Test liquidity staking with gold tier (30+ day lock)"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'liquidity-stake', '30.0',
            '--lock-days', '30'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = extract_json_from_output(result.output)
        assert data['tier'] == 'gold'
        assert data['apy'] == 8.0
    
    def test_liquidity_stake_insufficient_balance(self, runner, temp_wallet, mock_config):
        """Test liquidity staking with insufficient balance"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'liquidity-stake', '500.0'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code != 0
        assert 'Insufficient balance' in result.output
    
    def test_liquidity_unstake_command(self, runner, temp_wallet, mock_config):
        """Test liquidity pool unstaking with rewards"""
        # Stake first (no lock)
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'liquidity-stake', '50.0',
            '--pool', 'main',
            '--lock-days', '0'
        ], obj={'config': mock_config, 'output_format': 'json'})
        assert result.exit_code == 0
        stake_id = extract_json_from_output(result.output)['stake_id']
        
        # Unstake
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'liquidity-unstake', stake_id
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = extract_json_from_output(result.output)
        assert data['stake_id'] == stake_id
        assert data['principal'] == 50.0
        assert 'rewards' in data
        assert data['total_returned'] >= 50.0
    
    def test_liquidity_unstake_invalid_id(self, runner, temp_wallet, mock_config):
        """Test liquidity unstaking with invalid ID"""
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'liquidity-unstake', 'nonexistent'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code != 0
        assert 'not found' in result.output
    
    def test_rewards_command(self, runner, temp_wallet, mock_config):
        """Test rewards summary command"""
        # Stake some tokens first
        runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'stake', '20.0', '--duration', '30'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'liquidity-stake', '20.0', '--pool', 'main'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        result = runner.invoke(wallet, [
            '--wallet-path', temp_wallet,
            'rewards'
        ], obj={'config': mock_config, 'output_format': 'json'})
        
        assert result.exit_code == 0
        data = extract_json_from_output(result.output)
        assert 'staking_active_amount' in data
        assert 'liquidity_active_amount' in data
        assert data['staking_active_amount'] == 20.0
        assert data['liquidity_active_amount'] == 20.0
        assert data['total_staked'] == 40.0
