# mypy: ignore-errors
#!/usr/bin/env python3
"""
Generate Ethereum wallet address for ETH-AIT bridge.
"""

import os
import sys

try:
    from eth_account import Account
except ImportError:
    print("Installing eth-account...")
    os.system(f"{sys.executable} -m pip install eth-account")
    from eth_account import Account


def generate_eth_address():
    """Generate a new Ethereum address and private key."""
    # Enable mnemonic features
    Account.enable_unaudited_hdwallet_features()
    
    # Create new account
    account = Account.create()
    
    address = account.address
    private_key = account.key.hex()
    
    print("\n=== Generated Ethereum Wallet Address ===")
    print(f"Address: {address}")
    print(f"Private Key: {private_key}")
    print("\nIMPORTANT:")
    print("- Store the private key securely")
    print("- Add the address to /etc/aitbc/exchange.env as ETH_WALLET_ADDRESS")
    print("- Fund this address with ETH to enable bridge operations")
    print("=" * 50)
    
    return address, private_key


if __name__ == "__main__":
    generate_eth_address()
