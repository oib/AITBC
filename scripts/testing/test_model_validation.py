#!/usr/bin/env python3
"""
Test the BlockImportRequest model
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class TransactionData(BaseModel):
    tx_hash: str
    sender: str
    recipient: str
    payload: Dict[str, Any] = Field(default_factory=dict)

class BlockImportRequest(BaseModel):
    height: int = Field(gt=0)
    hash: str
    parent_hash: str
    proposer: str
    timestamp: str
    tx_count: int = Field(ge=0)
    state_root: Optional[str] = None
    transactions: List[TransactionData] = Field(default_factory=list)

# Test creating the request
test_data = {
    "height": 1,
    "hash": "0xtest",
    "parent_hash": "0x00",
    "proposer": "test",
    "timestamp": "2026-01-29T10:20:00",
    "tx_count": 1,
    "transactions": [{
        "tx_hash": "0xtx123",
        "sender": "0xsender",
        "recipient": "0xrecipient",
        "payload": {"test": "data"}
    }]
}

print("Test data:")
print(test_data)

try:
    request = BlockImportRequest(**test_data)
    print("\n✅ Request validated successfully!")
    print(f"Transactions count: {len(request.transactions)}")
    if request.transactions:
        tx = request.transactions[0]
        print(f"First transaction:")
        print(f"  tx_hash: {tx.tx_hash}")
        print(f"  sender: {tx.sender}")
        print(f"  recipient: {tx.recipient}")
except Exception as e:
    print(f"\n❌ Validation failed: {e}")
    import traceback
    traceback.print_exc()
