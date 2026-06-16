"""
Constants Tests
Tests for AITBC common constants
"""

from pathlib import Path

import pytest
from aitbc import (
    AGENT_COORDINATOR_PORT,
    BLOCKCHAIN_DATA_DIR,
    BLOCKCHAIN_P2P_PORT,
    BLOCKCHAIN_RPC_PORT,
    CONFIG_DIR,
    DATA_DIR,
    ENV_FILE,
    KEYSTORE_DIR,
    LOG_DIR,
    MARKETPLACE_DATA_DIR,
    MARKETPLACE_PORT,
    NODE_ENV_FILE,
    REPO_DIR,
)


class TestConstants:
    """Test AITBC constants"""

    def test_data_dir(self):
        """Test DATA_DIR constant"""
        assert DATA_DIR == Path("/var/lib/aitbc")

    def test_config_dir(self):
        """Test CONFIG_DIR constant"""
        assert CONFIG_DIR == Path("/etc/aitbc")

    def test_log_dir(self):
        """Test LOG_DIR constant"""
        assert LOG_DIR == Path("/var/log/aitbc")

    def test_repo_dir(self):
        """Test REPO_DIR constant"""
        assert REPO_DIR == Path("/opt/aitbc")

    def test_keystore_dir(self):
        """Test KEYSTORE_DIR constant"""
        assert KEYSTORE_DIR == DATA_DIR / "keystore"

    def test_blockchain_data_dir(self):
        """Test BLOCKCHAIN_DATA_DIR constant"""
        assert BLOCKCHAIN_DATA_DIR == DATA_DIR / "data" / "ait-mainnet"

    def test_marketplace_data_dir(self):
        """Test MARKETPLACE_DATA_DIR constant"""
        assert MARKETPLACE_DATA_DIR == DATA_DIR / "data" / "marketplace"

    def test_env_file(self):
        """Test ENV_FILE constant"""
        assert ENV_FILE == CONFIG_DIR / ".env"

    def test_node_env_file(self):
        """Test NODE_ENV_FILE constant"""
        assert NODE_ENV_FILE == CONFIG_DIR / "node.env"

    def test_blockchain_rpc_port(self):
        """Test BLOCKCHAIN_RPC_PORT constant"""
        assert BLOCKCHAIN_RPC_PORT == 8202

    def test_blockchain_p2p_port(self):
        """Test BLOCKCHAIN_P2P_PORT constant"""
        assert BLOCKCHAIN_P2P_PORT == 8200

    def test_agent_coordinator_port(self):
        """Test AGENT_COORDINATOR_PORT constant"""
        assert AGENT_COORDINATOR_PORT == 9001

    def test_marketplace_port(self):
        """Test MARKETPLACE_PORT constant"""
        assert MARKETPLACE_PORT == 8081


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
