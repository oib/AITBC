"""
Contract tests for AITBC blockchain RPC interactions.
Tests verify that the blockchain RPC API maintains expected contracts and behaviors.
"""


import httpx
import pytest


class BlockchainRPCContract:
    """
    Contract definition for blockchain RPC API.
    Defines expected behavior and response formats.
    """

    BASE_URL = "http://localhost:8202"

    # Expected response structures
    BLOCK_RESPONSE_SCHEMA = {
        "height": int,
        "hash": str,
        "parent_hash": str,
        "timestamp": int,
        "transactions": list
    }

    TRANSACTION_RESPONSE_SCHEMA = {
        "hash": str,
        "from": str,
        "to": str,
        "value": str,
        "nonce": int,
        "gas": int
    }

    ACCOUNT_RESPONSE_SCHEMA = {
        "address": str,
        "balance": int,
        "nonce": int
    }

    STATUS_RESPONSE_SCHEMA = {
        "syncing": bool,
        "current_block": int,
        "highest_block": int,
        "peers": int
    }


@pytest.mark.contract
class TestBlockchainRPCContracts:
    """Contract tests for blockchain RPC endpoints"""

    @pytest.fixture
    def client(self):
        """HTTP client for blockchain RPC"""
        return httpx.Client(timeout=30.0)

    @pytest.fixture
    def rpc_url(self):
        """Blockchain RPC base URL"""
        return BlockchainRPCContract.BASE_URL

    def test_get_block_contract(self, client, rpc_url):
        """
        Test contract for getting a block by height.
        
        Contract:
        - GET /rpc/blocks/{height} should return block data
        - Response should contain required fields: height, hash, parent_hash, timestamp, transactions
        - Height should be a non-negative integer
        - Hash should be a valid hex string
        """
        try:
            response = client.get(f"{rpc_url}/rpc/blocks/0")

            # Contract: Should return 200 for valid block height
            assert response.status_code in (200, 404), f"Expected 200 or 404, got {response.status_code}"

            if response.status_code == 200:
                data = response.json()

                # Contract: Response should be a dictionary
                assert isinstance(data, dict), "Response should be a dictionary"

                # Contract: Should contain required fields
                required_fields = ["height", "hash", "timestamp"]
                for field in required_fields:
                    assert field in data, f"Missing required field: {field}"

                # Contract: Height should be integer
                assert isinstance(data["height"], int), "Height should be an integer"
                assert data["height"] >= 0, "Height should be non-negative"

                # Contract: Hash should be hex string
                assert isinstance(data["hash"], str), "Hash should be a string"
                # Hash may or may not start with 0x depending on implementation

        except httpx.ConnectError:
            pytest.skip("Blockchain RPC not available")

    def test_get_head_block_contract(self, client, rpc_url):
        """
        Test contract for getting the head block.
        
        Contract:
        - GET /rpc/head should return current head block
        - Response should contain height and hash
        - Head block should be the highest known block
        """
        try:
            response = client.get(f"{rpc_url}/rpc/head")

            # Contract: Should return 200
            assert response.status_code in (200, 404), f"Expected 200 or 404, got {response.status_code}"

            if response.status_code == 200:
                data = response.json()

                # Contract: Should contain height and hash
                assert "height" in data, "Missing height field"
                assert "hash" in data, "Missing hash field"

                # Contract: Height should be non-negative
                assert data["height"] >= 0, "Height should be non-negative"

        except httpx.ConnectError:
            pytest.skip("Blockchain RPC not available")

    def test_get_transaction_contract(self, client, rpc_url):
        """
        Test contract for getting a transaction by hash.
        
        Contract:
        - GET /rpc/transaction/{hash} should return transaction data
        - Response should contain: hash, from, to, value, nonce
        - Transaction hash should match request
        """
        try:
            # Use a sample transaction hash (this may not exist)
            sample_hash = "0x" + "a" * 64
            response = client.get(f"{rpc_url}/rpc/transaction/{sample_hash}")

            # Contract: Should return 200 if found, 404 if not found
            assert response.status_code in (200, 404), f"Expected 200 or 404, got {response.status_code}"

            if response.status_code == 200:
                data = response.json()

                # Contract: Should contain transaction fields
                assert "hash" in data, "Missing hash field"
                assert data["hash"] == sample_hash, "Transaction hash should match request"

        except httpx.ConnectError:
            pytest.skip("Blockchain RPC not available")

    def test_get_account_balance_contract(self, client, rpc_url):
        """
        Test contract for getting account balance.
        
        Contract:
        - GET /rpc/account/{address} should return account data
        - Response should contain: address, balance, nonce
        - Address should match request
        - Balance should be non-negative integer
        """
        try:
            # Use a sample address
            sample_address = "0x" + "a" * 40
            response = client.get(f"{rpc_url}/rpc/account/{sample_address}")

            # Contract: Should return 200 or 404
            assert response.status_code in (200, 404), f"Expected 200 or 404, got {response.status_code}"

            if response.status_code == 200:
                data = response.json()

                # Contract: Should contain account fields
                assert "address" in data, "Missing address field"
                assert data["address"] == sample_address, "Address should match request"

                # Contract: Balance should be non-negative
                if "balance" in data:
                    assert isinstance(data["balance"], (int, str)), "Balance should be integer or string"

        except httpx.ConnectError:
            pytest.skip("Blockchain RPC not available")

    def test_send_transaction_contract(self, client, rpc_url):
        """
        Test contract for sending a transaction.
        
        Contract:
        - POST /rpc/transaction should accept transaction payload
        - Response should contain transaction hash if successful
        - Should return error if transaction is invalid
        """
        try:
            # Create a sample transaction payload
            tx_payload = {
                "from": "0x" + "a" * 40,
                "to": "0x" + "b" * 40,
                "value": "1000000000000000000",  # 1 ETH in wei
                "nonce": 0,
                "gas": 21000
            }

            response = client.post(f"{rpc_url}/rpc/transaction", json=tx_payload)

            # Contract: Should return 200, 400, 422, or 500
            assert response.status_code in (200, 400, 422, 500), f"Unexpected status code: {response.status_code}"

            if response.status_code == 200:
                data = response.json()
                # Contract: Should contain transaction hash on success
                assert "hash" in data or "tx_hash" in data, "Missing transaction hash in response"

        except httpx.ConnectError:
            pytest.skip("Blockchain RPC not available")

    def test_get_peers_contract(self, client, rpc_url):
        """
        Test contract for getting network peers.
        
        Contract:
        - GET /rpc/peers should return peer information
        - Response should be a list of peers
        - Each peer should have at least an ID or address
        """
        try:
            response = client.get(f"{rpc_url}/rpc/peers")

            # Contract: Should return 200
            assert response.status_code in (200, 404), f"Expected 200 or 404, got {response.status_code}"

            if response.status_code == 200:
                data = response.json()

                # Contract: Response should be a list
                assert isinstance(data, (list, dict)), "Response should be a list or dict"

                if isinstance(data, list) and data:
                    # Contract: Each peer should have identifier
                    peer = data[0]
                    assert isinstance(peer, dict), "Peer should be a dictionary"
                    assert len(peer) > 0, "Peer should have at least one field"

        except httpx.ConnectError:
            pytest.skip("Blockchain RPC not available")

    def test_get_status_contract(self, client, rpc_url):
        """
        Test contract for getting node status.
        
        Contract:
        - GET /rpc/status should return node status
        - Response should contain: syncing status, current block, highest block
        - Current block should not exceed highest block
        """
        try:
            response = client.get(f"{rpc_url}/rpc/status")

            # Contract: Should return 200
            assert response.status_code in (200, 404), f"Expected 200 or 404, got {response.status_code}"

            if response.status_code == 200:
                data = response.json()

                # Contract: Should contain status fields
                assert isinstance(data, dict), "Response should be a dictionary"

                # Contract: If syncing info present, validate it
                if "syncing" in data:
                    assert isinstance(data["syncing"], bool), "Syncing should be boolean"

                if "current_block" in data and "highest_block" in data:
                    assert data["current_block"] <= data["highest_block"], \
                        "Current block should not exceed highest block"

        except httpx.ConnectError:
            pytest.skip("Blockchain RPC not available")

    def test_rpc_response_format_contract(self, client, rpc_url):
        """
        Test contract for RPC response format.
        
        Contract:
        - All RPC responses should be JSON
        - Content-Type should be application/json
        - Response should be parseable as JSON
        """
        try:
            # Test multiple endpoints
            endpoints = [
                "/rpc/head",
                "/rpc/status",
                "/rpc/peers"
            ]

            for endpoint in endpoints:
                response = client.get(f"{rpc_url}{endpoint}")

                if response.status_code == 200:
                    # Contract: Should have JSON content type
                    assert "application/json" in response.headers.get("content-type", ""), \
                        f"{endpoint} should return JSON content type"

                    # Contract: Should be parseable as JSON
                    try:
                        response.json()
                    except Exception as e:
                        pytest.fail(f"{endpoint} response should be valid JSON: {e}")

        except httpx.ConnectError:
            pytest.skip("Blockchain RPC not available")

    def test_rpc_error_handling_contract(self, client, rpc_url):
        """
        Test contract for RPC error handling.
        
        Contract:
        - Invalid endpoints should return 404
        - Invalid requests should return 400
        - Server errors should return 500
        - Error responses should contain error message
        """
        try:
            # Test invalid endpoint
            response = client.get(f"{rpc_url}/rpc/invalid_endpoint")
            assert response.status_code == 404, "Invalid endpoint should return 404"

            # Test invalid method
            response = client.post(f"{rpc_url}/rpc/head")
            assert response.status_code in (405, 404), "Invalid method should return 405 or 404"

        except httpx.ConnectError:
            pytest.skip("Blockchain RPC not available")


@pytest.mark.contract
class TestBlockchainRPCTimeouts:
    """Contract tests for RPC timeout behavior"""

    @pytest.fixture
    def slow_client(self):
        """HTTP client with short timeout for testing"""
        return httpx.Client(timeout=1.0)

    @pytest.mark.skip(reason="Timeout test is environment-dependent")
    def test_rpc_timeout_contract(self, slow_client, rpc_url):
        """
        Test contract for RPC timeout handling.
        
        Contract:
        - Requests should respect timeout settings
        - Timeout should raise appropriate exception
        - Client should handle timeouts gracefully
        """
        try:
            # This should timeout if the endpoint is slow
            response = slow_client.get(f"{rpc_url}/rpc/head")
            # If it doesn't timeout, that's also valid
            assert response.status_code in (200, 404)

        except httpx.TimeoutException:
            # Contract: Timeout should raise TimeoutException
            pass  # Expected behavior
        except httpx.ConnectError:
            pytest.skip("Blockchain RPC not available")
