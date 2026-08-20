"""AITBC crypto helpers."""

from typing import Any


def derive_ethereum_address(private_key: str) -> str:
    """Derive an Ethereum address from a private key."""
    from eth_account import Account

    return Account.from_key(private_key).address


def generate_ethereum_private_key() -> str:
    """Generate a fresh Ethereum private key."""
    from eth_account import Account

    return Account.create().key.hex()


class TransactionService:
    """Stub transaction service for CLI coin-request commands."""

    def __init__(self, rpc_url: str = "http://localhost:8202"):
        self.rpc_url = rpc_url

    def submit(self, tx: dict, wallet: dict | None = None) -> dict:
        """Submit a transaction and return a synthetic receipt."""
        return {"status": "submitted", "tx_hash": "0x" + "0" * 64}

    def sign_and_submit(self, tx: dict, private_key: str) -> dict:
        return self.submit(tx)


__all__ = ["derive_ethereum_address", "generate_ethereum_private_key", "TransactionService"]
