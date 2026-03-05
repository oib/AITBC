"""Additional tests for remaining wallet CLI commands"""

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

class TestWalletRemainingCommands:
    
    def test_liquidity_unstake_success(self, runner, mock_wallet_dir):
        """Test successful liquidity unstake"""
        import datetime
        start_date = (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat()
        
        wallet_data = {
            "address": "test_address",
            "balance": 50.0,
            "transactions": [],
            "liquidity": [{
                "stake_id": "liq_test123",
                "pool": "main",
                "amount": 50.0,
                "apy": 8.0,
                "start_date": start_date,
                "status": "active"
            }]
        }
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        with patch('aitbc_cli.commands.wallet._save_wallet') as mock_save:
            result = runner.invoke(wallet, [
                '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
                'liquidity-unstake', 'liq_test123'
            ])
            
            assert result.exit_code == 0
            assert "withdrawn" in result.output.lower()
            mock_save.assert_called_once()
            
    def test_liquidity_unstake_not_found(self, runner, mock_wallet_dir):
        """Test liquidity unstake for non-existent stake"""
        wallet_data = {"address": "test_address", "balance": 50.0, "liquidity": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'liquidity-unstake', 'non_existent'
        ])
        
        assert "not found" in result.output.lower()

    def test_multisig_create_success(self, runner, tmp_path):
        """Test successful multisig wallet creation"""
        result = runner.invoke(wallet, [
            'multisig-create',
            '--name', 'test_multisig',
            '--threshold', '2',
            'aitbc1addr1',
            'aitbc1addr2', 
            'aitbc1addr3'
        ], obj={'wallet_dir': tmp_path})
        
        assert result.exit_code == 0
        assert "created" in result.output.lower()
        assert "2-of-3" in result.output
        
    def test_multisig_create_threshold_exceeds_signers(self, runner, tmp_path):
        """Test multisig create with threshold exceeding signers"""
        result = runner.invoke(wallet, [
            'multisig-create',
            '--name', 'test_multisig',
            '--threshold', '5',
            'aitbc1addr1',
            'aitbc1addr2'
        ], obj={'wallet_dir': tmp_path})
        
        assert "threshold" in result.output.lower()
        assert "exceed" in result.output.lower()
        
    def test_multisig_create_already_exists(self, runner, tmp_path):
        """Test multisig create when wallet already exists"""
        # Create existing multisig file
        multisig_file = tmp_path / "test_multisig_multisig.json"
        with open(multisig_file, "w") as f:
            json.dump({"wallet_id": "existing"}, f)
            
        result = runner.invoke(wallet, [
            'multisig-create',
            '--name', 'test_multisig',
            '--threshold', '2',
            'aitbc1addr1',
            'aitbc1addr2'
        ], obj={'wallet_dir': tmp_path})
        
        assert "already exists" in result.output.lower()

    def test_multisig_propose_success(self, runner, tmp_path):
        """Test successful multisig transaction proposal"""
        # Create multisig wallet
        multisig_data = {
            "wallet_id": "test_multisig",
            "type": "multisig",
            "address": "aitbc1multisig",
            "signers": ["aitbc1addr1", "aitbc1addr2"],
            "threshold": 2,
            "balance": 100.0,
            "transactions": [],
            "pending_transactions": []
        }
        multisig_file = tmp_path / "test_multisig_multisig.json"
        with open(multisig_file, "w") as f:
            json.dump(multisig_data, f)
            
        result = runner.invoke(wallet, [
            'multisig-propose',
            '--wallet', 'test_multisig',
            'aitbc1recipient', '25.0',
            '--description', 'Test payment'
        ], obj={'wallet_dir': tmp_path})
        
        assert result.exit_code == 0
        assert "proposed" in result.output.lower()
        
    def test_multisig_propose_insufficient_balance(self, runner, tmp_path):
        """Test multisig propose with insufficient balance"""
        multisig_data = {
            "wallet_id": "test_multisig",
            "balance": 10.0,
            "signers": ["aitbc1addr1"],
            "threshold": 1,
            "pending_transactions": []
        }
        multisig_file = tmp_path / "test_multisig_multisig.json"
        with open(multisig_file, "w") as f:
            json.dump(multisig_data, f)
            
        result = runner.invoke(wallet, [
            'multisig-propose',
            '--wallet', 'test_multisig',
            'aitbc1recipient', '25.0'
        ], obj={'wallet_dir': tmp_path})
        
        assert "insufficient balance" in result.output.lower()

    def test_multisig_challenge_success(self, runner, tmp_path):
        """Test successful multisig challenge creation"""
        multisig_data = {
            "wallet_id": "test_multisig",
            "pending_transactions": [{
                "tx_id": "mstx_12345678",
                "to": "aitbc1recipient",
                "amount": 25.0,
                "status": "pending",
                "proposed_at": "2023-01-01T10:00:00"
            }]
        }
        multisig_file = tmp_path / "test_multisig_multisig.json"
        with open(multisig_file, "w") as f:
            json.dump(multisig_data, f)
            
        with patch('aitbc_cli.commands.wallet.multisig_security') as mock_security:
            mock_security.create_signing_request.return_value = {
                "challenge": "challenge_123",
                "nonce": "nonce_456",
                "message": "Sign this message"
            }
            
            result = runner.invoke(wallet, [
                'multisig-challenge',
                '--wallet', 'test_multisig',
                'mstx_12345678'
            ], obj={'wallet_dir': tmp_path})
            
            assert result.exit_code == 0
            assert "challenge" in result.output.lower()
            
    def test_multisig_challenge_not_found(self, runner, tmp_path):
        """Test multisig challenge for non-existent transaction"""
        multisig_data = {"wallet_id": "test_multisig", "pending_transactions": []}
        multisig_file = tmp_path / "test_multisig_multisig.json"
        with open(multisig_file, "w") as f:
            json.dump(multisig_data, f)
            
        result = runner.invoke(wallet, [
            'multisig-challenge',
            '--wallet', 'test_multisig',
            'non_existent_tx'
        ], obj={'wallet_dir': tmp_path})
        
        assert "not found" in result.output.lower()

    def test_sign_challenge_success(self, runner):
        """Test successful challenge signing"""
        with patch('aitbc_cli.commands.wallet.sign_challenge') as mock_sign:
            mock_sign.return_value = "0xsignature123"
            
            result = runner.invoke(wallet, [
                'sign-challenge',
                'challenge_123',
                '0xprivatekey456'
            ])
            
            assert result.exit_code == 0
            assert "signature" in result.output.lower()
            
    def test_sign_challenge_failure(self, runner):
        """Test challenge signing failure"""
        with patch('aitbc_cli.commands.wallet.sign_challenge') as mock_sign:
            mock_sign.side_effect = Exception("Invalid key")
            
            result = runner.invoke(wallet, [
                'sign-challenge',
                'challenge_123',
                'invalid_key'
            ])
            
            assert "failed" in result.output.lower()

    def test_multisig_sign_success(self, runner, tmp_path):
        """Test successful multisig transaction signing"""
        multisig_data = {
            "wallet_id": "test_multisig",
            "signers": ["aitbc1signer1", "aitbc1signer2"],
            "threshold": 2,
            "pending_transactions": [{
                "tx_id": "mstx_12345678",
                "to": "aitbc1recipient",
                "amount": 25.0,
                "status": "pending",
                "signatures": []
            }]
        }
        multisig_file = tmp_path / "test_multisig_multisig.json"
        with open(multisig_file, "w") as f:
            json.dump(multisig_data, f)
            
        with patch('aitbc_cli.commands.wallet.multisig_security') as mock_security:
            mock_security.verify_and_add_signature.return_value = (True, "Valid signature")
            
            result = runner.invoke(wallet, [
                'multisig-sign',
                '--wallet', 'test_multisig',
                'mstx_12345678',
                '--signer', 'aitbc1signer1',
                '--signature', '0xsig123'
            ], obj={'wallet_dir': tmp_path})
            
            assert result.exit_code == 0
            assert "1/2" in result.output  # 1 of 2 signatures collected
            
    def test_multisig_sign_unauthorized(self, runner, tmp_path):
        """Test multisig sign by unauthorized signer"""
        multisig_data = {
            "wallet_id": "test_multisig",
            "signers": ["aitbc1signer1", "aitbc1signer2"],
            "threshold": 2,
            "pending_transactions": [{
                "tx_id": "mstx_12345678",
                "status": "pending"
            }]
        }
        multisig_file = tmp_path / "test_multisig_multisig.json"
        with open(multisig_file, "w") as f:
            json.dump(multisig_data, f)
            
        result = runner.invoke(wallet, [
            'multisig-sign',
            '--wallet', 'test_multisig',
            'mstx_12345678',
            '--signer', 'aitbc1unauthorized',
            '--signature', '0xsig123'
        ], obj={'wallet_dir': tmp_path})
        
        assert "not an authorized signer" in result.output.lower()

    def test_request_payment_success(self, runner, mock_wallet_dir):
        """Test successful payment request creation"""
        wallet_data = {"address": "aitbc1test123", "transactions": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'request-payment',
            'aitbc1payer456', '100.0',
            '--description', 'Services rendered'
        ])
        
        assert result.exit_code == 0
        assert "payment_request" in result.output.lower()
        assert "aitbc1payer456" in result.output
        
    def test_request_payment_wallet_not_found(self, runner, mock_wallet_dir):
        """Test payment request with non-existent wallet"""
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "non_existent.json"),
            'request-payment',
            'aitbc1payer456', '100.0'
        ])
        
        assert "not found" in result.output.lower()

    def test_rewards_success(self, runner, mock_wallet_dir):
        """Test successful rewards display"""
        import datetime
        start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
        
        wallet_data = {
            "address": "test_address",
            "balance": 150.0,
            "staking": [{
                "amount": 50.0,
                "apy": 5.0,
                "start_date": start_date,
                "status": "active"
            }, {
                "amount": 25.0,
                "rewards": 2.5,
                "status": "completed"
            }],
            "liquidity": [{
                "amount": 30.0,
                "apy": 8.0,
                "start_date": start_date,
                "status": "active"
            }, {
                "amount": 20.0,
                "rewards": 1.8,
                "status": "completed"
            }]
        }
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'rewards'
        ])
        
        assert result.exit_code == 0
        assert "staking" in result.output.lower()
        assert "liquidity" in result.output.lower()
        assert "earned" in result.output.lower()
        
    def test_rewards_empty(self, runner, mock_wallet_dir):
        """Test rewards display with no staking or liquidity"""
        wallet_data = {"address": "test_address", "staking": [], "liquidity": []}
        with open(mock_wallet_dir / "test_wallet.json", "w") as f:
            json.dump(wallet_data, f)
            
        result = runner.invoke(wallet, [
            '--wallet-path', str(mock_wallet_dir / "test_wallet.json"),
            'rewards'
        ])
        
        assert result.exit_code == 0
        assert "0" in result.output  # Should show zero rewards
