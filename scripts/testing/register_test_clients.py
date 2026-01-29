#!/usr/bin/env python3
"""Register test clients for payment integration testing"""

import asyncio
import httpx
import json

# Configuration
COORDINATOR_URL = "http://127.0.0.1:8000/v1"
CLIENT_KEY = "test_client_key_123"
MINER_KEY = "REDACTED_MINER_KEY"

async def register_client():
    """Register a test client"""
    async with httpx.AsyncClient() as client:
        # Register client
        response = await client.post(
            f"{COORDINATOR_URL}/clients/register",
            headers={"X-API-Key": CLIENT_KEY},
            json={"name": "Test Client", "description": "Client for payment testing"}
        )
        print(f"Client registration: {response.status_code}")
        if response.status_code not in [200, 201]:
            print(f"Response: {response.text}")
        else:
            print("✓ Test client registered successfully")

async def register_miner():
    """Register a test miner"""
    async with httpx.AsyncClient() as client:
        # Register miner
        response = await client.post(
            f"{COORDINATOR_URL}/miners/register",
            headers={"X-API-Key": MINER_KEY},
            json={
                "name": "Test Miner",
                "description": "Miner for payment testing",
                "capacity": 100,
                "price_per_hour": 0.1,
                "hardware": {"gpu": "RTX 4090", "memory": "24GB"}
            }
        )
        print(f"Miner registration: {response.status_code}")
        if response.status_code not in [200, 201]:
            print(f"Response: {response.text}")
        else:
            print("✓ Test miner registered successfully")

async def main():
    print("=== Registering Test Clients ===")
    await register_client()
    await register_miner()
    print("\n✅ Test clients registered successfully!")

if __name__ == "__main__":
    asyncio.run(main())
