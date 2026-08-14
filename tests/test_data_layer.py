"""Tests for aitbc.data_layer"""

from aitbc.data_layer import DataLayer, MockDataGenerator


class TestDataLayer:
    def test_init_mock(self):
        dl = DataLayer(use_mock_data=True)
        assert dl.use_mock_data is True

    def test_init_real(self):
        dl = DataLayer(use_mock_data=False)
        assert dl.use_mock_data is False


class TestMockDataGenerator:
    def test_generate_transactions(self):
        gen = MockDataGenerator()
        txs = gen.generate_transactions(limit=3)
        assert len(txs) == 3
        assert all("from_address" in tx for tx in txs)

    def test_generate_transactions_with_type(self):
        gen = MockDataGenerator()
        txs = gen.generate_transactions(limit=2, tx_type="transfer")
        assert all(tx["type"] == "transfer" for tx in txs)

    def test_generate_blocks(self):
        gen = MockDataGenerator()
        blocks = gen.generate_blocks(limit=3)
        assert len(blocks) == 3
        assert all("height" in b for b in blocks)

    def test_generate_blocks_with_validator(self):
        gen = MockDataGenerator()
        blocks = gen.generate_blocks(limit=2, validator="0x123")
        assert all(b["validator"] == "0x123" for b in blocks)

    def test_generate_analytics_1h(self):
        gen = MockDataGenerator()
        data = gen.generate_analytics("1h")
        assert "volume_data" in data
        assert len(data["volume_data"]["labels"]) == 12

    def test_generate_analytics_24h(self):
        gen = MockDataGenerator()
        data = gen.generate_analytics("24h")
        assert "volume_data" in data
        assert len(data["volume_data"]["labels"]) == 12

    def test_generate_analytics_7d(self):
        gen = MockDataGenerator()
        data = gen.generate_analytics("7d")
        assert "volume_data" in data
        assert len(data["volume_data"]["labels"]) == 7

    def test_generate_analytics_30d(self):
        gen = MockDataGenerator()
        data = gen.generate_analytics("30d")
        assert "volume_data" in data
        assert len(data["volume_data"]["labels"]) == 4
