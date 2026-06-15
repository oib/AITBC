"""Tests for aitbc.network.web3_utils (fallback paths without web3)"""

from unittest.mock import patch

import pytest

from aitbc.network.web3_utils import WEB3_AVAILABLE, Web3Client


class TestWeb3Client:
    def test_web3_not_available(self):
        with patch("aitbc.network.web3_utils.WEB3_AVAILABLE", False):
            with pytest.raises(ImportError):
                Web3Client("https://rpc.example.com")

    def test_web3_available_flag(self):
        assert WEB3_AVAILABLE is False
