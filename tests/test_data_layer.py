"""
Data Layer Tests
Tests for AITBC data layer abstraction
"""

import pytest

from aitbc.data_layer import (
    DataLayer,
    MockDataGenerator,
    RealDataFetcher,
    get_data_layer,
)


class TestDataLayer:
    """Test DataLayer class"""

    def test_data_layer_class_exists(self):
        """Test DataLayer class exists"""
        assert DataLayer is not None

    def test_data_layer_can_be_instantiated(self):
        """Test DataLayer can be instantiated"""
        data_layer = DataLayer()
        assert data_layer is not None

    def test_data_layer_use_mock_data_false(self):
        """Test DataLayer with use_mock_data=False"""
        data_layer = DataLayer(use_mock_data=False)
        assert data_layer.use_mock_data is False

    def test_data_layer_use_mock_data_true(self):
        """Test DataLayer with use_mock_data=True"""
        data_layer = DataLayer(use_mock_data=True)
        assert data_layer.use_mock_data is True

    def test_data_layer_env_var(self):
        """Test DataLayer reads USE_MOCK_DATA env var"""
        import os
        os.environ["USE_MOCK_DATA"] = "true"
        data_layer = DataLayer()
        assert data_layer.use_mock_data is True
        del os.environ["USE_MOCK_DATA"]

    def test_data_layer_components(self):
        """Test DataLayer has required components"""
        data_layer = DataLayer()
        assert hasattr(data_layer, 'mock_generator')
        assert hasattr(data_layer, 'real_fetcher')
        assert isinstance(data_layer.mock_generator, MockDataGenerator)
        assert isinstance(data_layer.real_fetcher, RealDataFetcher)

    @pytest.mark.asyncio
    async def test_get_transactions_mock(self):
        """Test get_transactions with mock data"""
        data_layer = DataLayer(use_mock_data=True)
        transactions = await data_layer.get_transactions(limit=10)
        assert len(transactions) == 10
        assert all("id" in tx for tx in transactions)

    @pytest.mark.asyncio
    async def test_get_transactions_with_filters(self):
        """Test get_transactions with filters"""
        data_layer = DataLayer(use_mock_data=True)
        transactions = await data_layer.get_transactions(
            address="0x1234567890123456789012345678901234567890",
            amount_min=1.0,
            amount_max=100.0,
            tx_type="transfer",
            limit=5
        )
        assert len(transactions) == 5

    @pytest.mark.asyncio
    async def test_get_blocks_mock(self):
        """Test get_blocks with mock data"""
        data_layer = DataLayer(use_mock_data=True)
        blocks = await data_layer.get_blocks(limit=10)
        assert len(blocks) == 10
        assert all("height" in block for block in blocks)

    @pytest.mark.asyncio
    async def test_get_blocks_with_validator(self):
        """Test get_blocks with validator filter"""
        data_layer = DataLayer(use_mock_data=True)
        validator = "0x1234567890123456789012345678901234567890"
        blocks = await data_layer.get_blocks(validator=validator, limit=5)
        assert len(blocks) == 5
        assert all(block["validator"] == validator for block in blocks)

    @pytest.mark.asyncio
    async def test_get_analytics_overview(self):
        """Test get_analytics_overview with mock data"""
        data_layer = DataLayer(use_mock_data=True)
        analytics = await data_layer.get_analytics_overview(period="24h")
        assert "total_transactions" in analytics
        assert "transaction_volume" in analytics
        assert "volume_data" in analytics
        assert "activity_data" in analytics

    @pytest.mark.asyncio
    async def test_get_analytics_overview_1h(self):
        """Test get_analytics_overview with 1h period"""
        data_layer = DataLayer(use_mock_data=True)
        analytics = await data_layer.get_analytics_overview(period="1h")
        assert "volume_data" in analytics
        assert len(analytics["volume_data"]["labels"]) == 12

    @pytest.mark.asyncio
    async def test_get_analytics_overview_7d(self):
        """Test get_analytics_overview with 7d period"""
        data_layer = DataLayer(use_mock_data=True)
        analytics = await data_layer.get_analytics_overview(period="7d")
        assert "volume_data" in analytics
        assert len(analytics["volume_data"]["labels"]) == 7


@pytest.mark.skip(reason="Requires real blockchain RPC endpoint")
class TestDataLayerReal:
    """Test DataLayer with real data fetching"""

    @pytest.mark.asyncio
    async def test_get_transactions_real(self):
        """Test get_transactions with real data"""
        data_layer = DataLayer(use_mock_data=False)
        # This would require a running blockchain RPC endpoint
        # Skipping for now
        pass


class TestMockDataGenerator:
    """Test MockDataGenerator class"""

    def test_generate_transactions(self):
        """Test generate_transactions method"""
        generator = MockDataGenerator()
        transactions = generator.generate_transactions(limit=10)
        assert len(transactions) == 10
        assert all("id" in tx for tx in transactions)
        assert all("from_address" in tx for tx in transactions)
        assert all("to_address" in tx for tx in transactions)

    def test_generate_transactions_with_address(self):
        """Test generate_transactions with specific address"""
        generator = MockDataGenerator()
        address = "0x1234567890123456789012345678901234567890"
        transactions = generator.generate_transactions(address=address, limit=5)
        assert len(transactions) == 5
        assert all(tx["from_address"] == address for tx in transactions)

    def test_generate_transactions_with_type(self):
        """Test generate_transactions with tx_type"""
        generator = MockDataGenerator()
        transactions = generator.generate_transactions(tx_type="transfer", limit=5)
        assert len(transactions) == 5
        assert all(tx["type"] == "transfer" for tx in transactions)

    def test_generate_blocks(self):
        """Test generate_blocks method"""
        generator = MockDataGenerator()
        blocks = generator.generate_blocks(limit=10)
        assert len(blocks) == 10
        assert all("height" in block for block in blocks)
        assert all("hash" in block for block in blocks)

    def test_generate_blocks_with_validator(self):
        """Test generate_blocks with validator"""
        generator = MockDataGenerator()
        validator = "0x1234567890123456789012345678901234567890"
        blocks = generator.generate_blocks(validator=validator, limit=5)
        assert len(blocks) == 5
        assert all(block["validator"] == validator for block in blocks)

    def test_generate_blocks_with_min_tx(self):
        """Test generate_blocks with min_tx"""
        generator = MockDataGenerator()
        blocks = generator.generate_blocks(min_tx=10, limit=5)
        assert len(blocks) == 5
        assert all(block["tx_count"] == 10 for block in blocks)

    def test_generate_analytics_24h(self):
        """Test generate_analytics with 24h period"""
        generator = MockDataGenerator()
        analytics = generator.generate_analytics(period="24h")
        assert "total_transactions" in analytics
        assert "transaction_volume" in analytics
        assert "volume_data" in analytics
        assert len(analytics["volume_data"]["labels"]) == 12

    def test_generate_analytics_1h(self):
        """Test generate_analytics with 1h period"""
        generator = MockDataGenerator()
        analytics = generator.generate_analytics(period="1h")
        assert len(analytics["volume_data"]["labels"]) == 12

    def test_generate_analytics_7d(self):
        """Test generate_analytics with 7d period"""
        generator = MockDataGenerator()
        analytics = generator.generate_analytics(period="7d")
        assert len(analytics["volume_data"]["labels"]) == 7

    def test_generate_analytics_30d(self):
        """Test generate_analytics with 30d period"""
        generator = MockDataGenerator()
        analytics = generator.generate_analytics(period="30d")
        assert len(analytics["volume_data"]["labels"]) == 4


class TestRealDataFetcher:
    """Test RealDataFetcher class"""

    def test_initialization(self):
        """Test RealDataFetcher can be instantiated"""
        fetcher = RealDataFetcher()
        assert fetcher is not None

    @pytest.mark.skip(reason="Requires real blockchain RPC endpoint")
    @pytest.mark.asyncio
    async def test_fetch_transactions(self):
        """Test fetch_transactions method"""
        fetcher = RealDataFetcher()
        # Requires running RPC endpoint
        pass

    @pytest.mark.skip(reason="Requires real blockchain RPC endpoint")
    @pytest.mark.asyncio
    async def test_fetch_blocks(self):
        """Test fetch_blocks method"""
        fetcher = RealDataFetcher()
        # Requires running RPC endpoint
        pass

    @pytest.mark.skip(reason="Requires real blockchain RPC endpoint")
    @pytest.mark.asyncio
    async def test_fetch_analytics(self):
        """Test fetch_analytics method"""
        fetcher = RealDataFetcher()
        # Requires running RPC endpoint
        pass


class TestGetDataLayer:
    """Test get_data_layer function"""

    def test_get_data_layer_singleton(self):
        """Test get_data_layer returns singleton"""
        # Reset global instance
        import aitbc.data_layer as dl_module
        dl_module._data_layer = None

        data_layer1 = get_data_layer(use_mock_data=True)
        data_layer2 = get_data_layer()

        assert data_layer1 is data_layer2

    def test_get_data_layer_with_param(self):
        """Test get_data_layer with parameter"""
        import aitbc.data_layer as dl_module
        dl_module._data_layer = None

        data_layer = get_data_layer(use_mock_data=False)
        assert data_layer.use_mock_data is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
