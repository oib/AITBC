"""
Ethereum RPC client for AITBC bridge operations.
Supports public endpoints (Infura, Alchemy, Cloudflare) with automatic fallback.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)

# Public fallback RPC endpoints (no API key required)
# NOTE: Most public RPCs now require API keys. Set ETH_RPC_URL, INFURA_API_KEY,
# or ALCHEMY_API_KEY environment variables for reliable connectivity.
_PUBLIC_MAINNET_RPCS = [
    "https://ethereum.publicnode.com",
    "https://1rpc.io/eth",
]
_PUBLIC_SEPOLIA_RPCS = [
    "https://ethereum-sepolia.publicnode.com",
    "https://1rpc.io/sepolia",
]


@dataclass
class EthereumConfig:
    """Configuration for Ethereum RPC connection."""

    network: str = field(default_factory=lambda: os.getenv("ETH_NETWORK", "sepolia"))
    rpc_url: str | None = field(default_factory=lambda: os.getenv("ETH_RPC_URL"))
    infura_key: str | None = field(default_factory=lambda: os.getenv("INFURA_API_KEY"))
    alchemy_key: str | None = field(default_factory=lambda: os.getenv("ALCHEMY_API_KEY"))
    timeout: int = 10
    max_retries: int = 3

    def get_rpc_urls(self) -> list[str]:
        """Return ordered list of RPC URLs to try."""
        urls: list[str] = []

        if self.rpc_url:
            urls.append(self.rpc_url)

        if self.infura_key:
            urls.append(f"https://{self.network}.infura.io/v3/{self.infura_key}")

        if self.alchemy_key:
            net = "eth-mainnet" if self.network == "mainnet" else f"eth-{self.network}"
            urls.append(f"https://{net}.g.alchemy.com/v2/{self.alchemy_key}")

        if self.network == "mainnet":
            urls.extend(_PUBLIC_MAINNET_RPCS)
        else:
            urls.extend(_PUBLIC_SEPOLIA_RPCS)

        return urls


class EthereumRPCClient:
    """
    Lightweight Ethereum JSON-RPC client for AITBC bridge operations.
    Uses web3.py with automatic endpoint fallback.
    """

    def __init__(self, config: EthereumConfig | None = None):
        self.config = config or EthereumConfig()
        self._w3 = None
        self._connected_url: str | None = None

    def _get_web3(self):
        """Lazy-initialize Web3 connection, trying each RPC URL in order."""
        if self._w3 is not None:
            return self._w3

        try:
            from web3 import Web3
        except ImportError:
            raise RuntimeError("web3 package not installed: pip install web3")

        for url in self.config.get_rpc_urls():
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": self.config.timeout}))
                if w3.is_connected():
                    self._w3 = w3
                    self._connected_url = url
                    logger.info("Connected to Ethereum RPC", url=url, network=self.config.network)
                    return w3
            except Exception as e:
                logger.debug("RPC endpoint failed", url=url, error=str(e))
                continue

        raise ConnectionError(
            f"Could not connect to any Ethereum RPC endpoint for network '{self.config.network}'. "
            "Set ETH_RPC_URL, INFURA_API_KEY, or ALCHEMY_API_KEY environment variables."
        )

    @property
    def is_connected(self) -> bool:
        """Check if connected to Ethereum node."""
        try:
            return self._get_web3().is_connected()
        except Exception:
            return False

    @property
    def connected_url(self) -> str | None:
        return self._connected_url

    def get_block_number(self) -> int:
        """Get the latest Ethereum block number."""
        return self._get_web3().eth.block_number

    def get_balance(self, address: str) -> dict[str, Any]:
        """
        Get ETH balance for an address.
        Returns wei and ether values.
        """
        from web3 import Web3

        w3 = self._get_web3()
        checksum_addr = Web3.to_checksum_address(address)
        wei = w3.eth.get_balance(checksum_addr)
        return {
            "address": checksum_addr,
            "wei": wei,
            "ether": float(Web3.from_wei(wei, "ether")),
            "network": self.config.network,
        }

    def get_block(self, block_identifier: int | str = "latest") -> dict[str, Any]:
        """Get block data by number or 'latest'/'earliest'/'pending'."""
        w3 = self._get_web3()
        block = w3.eth.get_block(block_identifier)
        return {
            "number": block.number,
            "hash": block.hash.hex(),
            "timestamp": block.timestamp,
            "transaction_count": len(block.transactions),
            "gas_used": block.gasUsed,
            "gas_limit": block.gasLimit,
        }

    def get_transaction(self, tx_hash: str) -> dict[str, Any] | None:
        """Get transaction data by hash."""
        from web3 import Web3

        w3 = self._get_web3()
        try:
            tx = w3.eth.get_transaction(tx_hash)
            return {
                "hash": tx.hash.hex(),
                "from": tx["from"],
                "to": tx.to,
                "value_wei": tx.value,
                "value_ether": float(Web3.from_wei(tx.value, "ether")),
                "block_number": tx.blockNumber,
                "nonce": tx.nonce,
                "gas": tx.gas,
                "gas_price": tx.gasPrice,
            }
        except Exception:
            return None

    def get_transaction_receipt(self, tx_hash: str) -> dict[str, Any] | None:
        """Get transaction receipt (includes confirmation status)."""
        w3 = self._get_web3()
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt is None:
                return None
            return {
                "hash": tx_hash,
                "block_number": receipt.blockNumber,
                "status": receipt.status,  # 1 = success, 0 = failure
                "confirmed": receipt.status == 1,
                "gas_used": receipt.gasUsed,
                "contract_address": receipt.contractAddress,
                "logs": len(receipt.logs),
            }
        except Exception:
            return None

    def get_gas_price(self) -> dict[str, Any]:
        """Get current gas price in wei and gwei."""
        from web3 import Web3

        w3 = self._get_web3()
        wei = w3.eth.gas_price
        return {
            "wei": wei,
            "gwei": float(Web3.from_wei(wei, "gwei")),
        }

    def call_contract(
        self,
        contract_address: str,
        abi: list,
        function_name: str,
        args: list | None = None,
    ) -> Any:
        """Call a read-only contract function."""
        from web3 import Web3

        w3 = self._get_web3()
        checksum = Web3.to_checksum_address(contract_address)
        contract = w3.eth.contract(address=checksum, abi=abi)
        fn = contract.functions[function_name]
        return fn(*(args or [])).call()

    def wait_for_transaction(self, tx_hash: str, timeout: int = 120, poll_interval: int = 5) -> dict[str, Any] | None:
        """Poll for transaction confirmation up to timeout seconds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            receipt = self.get_transaction_receipt(tx_hash)
            if receipt is not None:
                return receipt
            time.sleep(poll_interval)
        return None

    def health_check(self) -> dict[str, Any]:
        """Return health status of the Ethereum RPC connection."""
        try:
            block = self.get_block_number()
            gas = self.get_gas_price()
            return {
                "status": "connected",
                "network": self.config.network,
                "rpc_url": self._connected_url,
                "latest_block": block,
                "gas_price_gwei": gas["gwei"],
            }
        except Exception as e:
            return {
                "status": "disconnected",
                "network": self.config.network,
                "error": str(e),
            }


# Global singleton — lazy-initialized
_client: EthereumRPCClient | None = None


def get_ethereum_client() -> EthereumRPCClient:
    """Get or create the global Ethereum RPC client singleton."""
    global _client
    if _client is None:
        _client = EthereumRPCClient()
    return _client
