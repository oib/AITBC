"""CLI EVM contract client for protected GPU rentals.

Wraps ``aitbc.ethereum_rpc.EthereumRPCClient`` with the helpers needed by
the ``aitbc market gpu`` commands: building, signing, and submitting
``AIPowerRental`` and ``EscrowService`` calls using a buyer's file-wallet
private key, then polling and validating the receipt.

The client is intentionally thin -- it does not manage gas pricing
strategies or nonces beyond the minimum needed for a protected rental --
so the command layer retains full control over what is signed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient


# Minimal ABI fragments for the calls the CLI needs. The full ABIs live in
# the contracts package; these are kept inline so the CLI does not depend on
# the Solidity toolchain at runtime.
_AIPOWER_RENTAL_ABI: list[dict[str, Any]] = [
    {
        "inputs": [
            {"name": "_agreementId", "type": "uint256"},
        ],
        "name": "startRental",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "_agreementId", "type": "uint256"}],
        "name": "getRentalAgreement",
        "outputs": [
            {
                "components": [
                    {"name": "agreementId", "type": "uint256"},
                    {"name": "provider", "type": "address"},
                    {"name": "consumer", "type": "address"},
                    {"name": "duration", "type": "uint256"},
                    {"name": "price", "type": "uint256"},
                    {"name": "startTime", "type": "uint256"},
                    {"name": "endTime", "type": "uint256"},
                    {"name": "platformFee", "type": "uint256"},
                    {"name": "status", "type": "uint8"},
                    {"name": "performance", "type": "tuple"},
                    {"name": "gpuModel", "type": "string"},
                    {"name": "computeUnits", "type": "uint256"},
                    {"name": "performanceProof", "type": "bytes32"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "_agreementId", "type": "uint256"}],
        "name": "completeRental",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

_ERC20_ABI: list[dict[str, Any]] = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass
class EVMTransactionResult:
    """Result of a submitted EVM transaction."""

    tx_hash: str
    status: int  # 1 = success, 0 = failure
    block_number: int
    gas_used: int
    from_address: str
    to_address: str


class EVMContractClient:
    """Thin EVM contract client for CLI protected-rental operations."""

    def __init__(
        self,
        rpc_url: str,
        chain_id: int,
        rental_contract_address: str,
        token_contract_address: str,
    ) -> None:
        self.rpc = EthereumRPCClient(EthereumConfig(rpc_url=rpc_url, network=str(chain_id)))
        self.chain_id = chain_id
        self.rental_contract = rental_contract_address
        self.token_contract = token_contract_address

    def get_rental_agreement(self, agreement_id: int) -> dict[str, Any]:
        """Read a rental agreement from the AIPowerRental contract."""
        result = self.rpc.call_contract(
            contract_address=self.rental_contract,
            abi=_AIPOWER_RENTAL_ABI,
            function_name="getRentalAgreement",
            args=[agreement_id],
        )
        return result

    def get_token_balance(self, address: str) -> int:
        """Read the ERC-20 balance of ``address``."""
        result = self.rpc.call_contract(
            contract_address=self.token_contract,
            abi=_ERC20_ABI,
            function_name="balanceOf",
            args=[address],
        )
        return int(result)

    def get_token_decimals(self) -> int:
        """Read the ERC-20 decimals."""
        result = self.rpc.call_contract(
            contract_address=self.token_contract,
            abi=_ERC20_ABI,
            function_name="decimals",
            args=[],
        )
        return int(result)

    def build_approve_tx(
        self,
        spender: str,
        amount: int,
        from_address: str,
        nonce: int,
        gas_limit: int = 100_000,
        gas_price: int | None = None,
    ) -> dict[str, Any]:
        """Build an ERC-20 approve transaction dict for external signing."""
        if gas_price is None:
            gas_price = int(self.rpc.get_gas_price()["wei"])
        data = self.rpc.encode_function_call(
            abi=_ERC20_ABI,
            function_name="approve",
            args=[spender, amount],
        )
        return {
            "to": self.token_contract,
            "from": from_address,
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": self.chain_id,
            "data": data,
            "value": 0,
        }

    def build_start_rental_tx(
        self,
        agreement_id: int,
        from_address: str,
        nonce: int,
        gas_limit: int = 300_000,
        gas_price: int | None = None,
    ) -> dict[str, Any]:
        """Build an AIPowerRental.startRental transaction dict for external signing."""
        if gas_price is None:
            gas_price = int(self.rpc.get_gas_price()["wei"])
        data = self.rpc.encode_function_call(
            abi=_AIPOWER_RENTAL_ABI,
            function_name="startRental",
            args=[agreement_id],
        )
        return {
            "to": self.rental_contract,
            "from": from_address,
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": self.chain_id,
            "data": data,
            "value": 0,
        }

    def build_complete_rental_tx(
        self,
        agreement_id: int,
        from_address: str,
        nonce: int,
        gas_limit: int = 200_000,
        gas_price: int | None = None,
    ) -> dict[str, Any]:
        """Build an AIPowerRental.completeRental transaction dict."""
        if gas_price is None:
            gas_price = int(self.rpc.get_gas_price()["wei"])
        data = self.rpc.encode_function_call(
            abi=_AIPOWER_RENTAL_ABI,
            function_name="completeRental",
            args=[agreement_id],
        )
        return {
            "to": self.rental_contract,
            "from": from_address,
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": self.chain_id,
            "data": data,
            "value": 0,
        }

    def sign_transaction(self, tx: dict[str, Any], private_key: str) -> str:
        """Sign an EVM transaction and return the raw hex string."""
        return self.rpc.sign_transaction(tx, private_key)

    def send_raw_transaction(self, raw_tx_hex: str) -> str:
        """Submit a raw signed transaction and return the tx hash."""
        return self.rpc.send_raw_transaction(raw_tx_hex)

    def wait_for_receipt(
        self,
        tx_hash: str,
        timeout_seconds: int = 120,
        poll_interval: float = 2.0,
    ) -> EVMTransactionResult:
        """Poll for a transaction receipt and return a structured result.

        Raises ``TimeoutError`` if the transaction is not mined within
        ``timeout_seconds``.
        """
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            receipt = self.rpc.get_transaction_receipt(tx_hash)
            if receipt is not None:
                return EVMTransactionResult(
                    tx_hash=tx_hash,
                    status=int(receipt.get("status", 0)),
                    block_number=int(receipt.get("blockNumber", 0)),
                    gas_used=int(receipt.get("gasUsed", 0)),
                    from_address=(receipt.get("from") or "").lower(),
                    to_address=(receipt.get("to") or "").lower(),
                )
            time.sleep(poll_interval)
        raise TimeoutError(f"Transaction {tx_hash} not mined within {timeout_seconds}s")

    def submit_and_wait(
        self,
        tx: dict[str, Any],
        private_key: str,
        timeout_seconds: int = 120,
    ) -> EVMTransactionResult:
        """Sign, submit, and wait for a transaction in one call."""
        raw = self.sign_transaction(tx, private_key)
        tx_hash = self.send_raw_transaction(raw)
        return self.wait_for_receipt(tx_hash, timeout_seconds=timeout_seconds)
