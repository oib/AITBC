import asyncio
from aitbc_chain.config import settings
from aitbc_chain.main import node_app
import httpx
import time
import os

# Create an alternate config just for this test process
os.environ["SUPPORTED_CHAINS"] = "ait-devnet,ait-testnet"
os.environ["DB_PATH"] = "./data/test_chain.db"
from aitbc_chain.config import settings as test_settings

# Make sure we use a clean DB for the test
if os.path.exists("./data/test_chain.db"):
    os.remove("./data/test_chain.db")
if os.path.exists("./data/test_chain.db-journal"):
    os.remove("./data/test_chain.db-journal")

async def run_test():
    print(f"Testing with chains: {test_settings.supported_chains}")
    
    # Start the app and the node
    import uvicorn
    from aitbc_chain.app import app
    from threading import Thread
    import requests

    def run_server():
        uvicorn.run(app, host="127.0.0.1", port=8181, log_level="error")

    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()
    
    time.sleep(2) # Give server time to start

    try:
        # Check health which should report supported chains
        resp = requests.get("http://127.0.0.1:8181/health")
        print("Health status:", resp.json())
        assert "ait-devnet" in resp.json()["supported_chains"]
        assert "ait-testnet" in resp.json()["supported_chains"]

        # The lifepan started the node with both chains.
        # Wait for a couple blocks to be proposed
        time.sleep(5)

        # Check block head for devnet
        resp = requests.get("http://127.0.0.1:8181/rpc/head?chain_id=ait-devnet")
        print("Devnet head:", resp.json())
        assert "hash" in resp.json()

        # Check block head for testnet
        resp = requests.get("http://127.0.0.1:8181/rpc/head?chain_id=ait-testnet")
        print("Testnet head:", resp.json())
        assert "hash" in resp.json()

        print("SUCCESS! Multi-chain support is working.")

    except Exception as e:
        print("Test failed:", e)

if __name__ == "__main__":
    import sys
    sys.path.append('src')
    asyncio.run(run_test())
