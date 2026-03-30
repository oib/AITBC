from locust import HttpUser, task, between
import json

class AITBCUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        # Setup test - check if blockchain RPC is available
        self.client.get("/health")
    
    @task(3)
    def check_blockchain_health(self):
        """Check blockchain health endpoint."""
        self.client.get("/health")
    
    @task(2)
    def get_blockchain_head(self):
        """Get current block head."""
        self.client.get("/rpc/head")
    
    @task(2)
    def get_mempool_status(self):
        """Get mempool status."""
        self.client.get("/rpc/mempool")
    
    @task(1)
    def get_blockchain_info(self):
        """Get blockchain information."""
        self.client.get("/docs")
    
    @task(1)
    def test_transaction_submission(self):
        """Test transaction submission (will likely fail but tests endpoint)."""
        try:
            self.client.post("/rpc/transaction", json={
                "from": "test-address",
                "to": "test-address-2", 
                "amount": 1,
                "fee": 10,
                "nonce": 0,
                "payload": "0x",
                "chain_id": "ait-mainnet"
            })
        except:
            # Expected to fail due to invalid signature, but tests endpoint availability
            pass
