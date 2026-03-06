"""
Test to verify the home directory fixture system works correctly
"""

import pytest
from pathlib import Path

from tests.e2e.fixtures import (
    FIXTURE_HOME_PATH, 
    CLIENT1_HOME_PATH, 
    MINER1_HOME_PATH,
    get_fixture_home_path,
    fixture_home_exists
)


def test_fixture_paths_exist():
    """Test that all fixture paths exist"""
    assert FIXTURE_HOME_PATH.exists(), f"Fixture home path {FIXTURE_HOME_PATH} does not exist"
    assert CLIENT1_HOME_PATH.exists(), f"Client1 home path {CLIENT1_HOME_PATH} does not exist"
    assert MINER1_HOME_PATH.exists(), f"Miner1 home path {MINER1_HOME_PATH} does not exist"


def test_fixture_helper_functions():
    """Test fixture helper functions work correctly"""
    # Test get_fixture_home_path
    client1_path = get_fixture_home_path("client1")
    miner1_path = get_fixture_home_path("miner1")
    
    assert client1_path == CLIENT1_HOME_PATH
    assert miner1_path == MINER1_HOME_PATH
    
    # Test fixture_home_exists
    assert fixture_home_exists("client1") is True
    assert fixture_home_exists("miner1") is True
    assert fixture_home_exists("nonexistent") is False


def test_fixture_structure():
    """Test that fixture directories have the expected structure"""
    # Check client1 structure
    client1_aitbc = CLIENT1_HOME_PATH / ".aitbc"
    assert client1_aitbc.exists(), "Client1 .aitbc directory should exist"
    
    client1_wallets = client1_aitbc / "wallets"
    client1_config = client1_aitbc / "config"
    client1_cache = client1_aitbc / "cache"
    
    assert client1_wallets.exists(), "Client1 wallets directory should exist"
    assert client1_config.exists(), "Client1 config directory should exist"
    assert client1_cache.exists(), "Client1 cache directory should exist"
    
    # Check miner1 structure
    miner1_aitbc = MINER1_HOME_PATH / ".aitbc"
    assert miner1_aitbc.exists(), "Miner1 .aitbc directory should exist"
    
    miner1_wallets = miner1_aitbc / "wallets"
    miner1_config = miner1_aitbc / "config"
    miner1_cache = miner1_aitbc / "cache"
    
    assert miner1_wallets.exists(), "Miner1 wallets directory should exist"
    assert miner1_config.exists(), "Miner1 config directory should exist"
    assert miner1_cache.exists(), "Miner1 cache directory should exist"


def test_fixture_config_files():
    """Test that fixture config files exist and are readable"""
    import yaml
    
    # Check client1 config
    client1_config_file = CLIENT1_HOME_PATH / ".aitbc" / "config.yaml"
    assert client1_config_file.exists(), "Client1 config.yaml should exist"
    
    with open(client1_config_file, 'r') as f:
        client1_config = yaml.safe_load(f)
    
    assert "agent" in client1_config, "Client1 config should have agent section"
    assert client1_config["agent"]["name"] == "client1", "Client1 config should have correct name"
    
    # Check miner1 config
    miner1_config_file = MINER1_HOME_PATH / ".aitbc" / "config.yaml"
    assert miner1_config_file.exists(), "Miner1 config.yaml should exist"
    
    with open(miner1_config_file, 'r') as f:
        miner1_config = yaml.safe_load(f)
    
    assert "agent" in miner1_config, "Miner1 config should have agent section"
    assert miner1_config["agent"]["name"] == "miner1", "Miner1 config should have correct name"


def test_fixture_wallet_files():
    """Test that fixture wallet files exist and have correct structure"""
    import json
    
    # Check client1 wallet
    client1_wallet_file = CLIENT1_HOME_PATH / ".aitbc" / "wallets" / "client1_wallet.json"
    assert client1_wallet_file.exists(), "Client1 wallet file should exist"
    
    with open(client1_wallet_file, 'r') as f:
        client1_wallet = json.load(f)
    
    assert "address" in client1_wallet, "Client1 wallet should have address"
    assert "balance" in client1_wallet, "Client1 wallet should have balance"
    assert "transactions" in client1_wallet, "Client1 wallet should have transactions list"
    assert client1_wallet["address"] == "aitbc1client1", "Client1 wallet should have correct address"
    
    # Check miner1 wallet
    miner1_wallet_file = MINER1_HOME_PATH / ".aitbc" / "wallets" / "miner1_wallet.json"
    assert miner1_wallet_file.exists(), "Miner1 wallet file should exist"
    
    with open(miner1_wallet_file, 'r') as f:
        miner1_wallet = json.load(f)
    
    assert "address" in miner1_wallet, "Miner1 wallet should have address"
    assert "balance" in miner1_wallet, "Miner1 wallet should have balance"
    assert "transactions" in miner1_wallet, "Miner1 wallet should have transactions list"
    assert miner1_wallet["address"] == "aitbc1miner1", "Miner1 wallet should have correct address"


def test_fixture_import():
    """Test that fixtures can be imported correctly"""
    from tests.e2e.fixtures import (
        HomeDirManager,
        create_test_wallet,
        setup_fixture_homes
    )
    
    # Test that classes are importable
    assert HomeDirManager is not None, "HomeDirManager should be importable"
    
    # Test that functions are importable
    assert callable(create_test_wallet), "create_test_wallet should be callable"
    assert callable(setup_fixture_homes), "setup_fixture_homes should be callable"
    
    # Test create_test_wallet function
    test_wallet = create_test_wallet("test_agent", "aitbc1test", 500)
    
    expected_keys = {"address", "balance", "transactions", "created_at", "agent_name"}
    assert set(test_wallet.keys()) == expected_keys, "Test wallet should have all expected keys"
    assert test_wallet["address"] == "aitbc1test", "Test wallet should have correct address"
    assert test_wallet["balance"] == 500, "Test wallet should have correct balance"
    assert test_wallet["agent_name"] == "test_agent", "Test wallet should have correct agent name"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
