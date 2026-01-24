#!/usr/bin/env python3
"""Load genesis accounts into the blockchain database"""

import json
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aitbc_chain.database import session_scope
from aitbc_chain.models import Account

def load_genesis_accounts(genesis_path: str = "data/devnet/genesis.json"):
    """Load accounts from genesis file into database"""
    
    # Read genesis file
    genesis_file = Path(genesis_path)
    if not genesis_file.exists():
        print(f"Error: Genesis file not found at {genesis_path}")
        return False
    
    with open(genesis_file) as f:
        genesis = json.load(f)
    
    # Load accounts
    with session_scope() as session:
        for account_data in genesis.get("accounts", []):
            address = account_data["address"]
            balance = account_data["balance"]
            nonce = account_data.get("nonce", 0)
            
            # Check if account already exists
            existing = session.query(Account).filter_by(address=address).first()
            if existing:
                existing.balance = balance
                existing.nonce = nonce
                print(f"Updated account {address}: balance={balance}")
            else:
                account = Account(address=address, balance=balance, nonce=nonce)
                session.add(account)
                print(f"Created account {address}: balance={balance}")
        
        session.commit()
    
    print("\nGenesis accounts loaded successfully!")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        genesis_path = sys.argv[1]
    else:
        genesis_path = "data/devnet/genesis.json"
    
    success = load_genesis_accounts(genesis_path)
    sys.exit(0 if success else 1)
