#!/usr/bin/env python3
"""
Test the Transaction model directly
"""

# Test creating a transaction model instance
tx_data = {
    "tx_hash": "0xtest123",
    "sender": "0xsender",
    "recipient": "0xrecipient",
    "payload": {"test": "data"}
}

print("Transaction data:")
print(tx_data)

# Simulate what the router does
print("\nExtracting fields:")
print(f"tx_hash: {tx_data.get('tx_hash')}")
print(f"sender: {tx_data.get('sender')}")
print(f"recipient: {tx_data.get('recipient')}")
