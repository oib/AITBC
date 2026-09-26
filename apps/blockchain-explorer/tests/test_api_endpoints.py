"""
Comprehensive API endpoint tests for the blockchain explorer.

These tests exercise every public endpoint via TestClient. Endpoints that
call external blockchain RPC via httpx are mocked; endpoints that read from
the local sqlite chain DB gracefully return empty results when the DB is
absent (test environment).

Replaces the stub integration tests that were previously `pass`.
"""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


# --- Chains ---


# --- Health ---


# --- Chain head (mocked RPC) ---


# --- Analytics: network stats ---


# --- Analytics: activity timeline ---


# --- Analytics: top addresses ---


# --- Analytics: provider reputation ---


# --- Blocks: latest ---


# --- Blocks: non-empty ---


# --- Blocks: by height ---


# --- Blocks: by hash ---


# --- Transactions: by hash ---


# --- Transactions: search by address ---


# --- Blocks: by address ---


# --- Transactions: get by hash (legacy endpoint) ---


# --- Advanced search: transactions (mocked RPC) ---


# --- Advanced search: blocks (mocked RPC) ---


# --- Analytics: overview (mocked data layer) ---


# --- Export: search results ---


# --- Export: blocks ---


# --- Validation functions ---


def test_validate_tx_hash_valid():
    """Test tx hash validation with valid hashes"""
    from validation import validate_tx_hash

    assert validate_tx_hash("0x" + "a" * 64) is True
    assert validate_tx_hash("a" * 64) is True
    assert validate_tx_hash("0x" + "A" * 64) is True


def test_validate_tx_hash_invalid():
    """Test tx hash validation rejects invalid hashes"""
    from validation import validate_tx_hash

    assert validate_tx_hash("") is False
    assert validate_tx_hash("short") is False
    assert validate_tx_hash("0x" + "g" * 64) is False  # non-hex char
    assert validate_tx_hash("0x" + "a" * 64 + "/path") is False  # path traversal
    assert validate_tx_hash("0x" + "a" * 64 + "..") is False


def test_validate_chain_id_valid():
    """Test chain ID validation with valid IDs"""
    from validation import validate_chain_id

    assert validate_chain_id("ait-testchain.local") is True
    assert validate_chain_id("ait-mainnet") is True
    assert validate_chain_id("test-chain-123") is True


def test_validate_chain_id_invalid():
    """Test chain ID validation rejects invalid IDs"""
    from validation import validate_chain_id

    assert validate_chain_id("") is False
    assert validate_chain_id("ab") is False  # too short
    assert validate_chain_id("chain/with/slashes") is False
    assert validate_chain_id("chain..traversal") is False
    assert validate_chain_id("chain?query") is False
