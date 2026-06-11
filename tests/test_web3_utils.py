"""
Web3 Utils Tests
Tests for AITBC Web3 utilities
"""

import pytest

from aitbc.network.web3_utils import Web3Client


class TestWeb3Client:
    """Test Web3Client class"""

    @pytest.mark.skip(reason="Web3 not installed in test environment")
    def test_web3_client_class_exists(self):
        """Test Web3Client class exists"""
        assert Web3Client is not None

    @pytest.mark.skip(reason="Web3 not installed in test environment")
    def test_web3_client_can_be_instantiated(self):
        """Test Web3Client can be instantiated"""
        client = Web3Client(rpc_url="http://localhost:8545")
        assert client is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
