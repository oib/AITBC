"""
Unit tests for AITBC Wallet Daemon
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from apps.wallet_daemon.src.app.main import app
from apps.wallet_daemon.src.app.models.wallet import Wallet, WalletStatus
from apps.wallet_daemon.src.app.models.transaction import Transaction, TransactionStatus
from apps.wallet_daemon.src.app.services.wallet_service import WalletService
from apps.wallet_daemon.src.app.services.transaction_service import TransactionService


@pytest.mark.unit
class TestWalletEndpoints:
    """Test wallet-related endpoints"""
    
    def test_create_wallet_success(self, wallet_client, sample_wallet_data, sample_user):
        """Test successful wallet creation"""
        response = wallet_client.post(
            "/v1/wallets",
            json=sample_wallet_data,
            headers={"X-User-ID": sample_user.id}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["address"] is not None
        assert data["status"] == "active"
        assert data["user_id"] == sample_user.id
    
    def test_get_wallet_balance(self, wallet_client, sample_wallet, sample_user):
        """Test getting wallet balance"""
        with patch('apps.wallet_daemon.src.app.services.wallet_service.WalletService.get_balance') as mock_balance:
            mock_balance.return_value = {
                "native": "1000.0",
                "tokens": {
                    "AITBC": "500.0",
                    "USDT": "100.0"
                }
            }
            
            response = wallet_client.get(
                f"/v1/wallets/{sample_wallet.id}/balance",
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "native" in data
        assert "tokens" in data
        assert data["native"] == "1000.0"
    
    def test_list_wallet_transactions(self, wallet_client, sample_wallet, sample_user):
        """Test listing wallet transactions"""
        with patch('apps.wallet_daemon.src.app.services.transaction_service.TransactionService.get_wallet_transactions') as mock_txs:
            mock_txs.return_value = [
                {
                    "id": "tx-123",
                    "type": "send",
                    "amount": "10.0",
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat()
                }
            ]
            
            response = wallet_client.get(
                f"/v1/wallets/{sample_wallet.id}/transactions",
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0


@pytest.mark.unit
class TestTransactionEndpoints:
    """Test transaction-related endpoints"""
    
    def test_send_transaction(self, wallet_client, sample_wallet, sample_user):
        """Test sending a transaction"""
        tx_data = {
            "to_address": "0x1234567890abcdef",
            "amount": "10.0",
            "token": "AITBC",
            "memo": "Test payment"
        }
        
        with patch('apps.wallet_daemon.src.app.services.transaction_service.TransactionService.send_transaction') as mock_send:
            mock_send.return_value = {
                "id": "tx-456",
                "hash": "0xabcdef1234567890",
                "status": "pending"
            }
            
            response = wallet_client.post(
                "/v1/transactions/send",
                json=tx_data,
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "tx-456"
        assert data["status"] == "pending"
    
    def test_sign_transaction(self, wallet_client, sample_wallet, sample_user):
        """Test transaction signing"""
        unsigned_tx = {
            "to": "0x1234567890abcdef",
            "amount": "10.0",
            "nonce": 1
        }
        
        with patch('apps.wallet_daemon.src.app.services.wallet_service.WalletService.sign_transaction') as mock_sign:
            mock_sign.return_value = {
                "signature": "0xsigned123456",
                "signed_transaction": unsigned_tx
            }
            
            response = wallet_client.post(
                f"/v1/wallets/{sample_wallet.id}/sign",
                json=unsigned_tx,
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "signature" in data
        assert data["signature"] == "0xsigned123456"
    
    def test_estimate_gas(self, wallet_client, sample_user):
        """Test gas estimation"""
        tx_data = {
            "to": "0x1234567890abcdef",
            "amount": "10.0",
            "data": "0x"
        }
        
        with patch('apps.wallet_daemon.src.app.services.transaction_service.TransactionService.estimate_gas') as mock_gas:
            mock_gas.return_value = {
                "gas_limit": "21000",
                "gas_price": "20",
                "total_cost": "0.00042"
            }
            
            response = wallet_client.post(
                "/v1/transactions/estimate-gas",
                json=tx_data,
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "gas_limit" in data
        assert "gas_price" in data


@pytest.mark.unit
class TestStakingEndpoints:
    """Test staking-related endpoints"""
    
    def test_stake_tokens(self, wallet_client, sample_wallet, sample_user):
        """Test token staking"""
        stake_data = {
            "amount": "100.0",
            "duration": 30,  # days
            "validator": "validator-123"
        }
        
        with patch('apps.wallet_daemon.src.app.services.staking_service.StakingService.stake') as mock_stake:
            mock_stake.return_value = {
                "stake_id": "stake-789",
                "amount": "100.0",
                "apy": "5.5",
                "unlock_date": (datetime.utcnow() + timedelta(days=30)).isoformat()
            }
            
            response = wallet_client.post(
                f"/v1/wallets/{sample_wallet.id}/stake",
                json=stake_data,
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 201
        data = response.json()
        assert data["stake_id"] == "stake-789"
        assert "apy" in data
    
    def test_unstake_tokens(self, wallet_client, sample_wallet, sample_user):
        """Test token unstaking"""
        with patch('apps.wallet_daemon.src.app.services.staking_service.StakingService.unstake') as mock_unstake:
            mock_unstake.return_value = {
                "unstake_id": "unstake-456",
                "amount": "100.0",
                "status": "pending",
                "release_date": (datetime.utcnow() + timedelta(days=7)).isoformat()
            }
            
            response = wallet_client.post(
                f"/v1/wallets/{sample_wallet.id}/unstake",
                json={"stake_id": "stake-789"},
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
    
    def test_get_staking_rewards(self, wallet_client, sample_wallet, sample_user):
        """Test getting staking rewards"""
        with patch('apps.wallet_daemon.src.app.services.staking_service.StakingService.get_rewards') as mock_rewards:
            mock_rewards.return_value = {
                "total_rewards": "5.5",
                "daily_average": "0.183",
                "claimable": "5.5"
            }
            
            response = wallet_client.get(
                f"/v1/wallets/{sample_wallet.id}/rewards",
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "total_rewards" in data
        assert data["claimable"] == "5.5"


@pytest.mark.unit
class TestDeFiEndpoints:
    """Test DeFi-related endpoints"""
    
    def test_swap_tokens(self, wallet_client, sample_wallet, sample_user):
        """Test token swapping"""
        swap_data = {
            "from_token": "AITBC",
            "to_token": "USDT",
            "amount": "100.0",
            "slippage": "0.5"
        }
        
        with patch('apps.wallet_daemon.src.app.services.defi_service.DeFiService.swap') as mock_swap:
            mock_swap.return_value = {
                "swap_id": "swap-123",
                "expected_output": "95.5",
                "price_impact": "0.1",
                "route": ["AITBC", "USDT"]
            }
            
            response = wallet_client.post(
                f"/v1/wallets/{sample_wallet.id}/swap",
                json=swap_data,
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "swap_id" in data
        assert "expected_output" in data
    
    def test_add_liquidity(self, wallet_client, sample_wallet, sample_user):
        """Test adding liquidity to pool"""
        liquidity_data = {
            "pool": "AITBC-USDT",
            "token_a": "AITBC",
            "token_b": "USDT",
            "amount_a": "100.0",
            "amount_b": "1000.0"
        }
        
        with patch('apps.wallet_daemon.src.app.services.defi_service.DeFiService.add_liquidity') as mock_add:
            mock_add.return_value = {
                "liquidity_id": "liq-456",
                "lp_tokens": "316.23",
                "share_percentage": "0.1"
            }
            
            response = wallet_client.post(
                f"/v1/wallets/{sample_wallet.id}/add-liquidity",
                json=liquidity_data,
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 201
        data = response.json()
        assert "lp_tokens" in data
    
    def test_get_liquidity_positions(self, wallet_client, sample_wallet, sample_user):
        """Test getting liquidity positions"""
        with patch('apps.wallet_daemon.src.app.services.defi_service.DeFiService.get_positions') as mock_positions:
            mock_positions.return_value = [
                {
                    "pool": "AITBC-USDT",
                    "lp_tokens": "316.23",
                    "value_usd": "2000.0",
                    "fees_earned": "10.5"
                }
            ]
            
            response = wallet_client.get(
                f"/v1/wallets/{sample_wallet.id}/positions",
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0


@pytest.mark.unit
class TestNFTEndpoints:
    """Test NFT-related endpoints"""
    
    def test_mint_nft(self, wallet_client, sample_wallet, sample_user):
        """Test NFT minting"""
        nft_data = {
            "collection": "aitbc-art",
            "metadata": {
                "name": "Test NFT",
                "description": "A test NFT",
                "image": "ipfs://QmHash",
                "attributes": [{"trait_type": "rarity", "value": "common"}]
            }
        }
        
        with patch('apps.wallet_daemon.src.app.services.nft_service.NFTService.mint') as mock_mint:
            mock_mint.return_value = {
                "token_id": "123",
                "contract_address": "0xNFTContract",
                "token_uri": "ipfs://QmMetadata",
                "owner": sample_wallet.address
            }
            
            response = wallet_client.post(
                f"/v1/wallets/{sample_wallet.id}/nft/mint",
                json=nft_data,
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 201
        data = response.json()
        assert data["token_id"] == "123"
    
    def test_transfer_nft(self, wallet_client, sample_wallet, sample_user):
        """Test NFT transfer"""
        transfer_data = {
            "token_id": "123",
            "to_address": "0xRecipient",
            "contract_address": "0xNFTContract"
        }
        
        with patch('apps.wallet_daemon.src.app.services.nft_service.NFTService.transfer') as mock_transfer:
            mock_transfer.return_value = {
                "transaction_id": "tx-nft-456",
                "status": "pending"
            }
            
            response = wallet_client.post(
                f"/v1/wallets/{sample_wallet.id}/nft/transfer",
                json=transfer_data,
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "transaction_id" in data
    
    def test_list_nfts(self, wallet_client, sample_wallet, sample_user):
        """Test listing owned NFTs"""
        with patch('apps.wallet_daemon.src.app.services.nft_service.NFTService.list_nfts') as mock_list:
            mock_list.return_value = [
                {
                    "token_id": "123",
                    "collection": "aitbc-art",
                    "name": "Test NFT",
                    "image": "ipfs://QmHash"
                }
            ]
            
            response = wallet_client.get(
                f"/v1/wallets/{sample_wallet.id}/nfts",
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0


@pytest.mark.unit
class TestSecurityFeatures:
    """Test wallet security features"""
    
    def test_enable_2fa(self, wallet_client, sample_wallet, sample_user):
        """Test enabling 2FA"""
        with patch('apps.wallet_daemon.src.app.services.security_service.SecurityService.enable_2fa') as mock_2fa:
            mock_2fa.return_value = {
                "secret": "JBSWY3DPEHPK3PXP",
                "qr_code": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
                "backup_codes": ["123456", "789012"]
            }
            
            response = wallet_client.post(
                f"/v1/wallets/{sample_wallet.id}/security/2fa/enable",
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert "qr_code" in data
    
    def test_verify_2fa(self, wallet_client, sample_wallet, sample_user):
        """Test 2FA verification"""
        verify_data = {
            "code": "123456"
        }
        
        with patch('apps.wallet_daemon.src.app.services.security_service.SecurityService.verify_2fa') as mock_verify:
            mock_verify.return_value = {"verified": True}
            
            response = wallet_client.post(
                f"/v1/wallets/{sample_wallet.id}/security/2fa/verify",
                json=verify_data,
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        assert response.json()["verified"] is True
    
    def test_whitelist_address(self, wallet_client, sample_wallet, sample_user):
        """Test address whitelisting"""
        whitelist_data = {
            "address": "0xTrustedAddress",
            "label": "Exchange wallet",
            "daily_limit": "10000.0"
        }
        
        response = wallet_client.post(
            f"/v1/wallets/{sample_wallet.id}/security/whitelist",
            json=whitelist_data,
            headers={"X-User-ID": sample_user.id}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["address"] == whitelist_data["address"]
        assert data["status"] == "active"


@pytest.mark.unit
class TestAnalyticsEndpoints:
    """Test analytics and reporting endpoints"""
    
    def test_get_portfolio_summary(self, wallet_client, sample_wallet, sample_user):
        """Test portfolio summary"""
        with patch('apps.wallet_daemon.src.app.services.analytics_service.AnalyticsService.get_portfolio') as mock_portfolio:
            mock_portfolio.return_value = {
                "total_value_usd": "5000.0",
                "assets": [
                    {"symbol": "AITBC", "value": "3000.0", "percentage": 60},
                    {"symbol": "USDT", "value": "2000.0", "percentage": 40}
                ],
                "24h_change": "+2.5%",
                "profit_loss": "+125.0"
            }
            
            response = wallet_client.get(
                f"/v1/wallets/{sample_wallet.id}/analytics/portfolio",
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "total_value_usd" in data
        assert "assets" in data
    
    def test_get_transaction_history(self, wallet_client, sample_wallet, sample_user):
        """Test transaction history analytics"""
        with patch('apps.wallet_daemon.src.app.services.analytics_service.AnalyticsService.get_transaction_history') as mock_history:
            mock_history.return_value = {
                "total_transactions": 150,
                "successful": 148,
                "failed": 2,
                "total_volume": "50000.0",
                "average_transaction": "333.33",
                "by_month": [
                    {"month": "2024-01", "count": 45, "volume": "15000.0"},
                    {"month": "2024-02", "count": 52, "volume": "17500.0"}
                ]
            }
            
            response = wallet_client.get(
                f"/v1/wallets/{sample_wallet.id}/analytics/transactions",
                headers={"X-User-ID": sample_user.id}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "total_transactions" in data
        assert "by_month" in data
