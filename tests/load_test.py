from locust import HttpUser, task, between
import json

class AITBCUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        # Setup test wallet
        response = self.client.post("/rpc/wallet/create", json={"name": "test-wallet"})
        self.wallet_data = response.json()
    
    @task(3)
    def check_balance(self):
        self.client.get(f"/rpc/getBalance/{self.wallet_data['address']}")
    
    @task(2)
    def get_network_status(self):
        self.client.get("/rpc/network")
    
    @task(1)
    def send_transaction(self):
        tx_data = {
            "from": self.wallet_data['address'],
            "to": "ait1testaddress123...",
            "amount": 1,
            "fee": 1
        }
        self.client.post("/rpc/sendTx", json=tx_data)
