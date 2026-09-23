"""
Market Tests
Tests for global chain market system
"""

from datetime import datetime
from decimal import Decimal

import pytest


class TestChainType:
    """Test ChainType enum"""

    def test_chain_type_values(self):
        """Test ChainType enum values"""
        from aitbc_cli.core.market import ChainType

        assert ChainType.TOPIC.value == "topic"
        assert ChainType.PRIVATE.value == "private"
        assert ChainType.RESEARCH.value == "research"
        assert ChainType.ENTERPRISE.value == "enterprise"
        assert ChainType.GOVERNANCE.value == "governance"


class TestMarketStatus:
    """Test MarketStatus enum"""

    def test_market_status_values(self):
        """Test MarketStatus enum values"""
        from aitbc_cli.core.market import MarketStatus

        assert MarketStatus.ACTIVE.value == "active"
        assert MarketStatus.PENDING.value == "pending"
        assert MarketStatus.SOLD.value == "sold"
        assert MarketStatus.EXPIRED.value == "expired"
        assert MarketStatus.DELISTED.value == "delisted"


class TestTransactionStatus:
    """Test TransactionStatus enum"""

    def test_transaction_status_values(self):
        """Test TransactionStatus enum values"""
        from aitbc_cli.core.market import TransactionStatus

        assert TransactionStatus.PENDING.value == "pending"
        assert TransactionStatus.CONFIRMED.value == "confirmed"
        assert TransactionStatus.COMPLETED.value == "completed"
        assert TransactionStatus.FAILED.value == "failed"
        assert TransactionStatus.REFUNDED.value == "refunded"


class TestChainListing:
    """Test ChainListing dataclass"""

    def test_chain_listing_creation(self):
        """Test creating ChainListing"""
        from aitbc_cli.core.market import ChainListing, ChainType, MarketStatus

        listing = ChainListing(
            listing_id="list123",
            chain_id="chain123",
            chain_name="Test Chain",
            chain_type=ChainType.TOPIC,
            description="A test chain",
            seller_id="seller123",
            price=Decimal("100.50"),
            currency="AIT",
            status=MarketStatus.ACTIVE,
            created_at=datetime.now(),
            expires_at=datetime.now(),
            metadata={},
            chain_specifications={},
            performance_metrics={},
            reputation_requirements={},
            governance_rules={},
        )

        assert listing.listing_id == "list123"
        assert listing.chain_id == "chain123"
        assert listing.price == Decimal("100.50")


class TestMarketTransaction:
    """Test MarketTransaction dataclass"""

    def test_market_transaction_creation(self):
        """Test creating MarketTransaction"""
        from aitbc_cli.core.market import MarketTransaction, TransactionStatus

        transaction = MarketTransaction(
            transaction_id="tx123",
            listing_id="list123",
            buyer_id="buyer123",
            seller_id="seller123",
            chain_id="chain123",
            price=Decimal("100.50"),
            currency="AIT",
            status=TransactionStatus.PENDING,
            created_at=datetime.now(),
            completed_at=None,
            escrow_address="escrow123",
            smart_contract_address="contract123",
            transaction_hash=None,
            metadata={},
        )

        assert transaction.transaction_id == "tx123"
        assert transaction.status == TransactionStatus.PENDING
        assert transaction.completed_at is None


class TestChainEconomy:
    """Test ChainEconomy dataclass"""

    def test_chain_economy_creation(self):
        """Test creating ChainEconomy"""
        from aitbc_cli.core.market import ChainEconomy

        economy = ChainEconomy(
            chain_id="chain123",
            total_value_locked=Decimal("1000000"),
            daily_volume=Decimal("50000"),
            market_cap=Decimal("10000000"),
            price_history=[],
            transaction_count=1000,
            active_users=500,
            agent_count=200,
            governance_tokens=Decimal("100000"),
            staking_rewards=Decimal("5000"),
            last_updated=datetime.now(),
        )

        assert economy.chain_id == "chain123"
        assert economy.total_value_locked == Decimal("1000000")
        assert economy.active_users == 500


class TestMarketMetrics:
    """Test MarketMetrics dataclass"""

    def test_market_metrics_creation(self):
        """Test creating MarketMetrics"""
        from aitbc_cli.core.market import MarketMetrics

        metrics = MarketMetrics(
            total_listings=100,
            active_listings=50,
            total_transactions=75,
            total_volume=Decimal("1000000"),
            average_price=Decimal("100"),
            popular_chain_types={"topic": 30, "private": 20},
            top_sellers=[{"seller_id": "seller1", "sales": 10}],
            price_trends={"topic": [Decimal("90"), Decimal("100"), Decimal("110")]},
            market_sentiment=0.75,
            last_updated=datetime.now(),
        )

        assert metrics.total_listings == 100
        assert metrics.active_listings == 50
        assert metrics.total_transactions == 75


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
