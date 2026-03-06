"""
Multi-Chain Wallet Daemon Tests

Tests for multi-chain functionality including chain management,
chain-specific wallet operations, and cross-chain migrations.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime

from app.chain.manager import ChainManager, ChainConfig, ChainStatus
from app.chain.multichain_ledger import MultiChainLedgerAdapter, ChainWalletMetadata
from app.chain.chain_aware_wallet_service import ChainAwareWalletService


class TestChainManager:
    """Test the chain manager functionality"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_path = self.temp_dir / "test_chains.json"
        self.chain_manager = ChainManager(self.config_path)
    
    def teardown_method(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_create_default_chain(self):
        """Test default chain creation"""
        assert len(self.chain_manager.chains) == 1
        assert "ait-devnet" in self.chain_manager.chains
        assert self.chain_manager.default_chain_id == "ait-devnet"
    
    def test_add_chain(self):
        """Test adding a new chain"""
        chain_config = ChainConfig(
            chain_id="test-chain",
            name="Test Chain",
            coordinator_url="http://localhost:8001",
            coordinator_api_key="test-key"
        )
        
        success = self.chain_manager.add_chain(chain_config)
        assert success is True
        assert "test-chain" in self.chain_manager.chains
        assert len(self.chain_manager.chains) == 2
    
    def test_add_duplicate_chain(self):
        """Test adding a duplicate chain"""
        chain_config = ChainConfig(
            chain_id="ait-devnet",  # Already exists
            name="Duplicate Chain",
            coordinator_url="http://localhost:8001",
            coordinator_api_key="test-key"
        )
        
        success = self.chain_manager.add_chain(chain_config)
        assert success is False
        assert len(self.chain_manager.chains) == 1
    
    def test_remove_chain(self):
        """Test removing a chain"""
        # First add a test chain
        chain_config = ChainConfig(
            chain_id="test-chain",
            name="Test Chain",
            coordinator_url="http://localhost:8001",
            coordinator_api_key="test-key"
        )
        self.chain_manager.add_chain(chain_config)
        
        # Remove it
        success = self.chain_manager.remove_chain("test-chain")
        assert success is True
        assert "test-chain" not in self.chain_manager.chains
        assert len(self.chain_manager.chains) == 1
    
    def test_remove_default_chain(self):
        """Test removing the default chain (should fail)"""
        success = self.chain_manager.remove_chain("ait-devnet")
        assert success is False
        assert "ait-devnet" in self.chain_manager.chains
    
    def test_set_default_chain(self):
        """Test setting default chain"""
        # Add a test chain first
        chain_config = ChainConfig(
            chain_id="test-chain",
            name="Test Chain",
            coordinator_url="http://localhost:8001",
            coordinator_api_key="test-key"
        )
        self.chain_manager.add_chain(chain_config)
        
        # Set as default
        success = self.chain_manager.set_default_chain("test-chain")
        assert success is True
        assert self.chain_manager.default_chain_id == "test-chain"
    
    def test_validate_chain_id(self):
        """Test chain ID validation"""
        # Valid active chain
        assert self.chain_manager.validate_chain_id("ait-devnet") is True
        
        # Invalid chain
        assert self.chain_manager.validate_chain_id("nonexistent") is False
        
        # Add inactive chain
        chain_config = ChainConfig(
            chain_id="inactive-chain",
            name="Inactive Chain",
            coordinator_url="http://localhost:8001",
            coordinator_api_key="test-key",
            status=ChainStatus.INACTIVE
        )
        self.chain_manager.add_chain(chain_config)
        
        # Inactive chain should be invalid
        assert self.chain_manager.validate_chain_id("inactive-chain") is False
    
    def test_get_chain_stats(self):
        """Test getting chain statistics"""
        stats = self.chain_manager.get_chain_stats()
        
        assert stats["total_chains"] == 1
        assert stats["active_chains"] == 1
        assert stats["default_chain"] == "ait-devnet"
        assert len(stats["chain_list"]) == 1


class TestMultiChainLedger:
    """Test the multi-chain ledger adapter"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.chain_manager = ChainManager(self.temp_dir / "chains.json")
        self.ledger = MultiChainLedgerAdapter(self.chain_manager, self.temp_dir)
    
    def teardown_method(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_create_wallet(self):
        """Test creating a wallet in a specific chain"""
        success = self.ledger.create_wallet(
            chain_id="ait-devnet",
            wallet_id="test-wallet",
            public_key="test-public-key",
            address="test-address"
        )
        
        assert success is True
        
        # Verify wallet exists
        wallet = self.ledger.get_wallet("ait-devnet", "test-wallet")
        assert wallet is not None
        assert wallet.wallet_id == "test-wallet"
        assert wallet.chain_id == "ait-devnet"
        assert wallet.public_key == "test-public-key"
    
    def test_create_wallet_invalid_chain(self):
        """Test creating wallet in invalid chain"""
        success = self.ledger.create_wallet(
            chain_id="invalid-chain",
            wallet_id="test-wallet",
            public_key="test-public-key"
        )
        
        assert success is False
    
    def test_list_wallets(self):
        """Test listing wallets"""
        # Create multiple wallets
        self.ledger.create_wallet("ait-devnet", "wallet1", "pub1")
        self.ledger.create_wallet("ait-devnet", "wallet2", "pub2")
        
        wallets = self.ledger.list_wallets("ait-devnet")
        assert len(wallets) == 2
        wallet_ids = [wallet.wallet_id for wallet in wallets]
        assert "wallet1" in wallet_ids
        assert "wallet2" in wallet_ids
    
    def test_record_event(self):
        """Test recording events"""
        success = self.ledger.record_event(
            chain_id="ait-devnet",
            wallet_id="test-wallet",
            event_type="test-event",
            data={"test": "data"}
        )
        
        assert success is True
        
        # Get events
        events = self.ledger.get_wallet_events("ait-devnet", "test-wallet")
        assert len(events) == 1
        assert events[0].event_type == "test-event"
        assert events[0].data["test"] == "data"
    
    def test_get_chain_stats(self):
        """Test getting chain statistics"""
        # Create a wallet first
        self.ledger.create_wallet("ait-devnet", "test-wallet", "test-pub")
        
        stats = self.ledger.get_chain_stats("ait-devnet")
        assert stats["chain_id"] == "ait-devnet"
        assert stats["wallet_count"] == 1
        assert "database_path" in stats


class TestChainAwareWalletService:
    """Test the chain-aware wallet service"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.chain_manager = ChainManager(self.temp_dir / "chains.json")
        self.ledger = MultiChainLedgerAdapter(self.chain_manager, self.temp_dir)
        
        # Mock keystore service
        with patch('app.chain.chain_aware_wallet_service.PersistentKeystoreService') as mock_keystore:
            self.mock_keystore = mock_keystore.return_value
            self.mock_keystore.create_wallet.return_value = Mock(
                public_key="test-pub-key",
                metadata={}
            )
            self.mock_keystore.sign_message.return_value = b"test-signature"
            self.mock_keystore.unlock_wallet.return_value = True
            self.mock_keystore.lock_wallet.return_value = True
            
            self.wallet_service = ChainAwareWalletService(self.chain_manager, self.ledger)
    
    def teardown_method(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_create_wallet(self):
        """Test creating a wallet in a specific chain"""
        wallet = self.wallet_service.create_wallet(
            chain_id="ait-devnet",
            wallet_id="test-wallet",
            password="test-password"
        )
        
        assert wallet is not None
        assert wallet.wallet_id == "test-wallet"
        assert wallet.chain_id == "ait-devnet"
        assert wallet.public_key == "test-pub-key"
    
    def test_create_wallet_invalid_chain(self):
        """Test creating wallet in invalid chain"""
        wallet = self.wallet_service.create_wallet(
            chain_id="invalid-chain",
            wallet_id="test-wallet",
            password="test-password"
        )
        
        assert wallet is None
    
    def test_sign_message(self):
        """Test signing a message"""
        # First create a wallet
        self.wallet_service.create_wallet("ait-devnet", "test-wallet", "test-password")
        
        signature = self.wallet_service.sign_message(
            chain_id="ait-devnet",
            wallet_id="test-wallet",
            password="test-password",
            message=b"test message"
        )
        
        assert signature == "test-signature"  # Mocked signature
    
    def test_unlock_wallet(self):
        """Test unlocking a wallet"""
        # First create a wallet
        self.wallet_service.create_wallet("ait-devnet", "test-wallet", "test-password")
        
        success = self.wallet_service.unlock_wallet(
            chain_id="ait-devnet",
            wallet_id="test-wallet",
            password="test-password"
        )
        
        assert success is True
    
    def test_list_wallets(self):
        """Test listing wallets"""
        # Create wallets in different chains
        self.wallet_service.create_wallet("ait-devnet", "wallet1", "password1")
        
        # Add another chain
        chain_config = ChainConfig(
            chain_id="test-chain",
            name="Test Chain",
            coordinator_url="http://localhost:8001",
            coordinator_api_key="test-key"
        )
        self.chain_manager.add_chain(chain_config)
        
        # Create wallet in new chain
        self.wallet_service.create_wallet("test-chain", "wallet2", "password2")
        
        # List all wallets
        all_wallets = self.wallet_service.list_wallets()
        assert len(all_wallets) == 2
        
        # List specific chain wallets
        devnet_wallets = self.wallet_service.list_wallets("ait-devnet")
        assert len(devnet_wallets) == 1
        assert devnet_wallets[0].wallet_id == "wallet1"
    
    def test_get_chain_wallet_stats(self):
        """Test getting chain wallet statistics"""
        # Create a wallet
        self.wallet_service.create_wallet("ait-devnet", "test-wallet", "test-password")
        
        stats = self.wallet_service.get_chain_wallet_stats("ait-devnet")
        assert stats["chain_id"] == "ait-devnet"
        assert "ledger_stats" in stats
        assert "keystore_stats" in stats


class TestMultiChainIntegration:
    """Integration tests for multi-chain functionality"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.chain_manager = ChainManager(self.temp_dir / "chains.json")
        self.ledger = MultiChainLedgerAdapter(self.chain_manager, self.temp_dir)
        
        # Add a second chain
        chain_config = ChainConfig(
            chain_id="test-chain",
            name="Test Chain",
            coordinator_url="http://localhost:8001",
            coordinator_api_key="test-key"
        )
        self.chain_manager.add_chain(chain_config)
    
    def teardown_method(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_cross_chain_wallet_isolation(self):
        """Test that wallets are properly isolated between chains"""
        # Create wallet with same ID in different chains
        self.ledger.create_wallet("ait-devnet", "same-wallet", "pub1", "addr1")
        self.ledger.create_wallet("test-chain", "same-wallet", "pub2", "addr2")
        
        # Verify they are different
        wallet1 = self.ledger.get_wallet("ait-devnet", "same-wallet")
        wallet2 = self.ledger.get_wallet("test-chain", "same-wallet")
        
        assert wallet1.chain_id == "ait-devnet"
        assert wallet2.chain_id == "test-chain"
        assert wallet1.public_key != wallet2.public_key
        assert wallet1.address != wallet2.address
    
    def test_chain_specific_events(self):
        """Test that events are chain-specific"""
        # Create wallets in different chains
        self.ledger.create_wallet("ait-devnet", "wallet1", "pub1")
        self.ledger.create_wallet("test-chain", "wallet2", "pub2")
        
        # Record events
        self.ledger.record_event("ait-devnet", "wallet1", "event1", {"chain": "devnet"})
        self.ledger.record_event("test-chain", "wallet2", "event2", {"chain": "test"})
        
        # Verify events are chain-specific
        events1 = self.ledger.get_wallet_events("ait-devnet", "wallet1")
        events2 = self.ledger.get_wallet_events("test-chain", "wallet2")
        
        assert len(events1) == 1
        assert len(events2) == 1
        assert events1[0].data["chain"] == "devnet"
        assert events2[0].data["chain"] == "test"
    
    def test_all_chain_stats(self):
        """Test getting statistics for all chains"""
        # Create wallets in different chains
        self.ledger.create_wallet("ait-devnet", "wallet1", "pub1")
        self.ledger.create_wallet("test-chain", "wallet2", "pub2")
        
        stats = self.ledger.get_all_chain_stats()
        assert stats["total_chains"] == 2
        assert stats["total_wallets"] == 2
        assert "ait-devnet" in stats["chain_stats"]
        assert "test-chain" in stats["chain_stats"]


if __name__ == "__main__":
    pytest.main([__file__])
