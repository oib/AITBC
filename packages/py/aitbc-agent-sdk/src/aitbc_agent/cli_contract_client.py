"""
CLI-based contract client for AITBC
Provides the same interface as ContractClient but uses CLI commands
"""

import asyncio
import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def set_logger(log):
    global logger
    logger = log


class CLIContractClient:
    """Contract client that uses AITBC CLI instead of Web3"""

    def __init__(self, config, private_key: str | None = None):
        self.config = config
        self.private_key = private_key
        self.contracts: dict[str, str] = {}  # Store addresses, not Web3 contracts
        self._load_contract_addresses()
        if logger:
            logger.info("CLIContractClient initialized")

    def _load_contract_addresses(self) -> None:
        """Load contract addresses from config"""
        # Store contract addresses by name
        if hasattr(self.config, "cross_chain_atomic_swap") and self.config.cross_chain_atomic_swap:
            self.contracts["cross_chain_atomic_swap"] = self.config.cross_chain_atomic_swap
        if hasattr(self.config, "payment_processor") and self.config.payment_processor:
            self.contracts["payment_processor"] = self.config.payment_processor
        if hasattr(self.config, "agent_market") and self.config.agent_market:
            self.contracts["agent_marketplace"] = self.config.agent_market
        if hasattr(self.config, "staking_contract") and self.config.staking_contract:
            self.contracts["staking_contract"] = self.config.staking_contract

    @staticmethod
    def _serialize_param(arg) -> str:
        if isinstance(arg, bytes):
            return f"0x{arg.hex()}"
        if isinstance(arg, (int, str)):
            return str(arg)
        return json.dumps(arg)

    @staticmethod
    def _build_cli_command(contract_address: str, method_name: str, params_json: str) -> list[str]:
        cmd = [
            "python3",
            "/opt/aitbc/cli/unified_cli.py",
            "contract",
            "call",
            "--address",
            contract_address,
            "--method",
            method_name,
            "--params",
            params_json,
        ]

        # Add password file if available
        password_file = "/var/lib/aitbc/keystore/.genesis_password"
        if os.path.exists(password_file):
            cmd.extend(["--password-file", password_file])
        return cmd

    async def send_transaction(self, contract_name: str, method_name: str, *args, **kwargs) -> str:
        """Send transaction via CLI"""
        contract_address = self.contracts.get(contract_name)
        if not contract_address:
            raise ValueError(f"Contract {contract_name} not found")

        params_json = "[" + ", ".join(self._serialize_param(arg) for arg in args) + "]"
        cmd = self._build_cli_command(contract_address, method_name, params_json)

        try:
            if logger:
                logger.info("Calling CLI: %s on %s", method_name, contract_name)

            result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                raise Exception(f"CLI call failed: {result.stderr}")

            if logger:
                logger.info("CLI call successful: %s", method_name)

            # Return pseudo tx hash
            return f"cli-{method_name}-{int(asyncio.get_event_loop().time())}"

        except Exception as e:
            if logger:
                logger.error("CLI transaction failed: %s", e)
            raise

    async def wait_for_transaction(self, tx_hash: str, timeout: int = 120) -> dict:
        """Wait for transaction (CLI version - returns immediately)"""
        if logger:
            logger.info("Transaction %s completed (CLI mode)", tx_hash)
        return {
            "status": "success",
            "block_number": 0,
            "gas_used": 0,
            "transaction_hash": tx_hash,
            "note": "CLI-based transaction",
        }
