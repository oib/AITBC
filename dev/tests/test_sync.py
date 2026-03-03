import asyncio
import httpx
import time

async def main():
    async with httpx.AsyncClient() as client:
        print("Submitting transaction to aitbc (testnet)...")
        tx_data = {
            "type": "transfer",
            "sender": "0xTEST_SENDER",
            "nonce": int(time.time()),
            "fee": 1,
            "payload": {"amount": 100, "recipient": "0xTEST_RECIPIENT"},
            "sig": "0xSIG"
        }
        resp = await client.post("http://10.1.223.93:8082/rpc/sendTx?chain_id=ait-testnet", json=tx_data)
        print("aitbc response:", resp.status_code, resp.text)
        
        print("Waiting 5 seconds for gossip propagation and block proposing...")
        await asyncio.sleep(5)
        
        print("Checking head on aitbc...")
        resp = await client.get("http://10.1.223.93:8082/rpc/head?chain_id=ait-testnet")
        print("aitbc head:", resp.status_code, resp.json())
        
        print("Checking head on aitbc1...")
        resp = await client.get("http://10.1.223.40:8082/rpc/head?chain_id=ait-testnet")
        print("aitbc1 head:", resp.status_code, resp.json())

if __name__ == "__main__":
    asyncio.run(main())
