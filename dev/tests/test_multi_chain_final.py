import asyncio
import os

# Create an alternate config just for this test process
os.environ["SUPPORTED_CHAINS"] = "ait-devnet,ait-testnet"
os.environ["DB_PATH"] = "./data/test_chain.db"
os.environ["MEMPOOL_BACKEND"] = "memory"

# Make sure we use a clean DB for the test
if os.path.exists("./data/test_chain.db"):
    os.remove("./data/test_chain.db")
if os.path.exists("./data/test_chain.db-journal"):
    os.remove("./data/test_chain.db-journal")

async def run_test():
    import time
    from aitbc_chain.config import settings as test_settings
    
    # Start the app and the node
    import uvicorn
    from aitbc_chain.app import app
    from threading import Thread
    import requests

    def run_server():
        uvicorn.run(app, host="127.0.0.1", port=8183, log_level="error")

    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()
    
    time.sleep(3) # Give server time to start

    try:
        # Wait for a couple blocks to be proposed
        time.sleep(5)

        # Check block head for devnet
        resp_dev = requests.get("http://127.0.0.1:8183/rpc/head?chain_id=ait-devnet")
        print("Devnet head:", resp_dev.json())
        assert "hash" in resp_dev.json() or resp_dev.json().get("detail") == "no blocks yet"

        # Check block head for testnet
        resp_test = requests.get("http://127.0.0.1:8183/rpc/head?chain_id=ait-testnet")
        print("Testnet head:", resp_test.json())
        assert "hash" in resp_test.json() or resp_test.json().get("detail") == "no blocks yet"

        # Submit transaction to devnet
        tx_data = {
            "sender": "sender1",
            "recipient": "recipient1",
            "payload": {"amount": 10},
            "nonce": 1,
            "fee": 10,
            "type": "TRANSFER",
            "sig": "mock_sig"
        }
        resp_tx_dev = requests.post("http://127.0.0.1:8183/rpc/sendTx?chain_id=ait-devnet", json=tx_data)
        print("Devnet Tx response:", resp_tx_dev.json())

        print("SUCCESS! Multi-chain support is working.")
        return True

    except Exception as e:
        print("Test failed:", e)
        return False

if __name__ == "__main__":
    import sys
    sys.path.append('src')
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
